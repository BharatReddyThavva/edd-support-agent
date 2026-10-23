"""Validate `evals/seed.jsonl` before it is pushed to Opik."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {"input", "expected_output", "metadata", "label", "critique"}
CASE_TYPES = {"policy", "order", "refusal"}
TOOL_NAMES = {"search_handbook", "get_order", "check_refund_eligibility", "escalate_to_human"}


def load_items(path: Path) -> list[dict[str, Any]]:
    with path.open() as dataset_file:
        return [json.loads(line) for line in dataset_file if line.strip()]


def validate_items(items: list[dict[str, Any]]) -> None:
    if not items:
        raise ValueError("Dataset is empty")
    for position, item in enumerate(items, start=1):
        missing = REQUIRED_FIELDS.difference(item)
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"Dataset item {position} is missing: {fields}")
        if not isinstance(item["input"], str) or not item["input"].strip():
            raise ValueError(f"Dataset item {position} input must be a non-empty string")
        if not isinstance(item["expected_output"], str) or not item["expected_output"].strip():
            raise ValueError(f"Dataset item {position} expected_output must be a non-empty string")
        metadata = item["metadata"]
        if not isinstance(metadata, dict):
            raise ValueError(f"Dataset item {position} metadata must be an object")
        if not isinstance(metadata.get("source"), str):
            raise ValueError(f"Dataset item {position} metadata.source must be a string")
        if metadata.get("case_type") not in CASE_TYPES:
            raise ValueError(f"Dataset item {position} metadata.case_type is invalid")
        if not isinstance(metadata.get("section"), str):
            raise ValueError(f"Dataset item {position} metadata.section must be a string")
        tools = metadata.get("expected_tools")
        if not isinstance(tools, list) or any(tool not in TOOL_NAMES for tool in tools):
            raise ValueError(f"Dataset item {position} metadata.expected_tools is invalid")
        if not isinstance(metadata.get("should_escalate"), bool):
            raise ValueError(f"Dataset item {position} metadata.should_escalate must be a boolean")
        quotes = metadata.get("quotes")
        if not isinstance(quotes, list) or any(not isinstance(quote, str) or not quote for quote in quotes):
            raise ValueError(f"Dataset item {position} metadata.quotes must be a list of strings")
        if item["label"] not in (0, 1):
            raise ValueError(f"Dataset item {position} label must be 0 or 1")
        if item["label"] == 0 and metadata["case_type"] != "refusal":
            raise ValueError(f"Dataset item {position} label 0 is only for refusal cases")
        if item["label"] == 1 and not quotes:
            raise ValueError(f"Dataset item {position} label 1 must quote the handbook")
        if not isinstance(item["critique"], str) or not item["critique"].strip():
            raise ValueError(f"Dataset item {position} critique must be a string")


def load_validated_items(path: Path) -> list[dict[str, Any]]:
    items = load_items(path)
    validate_items(items)
    return items
