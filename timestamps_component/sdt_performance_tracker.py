# File: sdt_performance_tracker.py
"""
SDT Performance Tracker
------------------------
Centralized performance timing module for the SDT Manager.

Tracks four categories of events:
  1. Component instantiation    — time to create SDT, IDS-SDT, Watchtower, etc.
  2. API endpoint calls         — request-to-response time for every HTTP endpoint
  3. Auth token acquisition     — time to register + poll + fetch OAuth2 token
  4. Token distribution         — time to send the token to each component

All records are stored in-memory (thread-safe) and exposed via query methods
that the API layer can surface through REST endpoints.
"""

import time
import threading
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

LOGGER = logging.getLogger(__name__)


class EventCategory(str, Enum):
    COMPONENT_INSTANTIATION = "component_instantiation"
    API_ENDPOINT = "api_endpoint"
    AUTH_TOKEN_ACQUISITION = "auth_token_acquisition"
    TOKEN_DISTRIBUTION = "token_distribution"


@dataclass
class TimingRecord:
    """A single performance timing record."""
    record_id: str
    category: str
    label: str                          # e.g. "SDT_LifeCycleManager", "POST /api/SDTM/digital-twin"
    started_at_iso: str                 # ISO-8601 timestamp
    started_at_epoch: float             # Unix epoch (high-res)
    ended_at_iso: Optional[str] = None
    ended_at_epoch: Optional[float] = None
    duration_seconds: Optional[float] = None
    status: str = "in_progress"         # in_progress | completed | failed
    metadata: Dict = field(default_factory=dict)   # free-form context (sdt_id, endpoint, etc.)


class PerformanceTracker:
    """Thread-safe performance tracker for the SDT Manager ecosystem."""

    def __init__(self):
        self._records: Dict[str, TimingRecord] = {}
        self._lock = threading.Lock()
        LOGGER.info("PerformanceTracker initialized")

    # ------------------------------------------------------------------
    # Core timing API
    # ------------------------------------------------------------------

    def start_timer(
        self,
        category: EventCategory,
        label: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Begin tracking a timed event.

        Args:
            category: One of the EventCategory values.
            label:    Human-readable description (method name, endpoint, etc.)
            metadata: Optional dict with extra context (sdt_id, component, …).

        Returns:
            A unique record_id used to stop the timer later.
        """
        record_id = uuid.uuid4().hex[:12]
        now = time.time()
        record = TimingRecord(
            record_id=record_id,
            category=category.value,
            label=label,
            started_at_iso=datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            started_at_epoch=now,
            metadata=metadata or {},
        )
        with self._lock:
            self._records[record_id] = record

        LOGGER.debug(f"[PERF] Timer started: {category.value} | {label} (id={record_id})")
        return record_id

    def stop_timer(
        self,
        record_id: str,
        status: str = "completed",
        extra_metadata: Optional[Dict] = None,
    ) -> Optional[float]:
        """
        Stop a running timer and compute the elapsed duration.

        Args:
            record_id:      The id returned by start_timer().
            status:         Final status — 'completed' or 'failed'.
            extra_metadata: Additional metadata to merge into the record.

        Returns:
            Duration in seconds, or None if record_id was not found.
        """
        now = time.time()
        with self._lock:
            record = self._records.get(record_id)
            if not record:
                LOGGER.warning(f"[PERF] Unknown record_id: {record_id}")
                return None

            record.ended_at_epoch = now
            record.ended_at_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
            record.duration_seconds = round(now - record.started_at_epoch, 6)
            record.status = status
            if extra_metadata:
                record.metadata.update(extra_metadata)

        LOGGER.info(
            f"[PERF] {record.category} | {record.label} "
            f"=> {record.duration_seconds:.4f}s [{status}]"
        )
        return record.duration_seconds

    # ------------------------------------------------------------------
    # Convenience context manager
    # ------------------------------------------------------------------

    class _TimerContext:
        """Context manager returned by PerformanceTracker.track()."""

        def __init__(self, tracker: "PerformanceTracker", record_id: str):
            self._tracker = tracker
            self.record_id = record_id
            self.duration: Optional[float] = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            status = "failed" if exc_type else "completed"
            extra = {}
            if exc_type:
                extra["error"] = str(exc_val)
            self.duration = self._tracker.stop_timer(self.record_id, status, extra)
            return False  # Do not suppress exceptions

    def track(
        self,
        category: EventCategory,
        label: str,
        metadata: Optional[Dict] = None,
    ) -> _TimerContext:
        """
        Context-manager shortcut for timing a block of code.

        Usage::

            with tracker.track(EventCategory.API_ENDPOINT, "POST /deploy") as t:
                do_work()
            print(t.duration)
        """
        rid = self.start_timer(category, label, metadata)
        return self._TimerContext(self, rid)

    # ------------------------------------------------------------------
    # Query API — used by the REST layer
    # ------------------------------------------------------------------

    def get_all_records(self) -> List[Dict]:
        """Return all timing records as a list of dicts (newest first)."""
        with self._lock:
            records = [asdict(r) for r in self._records.values()]
        records.sort(key=lambda r: r["started_at_epoch"], reverse=True)
        return records

    def get_records_by_category(self, category: EventCategory) -> List[Dict]:
        """Return timing records filtered by category (newest first)."""
        with self._lock:
            records = [
                asdict(r) for r in self._records.values()
                if r.category == category.value
            ]
        records.sort(key=lambda r: r["started_at_epoch"], reverse=True)
        return records

    def get_records_by_sdt_id(self, sdt_id: str) -> List[Dict]:
        """Return timing records where metadata contains the given sdt_id."""
        with self._lock:
            records = [
                asdict(r) for r in self._records.values()
                if r.metadata.get("sdt_id") == sdt_id
            ]
        records.sort(key=lambda r: r["started_at_epoch"], reverse=True)
        return records

    def get_record(self, record_id: str) -> Optional[Dict]:
        """Return a single timing record by its id."""
        with self._lock:
            r = self._records.get(record_id)
            return asdict(r) if r else None

    def get_summary(self) -> Dict:
        """
        Return an aggregate summary grouped by category:
          - count, avg, min, max duration for each category
        """
        with self._lock:
            records = list(self._records.values())

        buckets: Dict[str, List[float]] = {}
        for r in records:
            if r.duration_seconds is not None:
                buckets.setdefault(r.category, []).append(r.duration_seconds)

        summary = {}
        for cat, durations in buckets.items():
            summary[cat] = {
                "count": len(durations),
                "total_seconds": round(sum(durations), 6),
                "avg_seconds": round(sum(durations) / len(durations), 6),
                "min_seconds": round(min(durations), 6),
                "max_seconds": round(max(durations), 6),
            }

        # Include categories with zero completed records
        for cat in EventCategory:
            if cat.value not in summary:
                summary[cat.value] = {
                    "count": 0,
                    "total_seconds": 0,
                    "avg_seconds": 0,
                    "min_seconds": 0,
                    "max_seconds": 0,
                }

        return summary

    def clear(self):
        """Clear all stored timing records."""
        with self._lock:
            self._records.clear()
        LOGGER.info("[PERF] All timing records cleared")