"""Metadata for plan-gated dashboard sections + the decorator that shows a
locked preview instead of the real page when the current plan doesn't
include that section (see billing/migrations/0003_seed_page_features.py for
the Feature rows these keys map to).

Drop a screenshot for each section at static/images/feature_previews/<image>
— referenced by filename only below so the folder can be filled in later
without touching code.
"""
from functools import wraps

from django.shortcuts import render

from . import services

FEATURE_PAGES = {
    "feature_campaigns": {
        "label": "Campaigns",
        "blurb": "Launch WhatsApp broadcast campaigns to your contacts and track delivery, reads and replies.",
        "image": "campaigns.png",
    },
    "feature_templates": {
        "label": "Templates",
        "blurb": "Create and manage WhatsApp message templates for approval and reuse across campaigns.",
        "image": "templates.png",
    },
    "feature_contacts": {
        "label": "Contacts",
        "blurb": "Import, tag and manage every WhatsApp contact your business talks to.",
        "image": "contacts.png",
    },
    "feature_messages": {
        "label": "Messages",
        "blurb": "Chat with your customers directly and reply to their WhatsApp messages in real time.",
        "image": "messages.png",
    },
    "feature_flows": {
        "label": "Flows",
        "blurb": "Build automated conversation flows that respond to customers instantly.",
        "image": "flows.png",
    },
    "feature_tags": {
        "label": "Tags",
        "blurb": "Organize contacts with custom tags so you can target the right audience for every campaign.",
        "image": "tags.png",
    },
}


def feature_required(feature_key):
    """Wraps a section's entry-point view. Anonymous requests are passed
    through unchanged (existing login handling on the view, if any, still
    applies) — only an authenticated user whose plan lacks the feature gets
    the locked preview instead of the real page."""
    meta = FEATURE_PAGES[feature_key]

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated or services.has_feature(request.user, feature_key):
                return view_func(request, *args, **kwargs)
            return render(request, "billing/feature_locked.html", {
                "feature_key": feature_key,
                "feature_label": meta["label"],
                "feature_blurb": meta["blurb"],
                "feature_image": meta["image"],
            })
        return wrapped
    return decorator
