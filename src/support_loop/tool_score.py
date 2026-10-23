"""Deterministic tool-selection score. No judge, no network."""

from __future__ import annotations


def score_tools(
    expected_tools: list[str] | None,
    tools_called: list[str] | None,
    should_escalate: bool | None,
) -> tuple[float, str]:
    expected = set(expected_tools or [])
    called = list(tools_called or [])
    called_set = set(called)
    if not expected:
        recall = 1.0 if not called_set else 0.0
    else:
        recall = len(expected & called_set) / len(expected)
    escalate_ok = ("escalate_to_human" in called_set) == bool(should_escalate)
    value = recall if escalate_ok else min(recall, 0.5)
    reason = (
        f"called={called or ['none']}; expected={sorted(expected) or ['none']}; "
        f"should_escalate={bool(should_escalate)}; escalate_ok={escalate_ok}"
    )
    return value, reason
