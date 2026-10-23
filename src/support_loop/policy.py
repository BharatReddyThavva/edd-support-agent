"""Refund, shipping, and escalation rules for Alder & Co.

The string values are the handbook. `data/support_handbook.md` must contain
each one verbatim, and the eval goldens quote them instead of paraphrasing.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

AS_OF = date(2026, 10, 15)
RETURN_WINDOW_DAYS = 30
DAMAGE_WINDOW_DAYS = 2
PRICE_WINDOW_DAYS = 7
WARRANTY_MONTHS = 12
WARRANTY_CATEGORIES = frozenset({"cookware", "tableware", "lighting"})

REASONS = ("return", "damaged", "cancel", "warranty", "price_adjustment")

RULES: dict[str, str] = {
    "PRIVACY": (
        "Order details are shared only when the order id and the email on the order match. "
        "Otherwise we say the order cannot be found."
    ),
    "RETURN_WINDOW": "A return request must reach us within 30 calendar days of the delivery date.",
    "RETURN_CONDITION": "The item must be unused, in its original packaging, with tags attached.",
    "RETURN_INSPECT": (
        "If the return is eligible, we accept it and inspect the item at the warehouse "
        "before paying the refund."
    ),
    "REFUND_TIMING": (
        "A refund to the original payment method is sent within 5 to 7 business days "
        "after the warehouse inspection passes."
    ),
    "STORE_CREDIT": (
        "Store credit is issued the same day the warehouse inspection passes, if you choose "
        "store credit instead of a refund to the original payment method."
    ),
    "FINAL_SALE": "Items marked final sale cannot be returned.",
    "PERSONALIZED": "Personalized or engraved items cannot be returned unless they arrive damaged.",
    "NOT_DELIVERED": (
        "A return, damage claim, or warranty claim can start only after the order status is delivered."
    ),
    "ALREADY_REFUNDED": "An order that already has a refund cannot be refunded again.",
    "DAMAGE_WINDOW": "Damage must be reported within 2 calendar days of the delivery date, photos included.",
    "DAMAGE_REMEDY": (
        "A damaged arrival is eligible for a replacement shipment, or a full refund if you "
        "refuse the replacement or the item is out of stock."
    ),
    "CANCEL_OPEN": "An order can be cancelled while its status is placed or packed.",
    "CANCEL_SHIPPED": "An order cannot be cancelled once its status is shipped or delivered.",
    "CANCEL_REFUND": (
        "A cancelled order is refunded to the original payment method within 5 to 7 business days."
    ),
    "WARRANTY_SCOPE": (
        "The 12-month warranty covers manufacturing defects in cookware, tableware, and lighting."
    ),
    "WARRANTY_SOFT": "The 12-month warranty does not cover soft goods.",
    "WARRANTY_START": "The warranty runs for 12 months from the delivery date.",
    "PRICE_WINDOW": "A price adjustment must be requested within 7 calendar days of the order date.",
    "PRICE_TERMS": (
        "The adjustment is the difference on the same SKU, once per order, paid as store credit and not as cash."
    ),
    "PRICE_NO_INVENT": "The store-credit amount is confirmed by a specialist. Do not invent the difference.",
    "EXECUTE": (
        "The agent never moves money and never changes an order. An eligible refund, replacement, "
        "cancellation, warranty review, or store credit is escalated so a specialist executes it."
    ),
    "SHIP_FREE": "Standard shipping is free on orders of \u20b92,000 or more.",
    "SHIP_STD": "Standard shipping costs \u20b979 and takes 5 to 7 business days.",
    "SHIP_EXP": "Express shipping costs \u20b9199 and takes 2 business days.",
    "SHIP_CITIES": (
        "Express shipping is available only for Bengaluru, Mumbai, Delhi, Hyderabad, Chennai, Pune, and Kolkata."
    ),
    "NEVER_ASK": "Never ask for a full card number, a UPI PIN, an OTP, or a password.",
    "OUT_OF_SCOPE": "If the handbook does not contain the answer, say you do not know and do not guess.",
    "CHARGEBACK": (
        "Mentions of a chargeback, a lawyer, or a consumer forum are escalated to a human "
        "specialist and are not decided by the agent."
    ),
    "WHOLESALE": "Alder & Co. sells retail orders only and does not open wholesale accounts.",
    "COMPETITOR": "We do not match other retailers' prices.",
    "ESCALATION_TICKET": "An escalation returns a ticket id and places the case on the specialist queue.",
    "UNKNOWN_REASON": (
        "Refund checks accept only these reasons: return, damaged, cancel, warranty, and price_adjustment."
    ),
    "AS_OF": "Eligibility in this assistant is calculated as of 15 October 2026.",
}


def as_of_long(day: date = AS_OF) -> str:
    return f"{day.day} {day.strftime('%B')} {day.year}"


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _item(order: dict[str, Any]) -> dict[str, Any]:
    return order["items"][0]


def public_order(order: dict[str, Any]) -> dict[str, Any]:
    item = _item(order)
    return {
        "order_id": order["order_id"],
        "status": order["status"],
        "placed_on": order["placed_on"],
        "delivered_on": order["delivered_on"],
        "item_name": item["name"],
        "sku": item["sku"],
        "category": item["category"],
        "final_sale": item["final_sale"],
        "personalized": item["personalized"],
        "payment_method": order["payment_method"],
        "city": order["city"],
        "total_inr": order["total_inr"],
        "refund_already_issued": order["refund_already_issued"],
    }


def not_found_payload() -> dict[str, Any]:
    return {
        "found": False,
        "eligible": False,
        "code": "ORDER_NOT_FOUND",
        "outcome": "deny",
        "should_escalate": False,
        "handbook_rule": RULES["PRIVACY"],
        "rules": [RULES["PRIVACY"]],
        "order": None,
    }


def _decision(
    order: dict[str, Any],
    code: str,
    *rule_keys: str,
    eligible: bool,
) -> dict[str, Any]:
    rules = [RULES[key] for key in rule_keys]
    return {
        "found": True,
        "eligible": eligible,
        "code": code,
        "outcome": "execute" if eligible else "deny",
        "should_escalate": eligible,
        "handbook_rule": rules[0],
        "rules": rules,
        "order": public_order(order),
    }


def _within(start: date | None, days: int, as_of: date) -> bool:
    return start is not None and as_of <= start + timedelta(days=days)


def check_refund(
    order: dict[str, Any] | None,
    reason: str,
    as_of: date = AS_OF,
) -> dict[str, Any]:
    """Decide a support action. `order` is None when the id and email do not both match."""
    if order is None:
        return not_found_payload()

    reason = reason.strip().lower()
    if reason not in REASONS:
        return _decision(order, "UNKNOWN_REASON", "UNKNOWN_REASON", eligible=False)

    if order["refund_already_issued"] and reason in {"return", "damaged", "cancel", "price_adjustment"}:
        return _decision(order, "ALREADY_REFUNDED", "ALREADY_REFUNDED", eligible=False)

    item = _item(order)
    status = order["status"]
    delivered = parse_date(order.get("delivered_on"))
    placed = parse_date(order["placed_on"])

    if reason == "cancel":
        if status in {"placed", "packed"}:
            return _decision(order, "CANCEL_ELIGIBLE", "CANCEL_OPEN", "CANCEL_REFUND", "EXECUTE", eligible=True)
        return _decision(order, "ALREADY_SHIPPED", "CANCEL_SHIPPED", eligible=False)

    if reason == "price_adjustment":
        if not _within(placed, PRICE_WINDOW_DAYS, as_of):
            return _decision(order, "PRICE_WINDOW", "PRICE_WINDOW", "COMPETITOR", eligible=False)
        return _decision(
            order,
            "PRICE_ELIGIBLE",
            "PRICE_WINDOW",
            "PRICE_TERMS",
            "PRICE_NO_INVENT",
            "EXECUTE",
            eligible=True,
        )

    if reason in {"return", "damaged", "warranty"} and status != "delivered":
        return _decision(order, "NOT_DELIVERED", "NOT_DELIVERED", eligible=False)

    if reason == "return":
        if item["final_sale"]:
            return _decision(order, "FINAL_SALE", "FINAL_SALE", eligible=False)
        if item["personalized"]:
            return _decision(order, "PERSONALIZED", "PERSONALIZED", eligible=False)
        if not _within(delivered, RETURN_WINDOW_DAYS, as_of):
            return _decision(order, "WINDOW_EXPIRED", "RETURN_WINDOW", eligible=False)
        return _decision(
            order,
            "RETURN_ELIGIBLE",
            "RETURN_WINDOW",
            "RETURN_CONDITION",
            "RETURN_INSPECT",
            "REFUND_TIMING",
            "STORE_CREDIT",
            "EXECUTE",
            eligible=True,
        )

    if reason == "damaged":
        if not _within(delivered, DAMAGE_WINDOW_DAYS, as_of):
            return _decision(order, "DAMAGE_WINDOW", "DAMAGE_WINDOW", eligible=False)
        return _decision(order, "DAMAGE_ELIGIBLE", "DAMAGE_WINDOW", "DAMAGE_REMEDY", "EXECUTE", eligible=True)

    if item["category"] not in WARRANTY_CATEGORIES:
        return _decision(order, "NO_WARRANTY", "WARRANTY_SOFT", "WARRANTY_SCOPE", eligible=False)
    if delivered is None or as_of > add_months(delivered, WARRANTY_MONTHS):
        return _decision(order, "WARRANTY_EXPIRED", "WARRANTY_START", "WARRANTY_SCOPE", eligible=False)
    return _decision(
        order,
        "WARRANTY_ELIGIBLE",
        "WARRANTY_SCOPE",
        "WARRANTY_START",
        "EXECUTE",
        eligible=True,
    )
