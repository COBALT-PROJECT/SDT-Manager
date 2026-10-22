"""Timing hooks kept separate from the current SDT Manager business logic."""
import inspect
from functools import wraps

from fastapi import HTTPException, Query
from fastapi.responses import Response

from sdt_performance_tracker import EventCategory


# Only identifiers and operation names are recorded. Never record arbitrary
# arguments, credentials, HTTP bodies, shell commands, or method return values.
SAFE_ARGUMENTS = {
    "sdt_id", "sdt_identifier", "identifier", "connector_id", "ids_connector_id",
    "connector_type", "deployment_name", "service_name", "component_label",
    "payload_type", "toeid", "replicas", "config_file",
}
SKIP_METHODS = {"_setup_routes", "start_server", "start_server_thread", "_worker_loop"}
NONE_IS_FAILURE = {
    "run_command", "_fetch_token", "_register_twin", "_get_service_cluster_ip",
    "_get_sdt_service_name", "_get_ids_sdt_service_name",
}


def category_for(name, default):
    if name == "run_command" or name.startswith("check_") or name == "apply_config_file":
        return EventCategory.KUBERNETES
    if name == "_send_template_to_sdt":
        return EventCategory.TEMPLATE_DELIVERY
    if name in {"_distribute_token", "_send_token_to_service"}:
        return EventCategory.TOKEN_DISTRIBUTION
    if name == "_run_auth_flow_async":
        return EventCategory.AUTH_TOKEN_ACQUISITION
    if name.startswith("delete") or name == "_delete_from_wallet":
        return EventCategory.DELETION
    if name.startswith("deploy"):
        return EventCategory.DEPLOYMENT
    return default


def result_failed(name, result):
    """Recognize explicit failure contracts without changing returned values."""
    if result is False:
        return True
    if result is None:
        return name in NONE_IS_FAILURE
    if hasattr(result, "valid"):
        return result.valid is False
    if isinstance(result, tuple) and result:
        if hasattr(result[0], "valid"):
            return result[0].valid is False
        return result[0] is False or result[0] is None
    if isinstance(result, dict):
        if "sdt_response" in result:
            response = result["sdt_response"]
            return response is None or response.status_code >= 400
        if result and all(isinstance(v, bool) for v in result.values()):
            return not all(result.values())
    return False


def instrument_component(instance, tracker, category):
    """Wrap instance methods, including internal substeps and nested IDS operations.

    Return values and exceptions pass through unchanged. Long-running server/worker
    loops are excluded; each request and each MQTT publish attempt is timed instead.
    """
    if getattr(instance, "_performance_instrumented", False):
        return instance
    instance._performance_instrumented = True
    for name, function in type(instance).__dict__.items():
        if name.startswith("__") or name in SKIP_METHODS or not inspect.isfunction(function):
            continue
        method = getattr(instance, name)
        signature = inspect.signature(method)

        def wrap(method, name, signature):
            @wraps(method)
            def timed(*args, **kwargs):
                arguments = signature.bind(*args, **kwargs).arguments
                metadata = {k: v for k, v in arguments.items()
                            if k in SAFE_ARGUMENTS and isinstance(v, (str, int, bool))}
                for key in ("sdt_identifier", "identifier"):
                    if key in metadata:
                        metadata["sdt_id"] = metadata[key]
                if name == "_publish":
                    event_id = arguments.get("payload", {}).get("event_id")
                    if isinstance(event_id, str):
                        metadata["mqtt_event_id"] = event_id
                if name == "report_failure":
                    tracker.mark_current_failed()
                with tracker.track(category_for(name, category),
                                   f"{type(instance).__name__}.{name}", metadata) as span:
                    result = method(*args, **kwargs)
                    if result_failed(name, result):
                        span.status = "failed"
                    if (name in {"deploy", "deploy_pod", "deploy_connector"}
                            and isinstance(result, tuple) and len(result) == 2
                            and isinstance(result[1], str)):
                        key = "sdt_id" if type(instance).__name__ == "SDT_LifeCycleManager" else "connector_id"
                        span.metadata[key] = result[1]
                    return result
            return timed

        setattr(instance, name, wrap(method, name, signature))
    if hasattr(instance, "ids_connector"):
        instrument_component(instance.ids_connector, tracker, EventCategory.KUBERNETES)
    return instance


def create_component(tracker, factory, category, *args, **kwargs):
    label = getattr(factory, "__qualname__", factory.__name__)
    with tracker.track(EventCategory.COMPONENT_INSTANTIATION, label):
        instance = factory(*args, **kwargs)
    return instrument_component(instance, tracker, category)


class PerformanceTimingMiddleware:
    """Measure complete ASGI responses, including errors and streamed bodies."""

    def __init__(self, app, tracker):
        self.app = app
        self.tracker = tracker

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method = scope.get("method", "")
        path = scope.get("path", "")[:300]
        with self.tracker.track(EventCategory.API_ENDPOINT, f"{method} {path}",
                                {"method": method, "path": path}) as span:
            async def timed_send(message):
                if message["type"] == "http.response.start":
                    status = message["status"]
                    span.metadata["http_status"] = status
                    if status >= 400:
                        span.status = "failed"
                await send(message)

            try:
                await self.app(scope, receive, timed_send)
            except Exception:
                span.metadata.setdefault("http_status", 500)
                raise


def add_performance_routes(app, tracker):
    def filtered(category=None, sdt_id=None, label=None):
        if category and category not in {c.value for c in EventCategory}:
            raise HTTPException(400, detail="Invalid performance category")
        return [r for r in tracker.get_all_records()
                if (not category or r["category"] == category)
                and (not sdt_id or r["metadata"].get("sdt_id") == sdt_id)
                and (not label or r["label"] == label)]

    @app.get("/api/SDTM/performance", tags=["Performance Monitoring"])
    def records(category: str = None, sdt_id: str = None, label: str = None,
                limit: int = Query(default=10000, ge=1, le=100000)):
        items = filtered(category, sdt_id, label)
        return {"count": len(items), "records": items[:limit],
                "returned_count": min(len(items), limit),
                "archive_errors": tracker.archive_errors,
                "evicted_records": tracker.evicted_records}

    @app.get("/api/SDTM/performance/summary", tags=["Performance Monitoring"])
    def summary():
        return tracker.get_summary()

    # Static routes must precede the record-id route.
    @app.get("/api/SDTM/performance/export", tags=["Performance Monitoring"])
    def export(category: str = None, sdt_id: str = None, label: str = None):
        return Response(tracker.to_csv(filtered(category, sdt_id, label)),
                        media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="performance.csv"'})

    @app.get("/api/SDTM/performance/{record_id}", tags=["Performance Monitoring"])
    def record(record_id: str):
        item = tracker.get_record(record_id)
        if item is None:
            raise HTTPException(404, detail="Performance record not found")
        return item

    @app.delete("/api/SDTM/performance", tags=["Performance Monitoring"])
    def clear():
        tracker.clear()
        return {"message": "Completed in-memory records cleared; archive and active events retained"}
