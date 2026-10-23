"""Keep a change only when every required metric is flat or better."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .results import RESULTS_DIR, load_result

# Hallucination scores badness. Every other metric is higher-is-better.
LOWER_IS_BETTER = {"hallucination"}
PLATEAU_WINDOW = 2


def normalize_metric_name(name: str) -> str:
    return name.removesuffix("_metric")


def _metric_mean(record: dict[str, Any], metric: str) -> float | None:
    target = normalize_metric_name(metric)
    for name, stats in record.get("aggregated_scores", {}).items():
        if normalize_metric_name(name) == target:
            return stats["mean"]
    for name, score in record.get("experiment_scores", {}).items():
        if normalize_metric_name(name) == target:
            return score["value"]
    return None


@dataclass
class MetricComparison:
    metric: str
    current: float | None
    baseline: float | None
    delta: float | None
    direction: str
    regressed: bool


@dataclass
class Verdict:
    experiment: str
    baseline: str | None
    decision: str
    comparisons: list[MetricComparison]
    plateaued: bool
    reason: str


def compare(current: dict[str, Any], baseline: dict[str, Any] | None) -> list[MetricComparison]:
    required = current.get("acceptance", {}).get("required_metrics", [])
    comparisons = []
    for metric in required:
        current_value = _metric_mean(current, metric)
        baseline_value = _metric_mean(baseline, metric) if baseline else None
        direction = "lower" if normalize_metric_name(metric) in LOWER_IS_BETTER else "higher"
        delta = (
            current_value - baseline_value
            if current_value is not None and baseline_value is not None
            else None
        )
        regressed = bool(delta is not None and (delta < 0 if direction == "higher" else delta > 0))
        comparisons.append(
            MetricComparison(
                metric=metric,
                current=current_value,
                baseline=baseline_value,
                delta=delta,
                direction=direction,
                regressed=regressed,
            )
        )
    return comparisons


def _is_flat(comparisons: list[MetricComparison]) -> bool:
    return bool(comparisons) and all(comparison.delta is not None and comparison.delta == 0 for comparison in comparisons)


def _recent_flat_streak(experiments: list[dict[str, Any]], up_to_name: str) -> int:
    streak = 0
    for entry in reversed(experiments):
        if entry["name"] == up_to_name:
            continue
        result = entry.get("result")
        if result is None:
            break
        if result.get("decision") == "keep" and result.get("flat"):
            streak += 1
        else:
            break
    return streak


def decide(
    experiment_name: str,
    experiments: list[dict[str, Any]],
    results_dir: Path = RESULTS_DIR,
) -> Verdict:
    entry = next((item for item in experiments if item["name"] == experiment_name), None)
    if entry is None:
        raise ValueError(f"No entry named {experiment_name!r} in experiments.json")

    current = load_result(experiment_name, results_dir)
    baseline_name = entry.get("acceptance", {}).get("compare_against")
    if baseline_name is None:
        return Verdict(
            experiment=experiment_name,
            baseline=None,
            decision="no_baseline",
            comparisons=[],
            plateaued=False,
            reason="No compare_against set - treated as the new baseline.",
        )

    baseline = load_result(baseline_name, results_dir)
    comparisons = compare(current, baseline)
    regressions = [item.metric for item in comparisons if item.regressed]
    flat = _is_flat(comparisons)
    if regressions:
        decision = "reject"
        reason = f"Regressed on: {', '.join(regressions)}."
    else:
        decision = "keep"
        reason = "Flat or improved on every required metric." if flat else "Improved."

    plateau_streak = _recent_flat_streak(experiments, experiment_name)
    plateaued = decision == "keep" and flat and plateau_streak + 1 >= PLATEAU_WINDOW
    return Verdict(
        experiment=experiment_name,
        baseline=baseline_name,
        decision=decision,
        comparisons=comparisons,
        plateaued=plateaued,
        reason=reason,
    )
