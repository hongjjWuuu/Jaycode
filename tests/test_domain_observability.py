import logging

from app.core.observability import JsonFormatter, MetricsRegistry, stable_error_code


def test_domain_operation_metrics_are_low_cardinality_and_timed(monkeypatch) -> None:
    from app.core import observability

    registry = MetricsRegistry()
    monkeypatch.setattr(observability, "metrics", registry)
    observability.record_domain_operation("workflow", "execute", 0.0, status="failed", error_code="ValueError")
    rendered = registry.render()
    assert 'jaycode_domain_operations_total{domain="workflow",error_code="INTERNAL_ERROR",operation="execute",status="failed"} 1.0' in rendered
    assert 'jaycode_domain_operation_seconds_count{domain="workflow",error_code="INTERNAL_ERROR",operation="execute",status="failed"} 1.0' in rendered


def test_stable_error_codes_reduce_exception_implementation_details() -> None:
    assert stable_error_code(ValueError("invalid graph")) == "VALIDATION_FAILED"
    assert stable_error_code(PermissionError("not approved")) == "FORBIDDEN"
    assert stable_error_code(TimeoutError("slow provider")) == "DEPENDENCY_TIMEOUT"
    assert stable_error_code("API_KEY_UNAVAILABLE") == "API_KEY_UNAVAILABLE"
    assert stable_error_code("some.dynamic.error") == "INTERNAL_ERROR"


def test_json_logs_keep_correlation_fields_without_payloads() -> None:
    record = logging.LogRecord("jaycode.test", logging.WARNING, __file__, 1, "operation_failed", (), None)
    record.request_id = "req-1"
    record.task_id = "task-1"
    record.trace_id = "trace-1"
    record.actor_id = "actor-1"
    record.role = "operator"
    record.error_code = "DEPENDENCY_UNAVAILABLE"
    rendered = JsonFormatter().format(record)
    assert '"request_id": "req-1"' in rendered
    assert '"task_id": "task-1"' in rendered
    assert '"trace_id": "trace-1"' in rendered
    assert "payload" not in rendered
