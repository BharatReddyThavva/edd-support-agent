"""Score the agent with Opik. Judges are for judgment; tool selection is deterministic."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import AnswerRelevance, BaseMetric, GEval, Hallucination
from opik.evaluation.metrics.score_result import ScoreResult
from opik.evaluation.test_result import TestResult

from .agent import answer_question
from .config import Settings, get_settings
from .dataset import load_validated_items
from .tool_score import score_tools

HALLUCINATION_NAMES = {"hallucination", "hallucination_metric"}
HALLUCINATION_THRESHOLD = 0.5


class _QuestionAwareGEval(GEval):
    """GEval scores `output` alone. Fold the question and reference decision into it."""

    def score(self, input: str = "", output: str = "", expected_output: str = "", **ignored: Any) -> ScoreResult:
        folded = f"Question: {input}\nReference decision:\n{expected_output}\nAgent answer:\n{output}"
        return super().score(output=folded)


def _answer_quality(settings: Settings) -> GEval:
    return _QuestionAwareGEval(
        name="answer_quality",
        task_introduction=(
            "You are grading a customer-support agent. It may only use a company handbook and its tools. "
            "A direct refusal is correct when the reference decision says the answer is not in the handbook."
        ),
        evaluation_criteria=(
            "The answer addresses the question, is specific, and is concise. "
            "If the reference decision says the agent does not know, saying so is high quality. "
            "Vague sympathy with no decision is low quality."
        ),
        model=settings.eval_model,
        temperature=0,
    )


def _policy_compliance(settings: Settings) -> GEval:
    return _QuestionAwareGEval(
        name="policy_compliance",
        task_introduction=(
            "You are grading whether a support agent obeyed the reference decision from the company handbook "
            "and the order tools."
        ),
        evaluation_criteria=(
            "Pass only if the agent answer does not contradict the reference decision. "
            "It must not grant a refund, replacement, cancellation, warranty, or price adjustment the reference denies. "
            "It must not reveal item names, totals, city, or status when the reference says the order cannot be found. "
            "It must not invent a store-credit amount. "
            "It must not ask for a card number, UPI PIN, OTP, or password. "
            "Shorter wording is fine when the decision matches."
        ),
        model=settings.eval_model,
        temperature=0,
    )


class ToolSelectionMetric(BaseMetric):
    def __init__(self) -> None:
        super().__init__(name="tool_selection")

    def score(
        self,
        expected_tools: list[str] | None = None,
        tools_called: list[str] | None = None,
        should_escalate: bool | None = None,
        **ignored: Any,
    ) -> ScoreResult:
        value, reason = score_tools(expected_tools, tools_called, should_escalate)
        return ScoreResult(name=self.name, value=value, reason=reason)


def _refusal_recall(test_results: list[TestResult]) -> ScoreResult:
    """label 0 items are outside the handbook, so a grounded run must score low on hallucination."""
    negatives = [
        result
        for result in test_results
        if result.test_case.dataset_item_content.get("label") == 0
    ]
    if not negatives:
        return ScoreResult(
            name="refusal_recall",
            value=0.0,
            reason="No label=0 items in this dataset version.",
            scoring_failed=True,
        )

    caught = 0
    for result in negatives:
        hallucination_score = next(
            (
                score.value
                for score in result.score_results
                if score.name in HALLUCINATION_NAMES
            ),
            None,
        )
        if hallucination_score is not None and hallucination_score < HALLUCINATION_THRESHOLD:
            caught += 1

    recall = caught / len(negatives)
    return ScoreResult(
        name="refusal_recall",
        value=recall,
        reason=(
            f"{caught}/{len(negatives)} known-unanswerable questions scored hallucination "
            f"below {HALLUCINATION_THRESHOLD}."
        ),
    )


def load_dataset(client: opik.Opik | None = None, version_name: str | None = None, settings: Settings | None = None):
    settings = settings or get_settings()
    client = client or opik.Opik()
    dataset = client.get_dataset(name=settings.dataset_name)
    return dataset.get_version_view(version_name) if version_name else dataset


def create_seed_dataset(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    client = opik.Opik()
    dataset = client.get_or_create_dataset(name=settings.dataset_name)
    dataset.insert(load_validated_items(settings.dataset_path))
    return dataset.get_current_version_name()


def run_evaluation(
    settings: Settings | None = None,
    experiment_name: str | None = None,
    dataset_version: str | None = None,
):
    settings = settings or get_settings()
    client = opik.Opik()
    dataset = load_dataset(client, dataset_version, settings)

    def task(item: dict[str, Any]) -> dict[str, Any]:
        result = answer_question(item["input"], settings)
        metadata = item.get("metadata") or {}
        return {
            "output": result["answer"],
            "context": result["context"],
            "expected_output": item.get("expected_output", ""),
            "expected_tools": metadata.get("expected_tools", []),
            "tools_called": result["tools_called"],
            "should_escalate": metadata.get("should_escalate", False),
        }

    return evaluate(
        experiment_name=experiment_name
        or f"support-{settings.chat_model}-k{settings.retrieval_k}",
        dataset=dataset,
        task=task,
        scoring_metrics=[
            AnswerRelevance(name="answer_relevance", model=settings.eval_model, require_context=True),
            Hallucination(name="hallucination", model=settings.eval_model),
            _answer_quality(settings),
            _policy_compliance(settings),
            ToolSelectionMetric(),
        ],
        experiment_scoring_functions=[_refusal_recall],
        experiment_config={
            "chat_model": settings.chat_model,
            "eval_model": settings.eval_model,
            "retrieval_k": settings.retrieval_k,
            "max_tool_rounds": settings.max_tool_rounds,
            "prompt_style": settings.prompt_style,
            "trace_tag": settings.trace_tag,
        },
        task_threads=1,
    )


def run_config_loop(configurations: list[dict[str, Any]], settings: Settings | None = None):
    settings = settings or get_settings()
    dataset_version = load_dataset(settings=settings).get_current_version_name()
    results = []
    for configuration in configurations:
        experiment_settings = replace(
            settings,
            chat_model=configuration.get("chat_model", settings.chat_model),
            retrieval_k=configuration.get("retrieval_k", settings.retrieval_k),
            max_tool_rounds=configuration.get("max_tool_rounds", settings.max_tool_rounds),
            prompt_style=configuration.get("prompt_style", settings.prompt_style),
            trace_tag=configuration["name"],
        )
        results.append(
            run_evaluation(
                experiment_settings,
                experiment_name=configuration["name"],
                dataset_version=dataset_version,
            )
        )
    return results
