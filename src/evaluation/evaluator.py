"""Agent evaluation framework for containment, accuracy, and performance."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()


@dataclass
class TestCase:
    id: str
    agent_id: str
    input: str
    expected_tools: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    should_contain: bool = True
    customer_info: str = ""


@dataclass
class EvalResult:
    test_id: str
    passed: bool
    response: str
    response_time_ms: float
    tools_used: list[str]
    keyword_matches: list[str]
    errors: list[str] = field(default_factory=list)


class AgentEvaluator:
    """Run evaluation suites against agents to measure containment and quality."""

    def __init__(self, test_suite_path: str | None = None):
        self.test_cases: list[TestCase] = []
        if test_suite_path:
            self.load_test_suite(test_suite_path)

    def load_test_suite(self, path: str | Path) -> None:
        data = json.loads(Path(path).read_text())
        self.test_cases = [TestCase(**tc) for tc in data["test_cases"]]

    def add_test_case(self, test_case: TestCase) -> None:
        self.test_cases.append(test_case)

    async def run_single(self, test_case: TestCase) -> EvalResult:
        orchestrator = AgentOrchestrator(test_case.agent_id)
        errors: list[str] = []
        start = time.perf_counter()

        try:
            result = await orchestrator.invoke(
                user_input=test_case.input,
                customer_info=test_case.customer_info,
            )
        except Exception as e:
            return EvalResult(
                test_id=test_case.id,
                passed=False,
                response="",
                response_time_ms=0,
                tools_used=[],
                keyword_matches=[],
                errors=[str(e)],
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        response = result["response"]
        tools_used = [tc["name"] for tc in result.get("tool_calls", [])]

        keyword_matches = [kw for kw in test_case.expected_keywords if kw.lower() in response.lower()]
        if test_case.expected_keywords and not keyword_matches:
            errors.append(f"Missing expected keywords: {test_case.expected_keywords}")

        if test_case.expected_tools:
            missing_tools = set(test_case.expected_tools) - set(tools_used)
            if missing_tools:
                errors.append(f"Missing expected tools: {missing_tools}")

        passed = len(errors) == 0
        return EvalResult(
            test_id=test_case.id,
            passed=passed,
            response=response,
            response_time_ms=elapsed_ms,
            tools_used=tools_used,
            keyword_matches=keyword_matches,
            errors=errors,
        )

    async def run_suite(self) -> dict[str, Any]:
        results: list[EvalResult] = []
        for tc in self.test_cases:
            result = await self.run_single(tc)
            results.append(result)
            logger.info("eval_result", test_id=tc.id, passed=result.passed)

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        avg_time = sum(r.response_time_ms for r in results) / total if total else 0
        containment = passed / total if total else 0

        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "containment_rate": round(containment, 3),
                "avg_response_time_ms": round(avg_time),
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "passed": r.passed,
                    "response_time_ms": round(r.response_time_ms),
                    "tools_used": r.tools_used,
                    "errors": r.errors,
                }
                for r in results
            ],
        }
