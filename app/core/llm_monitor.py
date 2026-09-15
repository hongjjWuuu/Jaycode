from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.core.observability import metrics
from app.harness.events import BEIJING_TZ

logger = logging.getLogger("jaycode.llm_monitor")


class LLMMonitor:
    def __init__(self) -> None:
        self._active_alerts: set[str] = set()

    def collect(self, traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        dimensions: defaultdict[tuple[str, str, str], dict[str, float]] = defaultdict(
            lambda: {"calls": 0, "failures": 0, "fallbacks": 0, "tokens": 0, "latency_ms": 0}
        )
        now = datetime.now(BEIJING_TZ)
        recent: list[dict[str, Any]] = []
        for trace in traces:
            labels = (
                _safe_label(trace.get("model"), "unknown"),
                _safe_label(trace.get("agent"), "unknown"),
                _safe_label(trace.get("prompt_version"), "unknown"),
            )
            bucket = dimensions[labels]
            bucket["calls"] += 1
            bucket["failures"] += bool(trace.get("error_message"))
            bucket["fallbacks"] += bool(trace.get("fallback_used"))
            bucket["latency_ms"] += int(trace.get("latency_ms") or 0)
            usage = trace.get("token_usage") if isinstance(trace.get("token_usage"), dict) else {}
            bucket["tokens"] += int(usage.get("total_tokens") or usage.get("total_token_count") or 0)
            created_at = str(trace.get("created_at") or "")
            try:
                timestamp = datetime.strptime(created_at, "%Y-%m-%d, %H:%M").replace(tzinfo=BEIJING_TZ)
            except ValueError:
                timestamp = now
            if now - timedelta(minutes=5) <= timestamp <= now + timedelta(seconds=5):
                recent.append(trace)

        for metric_name, field in (("jaycode_llm_calls_total", "calls"), ("jaycode_llm_failures_total", "failures"), ("jaycode_llm_fallbacks_total", "fallbacks"), ("jaycode_llm_tokens_total", "tokens"), ("jaycode_llm_latency_ms_sum", "latency_ms"), ("jaycode_llm_latency_ms_count", "calls")):
            values = {
                (("model", model), ("agent", agent), ("prompt_version", prompt)): stats[field]
                for (model, agent, prompt), stats in dimensions.items()
            }
            metrics.replace_series(metric_name, values)
        metrics.replace_series(
            "jaycode_llm_fallback_rate",
            {(("model", model), ("agent", agent), ("prompt_version", prompt)): stats["fallbacks"] / stats["calls"] for (model, agent, prompt), stats in dimensions.items() if stats["calls"]},
        )
        metrics.replace_series(
            "jaycode_llm_failure_rate",
            {(("model", model), ("agent", agent), ("prompt_version", prompt)): stats["failures"] / stats["calls"] for (model, agent, prompt), stats in dimensions.items() if stats["calls"]},
        )

        sample_count = len(recent)
        fallback_rate = sum(bool(item.get("fallback_used")) for item in recent) / sample_count if sample_count else 0.0
        failure_rate = sum(bool(item.get("error_message")) for item in recent) / sample_count if sample_count else 0.0
        latencies = sorted(int(item.get("latency_ms") or 0) for item in recent)
        p95 = latencies[min(len(latencies) - 1, max(0, int(len(latencies) * 0.95)))] if latencies else 0
        metrics.set("jaycode_llm_p95_latency_ms", p95)
        alerts = []
        if sample_count >= settings.jaycode_llm_alert_min_samples:
            if fallback_rate > settings.jaycode_llm_fallback_rate_threshold:
                alerts.append({"name": "llm_fallback_rate", "value": fallback_rate, "threshold": settings.jaycode_llm_fallback_rate_threshold})
            if failure_rate > settings.jaycode_llm_schema_failure_rate_threshold:
                alerts.append({"name": "llm_schema_failure_rate", "value": failure_rate, "threshold": settings.jaycode_llm_schema_failure_rate_threshold})
        if p95 > settings.jaycode_llm_p95_latency_threshold_ms:
            alerts.append({"name": "llm_p95_latency_ms", "value": p95, "threshold": settings.jaycode_llm_p95_latency_threshold_ms})
        active_names = {str(alert["name"]) for alert in alerts}
        for name in ("llm_fallback_rate", "llm_schema_failure_rate", "llm_p95_latency_ms"):
            metrics.set("jaycode_llm_alert_active", int(name in active_names), {"alert": name})
        for alert in alerts:
            if alert["name"] not in self._active_alerts:
                logger.warning("llm_threshold_exceeded", extra={"error_code": str(alert["name"]).upper(), "status": "active"})
        self._active_alerts = active_names
        return alerts


def _safe_label(value: Any, default: str) -> str:
    text = str(value or default)
    return "".join(char for char in text[:80] if char.isalnum() or char in "._:-") or default


llm_monitor = LLMMonitor()
