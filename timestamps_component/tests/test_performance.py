import asyncio
import contextvars
import csv
import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

import sdt_performance_tracker as timing
from performance_instrumentation import (
    PerformanceTimingMiddleware, instrument_component,
)
from performance_http import requests, original_requests
from sdt_performance_tracker import EventCategory as C, PerformanceTracker


def test_monotonic_duration_survives_wall_clock_change(monkeypatch):
    tracker = PerformanceTracker(output_path="")
    monkeypatch.setattr(timing.time, "time", Mock(side_effect=[100, 90]))
    monkeypatch.setattr(timing.time, "perf_counter", Mock(side_effect=[10, 12.5]))
    rid = tracker.start_timer(C.DEPLOYMENT, "deploy")
    assert tracker.stop_timer(rid) == 2.5
    assert tracker.get_record(rid)["ended_at_epoch"] < tracker.get_record(rid)["started_at_epoch"]


def test_nested_failures_and_background_context(tmp_path):
    tracker = PerformanceTracker(output_path=str(tmp_path / "events.jsonl"))
    with tracker.track(C.DEPLOYMENT, "root", {"sdt_id": "twin-1"}) as parent:
        context = contextvars.copy_context()
        def background():
            with tracker.track(C.AUTH_TOKEN_ACQUISITION, "auth"):
                raise ValueError("must-not-appear-secret")
        with ThreadPoolExecutor(1) as pool:
            with pytest.raises(ValueError):
                pool.submit(context.run, background).result()
    records = tracker.get_all_records()
    child = next(r for r in records if r["label"] == "auth")
    assert child["parent_record_id"] == parent.record_id
    assert child["trace_id"] == parent.record_id
    assert child["metadata"]["sdt_id"] == "twin-1"
    assert child["status"] == "failed"
    assert tracker.get_record(parent.record_id)["status"] == "partial_failure"
    assert "must-not-appear-secret" not in (tmp_path / "events.jsonl").read_text()


def test_concurrency_retention_and_clear_keep_full_archive(tmp_path):
    path = tmp_path / "events.jsonl"
    tracker = PerformanceTracker(output_path=str(path), max_records=5)
    active = tracker.start_timer(C.LIFECYCLE, "in-flight")
    def run(i):
        with tracker.track(C.KUBERNETES, f"event-{i}"):
            pass
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(run, range(80)))
    assert len(tracker.get_all_records()) == 6
    assert tracker.evicted_records == 75
    tracker.clear()
    assert tracker.get_record(active)["status"] == "in_progress"
    tracker.stop_timer(active)
    tracker.stop_timer(active)  # Idempotent completion must not duplicate the archive.
    archived = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(archived) == 81
    assert len({r["record_id"] for r in archived}) == 81


def test_archive_failure_does_not_break_business_operation(tmp_path):
    tracker = PerformanceTracker(output_path=str(tmp_path))  # A directory cannot be appended.
    with tracker.track(C.LIFECYCLE, "operation"):
        pass
    assert tracker.archive_errors == 1
    assert tracker.get_all_records()[0]["status"] == "completed"


def test_wrappers_preserve_results_and_recognize_swallowed_failure():
    class Component:
        def run_command(self, command):
            return None
        def deploy(self, sdt_id, access_token):
            self.run_command("secret command")
            return None, None
    tracker = PerformanceTracker(output_path="")
    component = instrument_component(Component(), tracker, C.LIFECYCLE)
    assert component.deploy("twin-1", "secret-token") == (None, None)
    records = tracker.get_all_records()
    assert len(records) == 2
    assert all(r["status"] == "failed" for r in records)
    assert all(r["metadata"]["sdt_id"] == "twin-1" for r in records)
    assert "secret" not in json.dumps(records)


@pytest.mark.parametrize("status", [200, 400, 503])
def test_http_status_and_streamed_response_are_recorded(status):
    tracker = PerformanceTracker(output_path="")
    messages = []
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status})
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        assert tracker.get_all_records()[0]["status"] == "in_progress"
        await send({"type": "http.response.body", "body": b"last"})
    async def send(message):
        messages.append(message)
    asyncio.run(PerformanceTimingMiddleware(app, tracker)(
        {"type": "http", "method": "POST", "path": "/test", "query_string": b"token=secret"},
        None, send,
    ))
    record = tracker.get_all_records()[0]
    assert record["status"] == ("failed" if status >= 400 else "completed")
    assert record["metadata"]["http_status"] == status
    assert len(messages) == 3
    assert "secret" not in json.dumps(record)


def test_outgoing_http_records_attempts_without_credentials(monkeypatch):
    tracker = PerformanceTracker(output_path="")
    response = Mock(status_code=401)
    monkeypatch.setattr(original_requests, "post", Mock(return_value=response))
    with tracker.track(C.AUTH_TOKEN_ACQUISITION, "auth"):
        assert requests.post("https://user:secret@example.test/token?key=secret",
                             json={"password": "secret"}) is response
    event = next(r for r in tracker.get_all_records() if r["category"] == "http_client")
    assert event["status"] == "failed"
    assert event["metadata"]["host"] == "example.test"
    assert "secret" not in json.dumps(tracker.get_all_records())


def test_csv_contains_timestamps_and_escaped_labels():
    tracker = PerformanceTracker(output_path="")
    with tracker.track(C.ADAPTER, "=formula"):
        pass
    rows = list(csv.DictReader(io.StringIO(tracker.to_csv(tracker.get_all_records()))))
    assert rows[0]["label"] == "'=formula"
    assert rows[0]["started_at_iso"] and rows[0]["ended_at_iso"]
    assert float(rows[0]["duration_seconds"]) >= 0


def test_mqtt_retries_are_individually_timed_and_keep_qos_and_redaction():
    from mqtt_failure_reporter import MQTTFailureReporter
    attempts = []
    def publish(**kwargs):
        attempts.append(kwargs)
        if len(attempts) < 3:
            raise OSError("temporary failure")
    tracker = PerformanceTracker(output_path="")
    reporter = MQTTFailureReporter(hostname="test", port=1883, enabled=False,
                                   publisher=publish, retry_delay=0, max_retries=3)
    instrument_component(reporter, tracker, C.MQTT_REPORTING)
    reporter.enabled = True
    reporter._worker = threading.Thread(target=reporter._worker_loop, daemon=True)
    reporter._worker.start()
    try:
        event_id = reporter.report_failure("test", "failure", details={"access_token": "secret"})
        reporter._queue.join()
    finally:
        reporter.stop()
    records = [r for r in tracker.get_all_records() if r["label"].endswith("._publish")]
    assert len(records) == 3
    assert sum(r["status"] == "failed" for r in records) == 2
    assert {r["metadata"]["mqtt_event_id"] for r in records} == {event_id}
    assert all(a["qos"] == 1 and not a["retain"] for a in attempts)
    assert all(json.loads(a["payload"])["details"]["access_token"] == "<redacted>" for a in attempts)
