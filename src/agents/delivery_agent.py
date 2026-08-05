"""Delivery Agent.

Access: orders.csv only (order_delivered_customer_date vs
order_estimated_delivery_date). Decides whether the order, from the
customer's point of view, actually arrived late -- independent of whose
fault it was, which is left to the Policy Agent to combine with the
Order & Seller Agent's handoff-timeliness finding.
"""

from __future__ import annotations

from src.data_loader import get_data
from src.facts import compute_delivery_facts
from src.llm_client import call_json
from src.state import CaseState
from src.tracing import event

SYSTEM_PROMPT = (
    "Ban la Delivery Agent. Chi dua tren du lieu JSON (ngay giao thuc te, ngay du kien) "
    "de nhan xet don co giao tre hay khong. KHONG suy doan ly do tre neu du lieu khong the so sanh. "
    "Tra ve JSON: {\"summary\": \"<1 cau tieng Viet>\"}."
)


def delivery_node(state: CaseState) -> dict:
    case_id = state["case_id"]

    if not state["order_found"]:
        facts = {
            "delivered_customer_date": None,
            "estimated_delivery_date": None,
            "is_late": False,
            "comparable": False,
        }
        return {
            "delivery_facts": facts,
            "delivery_narrative": "Khong tim thay order_id trong du lieu Olist.",
            "trace_events": [event(case_id, "delivery", "skip_order_not_found")],
        }

    bundle = get_data().get_bundle(state["claimed_order_id"])
    facts = compute_delivery_facts(bundle)

    llm_result = call_json(
        SYSTEM_PROMPT,
        {
            "delivered_customer_date": facts["delivered_customer_date"],
            "estimated_delivery_date": facts["estimated_delivery_date"],
            "is_late": facts["is_late"],
            "comparable": facts["comparable"],
        },
    )
    narrative = llm_result["data"].get("summary", "") if llm_result["ok"] else ""

    return {
        "delivery_facts": facts,
        "delivery_narrative": narrative,
        "trace_events": [
            event(
                case_id,
                "delivery",
                "analyze",
                detail={"is_late": facts["is_late"], "comparable": facts["comparable"]},
                llm_call=llm_result,
            )
        ],
    }
