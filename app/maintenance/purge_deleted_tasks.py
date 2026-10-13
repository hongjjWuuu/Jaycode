"""Permanently purge task records whose 30-day recycle-bin retention expired.

Run this command once per day from Windows Task Scheduler, cron, or the
deployment job runner: ``python -m app.maintenance.purge_deleted_tasks``.
"""

from __future__ import annotations

import json

from app.core.security import audit_action
from app.persistence.factory import get_persistence_stores


def main() -> int:
    task_ids = get_persistence_stores().task.purge_expired_deleted_tasks()
    audit_action(
        "task_purge_expired",
        "task",
        status="completed",
        metadata={"purged_count": len(task_ids), "task_ids": task_ids},
    )
    print(json.dumps({"purged_count": len(task_ids), "task_ids": task_ids}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
