from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNED_ROOTS = ("README.md", "docs", "app", "web/src", "examples", "scripts", "tests")
FORBIDDEN_MARKERS = (
    "f:/jayagent/" + "jaycode",
    "dev" + "agent",
    "x_" + "dev" + "agent",
    "phase_1",
    "phase_3_runtime",
    "phase_4_web_workbench",
    "phase_5_workflow_runtime",
    "phase_6_visual_workflow_entry",
    "phase_7_pgvector_rag",
    "phase_8_workflow_production",
    "implementation_timeline",
    "test_memory_store.py",
)


def _files_to_scan() -> list[Path]:
    files: list[Path] = []
    for relative in SCANNED_ROOTS:
        path = ROOT / relative
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(
                item
                for item in path.rglob("*")
                if item.is_file()
                and item.name != "test_cleanup_regressions.py"
                and item.suffix.lower() not in {".pyc", ".lock", ".db", ".sqlite3"}
                and "__pycache__" not in item.parts
            )
    return sorted(set(files))


def test_removed_environment_and_legacy_markers_are_absent() -> None:
    violations: list[str] = []
    for path in _files_to_scan():
        if path.suffix.lower() in {".lock", ".db", ".sqlite3"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)} contains {marker!r}")
    assert not violations, "\n".join(violations)


def test_markdown_local_links_resolve() -> None:
    missing: list[str] = []
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in (ROOT / "docs").rglob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in link_pattern.finditer(text):
            target = match.group(1).split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "codex:")):
                continue
            if not (path.parent / target).resolve().exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")
    assert not missing, "\n".join(missing)


def test_frontend_default_project_path_is_portable() -> None:
    source = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    assert "const defaultProjectPath = '.';" in source
