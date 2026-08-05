from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol

from .schemas import (
    DeliveryReport,
    OrderItemFact,
    OrderReport,
    PaymentFact,
    PaymentReport,
)


class SourceRepository(Protocol):
    def get_order(self, order_id: str) -> dict[str, Any] | None: ...

    def get_items(self, order_id: str) -> list[dict[str, Any]]: ...

    def get_payments(self, order_id: str) -> list[dict[str, Any]]: ...


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal(0)
    return Decimal(str(value))


def _float(value: Any) -> float:
    return float(_decimal(value))


def _timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _timestamp_text(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.isoformat(sep=" ") if parsed else None


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_order_report(repository: SourceRepository, order_id: str) -> OrderReport:
    order = repository.get_order(order_id)
    rows = repository.get_items(order_id)
    items = [
        OrderItemFact(
            order_id=order_id,
            order_item_id=int(row["order_item_id"]),
            product_id=_text(row.get("product_id")),
            seller_id=_text(row.get("seller_id")),
            shipping_limit_date=_timestamp_text(row.get("shipping_limit_date")),
            price_brl=_float(row.get("price")),
            freight_brl=_float(row.get("freight_value")),
        )
        for row in rows
    ]
    seller_ids = sorted({item.seller_id for item in items if item.seller_id})
    item_total = sum((_decimal(item.price_brl) for item in items), Decimal(0))
    freight_total = sum((_decimal(item.freight_brl) for item in items), Decimal(0))
    evidence_ids = []
    if order is not None:
        evidence_ids.append(f"order:{order_id}")
    evidence_ids.extend(f"item:{order_id}:{item.order_item_id}" for item in items)
    evidence_ids.extend(f"seller:{seller_id}" for seller_id in seller_ids)
    return OrderReport(
        order_id=order_id,
        found=order is not None,
        order_status=_text(order.get("order_status")) if order else None,
        customer_id=_text(order.get("customer_id")) if order else None,
        items=items,
        seller_ids=seller_ids,
        item_total_brl=_money(item_total),
        freight_total_brl=_money(freight_total),
        evidence_ids=evidence_ids,
    )


def build_payment_report(
    repository: SourceRepository,
    order_id: str,
    order_report: OrderReport,
) -> PaymentReport:
    rows = repository.get_payments(order_id)
    payments = [
        PaymentFact(
            order_id=order_id,
            payment_sequential=int(row["payment_sequential"]),
            payment_type=_text(row.get("payment_type")),
            payment_installments=int(row.get("payment_installments") or 0),
            payment_value_brl=_float(row.get("payment_value")),
        )
        for row in rows
    ]
    payment_total = sum(
        (_decimal(payment.payment_value_brl) for payment in payments),
        Decimal(0),
    )
    item_total = _decimal(order_report.item_total_brl)
    freight_total = _decimal(order_report.freight_total_brl)
    difference = payment_total - item_total - freight_total
    evidence_ids = [
        f"payment:{order_id}:{payment.payment_sequential}" for payment in payments
    ]
    return PaymentReport(
        order_id=order_id,
        payments=payments,
        payment_row_count=len(payments),
        payment_total_brl=_money(payment_total),
        item_total_brl=_money(item_total),
        freight_total_brl=_money(freight_total),
        reconciliation_difference_brl=_money(difference),
        matches_item_plus_freight=bool(payments)
        and abs(difference) <= Decimal("0.10"),
        evidence_ids=evidence_ids,
    )


def build_delivery_report(
    repository: SourceRepository,
    order_id: str,
    order_report: OrderReport,
) -> DeliveryReport:
    order = repository.get_order(order_id)
    if order is None:
        return DeliveryReport(order_id=order_id, delivery_outcome="unknown")

    estimated = _timestamp(order.get("order_estimated_delivery_date"))
    delivered = _timestamp(order.get("order_delivered_customer_date"))
    carrier = _timestamp(order.get("order_delivered_carrier_date"))
    if delivered is None or estimated is None:
        outcome = "unknown"
    elif delivered > estimated:
        outcome = "late"
    else:
        outcome = "on_time"

    late_sellers: set[str] = set()
    comparable = 0
    for item in order_report.items:
        shipping_limit = _timestamp(item.shipping_limit_date)
        if carrier is not None and shipping_limit is not None:
            comparable += 1
            if carrier > shipping_limit and item.seller_id:
                late_sellers.add(item.seller_id)

    evidence_ids = [f"order:{order_id}"]
    evidence_ids.extend(
        f"item:{order_id}:{item.order_item_id}" for item in order_report.items
    )
    evidence_ids.extend(f"seller:{seller_id}" for seller_id in sorted(late_sellers))
    return DeliveryReport(
        order_id=order_id,
        delivery_outcome=outcome,
        estimated_delivery_date=_timestamp_text(order.get("order_estimated_delivery_date")),
        delivered_customer_date=_timestamp_text(order.get("order_delivered_customer_date")),
        delivered_carrier_date=_timestamp_text(order.get("order_delivered_carrier_date")),
        late_seller_ids=sorted(late_sellers),
        comparable_item_count=comparable,
        evidence_ids=evidence_ids,
    )
