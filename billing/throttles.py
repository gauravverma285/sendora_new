from django.core.cache import cache
from django.utils import timezone
from rest_framework.throttling import BaseThrottle

from . import services

# Counts land in a plain calendar-hour bucket rather than a sliding window —
# simple, and close enough for "N requests/hour" to mean something to a
# customer integrating against it.
CACHE_PREFIX = "billing:api_throttle"


class PlanRateThrottle(BaseThrottle):
    """Caps external API requests at the calling user's plan's
    `api_rate_limit` (requests/hour). A plan that doesn't grant the feature
    at all (limit 0) blocks every request; `None` means unlimited."""

    def allow_request(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return True  # DRF's IsAuthenticated already rejects these first

        limit = services.get_api_rate_limit(user)
        if limit is None:
            return True
        if limit <= 0:
            self._wait = 3600
            return False

        bucket = timezone.now().strftime("%Y%m%d%H")
        cache_key = f"{CACHE_PREFIX}:{user.id}:{bucket}"
        count = cache.get(cache_key, 0)
        if count >= limit:
            self._wait = 3600
            return False

        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, timeout=3600)
        else:
            if count == 0:
                cache.touch(cache_key, timeout=3600)
        return True

    def wait(self):
        return getattr(self, "_wait", None)
