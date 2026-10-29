"""Chat / Messages inbox: recording and reading WhatsApp messages.

Every function here takes the owning account (`user`) explicitly and only
ever touches that account's rows — the webhook works out which account a
message belongs to from the receiving phone_number_id, so two accounts that
talk to the same customer number never see each other's conversations.

The public record_* helpers never raise: a failure while logging a message
into the inbox must not break the webhook or a campaign send.
"""
import logging
import re
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import ChatMessage, Contact, Conversation

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=24)
# A person answered (from the inbox, or from the WhatsApp phone app), so the
# conversation no longer needs attention. Automated sends (campaign / flow /
# API) deliberately do NOT clear unread.
HUMAN_SOURCES = ("chat", "app")
_STATUS_RANK = {"received": 0, "sent": 1, "delivered": 2, "read": 3, "failed": 4}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def normalize_number(number):
    """Digits only — the form WhatsApp uses for wa_id / the `to` field."""
    return re.sub(r"\D", "", str(number or ""))


def _ts(value):
    """Unix-seconds string/int from a webhook -> aware UTC datetime."""
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return timezone.now()


def find_contact(user, number):
    """The saved Contact (if any) for this account matching a WhatsApp
    number. Saved numbers may or may not carry a leading "+"."""
    number = normalize_number(number)
    if not number:
        return None
    return Contact.objects.filter(user=user, mobile_number__in=[number, f"+{number}"]).first()


def contacts_by_number(user, numbers):
    """{digits-only number: Contact} for a batch of numbers, in one query."""
    wanted = set()
    for n in numbers:
        wanted.update([n, f"+{n}"])
    found = {}
    for c in Contact.objects.filter(user=user, mobile_number__in=wanted):
        found.setdefault(normalize_number(c.mobile_number), c)
    return found


def display_name(conversation, contact=None):
    if contact and contact.name:
        return contact.name
    if conversation.profile_name:
        return conversation.profile_name
    return f"+{conversation.contact_number}"


def window_state(conversation):
    """{'open': bool, 'expires_at': datetime|None} for WhatsApp's 24-hour
    customer-service window (free-form replies allowed only inside it)."""
    last = conversation.last_inbound_at
    if not last:
        return {"open": False, "expires_at": None}
    expires = last + WINDOW
    return {"open": expires > timezone.now(), "expires_at": expires}


# --------------------------------------------------------------------------
# Describing a message (for the list preview + bubble text)
# --------------------------------------------------------------------------

def describe_inbound(message):
    """Pull the display fields out of a webhook `messages[]` entry."""
    mtype = message.get("type") or "text"
    data = message.get(mtype) or {}
    body = media_id = mime = filename = ""

    if mtype == "text":
        body = data.get("body", "")
    elif mtype in ("image", "video", "audio", "document", "sticker"):
        media_id = data.get("id", "")
        mime = data.get("mime_type", "")
        filename = data.get("filename", "")
        body = data.get("caption", "")
    elif mtype == "location":
        body = " · ".join(p for p in (data.get("name"), data.get("address")) if p) or \
            f"{data.get('latitude', '')}, {data.get('longitude', '')}"
    elif mtype == "button":
        body = data.get("text", "")
    elif mtype == "interactive":
        sub = data.get("type")
        reply = data.get(sub) or {}
        body = reply.get("title", "")
    elif mtype == "reaction":
        body = data.get("emoji", "")
    elif mtype == "contacts":
        names = [(c.get("name") or {}).get("formatted_name", "") for c in message.get("contacts", [])]
        body = ", ".join(n for n in names if n)

    return {"type": mtype, "body": body, "media_id": media_id, "mime": mime, "filename": filename}


def describe_outbound(payload):
    """Same, from a Cloud API send payload we built."""
    mtype = payload.get("type") or "text"
    data = payload.get(mtype) or {}
    body = media_id = filename = ""

    if mtype == "text":
        body = data.get("body", "")
    elif mtype == "template":
        body = f"Template: {data.get('name', '')}"
    elif mtype in ("image", "video", "audio", "document"):
        media_id = data.get("id", "")
        filename = data.get("filename", "")
        body = data.get("caption", "")
    elif mtype == "interactive":
        body = (data.get("body") or {}).get("text", "").strip()
        header = data.get("header") or {}
        htype = header.get("type")
        if htype in ("image", "video", "document"):
            media_id = (header.get(htype) or {}).get("id", "")
            filename = (header.get(htype) or {}).get("filename", "")

    return {"type": mtype, "body": body, "media_id": media_id, "mime": "", "filename": filename}


_PREVIEW_LABEL = {
    "image": "📷 Photo", "video": "🎥 Video", "audio": "🎤 Audio", "sticker": "Sticker",
    "location": "📍 Location", "contacts": "👤 Contact", "reaction": "Reaction",
}


def make_preview(desc):
    mtype, body = desc["type"], desc["body"]
    if mtype == "document":
        return f"📄 {desc['filename'] or 'Document'}"[:250]
    if mtype in ("image", "video"):
        label = _PREVIEW_LABEL[mtype]
        return f"{label} {body}".strip()[:250]
    if mtype in _PREVIEW_LABEL and not body:
        return _PREVIEW_LABEL[mtype]
    return (body or "[unsupported message]")[:250]


# --------------------------------------------------------------------------
# Conversation bookkeeping
# --------------------------------------------------------------------------

def _get_conversation(user, number, profile_name=""):
    conv, created = Conversation.objects.get_or_create(user=user, contact_number=number)
    if profile_name and conv.profile_name != profile_name:
        conv.profile_name = profile_name
        conv.save(update_fields=["profile_name"])
    return conv


def _touch(conv, direction, preview, when, inbound):
    """Update the conversation summary — only forward in time, so an
    out-of-order webhook can't move the "last message" backwards."""
    if not conv.last_message_at or when >= conv.last_message_at:
        conv.last_message_at = when
        conv.last_message_preview = preview
        conv.last_direction = direction
    if inbound and (not conv.last_inbound_at or when > conv.last_inbound_at):
        conv.last_inbound_at = when
    conv.save(update_fields=["last_message_at", "last_message_preview", "last_direction", "last_inbound_at"])


# --------------------------------------------------------------------------
# Recording messages
# --------------------------------------------------------------------------

def record_inbound(user, message, profile_names=None):
    """Store one webhook `messages[]` entry for `user`. Idempotent on wamid."""
    try:
        number = normalize_number(message.get("from"))
        wamid = message.get("id")
        if not number:
            return None
        if wamid and ChatMessage.objects.filter(wamid=wamid).exists():
            return None

        desc = describe_inbound(message)
        when = _ts(message.get("timestamp"))
        with transaction.atomic():
            conv = _get_conversation(user, number, (profile_names or {}).get(message.get("from"), ""))
            msg = ChatMessage.objects.create(
                user=user, conversation=conv, direction="in", message_type=desc["type"],
                body=desc["body"], media_id=desc["media_id"], media_mime=desc["mime"],
                filename=desc["filename"], payload=message, wamid=wamid,
                status="received", source="webhook", timestamp=when,
            )
            _touch(conv, "in", make_preview(desc), when, inbound=True)
            Conversation.objects.filter(pk=conv.pk).update(unread_count=F("unread_count") + 1)
        return msg
    except IntegrityError:
        return None  # same wamid arrived twice at once
    except Exception:
        logger.exception("Could not record inbound chat message")
        return None


def record_outbound(user, to_number, payload, response_json, ok, source, when=None):
    """Store a message WE sent (campaign / flow / API / chat).

    `response_json` is Meta's send response; `ok` whether the HTTP call
    succeeded. A send Meta rejected outright is stored as a failed message
    so the conversation shows what happened."""
    try:
        number = normalize_number(to_number)
        if not number:
            return None
        response_json = response_json or {}
        sent = response_json.get("messages") or []
        wamid = sent[0].get("id") if (ok and sent) else None
        if wamid and ChatMessage.objects.filter(wamid=wamid).exists():
            return None

        error = ""
        if not ok:
            err = response_json.get("error") or {}
            error = " — ".join(p for p in (err.get("message"), (err.get("error_data") or {}).get("details")) if p) \
                or "Message could not be sent."

        desc = describe_outbound(payload or {})
        when = when or timezone.now()
        with transaction.atomic():
            conv = _get_conversation(user, number)
            msg = ChatMessage.objects.create(
                user=user, conversation=conv, direction="out", message_type=desc["type"],
                body=desc["body"], media_id=desc["media_id"], filename=desc["filename"],
                payload=payload or {}, wamid=wamid,
                status="sent" if ok else "failed", source=source,
                error_message=error, timestamp=when,
            )
            _touch(conv, "out", make_preview(desc), when, inbound=False)
            if source in HUMAN_SOURCES:
                Conversation.objects.filter(pk=conv.pk).update(unread_count=0)
        return msg
    except IntegrityError:
        return None
    except Exception:
        logger.exception("Could not record outbound chat message")
        return None


def record_echo(user, echo):
    """A message sent from the WhatsApp Business *phone app* on a number that
    is also connected to the Cloud API (Coexistence) — Meta echoes it to us.
    Best-effort: shaped like an inbound message but addressed `to` the customer."""
    try:
        number = normalize_number(echo.get("to"))
        wamid = echo.get("id")
        if not number:
            return None
        if wamid and ChatMessage.objects.filter(wamid=wamid).exists():
            return None
        desc = describe_inbound(echo)
        when = _ts(echo.get("timestamp"))
        with transaction.atomic():
            conv = _get_conversation(user, number)
            msg = ChatMessage.objects.create(
                user=user, conversation=conv, direction="out", message_type=desc["type"],
                body=desc["body"], media_id=desc["media_id"], media_mime=desc["mime"],
                filename=desc["filename"], payload=echo, wamid=wamid,
                status="sent", source="app", timestamp=when,
            )
            _touch(conv, "out", make_preview(desc), when, inbound=False)
            Conversation.objects.filter(pk=conv.pk).update(unread_count=0)
        return msg
    except IntegrityError:
        return None
    except Exception:
        logger.exception("Could not record message echo")
        return None


def apply_status(wamid, status, when, errors=None):
    """A delivery-status webhook for a message we sent: move it forward
    (sent -> delivered -> read) or mark it failed. Never moves backwards."""
    try:
        msg = ChatMessage.objects.filter(wamid=wamid, direction="out").first()
        if not msg or status not in _STATUS_RANK:
            return
        changed = []
        if _STATUS_RANK[status] > _STATUS_RANK.get(msg.status, 0):
            msg.status = status
            changed.append("status")
        if status == "failed" and errors:
            err = errors[0]
            text = " — ".join(p for p in (err.get("message"), (err.get("error_data") or {}).get("details")) if p)
            if text and text != msg.error_message:
                msg.error_message = text
                changed.append("error_message")
        if changed:
            msg.save(update_fields=changed)
    except Exception:
        logger.exception("Could not apply status to chat message")


# --------------------------------------------------------------------------
# Serialising for the UI
# --------------------------------------------------------------------------

def _iso(dt):
    return dt.isoformat() if dt else None


def serialize_message(msg):
    return {
        "id": msg.id,
        "direction": msg.direction,
        "type": msg.message_type,
        "body": msg.body,
        "media_url": f"/services/messages/media/{msg.id}/" if msg.media_id else "",
        "mime": msg.media_mime,
        "filename": msg.filename,
        "status": msg.status,
        "error": msg.error_message,
        "source": msg.source,
        "ts": _iso(msg.timestamp),
    }


def serialize_conversation(conv, contact=None):
    name = display_name(conv, contact)
    return {
        "number": conv.contact_number,
        "name": name,
        "saved": bool(contact),
        "preview": conv.last_message_preview,
        "direction": conv.last_direction,
        "last_at": _iso(conv.last_message_at),
        "unread": conv.unread_count,
    }
