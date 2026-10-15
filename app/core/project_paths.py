from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings


class ProjectPathError(ValueError):
    def __init__(self, error_code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class ResolvedProject:
    input_path: str
    resolved_path: str
    project_name: str
    project_id: str
    allowed_root: str

    def model_dump(self) -> dict[str, str]:
        return asdict(self)


def _absolute_config_path(value: str, *, fallback: Path) -> Path:
    candidate = Path(value).expanduser() if value.strip() else fallback
    if not candidate.is_absolute():
        candidate = fallback / candidate
    return candidate.resolve()


def workspace_root() -> Path:
    repository_root = Path(__file__).resolve().parents[2]
    return _absolute_config_path(settings.jaycode_workspace_root, fallback=repository_root)


def allowed_project_roots() -> tuple[Path, ...]:
    configured = [part.strip() for part in settings.jaycode_allowed_project_roots.split(os.pathsep) if part.strip()]
    base = workspace_root()
    return tuple(_absolute_config_path(part, fallback=base) for part in configured) or (base,)


def project_browser_roots() -> list[dict[str, str]]:
    """Expose opaque root identifiers instead of accepting arbitrary paths."""
    return [
        {"root_id": hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()[:16], "name": root.name or str(root), "path": str(root)}
        for root in allowed_project_roots()
    ]


def browse_project_directories(root_id: str, relative_path: str = "") -> dict[str, Any]:
    root = next((item for item in allowed_project_roots() if hashlib.sha256(os.path.normcase(str(item)).encode("utf-8")).hexdigest()[:16] == root_id), None)
    if root is None:
        raise ProjectPathError("PROJECT_BROWSER_ROOT_INVALID", "目录浏览根目录不存在或不可访问。")
    raw_relative = (relative_path or "").strip().replace("\\", "/")
    candidate = (root / raw_relative).resolve()
    if raw_relative.startswith("/") or not _is_within(candidate, root):
        raise ProjectPathError("PROJECT_PATH_OUTSIDE_ALLOWED_ROOTS", "不能浏览允许目录范围外的位置。")
    if not candidate.exists() or not candidate.is_dir():
        raise ProjectPathError("PROJECT_PATH_INVALID", "目录不存在或不可访问。")
    directories = []
    for child in sorted(candidate.iterdir(), key=lambda item: item.name.casefold()):
        resolved_child = child.resolve()
        if child.is_dir() and _is_within(resolved_child, root):
            directories.append({"name": child.name, "relative_path": str(resolved_child.relative_to(root)).replace("\\", "/")})
    return {"root_id": root_id, "root_name": root.name or str(root), "relative_path": str(candidate.relative_to(root)).replace("\\", "/"), "resolved_path": str(candidate), "directories": directories}


def _is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(str(root))
    except ValueError:
        return False


def resolve_project_path(project_path: str | None) -> ResolvedProject:
    raw = (project_path or "").strip()
    if not raw:
        raise ProjectPathError("PROJECT_PATH_REQUIRED", "请选择并验证项目路径。")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root() / candidate
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ProjectPathError(
            "PROJECT_PATH_INVALID",
            "项目路径不存在或不是目录。",
            input_path=raw,
            resolved_path=str(resolved),
        )

    allowed_root = next((root for root in allowed_project_roots() if _is_within(resolved, root)), None)
    if allowed_root is None:
        raise ProjectPathError(
            "PROJECT_PATH_OUTSIDE_ALLOWED_ROOTS",
            "项目路径不在允许访问的目录范围内。",
            input_path=raw,
            resolved_path=str(resolved),
            allowed_roots=[str(root) for root in allowed_project_roots()],
        )

    identity = os.path.normcase(str(resolved)).replace("\\", "/")
    project_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return ResolvedProject(raw, str(resolved), resolved.name, project_id, str(allowed_root))


def project_collection(project_id: str) -> str:
    return f"project::{project_id}"
