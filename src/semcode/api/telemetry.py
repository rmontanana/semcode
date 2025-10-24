"""
Lightweight in-memory telemetry collectors for the FastAPI layer.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Literal, Optional, TypedDict


@dataclass
class TelemetryEvent:
    kind: Literal["ingest", "query"]
    ok: bool
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class IngestStats:
    count: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0
    last_timestamp: Optional[float] = None

    def average_duration_ms(self) -> float:
        return self.total_duration_ms / self.count if self.count else 0.0


@dataclass
class QueryStats(IngestStats):
    fallbacks: int = 0


class RecentEvent(TypedDict):
    kind: Literal["ingest", "query"]
    ok: bool
    duration_ms: float
    metadata: Dict[str, Any]
    timestamp: float


class IngestSnapshot(TypedDict):
    count: int
    failures: int
    total_duration_ms: float
    last_timestamp: Optional[float]
    average_duration_ms: float


class QuerySnapshot(IngestSnapshot):
    fallbacks: int


class TelemetrySnapshot(TypedDict):
    ingest: IngestSnapshot
    query: QuerySnapshot
    recent_events: List[RecentEvent]


class Telemetry:
    """In-memory stats tracker exposed via the `/telemetry` endpoint."""

    def __init__(self, history_size: int = 50) -> None:
        self._lock = threading.Lock()
        self._history: Deque[TelemetryEvent] = deque(maxlen=history_size)
        self._ingest = IngestStats()
        self._query = QueryStats()

    def record_ingest(
        self, duration_ms: float, ok: bool, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        metadata = dict(metadata or {})
        event = TelemetryEvent(
            kind="ingest", ok=ok, duration_ms=duration_ms, metadata=metadata
        )
        with self._lock:
            self._history.appendleft(event)
            self._ingest.count += 1
            self._ingest.total_duration_ms += duration_ms
            self._ingest.last_timestamp = event.timestamp
            if not ok:
                self._ingest.failures += 1

    def record_query(
        self, duration_ms: float, ok: bool, used_fallback: bool = False
    ) -> None:
        metadata: Dict[str, Any] = {"fallback_used": used_fallback}
        event = TelemetryEvent(
            kind="query", ok=ok, duration_ms=duration_ms, metadata=metadata
        )
        with self._lock:
            self._history.appendleft(event)
            self._query.count += 1
            self._query.total_duration_ms += duration_ms
            self._query.last_timestamp = event.timestamp
            if not ok:
                self._query.failures += 1
            if used_fallback:
                self._query.fallbacks += 1

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            ingest_avg = self._ingest.average_duration_ms()
            query_avg = self._query.average_duration_ms()
            history: List[RecentEvent] = [
                {
                    "kind": event.kind,
                    "ok": event.ok,
                    "duration_ms": event.duration_ms,
                    "metadata": dict(event.metadata),
                    "timestamp": event.timestamp,
                }
                for event in list(self._history)
            ]
        return {
            "ingest": {
                "count": self._ingest.count,
                "failures": self._ingest.failures,
                "total_duration_ms": self._ingest.total_duration_ms,
                "last_timestamp": self._ingest.last_timestamp,
                "average_duration_ms": ingest_avg,
            },
            "query": {
                "count": self._query.count,
                "failures": self._query.failures,
                "fallbacks": self._query.fallbacks,
                "total_duration_ms": self._query.total_duration_ms,
                "last_timestamp": self._query.last_timestamp,
                "average_duration_ms": query_avg,
            },
            "recent_events": history,
        }
