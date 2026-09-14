from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.marketplace.installer import _load_manifest, _safe_extract
from app.providers.mcp_provider import RealMCPProvider


def test_api_key_rbac_and_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jaycode_auth_enabled", True)
    monkeypatch.setattr(settings, "jaycode_api_keys", "user-key:user,reviewer-key:reviewer,admin-key:admin")
    client = TestClient(app)

    missing = client.get("/api/v1/skills", headers={"X-Request-ID": "req-test-1"})
    assert missing.status_code == 401
    assert missing.json()["error_code"] == "AUTHENTICATION_REQUIRED"
    assert missing.headers["X-Request-ID"] == "req-test-1"

    forbidden = client.post(
        "/api/v1/marketplace/install",
        headers={"Authorization": "Bearer user-key", "X-Request-ID": "req-test-2"},
        json={},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == "FORBIDDEN"

    audit = client.get("/api/v1/security/audit", headers={"Authorization": "Bearer admin-key"})
    assert audit.status_code == 200
    assert any(item["request_id"] == "req-test-2" for item in audit.json()["audits"])


def test_marketplace_remote_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jaycode_marketplace_remote_enabled", False)
    with pytest.raises(PermissionError, match="disabled"):
        _load_manifest("https://example.com/plugin.json")


def test_marketplace_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../escape.txt", "blocked")
    with ZipFile(archive_path) as archive:
        with pytest.raises(ValueError, match="unsafe path"):
            _safe_extract(archive, tmp_path / "out")


def test_mcp_process_configuration_is_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = RealMCPProvider()
    monkeypatch.setattr(settings, "jaycode_mcp_allowed_commands", "python.exe,node.exe")
    with pytest.raises(PermissionError, match="not in"):
        provider._validate_server_process_config({"command": "powershell.exe", "args": [], "env": {}})
    with pytest.raises(PermissionError, match="Shell-style"):
        provider._validate_server_process_config({"command": "python.exe", "args": ["-c", "print(1)"], "env": {}})
