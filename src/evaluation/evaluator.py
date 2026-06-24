"""Agent evaluation framework for containment, accuracy, grounding, and benchmarks."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from src.config import load_agent_config, project_path
from src.workflows.orchestrator import AgentOrchestrator

logger = structlog.get_logger()


@dataclass
class EvalCase:
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
    contained: bool = True
    grounding_score: float = 0.0
    hallucination_risk: str = "low"
    errors: list[str] = field(default_factory=list)


class AgentEvaluator:
    """Run evaluation suites against agents to measure containment and quality."""

    def __init__(self, test_suite_path: str | None = None):
        self.test_cases: list[EvalCase] = []
        self.benchmarks: list[dict[str, Any]] = []
        self.eval_config = load_agent_config().get("evaluation", {})
        self.hallucination_threshold = self.eval_config.get("hallucination_threshold", 0.15)
        if test_suite_path:
            self.load_test_suite(test_suite_path)
        benchmark_path = self.eval_config.get("benchmark_suite")
        if benchmark_path:
            self.load_benchmarks(benchmark_path)

    def load_test_suite(self, path: str | Path) -> None:
        data = json.loads(project_path(path).read_text())
        self.test_cases = [EvalCase(**tc) for tc in data["test_cases"]]

    def load_benchmarks(self, path: str | Path) -> None:
        data = json.loads(project_path(path).read_text())
        self.benchmarks = data.get("benchmarks", [])

    def add_test_case(self, test_case: EvalCase) -> None:
        self.test_cases.append(test_case)

    async def run_single(self, test_case: EvalCase) -> EvalResult:
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
        metrics = result.get("metrics", {})
        contained = "transfer_to_human" not in tools_used

        keyword_matches = [kw for kw in test_case.expected_keywords if kw.lower() in response.lower()]
        if test_case.expected_keywords and not keyword_matches:
            errors.append(f"Missing expected keywords: {test_case.expected_keywords}")

        if test_case.expected_tools:
            missing_tools = set(test_case.expected_tools) - set(tools_used)
            if missing_tools:
                errors.append(f"Missing expected tools: {missing_tools}")

        if test_case.should_contain and not contained:
            errors.append("Expected containment (no human transfer)")
        elif not test_case.should_contain and contained:
            errors.append("Expected escalation to human agent")

        grounding_score = metrics.get("grounding_score", 0.0)
        hallucination_risk = metrics.get("hallucination_risk", "unknown")
        if hallucination_risk == "high":
            errors.append("High hallucination risk detected")

        passed = len(errors) == 0
        return EvalResult(
            test_id=test_case.id,
            passed=passed,
            response=response,
            response_time_ms=elapsed_ms,
            tools_used=tools_used,
            keyword_matches=keyword_matches,
            contained=contained,
            grounding_score=grounding_score,
            hallucination_risk=hallucination_risk,
            errors=errors,
        )

    async def run_benchmarks(self) -> dict[str, Any]:
        results = []
        for bench in self.benchmarks:
            orchestrator = AgentOrchestrator(bench["agent_id"])
            result = await orchestrator.invoke(bench["input"])
            metrics = result.get("metrics", {})
            passed = True
            errors = []

            if bench.get("expect_guardrail_block"):
                if not metrics.get("guardrail_blocked"):
                    passed = False
                    errors.append("Expected guardrail block")
            else:
                for kw in bench.get("expected_keywords", []):
                    if kw.lower() not in result["response"].lower():
                        passed = False
                        errors.append(f"Missing keyword: {kw}")
                min_grounding = bench.get("min_grounding_score", 0.0)
                if metrics.get("grounding_score", 0) < min_grounding:
                    passed = False
                    errors.append("Grounding score below threshold")

            results.append({
                "benchmark_id": bench["id"],
                "passed": passed,
                "errors": errors,
                "metrics": metrics,
            })

        passed = sum(1 for r in results if r["passed"])
        return {
            "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
            "results": results,
        }

    async def run_suite(self) -> dict[str, Any]:
        results: list[EvalResult] = []
        for tc in self.test_cases:
            result = await self.run_single(tc)
            results.append(result)
            logger.info("eval_result", test_id=tc.id, passed=result.passed)

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        avg_time = sum(r.response_time_ms for r in results) / total if total else 0
        contained_count = sum(1 for r in results if r.contained)
        containment_rate = contained_count / total if total else 0
        high_hallucination = sum(1 for r in results if r.hallucination_risk == "high")
        hallucination_rate = high_hallucination / total if total else 0
        avg_grounding = sum(r.grounding_score for r in results) / total if total else 0

        benchmark_results = await self.run_benchmarks() if self.benchmarks else None

        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "containment_rate": round(containment_rate, 3),
                "contained_sessions": contained_count,
                "avg_response_time_ms": round(avg_time),
                "hallucination_rate": round(hallucination_rate, 3),
                "avg_grounding_score": round(avg_grounding, 3),
            },
            "results": [
                {
                    "test_id": r.test_id,
                    "passed": r.passed,
                    "response_time_ms": round(r.response_time_ms),
                    "tools_used": r.tools_used,
                    "contained": r.contained,
                    "grounding_score": r.grounding_score,
                    "hallucination_risk": r.hallucination_risk,
                    "errors": r.errors,
                }
                for r in results
            ],
            "benchmarks": benchmark_results,
        }
