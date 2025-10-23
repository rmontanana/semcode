"""
Lightweight in-memory telemetry collectors for the FastAPI layer.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Literal, Optional


@dataclass
class TelemetryEvent:
    kind: Literal["ingest", "query"]
    ok: bool
    duration_ms: float
    metadata: Dict[str, object] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class Telemetry:
    """In-memory stats tracker exposed via the `/telemetry` endpoint."""

    def __init__(self, history_size: int = 50) -> None:
        self._lock = threading.Lock()
        self._history: Deque[TelemetryEvent] = deque(maxlen=history_size)
        self._ingest = {
            "count": 0,
            "failures": 0,
            "total_duration_ms": 0.0,
            "last_timestamp": None,
        }
        self._query = {
            "count": 0,
            "failures": 0,
            "fallbacks": 0,
            "total_duration_ms": 0.0,
            "last_timestamp": None,
        }

    def record_ingest(
        self, duration_ms: float, ok: bool, metadata: Optional[Dict[str, object]] = None
    ) -> None:
        metadata = metadata or {}
        event = TelemetryEvent(
            kind="ingest", ok=ok, duration_ms=duration_ms, metadata=metadata
        )
        with self._lock:
            self._history.appendleft(event)
            self._ingest["count"] += 1
            self._ingest["total_duration_ms"] += duration_ms
            self._ingest["last_timestamp"] = event.timestamp
            if not ok:
                self._ingest["failures"] += 1

    def record_query(
        self, duration_ms: float, ok: bool, used_fallback: bool = False
    ) -> None:
        metadata = {"fallback_used": used_fallback}
        event = TelemetryEvent(
            kind="query", ok=ok, duration_ms=duration_ms, metadata=metadata
        )
        with self._lock:
            self._history.appendleft(event)
            self._query["count"] += 1
            self._query["total_duration_ms"] += duration_ms
            self._query["last_timestamp"] = event.timestamp
            if not ok:
                self._query["failures"] += 1
            if used_fallback:
                self._query["fallbacks"] += 1

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            ingest_avg = (
                self._ingest["total_duration_ms"] / self._ingest["count"]
                if self._ingest["count"]
                else 0.0
            )
            query_avg = (
                self._query["total_duration_ms"] / self._query["count"]
                if self._query["count"]
                else 0.0
            )
            history = [
                {
                    "kind": event.kind,
                    "ok": event.ok,
                    "duration_ms": event.duration_ms,
                    "metadata": event.metadata,
                    "timestamp": event.timestamp,
                }
                for event in list(self._history)
            ]
        return {
            "ingest": {
                **self._ingest,
                "average_duration_ms": ingest_avg,
            },
            "query": {
                **self._query,
                "average_duration_ms": query_avg,
            },
            "recent_events": history,
        }
