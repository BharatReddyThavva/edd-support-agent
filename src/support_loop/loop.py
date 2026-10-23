"""One experiment at a time: score it, keep the code, or put the code back."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .evals import load_dataset, run_evaluation
from .results import save_result, to_result_record
from .verdict import Verdict, decide

SOURCE_PATHS = ["src"]
RECORD_PATHS = ["evals/experiments.json", "evals/results"]


def load_experiments(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def settings_for(experiment: dict[str, Any], settings: Settings) -> Settings:
    return replace(
        settings,
        chat_model=experiment.get("chat_model", settings.chat_model),
        retrieval_k=experiment.get("retrieval_k", settings.retrieval_k),
        max_tool_rounds=experiment.get("max_tool_rounds", settings.max_tool_rounds),
        prompt_style=experiment.get("prompt_style", settings.prompt_style),
        trace_tag=experiment["name"],
    )


def run_experiment(
    experiment: dict[str, Any],
    settings: Settings | None = None,
    dataset_version: str | None = None,
) -> dict[str, Any]:
    settings = settings_for(experiment, settings or get_settings())
    evaluation = run_evaluation(
        settings,
        experiment_name=experiment["name"],
        dataset_version=dataset_version,
    )
    return {
        "name": experiment["name"],
        "change": experiment["change"],
        "acceptance": experiment.get("acceptance", {}),
        "evaluation": evaluation,
    }


def run_experiment_loop(
    experiments_path: Path = Path("evals/experiments.json"),
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    dataset_version = load_dataset(settings=settings).get_current_version_name()
    return [
        run_experiment(experiment, settings, dataset_version)
        for experiment in load_experiments(experiments_path)
    ]


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def _commit(paths: list[str], message: str) -> None:
    _git("add", *paths)
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    _git("commit", "-m", message)


def _revert(paths: list[str]) -> None:
    _git("restore", "--worktree", "--staged", *paths)


def run_iteration(
    name: str,
    experiments_path: Path = Path("evals/experiments.json"),
    settings: Settings | None = None,
) -> Verdict:
    experiments = load_experiments(experiments_path)
    entry = next((experiment for experiment in experiments if experiment["name"] == name), None)
    if entry is None:
        raise ValueError(f"No entry named {name!r} in {experiments_path}")

    dataset_version = load_dataset(settings=settings).get_current_version_name()
    result = run_experiment(entry, settings, dataset_version)
    save_result(to_result_record(result))

    verdict = decide(name, experiments)
    comparisons = verdict.comparisons
    entry["result"] = {
        "decision": verdict.decision,
        "reason": verdict.reason,
        "plateaued": verdict.plateaued,
        "flat": bool(comparisons) and all(item.delta is not None and item.delta == 0 for item in comparisons),
        "comparisons": [asdict(item) for item in comparisons],
    }
    experiments_path.write_text(json.dumps(experiments, indent=2) + "\n")

    if verdict.decision == "reject":
        _revert(SOURCE_PATHS)
        _commit(RECORD_PATHS, f"{name} (rejected): {entry['change']}")
    else:
        _commit(SOURCE_PATHS + RECORD_PATHS, f"{name}: {entry['change']}")
    return verdict
