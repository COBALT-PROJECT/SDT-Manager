import asyncio
import json
import sys
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parents[2] / "SDT-Manager"
sys.path.insert(0, str(SOURCE_DIR))

from mqtt_failure_reporter import (  # noqa: E402
    MQTTFailureReporter,
    MQTTFailureReportingMiddleware,
)


def test_http_failure_is_reported_with_qos_one_and_redaction():
    attempts = []

    def publisher(**kwargs):
        attempts.append(kwargs)

    reporter = MQTTFailureReporter(
        hostname="test-broker",
        component_id="sdt-manager-test",
        port=1883,
        retry_delay=0,
        publisher=publisher,
    )

    async def endpoint(scope, receive, send):
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({
            "type": "http.response.body",
            "body": b'{"detail":"bad credentials","access_token":"do-not-publish"}',
        })

    async def invoke():
        async def send(_message):
            return None

        middleware = MQTTFailureReportingMiddleware(endpoint, reporter)
        await middleware(
            {"type": "http", "method": "POST", "path": "/test"},
            lambda: None,
            send,
        )

    try:
        asyncio.run(invoke())
        reporter._queue.join()
    finally:
        reporter.stop()

    assert len(attempts) == 1
    assert attempts[0]["topic"] == "components/sdt-manager-test/reports"
    assert attempts[0]["qos"] == 1
    assert attempts[0]["retain"] is False

    payload = json.loads(attempts[0]["payload"])
    assert payload["state"] == "failed"
    assert payload["details"]["error_category"] == "authentication_error"
    assert payload["details"]["response"]["access_token"] == "<redacted>"


def test_publish_is_retried_with_the_same_event_id():
    attempts = []

    def flaky_publisher(**kwargs):
        attempts.append(kwargs)
        if len(attempts) < 3:
            raise OSError("temporary broker failure")

    reporter = MQTTFailureReporter(
        hostname="test-broker",
        port=1883,
        publisher=flaky_publisher,
        max_retries=3,
        retry_delay=0,
    )

    try:
        event_id = reporter.report_failure("Test operation", "Test failure")
        reporter._queue.join()
    finally:
        reporter.stop()

    assert len(attempts) == 3
    assert {json.loads(attempt["payload"])["event_id"] for attempt in attempts} == {
        event_id
    }
