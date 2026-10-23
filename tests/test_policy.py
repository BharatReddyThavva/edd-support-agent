from pathlib import Path

from support_loop.orders import load_orders, refund_decision
from support_loop.policy import RULES, as_of_long, check_refund

ROOT = Path(__file__).resolve().parents[1]
ORDERS = load_orders(ROOT / "data" / "orders.json")

DECISIONS = [
    ("ALD-1042", "meera.iyer@example.com", "return", "RETURN_ELIGIBLE", True),
    ("ALD-1042", "meera.iyer@example.com", "warranty", "NO_WARRANTY", False),
    ("ALD-1042", "priya.nair@example.com", "return", "ORDER_NOT_FOUND", False),
    ("ALD-1107", "arjun.desai@example.com", "return", "WINDOW_EXPIRED", False),
    ("ALD-1107", "arjun.desai@example.com", "warranty", "WARRANTY_ELIGIBLE", True),
    ("ALD-1107", "arjun.desai@example.com", "price_adjustment", "PRICE_WINDOW", False),
    ("ALD-1188", "nisha.rao@example.com", "cancel", "ALREADY_SHIPPED", False),
    ("ALD-1188", "nisha.rao@example.com", "return", "NOT_DELIVERED", False),
    ("ALD-1210", "sameera.khan@example.com", "cancel", "CANCEL_ELIGIBLE", True),
    ("ALD-1255", "vivek.nair@example.com", "return", "FINAL_SALE", False),
    ("ALD-1255", "vivek.nair@example.com", "damaged", "DAMAGE_WINDOW", False),
    ("ALD-1302", "leela.menon@example.com", "return", "PERSONALIZED", False),
    ("ALD-1302", "leela.menon@example.com", "damaged", "DAMAGE_ELIGIBLE", True),
    ("ALD-1330", "farhan.qureshi@example.com", "return", "ALREADY_REFUNDED", False),
    ("ALD-1404", "divya.shah@example.com", "warranty", "WARRANTY_ELIGIBLE", True),
    ("ALD-1419", "divya.shah@example.com", "warranty", "WARRANTY_EXPIRED", False),
    ("ALD-1500", "hari.bose@example.com", "price_adjustment", "PRICE_ELIGIBLE", True),
    ("ALD-9999", "hari.bose@example.com", "return", "ORDER_NOT_FOUND", False),
    ("ALD-1042", "meera.iyer@example.com", "exchange", "UNKNOWN_REASON", False),
]


def test_every_rule_is_in_the_handbook():
    handbook = (ROOT / "data" / "support_handbook.md").read_text()
    missing = [key for key, sentence in RULES.items() if sentence not in handbook]
    assert missing == []
    assert as_of_long() in handbook


def test_refund_decisions():
    for order_id, email, reason, code, eligible in DECISIONS:
        decision = refund_decision(ORDERS, order_id, email, reason)
        assert decision["code"] == code, decision
        assert decision["eligible"] is eligible
        assert decision["should_escalate"] is eligible
        assert decision["handbook_rule"] in (ROOT / "data" / "support_handbook.md").read_text()


def test_email_mismatch_does_not_leak_the_order():
    decision = check_refund(None, "return")
    rendered = str(decision)
    assert "Indigo cotton throw" not in rendered
    assert "Hyderabad" not in rendered
    assert decision["order"] is None
    looked_up = refund_decision(ORDERS, "ALD-1042", "priya.nair@example.com", "return")
    assert "Indigo" not in str(looked_up)
