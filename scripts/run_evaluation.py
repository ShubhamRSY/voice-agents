#!/usr/bin/env python3
"""Run the agent evaluation suite."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.evaluator import AgentEvaluator


async def main():
    suite_path = Path(__file__).parent.parent / "tests" / "evaluation" / "test_cases.json"
    evaluator = AgentEvaluator(str(suite_path))
    results = await evaluator.run_suite()

    print("\n=== Evaluation Results ===")
    print(json.dumps(results["summary"], indent=2))
    print("\n=== Details ===")
    for r in results["results"]:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['test_id']} ({r['response_time_ms']}ms)")
        if r["errors"]:
            for err in r["errors"]:
                print(f"         Error: {err}")


if __name__ == "__main__":
    asyncio.run(main())
