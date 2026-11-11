"""Repeatable, versioned model screening for EIVA's Groq candidates."""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from typing import Any
from uuid import uuid4

from groq import AsyncGroq, GroqError
import yaml

from backend.config import get_settings
from backend.core.model_router import ModelRouter
from backend.observability.logging import configure_logging, redact_sensitive_text


def score_answer(answer: str, criteria: list[dict[str, str]]) -> dict[str, Any]:
    checks = [
        {
            "id": criterion["id"],
            "passed": re.search(criterion["pattern"], answer, flags=re.IGNORECASE) is not None,
        }
        for criterion in criteria
    ]
    passed = sum(check["passed"] for check in checks)
    total = len(checks)
    return {
        "criteria": checks,
        "passed": passed,
        "total": total,
        "score": round(passed / total, 3) if total else 0.0,
        "all_passed": passed == total,
    }


async def evaluate_candidate(
    client: AsyncGroq,
    model: str,
    cases: list[dict[str, Any]],
    pricing: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    router = ModelRouter(client, {"evaluation": model}, pricing=pricing)
    case_results = []
    for case in cases:
        request_id = str(uuid4())
        started = time.perf_counter()
        completion = await router.complete(
            "evaluation",
            [{"role": "user", "content": case["prompt"]}],
            request_id=request_id,
            temperature=0,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        answer = completion.choices[0].message.content or ""
        usage = completion.usage
        case_results.append(
            {
                "case_id": case["id"],
                "prompt_version": case["prompt_version"],
                "role": case["role"],
                "category": case["category"],
                "request_id": request_id,
                "prompt": case["prompt"],
                "answer": answer,
                "model": completion.model or model,
                "latency_ms": latency_ms,
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                },
                "estimated_cost_usd": router.estimate_cost(
                    completion.model or model,
                    getattr(usage, "prompt_tokens", None),
                    getattr(usage, "completion_tokens", None),
                ),
                "quality": score_answer(answer, case["criteria"]),
            }
        )

    criteria_passed = sum(result["quality"]["passed"] for result in case_results)
    criteria_total = sum(result["quality"]["total"] for result in case_results)
    cases_passed = sum(result["quality"]["all_passed"] for result in case_results)
    latencies = [result["latency_ms"] for result in case_results if result["latency_ms"] is not None]
    total_tokens = sum(result["usage"]["total_tokens"] or 0 for result in case_results)
    cost_values = [result["estimated_cost_usd"] for result in case_results]
    return {
        "summary": {
            "cases_passed": cases_passed,
            "case_count": len(case_results),
            "criteria_passed": criteria_passed,
            "criteria_total": criteria_total,
            "criteria_score": round(criteria_passed / criteria_total, 3) if criteria_total else 0.0,
            "mean_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(sum(value for value in cost_values if value is not None), 8)
            if all(value is not None for value in cost_values) and cost_values else None,
        },
        "cases": case_results,
    }


async def run_evaluation(dataset_path: Path, output_path: Path) -> dict[str, Any]:
    settings = get_settings()
    model_config = yaml.safe_load(Path(settings.models_config_path).read_text(encoding="utf-8")) or {}
    if model_config.get("provider") != "groq":
        raise ValueError("EIVA model evaluation only supports the configured Groq provider")

    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    candidates = sorted(set(model_config.get("roles", {}).values()))
    if not candidates:
        raise ValueError("No model candidates are configured")

    client = AsyncGroq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
        max_retries=settings.groq_max_retries,
    )
    report: dict[str, Any] = {
        "evaluation_id": str(uuid4()),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "provider": "groq",
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "human_review_required": dataset.get("human_review_required", True),
        "scoring_note": "Regex-based screening criteria are a first pass; inspect answers before making model-role decisions.",
        "models": {},
    }

    try:
        for model in candidates:
            try:
                report["models"][model] = await evaluate_candidate(
                    client, model, dataset["cases"], model_config.get("pricing_usd_per_million_tokens", {})
                )
            except GroqError as exc:
                report["models"][model] = {
                    "error": {
                        "type": type(exc).__name__,
                        "status_code": getattr(exc, "status_code", None),
                    }
                }
    finally:
        await client.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_report = _redact_report(report)
    output_path.write_text(json.dumps(safe_report, indent=2, ensure_ascii=False), encoding="utf-8")
    return safe_report


def _redact_report(value: Any) -> Any:
    """Redact credential-shaped strings before writing local evaluation artifacts."""
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        return [_redact_report(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_report(item) for key, item in value.items()}
    return value


async def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("backend/evaluations/datasets/model_screening_v1.json"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/model_evaluation.json"))
    args = parser.parse_args()
    report = await run_evaluation(args.dataset, args.output)
    for model, result in report["models"].items():
        if "error" in result:
            print(f"{model}: unavailable ({result['error']['type']})")
            continue
        summary = result["summary"]
        print(
            f"{model}: {summary['cases_passed']}/{summary['case_count']} cases, "
            f"{summary['criteria_passed']}/{summary['criteria_total']} criteria, "
            f"mean {summary['mean_latency_ms']} ms, {summary['total_tokens']} tokens"
        )
    print(f"Evaluation report saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
