from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from . import services
from .models import Plan


@login_required
def plan_list(request):
    plans = (
        Plan.objects.filter(is_active=True)
        .prefetch_related("plan_features__feature")
        .order_by("order", "price")
    )
    subscription = services.ensure_subscription(request.user)
    current_plan = subscription.plan if subscription and subscription.is_active else None

    plan_rows = []
    for plan in plans:
        rows = []
        for pf in plan.plan_features.all():
            if pf.feature.feature_type == "numeric":
                value = "Unlimited" if pf.limit_value is None else f"{pf.limit_value:,}"
            else:
                value = "Included" if pf.is_enabled else None
            if value:
                rows.append({"name": pf.feature.name, "value": value})
        plan_rows.append({"plan": plan, "rows": rows})

    return render(request, "billing/plan_list.html", {
        "plan_rows": plan_rows,
        "subscription": subscription,
        "current_plan": current_plan,
    })


@login_required
def checkout(request, slug):
    plan = get_object_or_404(Plan, slug=slug, is_active=True)

    if request.method == "POST":
        services.subscribe_user(request.user, plan)
        if plan.is_free or plan.price == 0:
            messages.success(request, f"You're now on the {plan.name} plan.")
        else:
            messages.success(request, f"Payment confirmed (demo) — you're now on the {plan.name} plan.")
        return redirect("billing:plan_list")

    return render(request, "billing/checkout.html", {"plan": plan})
