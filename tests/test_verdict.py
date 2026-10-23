import json
from pathlib import Path

from support_loop.tool_score import score_tools
from support_loop.verdict import compare, decide

REQUIRED = ["answer_relevance", "hallucination", "tool_selection", "refusal_recall"]


def _record(name: str, scores: dict[str, float], experiment_scores: dict[str, float] | None = None) -> dict:
    return {
        "name": name,
        "change": name,
        "acceptance": {"compare_against": "baseline", "required_metrics": REQUIRED},
        "aggregated_scores": {
            metric: {"mean": value, "min": value, "max": value, "std": 0}
            for metric, value in scores.items()
        },
        "experiment_scores": {
            metric: {"value": value, "reason": "test"}
            for metric, value in (experiment_scores or {}).items()
        },
        "cases": [],
    }


def _write(directory: Path, record: dict) -> None:
    (directory / f"{record['name']}.json").write_text(json.dumps(record))


def test_hallucination_regression_is_an_increase():
    comparisons = compare(
        _record("next", {"answer_relevance": 0.8, "hallucination": 0.4, "tool_selection": 1}, {"refusal_recall": 1}),
        _record("baseline", {"answer_relevance": 0.8, "hallucination": 0.2, "tool_selection": 1}, {"refusal_recall": 1}),
    )
    by_name = {item.metric: item for item in comparisons}
    assert by_name["hallucination"].regressed is True
    assert by_name["answer_relevance"].regressed is False


def test_keep_reject_and_plateau(tmp_path: Path):
    baseline = _record(
        "baseline",
        {"answer_relevance": 0.7, "hallucination": 0.2, "tool_selection": 1},
        {"refusal_recall": 1},
    )
    baseline["acceptance"] = {"compare_against": None, "required_metrics": REQUIRED}
    better = _record(
        "better",
        {"answer_relevance": 0.9, "hallucination": 0.1, "tool_selection": 1},
        {"refusal_recall": 1},
    )
    better["acceptance"]["compare_against"] = "baseline"
    worse = _record(
        "worse",
        {"answer_relevance": 0.5, "hallucination": 0.2, "tool_selection": 1},
        {"refusal_recall": 1},
    )
    flat = _record(
        "flat-2",
        {"answer_relevance": 0.7, "hallucination": 0.2, "tool_selection": 1},
        {"refusal_recall": 1},
    )
    for record in (baseline, better, worse, flat):
        _write(tmp_path, record)

    experiments = [
        {"name": "baseline", "acceptance": baseline["acceptance"], "result": {"decision": "no_baseline", "flat": False}},
        {"name": "flat-1", "acceptance": flat["acceptance"], "result": {"decision": "keep", "flat": True}},
        {"name": "better", "acceptance": better["acceptance"]},
        {"name": "worse", "acceptance": worse["acceptance"]},
        {"name": "flat-2", "acceptance": flat["acceptance"]},
    ]
    assert decide("baseline", experiments, tmp_path).decision == "no_baseline"
    assert decide("better", experiments, tmp_path).decision == "keep"
    assert decide("worse", experiments, tmp_path).decision == "reject"

    flat_experiments = [
        {"name": "baseline", "result": {"decision": "keep", "flat": True}},
        {"name": "flat-2", "acceptance": flat["acceptance"]},
    ]
    verdict = decide("flat-2", flat_experiments, tmp_path)
    assert verdict.decision == "keep"
    assert verdict.plateaued is True


def test_tool_score_requires_expected_tools_and_escalation_bit():
    perfect, _ = score_tools(
        ["search_handbook", "get_order", "escalate_to_human"],
        ["get_order", "search_handbook", "escalate_to_human"],
        True,
    )
    assert perfect == 1
    missed, _ = score_tools(["search_handbook", "get_order"], ["search_handbook"], False)
    assert missed == 0.5
    escalated_a_denial, _ = score_tools(["search_handbook"], ["search_handbook", "escalate_to_human"], False)
    assert escalated_a_denial == 0.5
