from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_p3_documents_describe_postgres_as_authoritative_store() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    startup = (ROOT / "docs" / "Jaycode 启动方式.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "P3 单机运维手册.md").read_text(encoding="utf-8")

    assert "jayagent_studio" in readme
    assert "正式运行" in readme
    assert "jayagent_studio" in startup
    assert "不能通过修改 `.env` 直接回退" in operations
    assert "jaycode_restore_test_*" in operations


def test_backup_and_restore_scripts_enforce_their_safety_guards() -> None:
    backup = (ROOT / "scripts" / "backup_postgres.ps1").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "restore_postgres_drill.ps1").read_text(encoding="utf-8")
    scheduler = (ROOT / "scripts" / "windows" / "jaycode-postgres-backup-task.ps1").read_text(encoding="utf-8")

    assert "pg_dump -U postgres -d jayagent_studio -Fc" in backup
    assert "pg_restore --list" in backup
    assert "jayagent_studio-(\\d{8}T\\d{6}Z)\\.dump" in backup
    assert "jaycode_restore_test_" in restore
    assert "AdminUrl must target loopback" in restore
    assert "dropdb -U postgres --if-exists" in restore
    assert '"register"' in scheduler
    assert "-Daily -At 3:15AM" in scheduler
