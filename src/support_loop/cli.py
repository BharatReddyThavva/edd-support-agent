"""Command line for the support-agent eval loop."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _print_answer(result: dict) -> None:
    print(result["answer"])
    tools = result.get("tools_called") or []
    print(f"\nTools: {', '.join(tools) if tools else 'none'}")


def _print_verdict(verdict) -> None:
    print(f"{verdict.decision}: {verdict.reason}")
    for comparison in verdict.comparisons:
        print(
            f"  {comparison.metric}: {comparison.baseline} -> {comparison.current} "
            f"(delta {comparison.delta}, {comparison.direction}-is-better)"
        )
    if verdict.plateaued:
        print("Plateaued: no metric moved on the last two kept runs. Change the structure, not the wording.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval-driven loop for the Alder & Co. support agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Validate the handbook, orders, and seed file offline")
    subparsers.add_parser("index", help="Index the support handbook into Qdrant")
    subparsers.add_parser("seed", help="Push evals/seed.jsonl to Opik as a new dataset version")
    subparsers.add_parser("evaluate", help="Score the current configuration without keep/reject")
    loop_parser = subparsers.add_parser("loop", help="Score every config in a sweep file, without keep/reject")
    loop_parser.add_argument("--config", default="evals/configs.json")
    experiment_parser = subparsers.add_parser("experiment-loop", help="Score every entry in experiments.json")
    experiment_parser.add_argument("--config", default="evals/experiments.json")
    run_parser = subparsers.add_parser("run", help="Score one named experiment and keep or revert it")
    run_parser.add_argument("name")
    run_parser.add_argument("--config", default="evals/experiments.json")
    report_parser = subparsers.add_parser("report", help="Show the worst-scoring cases for an experiment")
    report_parser.add_argument("name")
    report_parser.add_argument("--worst", type=int, default=5)
    report_parser.add_argument("--metric", default=None)
    ask_parser = subparsers.add_parser("ask", help="Ask the support agent one question")
    ask_parser.add_argument("question")
    args = parser.parse_args()

    if args.command == "check":
        from .dataset import load_validated_items
        from .orders import load_orders
        from .policy import RULES, as_of_long

        handbook = Path("data/support_handbook.md").read_text()
        missing = [key for key, sentence in RULES.items() if sentence not in handbook]
        if missing:
            raise SystemExit(f"Handbook is missing rules: {', '.join(missing)}")
        if as_of_long() not in handbook:
            raise SystemExit("Handbook is missing the frozen as-of date.")
        orders = load_orders(Path("data/orders.json"))
        items = load_validated_items(Path("evals/seed.jsonl"))
        print(f"OK: {len(RULES)} handbook rules, {len(orders)} orders, {len(items)} goldens.")
        return

    if args.command == "report":
        from .report import load_and_format

        print(load_and_format(args.name, n=args.worst, metric=args.metric))
        return

    import opik

    try:
        if args.command == "index":
            from .indexing import index_handbook

            print(f"Indexed {index_handbook()} chunks.")
        elif args.command == "seed":
            from .evals import create_seed_dataset

            print(f"Dataset version: {create_seed_dataset()}")
        elif args.command == "evaluate":
            from .evals import run_evaluation

            print(run_evaluation())
        elif args.command == "loop":
            from .evals import run_config_loop

            configurations = json.loads(Path(args.config).read_text())
            for result in run_config_loop(configurations):
                aggregated = result.aggregate_evaluation_scores().aggregated_scores
                summary = ", ".join(f"{name}={stats.mean:.3f}" for name, stats in aggregated.items())
                print(f"{result.experiment_name}: {summary}")
        elif args.command == "experiment-loop":
            from .loop import run_experiment_loop

            for result in run_experiment_loop(Path(args.config)):
                print(result["name"])
        elif args.command == "run":
            from .loop import run_iteration

            _print_verdict(run_iteration(args.name, Path(args.config)))
        else:
            from .agent import answer_question

            _print_answer(answer_question(args.question))
    finally:
        opik.flush_tracker()
