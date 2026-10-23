import json
from pathlib import Path

from support_loop.dataset import load_validated_items
from support_loop.orders import load_orders, refund_decision

ROOT = Path(__file__).resolve().parents[1]


def test_seed_quotes_and_decisions_match_the_source():
    handbook = (ROOT / "data" / "support_handbook.md").read_text()
    orders = load_orders(ROOT / "data" / "orders.json")
    items = load_validated_items(ROOT / "evals" / "seed.jsonl")
    assert len(items) >= 20
    labels = {item["label"] for item in items}
    assert labels == {0, 1}
    assert sum(item["label"] == 0 for item in items) >= 4

    for item in items:
        metadata = item["metadata"]
        for quote in metadata["quotes"]:
            assert quote in handbook
            assert quote in item["expected_output"]
        assert ("escalate_to_human" in metadata["expected_tools"]) is metadata["should_escalate"]
        if "eligibility_code" not in metadata:
            continue
        decision = refund_decision(orders, metadata["order_id"], metadata["email"], metadata["reason"])
        assert decision["code"] == metadata["eligibility_code"]
        assert decision["should_escalate"] is metadata["should_escalate"] or metadata["expected_tools"] == [
            "search_handbook",
            "get_order",
            "escalate_to_human",
        ]
        if decision["code"] == "ORDER_NOT_FOUND":
            real = next(order for order in orders if order["order_id"] == metadata["order_id"])
            assert real["items"][0]["name"] not in item["expected_output"]
            assert real["city"] not in item["expected_output"]


def test_experiments_point_at_known_metrics():
    experiments = json.loads((ROOT / "evals" / "experiments.json").read_text())
    names = [experiment["name"] for experiment in experiments]
    assert names[0] == "baseline"
    assert experiments[0]["acceptance"]["compare_against"] is None
    for experiment in experiments[1:]:
        assert experiment["acceptance"]["compare_against"] in names
