from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from app.main import app

router = APIRouter()


@router.get("/api/v1/test-error-envelope/not-found", include_in_schema=False)
def _not_found() -> None:
    raise HTTPException(status_code=404, detail="Test resource not found")


@router.get("/api/v1/test-error-envelope/unhandled", include_in_schema=False)
def _unhandled() -> None:
    raise RuntimeError("sensitive internal detail")


app.include_router(router)


def test_http_exception_uses_compatible_error_envelope() -> None:
    response = TestClient(app).get("/api/v1/test-error-envelope/not-found", headers={"x-request-id": "req-test"})
    assert response.status_code == 404
    assert response.headers["x-request-id"] == "req-test"
    assert response.json() == {
        "error_code": "NOT_FOUND",
        "message": "Test resource not found",
        "request_id": "req-test",
        "details": {},
        "detail": "Test resource not found",
    }


def test_unhandled_exception_is_not_exposed() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/test-error-envelope/unhandled")
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"
    assert "sensitive" not in response.text


def test_http_metrics_use_route_template_not_resource_identifier() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/tasks/task-contains-high-cardinality-id")
    assert response.status_code == 404
    metrics = client.get("/metrics").text
    assert 'path="/api/v1/tasks/{task_id}"' in metrics
    assert "task-contains-high-cardinality-id" not in metrics
