#!/usr/bin/env python3
"""Generate a balanced, deterministic 50-case development batch from Olist data.

These cases are useful for local integration tests. They are not the official
competition inputs and should be replaced when the instructor-provided batch is
available.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

TOLERANCE = Decimal("0.10")


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def text(value: object) -> str:
    return "" if value is None else str(value).strip()


def money(value: object) -> Decimal:
    raw = text(value)
    return Decimal(raw) if raw else Decimal(0)


def timestamp(value: object) -> datetime | None:
    raw = text(value)
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def classify_orders(data_dir: Path) -> dict[str, list[str]]:
    orders = {row["order_id"]: row for row in load_csv(data_dir / "olist_orders_dataset.csv")}
    items_by_order: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_csv(data_dir / "olist_order_items_dataset.csv"):
        items_by_order[row["order_id"]].append(row)
    payments_by_order: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in load_csv(data_dir / "olist_order_payments_dataset.csv"):
        payments_by_order[row["order_id"]].append(row)

    candidates: defaultdict[str, list[str]] = defaultdict(list)
    for order_id in sorted(orders):
        order = orders[order_id]
        items = items_by_order.get(order_id, [])
        payments = payments_by_order.get(order_id, [])
        item_total = sum((money(row.get("price")) for row in items), Decimal(0))
        freight_total = sum((money(row.get("freight_value")) for row in items), Decimal(0))
        payment_total = sum((money(row.get("payment_value")) for row in payments), Decimal(0))
        payment_matches = bool(payments) and abs(payment_total - item_total - freight_total) <= TOLERANCE

        estimated = timestamp(order.get("order_estimated_delivery_date"))
        delivered = timestamp(order.get("order_delivered_customer_date"))
        carrier = timestamp(order.get("order_delivered_carrier_date"))
        delivery_late = delivered is not None and estimated is not None and delivered > estimated
        delivery_on_time = delivered is not None and estimated is not None and delivered <= estimated

        late_sellers: set[str] = set()
        comparable = 0
        for item in items:
            shipping_limit = timestamp(item.get("shipping_limit_date"))
            if carrier is not None and shipping_limit is not None:
                comparable += 1
                if carrier > shipping_limit:
                    late_sellers.add(text(item.get("seller_id")))

        status = text(order.get("order_status"))
        if status == "canceled" and payment_total > 0:
            category = "canceled_order_paid"
        elif status == "unavailable" and payment_total > 0:
            category = "unavailable_order_paid"
        elif delivery_late and len(late_sellers) == 1:
            category = "late_delivery_seller"
        elif delivery_late and comparable > 0 and not late_sellers:
            category = "late_delivery_logistics"
        elif delivery_on_time and payment_matches and len(payments) >= 2:
            category = "valid_split_payment"
        elif delivery_on_time and payment_matches:
            category = "unsupported_late_claim"
        else:
            continue
        candidates[category].append(order_id)
    return dict(candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--input-dir", type=Path, default=Path("input"))
    args = parser.parse_args()

    quotas = {
        "canceled_order_paid": 8,
        "unavailable_order_paid": 8,
        "late_delivery_seller": 8,
        "late_delivery_logistics": 8,
        "valid_split_payment": 8,
        "unsupported_late_claim": 10,
    }
    messages = {
        "canceled_order_paid": "Đơn hàng của tôi đã bị hủy nhưng tôi đã thanh toán. Hãy kiểm tra và hoàn tiền.",
        "unavailable_order_paid": "Đơn hàng không thể thực hiện nhưng tôi đã thanh toán. Hãy kiểm tra quyền lợi hoàn tiền.",
        "late_delivery_seller": "Đơn hàng giao trễ. Hãy kiểm tra seller có bàn giao hàng sau thời hạn hay không.",
        "late_delivery_logistics": "Đơn hàng giao trễ dù seller có thể đã bàn giao đúng hạn. Hãy kiểm tra đơn vị vận chuyển.",
        "valid_split_payment": "Tôi thấy đơn hàng có nhiều giao dịch thanh toán. Hãy đối soát xem có hợp lệ không.",
        "unsupported_late_claim": "Đơn hàng của tôi có dấu hiệu giao trễ. Hãy kiểm tra nguyên nhân và quyền lợi phù hợp.",
    }
    candidates = classify_orders(args.data_dir)
    selected: list[tuple[str, str]] = []
    for category, quota in quotas.items():
        available = candidates.get(category, [])
        if len(available) < quota:
            raise RuntimeError(
                f"Not enough data for {category}: need {quota}, found {len(available)}"
            )
        selected.extend((category, order_id) for order_id in available[:quota])

    args.input_dir.mkdir(parents=True, exist_ok=True)
    for index, (category, order_id) in enumerate(selected, start=1):
        case = {
            "case_id": f"EC_{index:03d}",
            "opened_at": "2018-10-18T00:00:00-03:00",
            "customer_request": {
                "language": "vi",
                "message": messages[category],
                "claimed_order_id": order_id,
            },
            "policy_version": "EC_POLICY_V1",
        }
        (args.input_dir / f"EC_{index:03d}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Generated {len(selected)} development cases in {args.input_dir}")
    for category, quota in quotas.items():
        print(f"  {category}: {quota}")
    print("These inputs are local development fixtures, not official competition inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

