#!/bin/sh
set -e

# Only the web container runs migrations/collectstatic; worker and beat wait
# for it to become healthy (see docker-compose.yml) before they start.
if [ "$1" = "web" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
    # settings.SITE_ID = 2 (django-allauth) — make sure that Site row exists.
    python manage.py shell -c "
import os
from django.contrib.sites.models import Site
Site.objects.update_or_create(id=2, defaults={'domain': os.environ.get('SITE_DOMAIN', 'sendora.systems'), 'name': 'Sendora'})
"
    exec gunicorn dpro.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-3}" \
        --timeout 120 \
        --access-logfile - \
        --forwarded-allow-ips '*'
elif [ "$1" = "worker" ]; then
    exec celery -A dpro worker -l info --concurrency "${CELERY_CONCURRENCY:-2}"
elif [ "$1" = "beat" ]; then
    exec celery -A dpro beat -l info --schedule /tmp/celerybeat-schedule
else
    exec "$@"
fi
