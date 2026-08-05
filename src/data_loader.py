"""Loads the Olist CSVs once and exposes read-only, per-order lookups.

Every agent goes through this module instead of touching pandas directly so
that "which CSVs an agent may read" (documented in architecture.md) is
enforced by which accessor functions it calls, and so no agent can invent an
order/item/payment/seller id that isn't actually in the dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from src.config import DATA_DIR


@dataclass
class CaseBundle:
    order_found: bool
    order: dict | None
    items: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    sellers: list[dict] = field(default_factory=list)


class OlistData:
    def __init__(self):
        self.orders = pd.read_csv(
            DATA_DIR / "olist_orders_dataset.csv",
            parse_dates=[
                "order_purchase_timestamp",
                "order_approved_at",
                "order_delivered_carrier_date",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
            ],
        )
        self.items = pd.read_csv(
            DATA_DIR / "olist_order_items_dataset.csv",
            parse_dates=["shipping_limit_date"],
        )
        self.payments = pd.read_csv(DATA_DIR / "olist_order_payments_dataset.csv")
        self.sellers = pd.read_csv(DATA_DIR / "olist_sellers_dataset.csv")

        self._orders_by_id = self.orders.set_index("order_id", drop=False)
        self._items_by_order = {
            oid: g.sort_values("order_item_id") for oid, g in self.items.groupby("order_id")
        }
        self._payments_by_order = {
            oid: g.sort_values("payment_sequential") for oid, g in self.payments.groupby("order_id")
        }
        self._sellers_by_id = self.sellers.set_index("seller_id", drop=False)

        self.valid_order_ids = set(self.orders["order_id"])
        self.valid_seller_ids = set(self.sellers["seller_id"])
        self.valid_item_keys = {
            f"{r.order_id}:{r.order_item_id}" for r in self.items.itertuples()
        }
        self.valid_payment_keys = {
            f"{r.order_id}:{r.payment_sequential}" for r in self.payments.itertuples()
        }

    @staticmethod
    def _ts(value):
        if pd.isna(value):
            return None
        return value.strftime("%Y-%m-%dT%H:%M:%S")

    def get_bundle(self, order_id: str) -> CaseBundle:
        if order_id not in self._orders_by_id.index:
            return CaseBundle(order_found=False, order=None)

        row = self._orders_by_id.loc[order_id]
        order = {
            "order_id": row["order_id"],
            "customer_id": row["customer_id"],
            "order_status": row["order_status"],
            "order_purchase_timestamp": self._ts(row["order_purchase_timestamp"]),
            "order_approved_at": self._ts(row["order_approved_at"]),
            "order_delivered_carrier_date": self._ts(row["order_delivered_carrier_date"]),
            "order_delivered_customer_date": self._ts(row["order_delivered_customer_date"]),
            "order_estimated_delivery_date": self._ts(row["order_estimated_delivery_date"]),
        }

        items = []
        for r in self._items_by_order.get(order_id, pd.DataFrame()).itertuples():
            items.append(
                {
                    "order_id": r.order_id,
                    "order_item_id": int(r.order_item_id),
                    "product_id": r.product_id,
                    "seller_id": r.seller_id,
                    "shipping_limit_date": self._ts(r.shipping_limit_date),
                    "price": float(r.price),
                    "freight_value": float(r.freight_value),
                }
            )

        payments = []
        for r in self._payments_by_order.get(order_id, pd.DataFrame()).itertuples():
            payments.append(
                {
                    "order_id": r.order_id,
                    "payment_sequential": int(r.payment_sequential),
                    "payment_type": r.payment_type,
                    "payment_installments": int(r.payment_installments),
                    "payment_value": float(r.payment_value),
                }
            )

        seller_ids = sorted({it["seller_id"] for it in items})
        sellers = []
        for sid in seller_ids:
            if sid in self._sellers_by_id.index:
                srow = self._sellers_by_id.loc[sid]
                sellers.append(
                    {
                        "seller_id": srow["seller_id"],
                        "seller_zip_code_prefix": str(srow["seller_zip_code_prefix"]),
                        "seller_city": srow["seller_city"],
                        "seller_state": srow["seller_state"],
                    }
                )

        return CaseBundle(order_found=True, order=order, items=items, payments=payments, sellers=sellers)


@lru_cache(maxsize=1)
def get_data() -> OlistData:
    return OlistData()
