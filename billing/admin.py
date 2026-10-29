from django.contrib import admin

from .models import Feature, Payment, Plan, PlanFeature, Subscription


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "feature_type", "order")
    list_editable = ("order",)
    prepopulated_fields = {"key": ("name",)}
    search_fields = ("name", "key")


class PlanFeatureInline(admin.TabularInline):
    """The literal "tick feature" UI: every registered Feature gets a row
    here on the Plan's own edit page, so creating a plan and ticking what
    it includes happens in one screen."""
    model = PlanFeature
    extra = 0
    min_num = 0
    autocomplete_fields = ("feature",)
    fields = ("feature", "is_enabled", "limit_value")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "duration_label", "is_free", "is_active", "is_default", "order")
    list_editable = ("order", "is_active", "is_default")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    inlines = [PlanFeatureInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "description")}),
        ("Pricing & duration", {"fields": ("price", "is_free", ("duration_value", "duration_unit"))}),
        ("Visibility", {"fields": ("is_active", "is_default", "is_featured", "order")}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.is_default:
            # Exactly one default plan — flip every other plan's flag off so
            # new-signup auto-assignment never has to guess which one to use.
            Plan.objects.exclude(pk=obj.pk).filter(is_default=True).update(is_default=False)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "start_date", "end_date", "is_active")
    list_filter = ("status", "plan")
    search_fields = ("user__username", "user__email")
    autocomplete_fields = ("user", "plan")

    @admin.display(boolean=True, description="Active now")
    def is_active(self, obj):
        return obj.is_active


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "plan", "amount", "is_demo", "created_at")
    list_filter = ("is_demo", "plan")
    search_fields = ("user__username", "user__email", "reference")
    readonly_fields = ("reference", "created_at")
