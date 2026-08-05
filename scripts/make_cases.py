import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INPUT = ROOT / "input"

def read(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def stamp(value):
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S") if value else None

orders = read("olist_orders_dataset.csv")
items = read("olist_order_items_dataset.csv")
payments = read("olist_order_payments_dataset.csv")
by_items = defaultdict(list)
by_payments = defaultdict(list)
for row in items:
    by_items[row["order_id"]].append(row)
for row in payments:
    by_payments[row["order_id"]].append(row)

def classify(order):
    oid = order["order_id"]
    rows = by_items[oid]
    pays = by_payments[oid]
    paid = sum(float(row["payment_value"]) for row in pays)
    item_total = sum(float(row["price"]) for row in rows)
    freight = sum(float(row["freight_value"]) for row in rows)
    reconciled = abs(paid - item_total - freight) <= 0.10
    delivered = stamp(order["order_delivered_customer_date"])
    estimated = stamp(order["order_estimated_delivery_date"])
    carrier = stamp(order["order_delivered_carrier_date"])
    late = bool(delivered and estimated and delivered > estimated)
    seller_late = bool(late and carrier and rows and any(row["shipping_limit_date"] and carrier > stamp(row["shipping_limit_date"]) for row in rows))
    if order["order_status"] == "canceled" and paid > 0:
        return "canceled_order_paid"
    if order["order_status"] == "unavailable" and paid > 0:
        return "unavailable_order_paid"
    if seller_late:
        return "late_delivery_seller"
    if late and carrier and rows:
        return "late_delivery_logistics"
    if len(pays) >= 2 and reconciled:
        return "valid_split_payment"
    if not late and reconciled:
        return "unsupported_late_claim"
    return None

selected = []
counts = defaultdict(int)
for order in orders:
    kind = classify(order)
    if kind and counts[kind] < 10:
        selected.append(order)
        counts[kind] += 1
    if len(selected) == 50:
        break

if len(selected) != 50:
    raise SystemExit(f"only found {len(selected)} supported cases: {dict(counts)}")
INPUT.mkdir(exist_ok=True)
for index, order in enumerate(selected, 1):
    case_id = f"EC_{index:03d}"
    payload = {
        "case_id": case_id,
        "opened_at": "2018-10-18T00:00:00-03:00",
        "customer_request": {
            "language": "vi",
            "message": "Hãy kiểm tra đơn hàng, nguyên nhân và quyền lợi phù hợp.",
            "claimed_order_id": order["order_id"],
        },
        "policy_version": "EC_POLICY_V1",
    }
    (INPUT / f"{case_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(dict(counts))
