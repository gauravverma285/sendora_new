from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.throttles import PlanRateThrottle

from . import chat as chat_log
from .api_utils import build_whatsapp_payload
from .models import ChatMessage, Conversation
from .serializers import LeadQuerySerializer, LeadSerializer, SendMessageSerializer, SendBulkMessageSerializer
from .tasks import send_whatsapp_api_message, send_whatsapp_api_bulk_messages


SINGLE_EXAMPLE = OpenApiExample(
    "Order confirmation",
    value={
        "to": "+919876543210",
        "template_name": "monthly_statement_document",
        "language": "en",
        "header": {"type": "document", "id": "1099418736383616", "filename": "Your bill"},
        "body_params": ["Amar", "August 2026", "4500rs", "15 September 2026"],
        "button_params": [
            {"index": 0, "sub_type": "url", "value": "aug-2026"},
            {"index": 1, "sub_type": "copy_code", "value": "PROMO123"},
        ],
    },
    request_only=True,
)

BULK_EXAMPLE = OpenApiExample(
    "Same message to several numbers",
    value={
        "to": ["+919876543210", "+917877383709"],
        "template_name": "hello_world",
        "language": "en_US",
        "body_params": [],
    },
    request_only=True,
)


class SendMessageView(APIView):
    """
    Send one WhatsApp template message to a single recipient, using the
    WhatsApp Business Account connected to your account (see Profile page).

    The message is queued and sent asynchronously; this returns immediately
    with a task id you can use to correlate logs on your side.
    """
    throttle_classes = [PlanRateThrottle]

    @extend_schema(
        request=SendMessageSerializer,
        examples=[SINGLE_EXAMPLE],
        responses={202: dict},
        summary="Send a single WhatsApp template message",
    )
    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payload = build_whatsapp_payload(
            to=data["to"],
            template_name=data["template_name"],
            language=data["language"],
            header=data.get("header"),
            body_params=data.get("body_params"),
            button_params=data.get("button_params"),
        )
        task = send_whatsapp_api_message.delay(payload, request.user.id)
        return Response(
            {"status": "queued", "task_id": task.id, "to": data["to"]},
            status=status.HTTP_202_ACCEPTED,
        )


class SendBulkMessageView(APIView):
    """
    Send the same WhatsApp template message to a plain list of recipient
    phone numbers — no per-recipient personalization, no contact list
    lookup, just the numbers you provide.
    """
    throttle_classes = [PlanRateThrottle]

    @extend_schema(
        request=SendBulkMessageSerializer,
        examples=[BULK_EXAMPLE],
        responses={202: dict},
        summary="Send a WhatsApp template message to multiple recipients",
    )
    def post(self, request):
        serializer = SendBulkMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payload = build_whatsapp_payload(
            to="",  # overwritten per recipient by the task
            template_name=data["template_name"],
            language=data["language"],
            header=data.get("header"),
            body_params=data.get("body_params"),
            button_params=data.get("button_params"),
        )
        task = send_whatsapp_api_bulk_messages.delay(payload, data["to"], request.user.id)
        return Response(
            {"status": "queued", "task_id": task.id, "recipient_count": len(data["to"])},
            status=status.HTTP_202_ACCEPTED,
        )


class NewLeadsView(APIView):
    """
    One-time WhatsApp lead feed. Two modes, picked by whether you pass
    `reengage_after_days`:

    WITHOUT it (testing mode): every inbound message is its own lead. Each
    message is delivered exactly once, ever — call again and you only get
    whatever arrived since your last call. A contact who messages 3 times
    produces 3 separate lead entries across however many polls it takes.

    WITH `reengage_after_days=N`: leads collapse to one per CONTACT instead
    of one per message. A contact who was already delivered is suppressed
    until both (a) at least N days have passed since that delivery, and
    (b) they've sent a fresh message since then — then their latest message
    is delivered as a new lead and the N-day gate re-arms. Silence alone
    never re-triggers it.

    Either way there's no replay: once a message/contact has been handed
    out, a lost response doesn't come back on its own. Look it up manually
    in the Messages inbox if that happens.
    """
    throttle_classes = [PlanRateThrottle]

    @extend_schema(
        parameters=[LeadQuerySerializer],
        responses={200: LeadSerializer(many=True)},
        summary="Fetch and consume new WhatsApp leads (one-time delivery)",
    )
    def get(self, request):
        query = LeadQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        reengage_after_days = query.validated_data.get("reengage_after_days")

        if reengage_after_days is None:
            data = self._deliver_per_message(request.user)
        else:
            data = self._deliver_per_contact(request.user, reengage_after_days)

        return Response(LeadSerializer(data, many=True).data)

    def _deliver_per_message(self, user):
        """Testing mode: every not-yet-delivered inbound message is its own lead."""
        with transaction.atomic():
            messages = list(
                ChatMessage.objects.select_for_update(skip_locked=True)
                .filter(user=user, direction="in", lead_delivered_at__isnull=True)
                .select_related("conversation")
                .order_by("timestamp", "id")
            )
            if not messages:
                return []

            contacts = chat_log.contacts_by_number(user, [m.conversation.contact_number for m in messages])
            data = [self._lead_dict(msg.conversation, msg, contacts) for msg in messages]

            ChatMessage.objects.filter(pk__in=[m.id for m in messages]).update(lead_delivered_at=timezone.now())

        return data

    def _deliver_per_contact(self, user, reengage_after_days):
        """Collapsed mode: one lead per contact, re-triggerable after N quiet days + a new message."""
        # Always eligible: never delivered before. ALSO eligible: delivered
        # more than N days ago, and messaged again since that delivery
        # (last_inbound_at is kept current on every inbound message, so
        # ">" delivery time means "a message arrived after it").
        cutoff = timezone.now() - timedelta(days=reengage_after_days)
        eligible = Q(lead_delivered_at__isnull=True) | Q(
            lead_delivered_at__lte=cutoff, last_inbound_at__gt=F("lead_delivered_at")
        )

        with transaction.atomic():
            # skip_locked=True: if two requests somehow land at once, each
            # gets a disjoint set of conversations instead of blocking on
            # (or double-delivering) the same rows.
            conversations = list(
                Conversation.objects.select_for_update(skip_locked=True)
                .filter(Q(user=user, last_inbound_at__isnull=False) & eligible)
                .order_by("created_at")
            )
            if not conversations:
                return []

            conv_ids = [c.id for c in conversations]
            latest_inbound = {}
            inbound_qs = (
                ChatMessage.objects.filter(conversation_id__in=conv_ids, direction="in")
                .order_by("conversation_id", "-timestamp", "-id")
            )
            for msg in inbound_qs:
                latest_inbound.setdefault(msg.conversation_id, msg)  # first hit per id, due to -timestamp ordering, is the latest

            contacts = chat_log.contacts_by_number(user, [c.contact_number for c in conversations])

            data = []
            for conv in conversations:
                msg = latest_inbound.get(conv.id)
                if msg:
                    data.append(self._lead_dict(conv, msg, contacts))

            Conversation.objects.filter(pk__in=conv_ids).update(lead_delivered_at=timezone.now())

        return data

    @staticmethod
    def _lead_dict(conversation, msg, contacts):
        return {
            "contact_number": f"+{conversation.contact_number}",
            "wa_id": conversation.contact_number,
            "name": chat_log.display_name(conversation, contacts.get(conversation.contact_number)),
            "message": msg.body,
            "message_type": msg.message_type,
            "timestamp": msg.timestamp,
            "wamid": msg.wamid or "",
        }
