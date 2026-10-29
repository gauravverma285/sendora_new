from django.db import migrations

# A single numeric feature drives both the API Access Token panel's
# visibility and the actual throttle on the external API (see
# billing/services.get_api_rate_limit, services/api_views.py). Leaving the
# limit unset on a plan defaults to 0 (blocked) — same convention as
# max_contacts/max_campaigns/max_flows; leaving the limit field itself blank
# on a plan that HAS ticked it means unlimited.
DEFAULT_FEATURES = [
    {"name": "API Access (requests/hour)", "key": "api_rate_limit", "feature_type": "numeric",
     "description": "How many external API requests per hour this plan allows. Untick to hide the API "
                     "token from this plan entirely; leave the limit blank for unlimited.", "order": 20},
]


def seed_features(apps, schema_editor):
    Feature = apps.get_model("billing", "Feature")
    for data in DEFAULT_FEATURES:
        Feature.objects.get_or_create(key=data["key"], defaults=data)


def remove_features(apps, schema_editor):
    Feature = apps.get_model("billing", "Feature")
    Feature.objects.filter(key__in=[d["key"] for d in DEFAULT_FEATURES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0003_seed_page_features"),
    ]

    operations = [
        migrations.RunPython(seed_features, remove_features),
    ]
