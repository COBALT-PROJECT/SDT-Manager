"""Thread-safe timestamps, monotonic durations, and a persistent completed-event archive."""
import contextvars
import csv
import io
import json
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

LOGGER = logging.getLogger(__name__)
CURRENT_TRACKER = contextvars.ContextVar("active_performance_tracker", default=None)


class EventCategory(str, Enum):
    COMPONENT_INSTANTIATION = "component_instantiation"
    API_ENDPOINT = "api_endpoint"
    AUTH_TOKEN_ACQUISITION = "auth_token_acquisition"
    TOKEN_DISTRIBUTION = "token_distribution"
    DEPLOYMENT = "deployment"
    DELETION = "deletion"
    ADAPTER = "adapter"
    TEMPLATE_DELIVERY = "template_delivery"
    CREDENTIAL_STORE = "credential_store"
    MQTT_REPORTING = "mqtt_reporting"
    KUBERNETES = "kubernetes"
    LIFECYCLE = "lifecycle"
    HTTP_CLIENT = "http_client"


class PerformanceTracker:
    """Keep active events and the latest completed events; archive every completion.

    Durations use perf_counter so wall-clock corrections do not distort measurements.
    JSONL is append-only across restarts. The query API covers this process's retained
    records. The archive is intentionally not erased by clear().
    """

    def __init__(self, output_path=None, max_records=None):
        self.output_path = output_path if output_path is not None else os.getenv(
            "PERFORMANCE_LOG_PATH", "performance_events.jsonl"
        )
        self.max_records = max(1, int(
            max_records if max_records is not None else
            os.getenv("PERFORMANCE_MAX_RECORDS", "10000")
        ))
        self._active = {}
        self._completed = OrderedDict()
        self._lock = threading.RLock()
        self._current = contextvars.ContextVar("performance_event", default=None)
        self.archive_errors = 0
        self.evicted_records = 0
        if self.output_path:
            Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

    def start_timer(self, category, label, metadata=None):
        record_id = uuid.uuid4().hex
        now = time.time()
        parent = self._current.get()
        with self._lock:
            parent_record = self._lookup(parent)
            inherited = {}
            if parent_record:
                inherited = {
                    key: value for key, value in parent_record["metadata"].items()
                    if key in {"sdt_id", "connector_id"}
                }
            inherited.update(metadata or {})
            record = {
                "record_id": record_id,
                "parent_record_id": parent,
                "trace_id": parent_record["trace_id"] if parent_record else record_id,
                "category": category.value if isinstance(category, EventCategory) else category,
                "label": label,
                "started_at_iso": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "started_at_epoch": now,
                "ended_at_iso": None,
                "ended_at_epoch": None,
                "duration_seconds": None,
                "status": "in_progress",
                "metadata": inherited,
                "_started_monotonic": time.perf_counter(),
                "_child_failed": False,
            }
            self._active[record_id] = record
        return record_id

    def _lookup(self, record_id):
        return self._active.get(record_id) or self._completed.get(record_id)

    @staticmethod
    def _public(record):
        return deepcopy({k: v for k, v in record.items() if not k.startswith("_")})

    def annotate_current(self, **metadata):
        with self._lock:
            record = self._active.get(self._current.get())
            if record:
                record["metadata"].update(metadata)

    def mark_current_failed(self):
        with self._lock:
            record = self._active.get(self._current.get())
            if record:
                record["_child_failed"] = True

    def stop_timer(self, record_id, status="completed", extra_metadata=None):
        now, monotonic = time.time(), time.perf_counter()
        with self._lock:
            record = self._active.pop(record_id, None)
            if record is None:
                old = self._completed.get(record_id)
                return old["duration_seconds"] if old else None
            record.update(
                ended_at_iso=datetime.fromtimestamp(now, timezone.utc).isoformat(),
                ended_at_epoch=now,
                duration_seconds=round(max(0, monotonic - record["_started_monotonic"]), 9),
                status=status,
            )
            if extra_metadata:
                record["metadata"].update(extra_metadata)
            # A recovered retry can complete successfully while retaining its failed
            # child count. Business methods that swallow failures are marked below.
            if record["_child_failed"] and status == "completed":
                record["status"] = "partial_failure"
            if record["status"] in {"failed", "partial_failure", "cancelled"}:
                parent = self._active.get(record["parent_record_id"])
                if parent:
                    parent["_child_failed"] = True
            self._completed[record_id] = record
            while len(self._completed) > self.max_records:
                self._completed.popitem(last=False)
                self.evicted_records += 1
            public = self._public(record)
            if self.output_path:
                try:
                    with open(self.output_path, "a", encoding="utf-8") as archive:
                        archive.write(json.dumps(public, ensure_ascii=False) + "\n")
                except OSError:
                    self.archive_errors += 1
                    LOGGER.exception("Cannot append performance event to %s", self.output_path)
        LOGGER.info("[PERF] %s | %s => %.6fs [%s]",
                    record["category"], record["label"],
                    record["duration_seconds"], record["status"])
        return record["duration_seconds"]

    @contextmanager
    def track(self, category, label, metadata=None):
        record_id = self.start_timer(category, label, metadata)
        token = self._current.set(record_id)
        tracker_token = CURRENT_TRACKER.set(self)
        span = TimingSpan(self, record_id)
        try:
            yield span
        except BaseException as exc:
            span.status = "cancelled" if not isinstance(exc, Exception) else "failed"
            # Exception messages may contain tokens, payloads, or URLs with secrets.
            span.metadata["exception_type"] = type(exc).__name__
            raise
        finally:
            span.duration = self.stop_timer(record_id, span.status, span.metadata)
            self._current.reset(token)
            CURRENT_TRACKER.reset(tracker_token)

    def get_all_records(self):
        with self._lock:
            records = [self._public(r) for r in
                       (*self._completed.values(), *self._active.values())]
        return sorted(records, key=lambda r: r["started_at_epoch"], reverse=True)

    def get_records_by_category(self, category):
        value = category.value if isinstance(category, EventCategory) else category
        return [r for r in self.get_all_records() if r["category"] == value]

    def get_records_by_sdt_id(self, sdt_id):
        return [r for r in self.get_all_records() if r["metadata"].get("sdt_id") == sdt_id]

    def get_record(self, record_id):
        with self._lock:
            record = self._lookup(record_id)
            return self._public(record) if record else None

    def get_summary(self):
        summary = {}
        records = self.get_all_records()
        for category in EventCategory:
            group = [r for r in records if r["category"] == category.value
                     and r["duration_seconds"] is not None]
            durations = [r["duration_seconds"] for r in group]
            summary[category.value] = {
                "count": len(group),
                "total_seconds": round(sum(durations), 9),
                "avg_seconds": round(sum(durations) / len(group), 9) if group else 0,
                "min_seconds": min(durations, default=0),
                "max_seconds": max(durations, default=0),
                "failed_count": sum(r["status"] in {"failed", "partial_failure", "cancelled"}
                                    for r in group),
            }
        return summary

    def clear(self):
        """Clear completed records in memory, retaining in-flight events and archive."""
        with self._lock:
            self._completed.clear()
            self.evicted_records = 0

    @staticmethod
    def to_csv(records):
        output = io.StringIO(newline="")
        fields = ["record_id", "parent_record_id", "trace_id", "category", "label",
                  "started_at_iso", "ended_at_iso", "started_at_epoch", "ended_at_epoch",
                  "duration_seconds", "status", "metadata"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = dict(record, metadata=json.dumps(record["metadata"], sort_keys=True))
            # Prevent spreadsheet formula execution when labels contain user input.
            writer.writerow({k: "'" + v if isinstance(v, str) and
                             v.startswith(("=", "+", "-", "@")) else v
                             for k, v in row.items()})
        return output.getvalue()


class TimingSpan:
    def __init__(self, tracker, record_id):
        self.tracker = tracker
        self.record_id = record_id
        self.status = "completed"
        self.metadata = {}
        self.duration = None
