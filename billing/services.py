"""Plan lookup + limit/feature enforcement helpers.

Kept independent of any specific model in `services` app — a caller passes
the current usage count in and gets back an allow/deny + the limit, so this
module never needs to know how a "contact" or "campaign" is counted.
"""
from django.utils import timezone

from .models import Payment, Plan, Subscription

# Feature keys used by the app. Defined once here so every call site and the
# seed command below agree on the same string.
MAX_CONTACTS = "max_contacts"
MAX_CAMPAIGNS = "max_campaigns"
MAX_FLOWS = "max_flows"
API_RATE_LIMIT = "api_rate_limit"


def get_default_plan():
    return Plan.objects.filter(is_default=True, is_active=True).first()


def get_subscription(user):
    """The user's current Subscription row, or None if they've never had
    one assigned yet (ensure_subscription below is what creates it)."""
    if not user or not user.is_authenticated:
        return None
    return Subscription.objects.select_related("plan").filter(user=user).first()


def ensure_subscription(user):
    """Guarantees a Subscription exists, assigning the admin's default plan
    on first touch. Called lazily (context processor / decorator) instead of
    a signal, so it also backfills users who existed before this app did —
    no data migration needed."""
    sub = get_subscription(user)
    if sub:
        return sub

    plan = get_default_plan()
    if not plan:
        return None

    sub = Subscription.objects.create(
        user=user,
        plan=plan,
        status=Subscription.ACTIVE,
        start_date=timezone.now(),
        end_date=plan.period_end(),
    )
    return sub


def get_active_plan(user):
    """The plan actually in effect right now: the subscribed plan while
    it's active, otherwise falls back to the default plan so a lapsed
    subscription degrades to free/default rather than unlimited or blocked."""
    sub = ensure_subscription(user)
    if sub and sub.is_active:
        return sub.plan
    return get_default_plan()


def check_limit(user, feature_key, current_count):
    """Returns (allowed, limit) for adding ONE more item of this kind.
    limit is None for unlimited. A feature the plan doesn't define at all
    is treated as blocked (limit 0) — an admin has to explicitly grant it."""
    plan = get_active_plan(user)
    if not plan:
        return False, 0
    limit = plan.limit(feature_key, default=0)
    if limit is None:
        return True, None
    return current_count < limit, limit


def get_api_rate_limit(user):
    """Requests/hour the user's plan allows on the external API, or None for
    unlimited. 0 means the plan doesn't grant API access at all — same
    "undefined on the plan = blocked" convention as check_limit."""
    plan = get_active_plan(user)
    return plan.limit(API_RATE_LIMIT, default=0) if plan else 0


def has_feature(user, feature_key):
    plan = get_active_plan(user)
    return bool(plan and plan.has(feature_key))


def subscribe_user(user, plan):
    """Demo checkout: records a Payment receipt and (re)activates the
    Subscription on `plan`, starting a fresh period from now."""
    now = timezone.now()
    payment = Payment.objects.create(user=user, plan=plan, amount=plan.price, is_demo=True)

    sub, _ = Subscription.objects.update_or_create(
        user=user,
        defaults={
            "plan": plan,
            "status": Subscription.ACTIVE,
            "start_date": now,
            "end_date": plan.period_end(now),
        },
    )
    return sub, payment
