"""Show the cases that actually failed, not the average."""

from __future__ import annotations

from typing import Any

from .results import load_result
from .verdict import LOWER_IS_BETTER, normalize_metric_name


def _badness(metric: str, value: float) -> float:
    if normalize_metric_name(metric) in LOWER_IS_BETTER:
        return value
    return 1.0 - value


def worst_cases(record: dict[str, Any], n: int = 5, metric: str | None = None) -> list[dict[str, Any]]:
    required = [metric] if metric else record.get("acceptance", {}).get("required_metrics", [])
    required_normalized = {normalize_metric_name(name) for name in required}

    def case_badness(case: dict[str, Any]) -> float:
        values = [
            _badness(score_name, score["value"])
            for score_name, score in case.get("scores", {}).items()
            if (not required or normalize_metric_name(score_name) in required_normalized)
            and not score.get("scoring_failed")
            and isinstance(score.get("value"), (int, float))
        ]
        return max(values) if values else 0.0

    ranked = sorted(record.get("cases", []), key=case_badness, reverse=True)
    return ranked[:n]


def format_report(record: dict[str, Any], n: int = 5, metric: str | None = None) -> str:
    lines = [f"Experiment: {record['name']} ({record.get('change', '')})", "Aggregated scores:"]
    for name, stats in record.get("aggregated_scores", {}).items():
        lines.append(
            f"  {name}: mean={stats['mean']:.3f} min={stats['min']:.3f} max={stats['max']:.3f}"
        )
    for name, score in record.get("experiment_scores", {}).items():
        lines.append(f"  {name}: {score['value']:.3f}")

    lines.append(f"\nWorst {n} cases:")
    for case in worst_cases(record, n, metric):
        lines.append(f"\n- input: {case.get('input')}")
        lines.append(f"  expected_output: {case.get('expected_output')}")
        lines.append(f"  actual output: {case.get('output')}")
        tools = case.get("tools_called") or []
        if tools:
            lines.append(f"  tools: {', '.join(tools)}")
        for score_name, score in case.get("scores", {}).items():
            lines.append(f"  [{score_name}] {score['value']} - {score.get('reason')}")
    return "\n".join(lines)


def load_and_format(name: str, n: int = 5, metric: str | None = None) -> str:
    return format_report(load_result(name), n=n, metric=metric)
