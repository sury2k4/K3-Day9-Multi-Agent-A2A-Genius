"""Order & Seller Agent.

Access: orders.csv (status, carrier date) + order_items.csv (seller_id,
shipping_limit_date) + sellers.csv. Determines order status and, per the
"muc bang giao" convention in README section 4, which seller(s) handed the
order to the carrier after their shipping_limit_date.
"""

from __future__ import annotations

from src.data_loader import get_data
from src.facts import compute_order_seller_facts
from src.llm_client import call_json
from src.state import CaseState
from src.tracing import event

SYSTEM_PROMPT = (
    "Ban la Order & Seller Agent. Ban chi duoc dua tren du lieu JSON duoc cung cap "
    "(order_status, danh sach seller, seller nao ban giao tre han shipping_limit_date). "
    "KHONG duoc bia them seller, item hay su kien khong co trong du lieu. "
    "Tra ve JSON: {\"summary\": \"<1-2 cau tieng Viet tom tat tinh trang don/seller>\"}."
)


def order_seller_node(state: CaseState) -> dict:
    case_id = state["case_id"]

    if not state["order_found"]:
        facts = {
            "order_status": None,
            "is_canceled": False,
            "is_unavailable": False,
            "seller_ids": [],
            "item_ids": [],
            "late_sellers": [],
            "late_items_by_seller": {},
            "has_items": False,
        }
        return {
            "order_facts": facts,
            "order_seller_narrative": "Khong tim thay order_id trong du lieu Olist.",
            "trace_events": [event(case_id, "order_seller", "skip_order_not_found")],
        }

    bundle = get_data().get_bundle(state["claimed_order_id"])
    facts = compute_order_seller_facts(bundle)

    llm_result = call_json(
        SYSTEM_PROMPT,
        {
            "order_status": facts["order_status"],
            "seller_ids": facts["seller_ids"],
            "late_sellers": facts["late_sellers"],
            "n_items": len(facts["item_ids"]),
        },
    )
    narrative = llm_result["data"].get("summary", "") if llm_result["ok"] else ""

    return {
        "order_facts": facts,
        "order_seller_narrative": narrative,
        "trace_events": [
            event(
                case_id,
                "order_seller",
                "analyze",
                detail={
                    "order_status": facts["order_status"],
                    "seller_ids": facts["seller_ids"],
                    "late_sellers": facts["late_sellers"],
                },
                llm_call=llm_result,
            )
        ],
    }
