"""Persist one experiment's scores so a later run can diff against it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS_DIR = Path("evals/results")


def _score_dict(score_results: list[Any]) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    for score in score_results:
        scores[score.name] = {
            "value": score.value,
            "reason": score.reason,
            "scoring_failed": score.scoring_failed,
        }
    return scores


def _stats(stats: Any) -> dict[str, float | None]:
    return {
        "mean": stats.mean,
        "min": stats.min,
        "max": stats.max,
        "std": getattr(stats, "std", None),
    }


def to_result_record(experiment: dict[str, Any]) -> dict[str, Any]:
    evaluation = experiment["evaluation"]
    aggregated = evaluation.aggregate_evaluation_scores().aggregated_scores
    cases = []
    for test_result in evaluation.test_results:
        case = test_result.test_case
        task_output = case.task_output or {}
        content = case.dataset_item_content or {}
        cases.append(
            {
                "dataset_item_id": case.dataset_item_id,
                "input": content.get("input"),
                "expected_output": content.get("expected_output"),
                "label": content.get("label"),
                "output": task_output.get("output"),
                "tools_called": task_output.get("tools_called", []),
                "scores": _score_dict(test_result.score_results),
            }
        )
    return {
        "name": experiment["name"],
        "change": experiment["change"],
        "acceptance": experiment.get("acceptance", {}),
        "experiment_id": evaluation.experiment_id,
        "experiment_url": evaluation.experiment_url,
        "dataset_id": evaluation.dataset_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aggregated_scores": {name: _stats(stats) for name, stats in aggregated.items()},
        "experiment_scores": {
            score.name: {"value": score.value, "reason": score.reason}
            for score in evaluation.experiment_scores
        },
        "cases": cases,
    }


def save_result(record: dict[str, Any], results_dir: Path = RESULTS_DIR) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{record['name']}.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return path


def load_result(name: str, results_dir: Path = RESULTS_DIR) -> dict[str, Any]:
    path = results_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No persisted result for experiment {name!r} at {path}. "
            f"Run it first with `support-loop run {name}`."
        )
    return json.loads(path.read_text())
