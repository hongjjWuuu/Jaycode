from fastapi.testclient import TestClient

from app.main import app


def test_web_app_can_be_created() -> None:
    assert app.title == "Jaycode"


def test_control_plane_health_and_catalogs() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/skills").status_code == 200
    assert client.get("/api/v1/marketplace/catalog").status_code == 200
    assert client.get("/api/v1/rag/status").status_code == 200
    assert client.get("/api/v1/benchmarks").status_code == 200


def test_workflow_validation() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/workflows/validate",
        json={
            "nodes": [
                {"id": "plan", "type": "planner"},
                {"id": "report", "type": "reporter"},
            ],
            "edges": [{"source": "plan", "target": "report"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_task_review_resume() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/tasks/run",
        json={
            "goal": "smoke review resume",
            "project_path": ".",
            "require_human_review": True,
            "nodes": [
                {"id": "plan", "type": "planner"},
                {"id": "review", "type": "human_review"},
                {"id": "report", "type": "reporter"},
            ],
            "edges": [
                {"source": "plan", "target": "review"},
                {"source": "review", "target": "report"},
            ],
        },
    )
    assert response.status_code == 200
    task = response.json()
    assert task["status"] == "waiting_review"

    approved = client.post(
        f"/api/v1/tasks/{task['task_id']}/approve",
        json={"comment": "test approval"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"
