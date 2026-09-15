from __future__ import annotations

import argparse
import gc
import json
import tempfile
from pathlib import Path

from app.harness.load_test import run_worker_load_test


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic local worker/store load test")
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jaycode-worker-load-") as directory:
        result = run_worker_load_test(Path(directory) / "load.db", args.tasks, args.workers)
        gc.collect()
    print(json.dumps(result, ensure_ascii=False))
    if result["claimed_count"] != args.tasks or result["unique_claimed_count"] != args.tasks or result["completed_count"] != args.tasks:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
