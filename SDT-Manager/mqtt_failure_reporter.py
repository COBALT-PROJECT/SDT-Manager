"""Best-effort MQTT failure reporting for the SDT Manager.

The reporter uses a bounded background queue so API responses never wait for
the MQTT broker.  Reporting failures are logged locally and are deliberately
not raised back into the operation that produced the original error.
"""

import json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any, Callable, Dict, Optional

from dotenv import load_dotenv


LOGGER = logging.getLogger(__name__)

MAX_OPERATION_LENGTH = 120
MAX_MESSAGE_LENGTH = 500
MAX_DETAILS_BYTES = 16 * 1024
MAX_CAPTURED_RESPONSE_BYTES = 8 * 1024

_SENSITIVE_KEY_PARTS = (
    "access_token",
    "authorization",
    "client_secret",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _redact(value: Any) -> Any:
    """Recursively redact credential-like values before reporting them."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "<redacted>"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _bounded_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    safe_details = _redact(details or {})
    encoded = json.dumps(safe_details, default=str, ensure_ascii=False).encode("utf-8")
    if len(encoded) <= MAX_DETAILS_BYTES:
        return safe_details

    # Never exceed the protocol's 16 KiB details limit.
    return {
        "truncated": True,
        "original_size_bytes": len(encoded),
    }


class MQTTFailureReporter:
    """Publish failure and recovery events to the configured MQTT broker."""

    def __init__(
        self,
        hostname: str,
        port: int,
        component_id: str = "sdt-manager-01",
        enabled: bool = True,
        queue_size: int = 1000,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        publisher: Optional[Callable[..., Any]] = None,
    ):
        self.hostname = hostname
        self.port = port
        self.component_id = component_id
        self.enabled = enabled
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0.0, retry_delay)
        self.topic = f"components/{component_id}/reports"
        self._publisher = publisher
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        if self.enabled:
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="mqtt-failure-reporter",
                daemon=True,
            )
            self._worker.start()
            LOGGER.info(
                "MQTT failure reporter enabled (broker=%s:%s, topic=%s)",
                self.hostname,
                self.port,
                self.topic,
            )
        else:
            LOGGER.info("MQTT failure reporter disabled")

    @classmethod
    def from_env(cls) -> "MQTTFailureReporter":
        load_dotenv(
            os.path.join(os.path.dirname(__file__), ".env"),
            override=False,
        )
        return cls(
            hostname=os.environ["MQTT_FAILURE_HOST"],
            port=int(os.environ["MQTT_FAILURE_PORT"]),
            component_id=os.environ.get("MQTT_COMPONENT_ID", "sdt-manager-01"),
            enabled=_env_bool("MQTT_FAILURE_REPORTING_ENABLED", True),
            queue_size=int(os.environ.get("MQTT_FAILURE_QUEUE_SIZE", "1000")),
            max_retries=int(os.environ.get("MQTT_FAILURE_MAX_RETRIES", "3")),
            retry_delay=float(os.environ.get("MQTT_FAILURE_RETRY_DELAY", "2")),
        )

    def report_failure(
        self,
        operation: str,
        message: str,
        severity: str = "critical",
        details: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> str:
        severity = severity if severity in {"warning", "critical"} else "critical"
        payload = {
            "event_id": event_id or str(uuid.uuid4()),
            "state": "failed",
            "severity": severity,
            "operation": _truncate(operation, MAX_OPERATION_LENGTH),
            "message": _truncate(message, MAX_MESSAGE_LENGTH),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "details": _bounded_details(details),
        }
        self._enqueue(payload)
        return payload["event_id"]

    def report_recovered(
        self,
        operation: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> str:
        payload = {
            "event_id": event_id or str(uuid.uuid4()),
            "state": "recovered",
            "operation": _truncate(operation, MAX_OPERATION_LENGTH),
            "message": _truncate(message, MAX_MESSAGE_LENGTH),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "details": _bounded_details(details),
        }
        self._enqueue(payload)
        return payload["event_id"]

    def _enqueue(self, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            LOGGER.error("MQTT failure report queue is full; dropping event %s", payload["event_id"])

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            for attempt in range(1, self.max_retries + 1):
                try:
                    self._publish(payload)
                    break
                except Exception as exc:  # Reporting must never break the API path.
                    if attempt >= self.max_retries:
                        LOGGER.error(
                            "Unable to publish MQTT failure report %s after %s attempts: %s",
                            payload.get("event_id"),
                            attempt,
                            exc,
                        )
                        break
                    delay = self.retry_delay * attempt
                    LOGGER.warning(
                        "MQTT publish attempt %s/%s failed for event %s: %s; retrying in %.1fs",
                        attempt,
                        self.max_retries,
                        payload.get("event_id"),
                        exc,
                        delay,
                    )
                    time.sleep(delay)
            self._queue.task_done()

    def _publish(self, payload: Dict[str, Any]) -> None:
        publisher = self._publisher
        if publisher is None:
            from paho.mqtt import publish

            publisher = publish.single

        publisher(
            topic=self.topic,
            payload=json.dumps(payload, ensure_ascii=False),
            hostname=self.hostname,
            port=self.port,
            qos=1,
            retain=False,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Allow queued events a short opportunity to publish during shutdown."""
        if not self.enabled or self._worker is None:
            return
        self._stop_event.set()
        self._worker.join(timeout=timeout)


class MQTTFailureReportingMiddleware:
    """ASGI middleware that reports all HTTP 4xx/5xx responses and crashes."""

    def __init__(self, app, reporter: MQTTFailureReporter):
        self.app = app
        self.reporter = reporter

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        response_body = bytearray()
        report_sent = False

        async def send_wrapper(message):
            nonlocal status_code, report_sent

            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                remaining = MAX_CAPTURED_RESPONSE_BYTES - len(response_body)
                if remaining > 0:
                    response_body.extend(body[:remaining])

            await send(message)

            if (
                message["type"] == "http.response.body"
                and not message.get("more_body", False)
                and status_code >= 400
                and not report_sent
            ):
                report_sent = True
                self._report_http_failure(scope, status_code, bytes(response_body))

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if not report_sent:
                report_sent = True
                operation = self._operation(scope)
                self.reporter.report_failure(
                    operation=operation,
                    message=_truncate(exc, MAX_MESSAGE_LENGTH) or "Unhandled endpoint exception",
                    severity="critical",
                    details={
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "error_category": self._exception_category(exc),
                        "exception_type": type(exc).__name__,
                    },
                )
            raise

    def _report_http_failure(self, scope, status_code: int, body: bytes) -> None:
        response_data = self._decode_response(body)
        message = self._response_message(response_data, status_code)
        self.reporter.report_failure(
            operation=self._operation(scope),
            message=message,
            severity=self._severity(status_code),
            details={
                "method": scope.get("method"),
                "path": scope.get("path"),
                "status_code": status_code,
                "error_category": self._status_category(status_code),
                "response": response_data,
            },
        )

    @staticmethod
    def _operation(scope) -> str:
        route = scope.get("route")
        route_path = getattr(route, "path", None) or scope.get("path", "unknown")
        return f"{scope.get('method', 'HTTP')} {route_path}"

    @staticmethod
    def _decode_response(body: bytes) -> Any:
        if not body:
            return None
        text = body.decode("utf-8", errors="replace")
        try:
            return _redact(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            return _truncate(text, MAX_MESSAGE_LENGTH)

    @staticmethod
    def _response_message(response_data: Any, status_code: int) -> str:
        if isinstance(response_data, dict):
            for key in ("detail", "error", "message"):
                value = response_data.get(key)
                if value:
                    if isinstance(value, (dict, list)):
                        return _truncate(json.dumps(value, default=str), MAX_MESSAGE_LENGTH)
                    return _truncate(value, MAX_MESSAGE_LENGTH)
        try:
            return f"HTTP {status_code} {HTTPStatus(status_code).phrase}"
        except ValueError:
            return f"HTTP {status_code} error"

    @staticmethod
    def _severity(status_code: int) -> str:
        return "critical" if status_code >= 500 or status_code in {401, 403} else "warning"

    @staticmethod
    def _status_category(status_code: int) -> str:
        return {
            400: "bad_request_or_string_mismatch",
            401: "authentication_error",
            403: "authorization_error",
            404: "not_found",
            408: "timeout",
            409: "conflict",
            422: "validation_error",
            429: "rate_limited",
            502: "dependency_error",
            503: "not_reachable",
            504: "timeout",
        }.get(status_code, "server_error" if status_code >= 500 else "client_error")

    @staticmethod
    def _exception_category(exc: Exception) -> str:
        name = type(exc).__name__.lower()
        message = str(exc).lower()
        if "timeout" in name or "timeout" in message:
            return "timeout"
        if "connection" in name or "unreachable" in message:
            return "not_reachable"
        if "auth" in name or "unauthorized" in message:
            return "authentication_or_authorization_error"
        if isinstance(exc, (KeyError, ValueError, TypeError)):
            return "invalid_data_or_string_mismatch"
        return "unhandled_exception"
