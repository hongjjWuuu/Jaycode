"""Fail when a supplied RAG Gold Set result regresses from its baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("current", type=Path, help="JSON result produced by the Gold Set evaluator")
    parser.add_argument("--baseline", type=Path, default=Path("tests/fixtures/rag_gold_baseline.json"))
    args = parser.parse_args()
    required = {"dataset_version", "recall_at_k", "mrr", "keyword_coverage"}
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))
    for name, payload in (("baseline", baseline), ("current", current)):
        if not isinstance(payload, dict) or not required.issubset(payload):
            missing = sorted(required - set(payload)) if isinstance(payload, dict) else sorted(required)
            raise SystemExit(f"{name} Gold Set result is invalid; missing: {', '.join(missing)}")
    if not isinstance(current.get("failed_cases"), list):
        raise SystemExit("current Gold Set result is invalid; failed_cases must be a list")
    tolerance = float(baseline.get("tolerance", 0.05))
    metrics = ("recall_at_k", "mrr", "keyword_coverage")
    regressions = [
        f"{metric}: {current.get(metric)} < {float(baseline.get(metric, 0)) - tolerance:.4f}"
        for metric in metrics
        if float(current[metric]) < float(baseline[metric]) - tolerance
    ]
    if regressions:
        print("RAG Gold Set regression detected:")
        print("\n".join(regressions))
        return 1
    print(f"RAG Gold Set baseline {baseline.get('dataset_version', 'unknown')} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
