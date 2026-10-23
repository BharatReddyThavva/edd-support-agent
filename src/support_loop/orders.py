"""Fictional order book. Email mismatch looks the same as an unknown order."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .policy import check_refund, not_found_payload


def load_orders(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def find_order(orders: list[dict[str, Any]], order_id: str, email: str) -> dict[str, Any] | None:
    order_id = order_id.strip().lower()
    email = email.strip().lower()
    for order in orders:
        if order["order_id"].lower() != order_id:
            continue
        if order["email"].strip().lower() != email:
            return None
        return order
    return None


def lookup_order(orders: list[dict[str, Any]], order_id: str, email: str) -> dict[str, Any]:
    order = find_order(orders, order_id, email)
    if order is None:
        return not_found_payload()
    from .policy import public_order

    return {"found": True, "order": public_order(order), "handbook_rule": None}


def refund_decision(
    orders: list[dict[str, Any]],
    order_id: str,
    email: str,
    reason: str,
) -> dict[str, Any]:
    return check_refund(find_order(orders, order_id, email), reason)
