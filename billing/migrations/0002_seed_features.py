from django.db import migrations

# Seeds the three numeric limits the app already enforces in code (contacts,
# campaigns, flows — see billing/services.py). The admin can still add any
# number of further Feature rows (boolean or numeric) from the admin site;
# nothing about the app requires these three specifically to exist, but
# without them a fresh install has no rows to tick on a new Plan.
DEFAULT_FEATURES = [
    {"name": "Max Contacts", "key": "max_contacts", "feature_type": "numeric",
     "description": "How many contacts this plan allows uploading in total.", "order": 1},
    {"name": "Max Campaigns", "key": "max_campaigns", "feature_type": "numeric",
     "description": "How many campaigns (sent or scheduled) this plan allows creating in total.", "order": 2},
    {"name": "Max Flows", "key": "max_flows", "feature_type": "numeric",
     "description": "How many automation flows this plan allows creating in total.", "order": 3},
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
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_features, remove_features),
    ]
