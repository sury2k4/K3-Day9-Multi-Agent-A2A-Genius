"""Deterministic fact extraction, one function per agent's data domain.

Every number and boolean that ends up in the graded output is computed here
in plain Python from the raw CSV rows in a CaseBundle -- never by an LLM --
so financial_resolution and evidence_ids stay exact and reproducible. The
LLM calls in each agent only narrate/rank what these functions already
decided; they cannot change the numbers.
"""

from __future__ import annotations

from datetime import datetime

from src.data_loader import CaseBundle

ROUND_TOLERANCE_BRL = 0.10


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")


def compute_order_seller_facts(bundle: CaseBundle) -> dict:
    """Order & Seller Agent domain: orders.csv + order_items.csv + sellers.csv."""
    order = bundle.order
    is_canceled = order["order_status"] == "canceled"
    is_unavailable = order["order_status"] == "unavailable"

    carrier_date = _parse(order["order_delivered_carrier_date"])
    seller_ids = sorted({it["seller_id"] for it in bundle.items})

    late_sellers: list[str] = []
    late_items_by_seller: dict[str, list[dict]] = {}
    if carrier_date is not None:
        for seller_id in seller_ids:
            seller_items = [it for it in bundle.items if it["seller_id"] == seller_id]
            violated = [
                it for it in seller_items
                if _parse(it["shipping_limit_date"]) is not None
                and carrier_date > _parse(it["shipping_limit_date"])
            ]
            if violated:
                late_sellers.append(seller_id)
                late_items_by_seller[seller_id] = violated

    return {
        "order_status": order["order_status"],
        "is_canceled": is_canceled,
        "is_unavailable": is_unavailable,
        "seller_ids": seller_ids,
        "item_ids": [f"{it['order_id']}:{it['order_item_id']}" for it in bundle.items],
        "late_sellers": late_sellers,
        "late_items_by_seller": late_items_by_seller,
        "has_items": len(bundle.items) > 0,
    }


def compute_delivery_facts(bundle: CaseBundle) -> dict:
    """Delivery Agent domain: orders.csv only (customer-facing delivery dates)."""
    order = bundle.order
    delivered = _parse(order["order_delivered_customer_date"])
    estimated = _parse(order["order_estimated_delivery_date"])

    if delivered is not None and estimated is not None:
        is_late = delivered > estimated
        comparable = True
    else:
        is_late = False
        comparable = False

    return {
        "delivered_customer_date": order["order_delivered_customer_date"],
        "estimated_delivery_date": order["order_estimated_delivery_date"],
        "is_late": is_late,
        "comparable": comparable,
    }


def compute_payment_facts(bundle: CaseBundle) -> dict:
    """Payment Agent domain: order_payments.csv + order_items.csv (price/freight only)."""
    item_total = round(sum(it["price"] for it in bundle.items), 2)
    freight_total = round(sum(it["freight_value"] for it in bundle.items), 2)
    payment_total = round(sum(p["payment_value"] for p in bundle.payments), 2)
    payment_count = len(bundle.payments)
    combined = round(item_total + freight_total, 2)
    split_valid = payment_count >= 2 and abs(payment_total - combined) <= ROUND_TOLERANCE_BRL
    reconciled = abs(payment_total - combined) <= ROUND_TOLERANCE_BRL

    return {
        "item_total": item_total,
        "freight_total": freight_total,
        "payment_total": payment_total,
        "payment_count": payment_count,
        "combined_item_freight": combined,
        "split_valid": split_valid,
        "reconciled": reconciled,
        "payment_ids": [f"{p['order_id']}:{p['payment_sequential']}" for p in bundle.payments],
    }
