from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict
from typing import Any


_EXCEPTION_ERROR_CODES: tuple[tuple[type[BaseException], str], ...] = (
    (PermissionError, "FORBIDDEN"),
    (FileNotFoundError, "NOT_FOUND"),
    (TimeoutError, "DEPENDENCY_TIMEOUT"),
    (ValueError, "VALIDATION_FAILED"),
    (ConnectionError, "DEPENDENCY_UNAVAILABLE"),
)


def stable_error_code(error: BaseException | str | None) -> str:
    """Map operational failures to a bounded metric/log label.

    Exception class names are implementation details and can create unbounded
    Prometheus label sets. Callers may pass an already-stable upper-case code;
    all other values are reduced to the public operational taxonomy.
    """
    if error is None:
        return "none"
    if isinstance(error, str):
        candidate = error.strip()
        if candidate and candidate.replace("_", "").isalnum() and candidate == candidate.upper():
            return candidate
        return "INTERNAL_ERROR"
    for error_type, code in _EXCEPTION_ERROR_CODES:
        if isinstance(error, error_type):
            return code
    return "INTERNAL_ERROR"


class MetricsRegistry:
    """Small dependency-free Prometheus registry for local and production use."""

    def __init__(self) -> None:
        self._values: defaultdict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1, labels: dict[str, str] | None = None) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._values[key] += value

    def set(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._values[key] = value

    def replace_series(self, name: str, series: dict[tuple[tuple[str, str], ...], float]) -> None:
        with self._lock:
            for key in [key for key in self._values if key[0] == name]:
                del self._values[key]
            for labels, value in series.items():
                self._values[(name, labels)] = value

    def observe(self, name: str, started: float, labels: dict[str, str] | None = None) -> None:
        self.inc(f"{name}_seconds_sum", time.perf_counter() - started, labels)
        self.inc(f"{name}_seconds_count", 1, labels)

    def render(self) -> str:
        with self._lock:
            values = list(self._values.items())
        lines = ["# HELP jaycode_info Jaycode runtime information", "# TYPE jaycode_info gauge", 'jaycode_info{service="jaycode"} 1']
        for (name, labels), value in sorted(values):
            label_text = "".join(f'{key}="{str(value).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"' for key, value in labels)
            lines.append(f"{name}{{{label_text}}} {value}" if label_text else f"{name} {value}")
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


def record_domain_operation(
    domain: str,
    operation: str,
    started: float,
    *,
    status: str,
    error_code: str = "",
) -> None:
    """Record low-cardinality domain results without leaking request payloads."""
    labels = {
        "domain": domain,
        "operation": operation,
        "status": status,
        "error_code": stable_error_code(error_code or None),
    }
    metrics.inc("jaycode_domain_operations_total", labels=labels)
    metrics.observe("jaycode_domain_operation", started, labels=labels)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("request_id", "task_id", "trace_id", "worker_id", "actor_id", "role", "status", "latency_ms", "error_code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("jaycode")
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)
