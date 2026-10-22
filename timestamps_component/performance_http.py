"""Requests facade recording individual outgoing HTTP calls, including poll attempts."""
from functools import wraps
from urllib.parse import urlsplit

import requests as original_requests

from sdt_performance_tracker import CURRENT_TRACKER, EventCategory


class TimedRequests:
    def __getattr__(self, name):
        original = getattr(original_requests, name)
        if name not in {"get", "post", "put", "patch", "delete", "head", "options"}:
            return original

        @wraps(original)
        def timed(url, *args, **kwargs):
            tracker = CURRENT_TRACKER.get()
            if tracker is None:
                return original(url, *args, **kwargs)
            parsed = urlsplit(url)
            metadata = {"method": name.upper(), "host": parsed.hostname,
                        "path": parsed.path[:300]}
            with tracker.track(EventCategory.HTTP_CLIENT,
                               f"{name.upper()} {parsed.hostname}{parsed.path[:300]}",
                               metadata) as span:
                response = original(url, *args, **kwargs)
                span.metadata["http_status"] = response.status_code
                if response.status_code >= 400:
                    span.status = "failed"
                return response
        return timed


requests = TimedRequests()
