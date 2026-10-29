import copy

from celery import shared_task
import logging
logger = logging.getLogger(__name__)

import requests
from django.conf import settings
from django.contrib.auth.models import User
from .models import Campaign  # or wherever your model is

@shared_task
def run_scheduled_campaign(campaign_id, user_id):
    try:
        from services.views import send_message_to_user  # if your payload creator is in utils

        user = User.objects.get(id=user_id)
        campaign = Campaign.objects.get(id=campaign_id, user=user)

        payload = campaign.sending_payload
        recipients = campaign.customer_list
        final_data = campaign.final_data
        print("final_data=-->",final_data)
        send_message_to_user(payload, recipients, final_data, user, campaign=campaign)

        print("📤 Sending messages...")
        # campaign.status = "sent"
        # campaign.save()
    except Exception as e:
        logger.error(f"Error running scheduled campaign ID {campaign_id}: {str(e)}", exc_info=True)


@shared_task
def async_send_messages(payload, recipients, final_data, user_id, campaign_id=None):
    from services.views import send_message_to_user  # if your payload creator is in utils

    user = User.objects.get(id=user_id)
    campaign = Campaign.objects.filter(id=campaign_id).first() if campaign_id else None
    return send_message_to_user(payload, recipients, final_data, user, campaign=campaign)


def _send_whatsapp_payload(payload, profile):
    """POST one already-built template-message payload to Meta's Cloud API
    for the given UserProfile's connected WABA/phone number."""
    graph_version = settings.META_GRAPH_API_VERSION
    url = f"https://graph.facebook.com/{graph_version}/{profile.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {profile.api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=payload, headers=headers)
    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw": response.text}

    # Show it in the account's Messages inbox as well.
    from services import chat as chat_log
    chat_log.record_outbound(profile.user, payload.get("to"), payload, response_data, response.ok, "api")

    return {"to": payload.get("to"), "status_code": response.status_code, "response": response_data}


@shared_task
def send_whatsapp_api_message(payload, user_id):
    """External-API single-recipient send — used by services.api_views."""
    from accounts.models import UserProfile

    profile = UserProfile.objects.get(user_id=user_id)
    if not (profile.phone_number_id and profile.api_key):
        return {"status": "error", "message": "Missing phone_number_id or API key on profile."}
    return _send_whatsapp_payload(payload, profile)


@shared_task
def send_whatsapp_api_bulk_messages(base_payload, recipients, user_id):
    """External-API bulk send — same template/params to a plain list of
    phone numbers, no per-recipient personalization."""
    from accounts.models import UserProfile

    profile = UserProfile.objects.get(user_id=user_id)
    if not (profile.phone_number_id and profile.api_key):
        return [{"status": "error", "message": "Missing phone_number_id or API key on profile."}]

    results = []
    for to in recipients:
        payload = copy.deepcopy(base_payload)
        payload["to"] = to
        results.append(_send_whatsapp_payload(payload, profile))
    return results