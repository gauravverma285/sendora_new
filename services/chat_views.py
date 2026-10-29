"""Views for the Messages inbox (WhatsApp chat).

Every view is @login_required and reads/writes only the signed-in account's
rows (Conversation / ChatMessage are keyed by `user`), so accounts can never
see each other's chats — even when they talk to the same customer number.
"""
import json
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from accounts.models import UserProfile
from billing.pages import feature_required

from . import chat
from .models import ChatMessage, Contact, Conversation, Tag

PAGE_SIZE = 100
OLDER_PAGE_SIZE = 50
MAX_TEXT = 4096

# Meta serves media from these hosts only — never fetch anything else on the
# strength of a URL in an API response.
_MEDIA_HOSTS = ("fbsbx.com", "facebook.com", "whatsapp.net", "fbcdn.net", "whatsapp.com")


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _profile(request):
    profile = UserProfile.objects.filter(user=request.user).first()
    if profile and profile.phone_number_id and profile.api_key:
        return profile
    return None


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


@login_required
@feature_required('feature_messages')
def chat_page(request):
    return render(request, "chat.html", {
        "connected": _profile(request) is not None,
        "initial_number": chat.normalize_number(request.GET.get("number")),
    })


@login_required
@require_GET
def chat_conversations(request):
    """The conversation list (left column) with tab counts."""
    q = request.GET.get("q", "").strip()
    tab = request.GET.get("tab", "all")

    base = Conversation.objects.filter(user=request.user, last_message_at__isnull=False)
    counts = {
        "all": base.count(),
        "incoming": base.filter(last_direction="in").count(),
        "outgoing": base.filter(last_direction="out").count(),
    }
    unread_total = base.aggregate(total=Sum("unread_count"))["total"] or 0

    qs = base
    if tab == "incoming":
        qs = qs.filter(last_direction="in")
    elif tab == "outgoing":
        qs = qs.filter(last_direction="out")

    if q:
        # Match the customer's name/number, or ANY message in the chat (not
        # just the latest one shown as the preview).
        in_messages = ChatMessage.objects.filter(user=request.user, body__icontains=q).values("conversation_id")
        cond = Q(profile_name__icontains=q) | Q(pk__in=in_messages)
        digits = chat.normalize_number(q)
        if digits:
            cond |= Q(contact_number__contains=digits)
        saved = Contact.objects.filter(user=request.user, name__icontains=q).values_list("mobile_number", flat=True)
        saved_numbers = [chat.normalize_number(n) for n in saved]
        if saved_numbers:
            cond |= Q(contact_number__in=saved_numbers)
        qs = qs.filter(cond)

    convs = list(qs.order_by("-last_message_at")[:200])
    saved_map = chat.contacts_by_number(request.user, [c.contact_number for c in convs])
    return JsonResponse({
        "counts": counts,
        "unread_total": unread_total,
        "conversations": [chat.serialize_conversation(c, saved_map.get(c.contact_number)) for c in convs],
    })


@login_required
@require_GET
def chat_thread(request):
    """One conversation: its messages plus the side-panel details.

    Modes: no params -> latest page; `after=<id>` -> only newer messages
    (plus fresh delivery statuses); `before=<id>` -> an older page."""
    number = chat.normalize_number(request.GET.get("number"))
    conv = Conversation.objects.filter(user=request.user, contact_number=number).first()
    if not conv:
        return JsonResponse({"error": "Conversation not found."}, status=404)

    after, before = _int(request.GET.get("after")), _int(request.GET.get("before"))
    all_msgs = ChatMessage.objects.filter(conversation=conv)

    has_more = False
    if after:
        messages = list(all_msgs.filter(id__gt=after).order_by("timestamp", "id"))
    elif before:
        older = list(all_msgs.filter(id__lt=before).order_by("-timestamp", "-id")[:OLDER_PAGE_SIZE + 1])
        has_more = len(older) > OLDER_PAGE_SIZE
        messages = list(reversed(older[:OLDER_PAGE_SIZE]))
    else:
        latest = list(all_msgs.order_by("-timestamp", "-id")[:PAGE_SIZE + 1])
        has_more = len(latest) > PAGE_SIZE
        messages = list(reversed(latest[:PAGE_SIZE]))

    if request.GET.get("mark_read") == "1" and conv.unread_count:
        Conversation.objects.filter(pk=conv.pk).update(unread_count=0)
        conv.unread_count = 0

    window = chat.window_state(conv)
    data = {
        "messages": [chat.serialize_message(m) for m in messages],
        "has_more": has_more,
        "window": {"open": window["open"], "expires_at": chat._iso(window["expires_at"])},
    }

    if after:
        # Delivery ticks change after a message was already shown.
        recent_out = all_msgs.filter(direction="out").order_by("-id")[:60]
        data["statuses"] = [{"id": m.id, "status": m.status, "error": m.error_message} for m in recent_out]

    if not after and not before:
        contact = chat.find_contact(request.user, number)
        counts = {
            "total": all_msgs.count(),
            "incoming": all_msgs.filter(direction="in").count(),
            "outgoing": all_msgs.filter(direction="out").count(),
        }
        recent = [
            {"event": "Message received" if m.direction == "in" else "Message sent",
             "text": m.body or m.message_type, "direction": m.direction, "ts": chat._iso(m.timestamp)}
            for m in all_msgs.order_by("-timestamp", "-id")[:3]
        ]
        data["conversation"] = {
            **chat.serialize_conversation(conv, contact),
            "profile_name": conv.profile_name,
            "first_message_at": chat._iso(conv.created_at),
        }
        data["contact"] = {
            "saved": bool(contact),
            "id": contact.id if contact else None,
            "email": (contact.email or "") if contact else "",
            "age": contact.age if contact else None,
            "tags": list(contact.tags.values("id", "name")) if contact else [],
        }
        data["available_tags"] = list(Tag.objects.filter(user=request.user).values("id", "name"))
        data["summary"] = counts
        data["recent"] = recent

    return JsonResponse(data)


@login_required
@require_POST
def chat_send(request):
    """Send a free-form text reply. WhatsApp only allows this within 24 hours
    of the customer's last message, so that's checked here first and turned
    into a clear message instead of Meta's `131047` rejection."""
    data = _json_body(request)
    number = chat.normalize_number(data.get("number"))
    text = (data.get("text") or "").strip()
    if not number or not text:
        return JsonResponse({"error": "Type a message to send."}, status=400)
    if len(text) > MAX_TEXT:
        return JsonResponse({"error": f"Messages can be at most {MAX_TEXT} characters."}, status=400)

    profile = _profile(request)
    if not profile:
        return JsonResponse({"error": "Connect your WhatsApp Business Account first (Profile page)."}, status=400)

    conv = Conversation.objects.filter(user=request.user, contact_number=number).first()
    if not conv or not chat.window_state(conv)["open"]:
        return JsonResponse({
            "error": "The 24-hour reply window is closed. WhatsApp only lets you send an approved template "
                     "message now — start a Template campaign, or wait for the customer to message you.",
            "window_closed": True,
        }, status=409)

    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": number,
        "type": "text", "text": {"body": text, "preview_url": True},
    }
    url = f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/{profile.phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {profile.api_key}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
    except requests.RequestException:
        return JsonResponse({"error": "Couldn't reach WhatsApp. Please try again."}, status=502)

    try:
        response_json = response.json()
    except ValueError:
        response_json = {}

    if not response.ok:
        err = response_json.get("error") or {}
        detail = (err.get("error_data") or {}).get("details")
        message = " — ".join(p for p in (err.get("message"), detail) if p) or "WhatsApp rejected the message."
        return JsonResponse({"error": message}, status=400)

    msg = chat.record_outbound(request.user, number, payload, response_json, True, "chat")
    return JsonResponse({"ok": True, "message": chat.serialize_message(msg) if msg else None})


@login_required
@require_POST
def chat_save_contact(request):
    """Save an unknown chat number into this account's Contacts."""
    data = _json_body(request)
    number = chat.normalize_number(data.get("number"))
    if not number or len(number) > 15:
        return JsonResponse({"error": "That isn't a valid phone number."}, status=400)

    contact = chat.find_contact(request.user, number)
    if contact:
        return JsonResponse({"ok": True, "already_saved": True})

    conv = Conversation.objects.filter(user=request.user, contact_number=number).first()
    name = (data.get("name") or "").strip() or (conv.profile_name if conv else "") or ""
    Contact.objects.create(user=request.user, name=name[:255], mobile_number=number)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def chat_add_tag(request):
    data = _json_body(request)
    contact = chat.find_contact(request.user, data.get("number"))
    if not contact:
        return JsonResponse({"error": "Save this number as a contact first."}, status=400)
    tag = Tag.objects.filter(id=_int(data.get("tag_id")), user=request.user).first()
    if not tag:
        return JsonResponse({"error": "Tag not found."}, status=404)
    contact.tags.add(tag)
    return JsonResponse({"ok": True, "tag": {"id": tag.id, "name": tag.name}})


def _inline_safe(mime):
    """Only media a browser plays/shows without running code is served
    inline; anything else (a customer-sent .html, .svg, ...) is downloaded
    instead, so a customer can't plant a script on our origin."""
    mime = (mime or "").lower()
    if mime == "image/svg+xml":
        return False
    return mime.startswith(("image/", "video/", "audio/"))


@login_required
@require_GET
def chat_media(request, message_id):
    """Proxy a WhatsApp media file (customer photo / voice note / document)
    using this account's own token — Meta's media URLs need it, so the
    browser can't fetch them directly."""
    msg = ChatMessage.objects.filter(id=message_id, user=request.user).first()
    if not msg or not msg.media_id:
        raise Http404("No media")
    profile = _profile(request)
    if not profile:
        raise Http404("Not connected")

    auth = {"Authorization": f"Bearer {profile.api_key}"}
    graph = settings.META_GRAPH_API_VERSION
    try:
        meta = requests.get(f"https://graph.facebook.com/{graph}/{msg.media_id}", headers=auth, timeout=15)
        info = meta.json() if meta.ok else {}
        media_url = info.get("url") or ""
        host = (urlparse(media_url).hostname or "").lower()
        if not media_url.startswith("https://") or not host.endswith(_MEDIA_HOSTS):
            raise Http404("Media unavailable")
        upstream = requests.get(media_url, headers=auth, stream=True, timeout=30)
    except (requests.RequestException, ValueError):
        raise Http404("Media unavailable")
    if not upstream.ok:
        raise Http404("Media unavailable")

    mime = info.get("mime_type") or msg.media_mime or upstream.headers.get("Content-Type", "")
    inline = _inline_safe(mime)
    response = StreamingHttpResponse(
        upstream.iter_content(chunk_size=65536),
        content_type=mime if inline else "application/octet-stream",
    )
    filename = (msg.filename or f"whatsapp-{msg.id}").replace('"', "")
    response["Content-Disposition"] = f'{"inline" if inline else "attachment"}; filename="{filename}"'
    response["Cache-Control"] = "private, max-age=300"
    return response
