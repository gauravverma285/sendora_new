from django.db import migrations

# Boolean "can this account even open this section" features, distinct from
# the numeric max_* limits (0001/0002) — a plan can grant a page but cap how
# much can be created in it, or block the page entirely. Keys mirror the
# sidebar sections in templates/services.html; see billing/pages.py for the
# preview copy/image shown when a plan doesn't include one.
DEFAULT_PAGE_FEATURES = [
    {"name": "Campaigns Page", "key": "feature_campaigns", "feature_type": "boolean",
     "description": "Access to the Campaign section (create/send/view campaigns).", "order": 10},
    {"name": "Templates Page", "key": "feature_templates", "feature_type": "boolean",
     "description": "Access to the Template section (create/manage WhatsApp templates).", "order": 11},
    {"name": "Contacts Page", "key": "feature_contacts", "feature_type": "boolean",
     "description": "Access to the Contacts section (add/import/manage contacts).", "order": 12},
    {"name": "Messages Page", "key": "feature_messages", "feature_type": "boolean",
     "description": "Access to the Messages/chat inbox section.", "order": 13},
    {"name": "Flows Page", "key": "feature_flows", "feature_type": "boolean",
     "description": "Access to the Flows (automation) section.", "order": 14},
    {"name": "Tags Page", "key": "feature_tags", "feature_type": "boolean",
     "description": "Access to the Tags section.", "order": 15},
]


def seed_features(apps, schema_editor):
    Feature = apps.get_model("billing", "Feature")
    for data in DEFAULT_PAGE_FEATURES:
        Feature.objects.get_or_create(key=data["key"], defaults=data)


def remove_features(apps, schema_editor):
    Feature = apps.get_model("billing", "Feature")
    Feature.objects.filter(key__in=[d["key"] for d in DEFAULT_PAGE_FEATURES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_seed_features"),
    ]

    operations = [
        migrations.RunPython(seed_features, remove_features),
    ]
