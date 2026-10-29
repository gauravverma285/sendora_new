import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Feature(models.Model):
    """One entry in the dynamic feature/limit registry. The admin defines
    these once (e.g. "Max Contacts", "Flow Builder") and every Plan then
    ticks a value for each one — nothing about what a "feature" is is
    hardcoded, so adding a new gate later is just a new Feature row, no
    code change."""
    NUMERIC = "numeric"   # a count-based limit, e.g. "Max Contacts": 500
    BOOLEAN = "boolean"   # an on/off capability, e.g. "Flow Builder": on
    TYPE_CHOICES = [(NUMERIC, "Numeric limit"), (BOOLEAN, "On/Off feature")]

    name = models.CharField(max_length=100, unique=True)
    key = models.SlugField(max_length=100, unique=True, help_text="Stable identifier used in code, e.g. 'max_contacts'.")
    feature_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=BOOLEAN)
    description = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0, help_text="Display order on the plan comparison page.")

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Plan(models.Model):
    """A subscription tier the admin creates from the Django admin. Price +
    a flexible duration (e.g. "14 days" for a trial, "1 month", "12 months"
    / "1 year" for a paid cycle) — plans aren't limited to a fixed
    monthly/yearly choice, any admin can invent a new cadence."""
    DAY, MONTH, YEAR = "day", "month", "year"
    DURATION_CHOICES = [(DAY, "Day(s)"), (MONTH, "Month(s)"), (YEAR, "Year(s)")]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.CharField(max_length=255, blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_free = models.BooleanField(default=False, help_text="Shows a \"Free\" badge; also settable on a plan with a non-zero price if you want a promo.")

    duration_value = models.PositiveIntegerField(default=1)
    duration_unit = models.CharField(max_length=5, choices=DURATION_CHOICES, default=MONTH)

    is_active = models.BooleanField(default=True, help_text="Unpublished plans are hidden from customers but keep working for anyone already on them.")
    is_default = models.BooleanField(default=False, help_text="Auto-assigned to every new signup. Only one plan should have this on.")
    is_featured = models.BooleanField(default=False, help_text="Highlighted as \"Most Popular\" on the plans page.")
    order = models.PositiveSmallIntegerField(default=0)

    features = models.ManyToManyField(Feature, through="PlanFeature", related_name="plans")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "price"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.name) or "plan"
            slug, n = base, 2
            while Plan.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def duration_label(self):
        n = self.duration_value
        unit = self.get_duration_unit_display().rstrip("(s)") if n == 1 else self.get_duration_unit_display()
        return f"{n} {unit}"

    def period_end(self, start=None):
        start = start or timezone.now()
        if self.duration_unit == self.DAY:
            return start + timezone.timedelta(days=self.duration_value)
        if self.duration_unit == self.YEAR:
            return start + timezone.timedelta(days=365 * self.duration_value)
        return start + timezone.timedelta(days=30 * self.duration_value)  # MONTH — simple, predictable

    def limit(self, feature_key, default=0):
        """The numeric value ticked for `feature_key` on this plan, or
        `default` if the plan doesn't define it. `None` means unlimited."""
        pf = self.plan_features.filter(feature__key=feature_key).first()
        return pf.limit_value if pf else default

    def has(self, feature_key):
        """Whether the boolean feature `feature_key` is ticked on for this plan."""
        pf = self.plan_features.filter(feature__key=feature_key).first()
        return bool(pf and pf.is_enabled)


class PlanFeature(models.Model):
    """One ticked row in a Plan's feature table — edited as an inline on the
    Plan admin page, which is the literal "tick feature" / set-a-limit UI."""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="plan_features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="plan_features")
    # Boolean features use is_enabled; numeric features use limit_value
    # (blank/None = unlimited for that plan).
    is_enabled = models.BooleanField(default=False)
    limit_value = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("plan", "feature")

    def __str__(self):
        return f"{self.plan.name} — {self.feature.name}"


class Subscription(models.Model):
    ACTIVE, CANCELLED, EXPIRED = "active", "cancelled", "expired"
    STATUS_CHOICES = [(ACTIVE, "Active"), (CANCELLED, "Cancelled"), (EXPIRED, "Expired")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=ACTIVE)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} — {self.plan.name}"

    @property
    def is_active(self):
        """Live, not cached — a stored 'active' status can go stale the
        moment end_date passes; nothing needs a cron job to keep this correct."""
        return self.status == self.ACTIVE and self.end_date > timezone.now()

    def days_remaining(self):
        return max((self.end_date - timezone.now()).days, 0)


class Payment(models.Model):
    """A demo payment record — no real payment gateway is wired up. Every
    checkout on this page always "succeeds"; this just keeps a receipt/audit
    trail so a subscription's history is visible."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=40, unique=True, default=uuid.uuid4, editable=False)
    is_demo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.user.username} — {self.plan.name}"
