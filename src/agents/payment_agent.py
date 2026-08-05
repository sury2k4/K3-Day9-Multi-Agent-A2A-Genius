"""Payment Agent.

Access: order_payments.csv + order_items.csv (price/freight only, to
reconcile totals). Reconciles the sum of payment rows against item total +
freight total within the 0.10 BRL tolerance from README section 4.
"""

from __future__ import annotations

from src.data_loader import get_data
from src.facts import compute_payment_facts
from src.llm_client import call_json
from src.state import CaseState
from src.tracing import event

SYSTEM_PROMPT = (
    "Ban la Payment Agent. Chi dua tren du lieu JSON (tong item+freight, tong thanh toan, "
    "so dong thanh toan) de nhan xet viec doi soat co khop khong. KHONG bia so tien. "
    "Tra ve JSON: {\"summary\": \"<1 cau tieng Viet>\"}."
)


def payment_node(state: CaseState) -> dict:
    case_id = state["case_id"]

    if not state["order_found"]:
        facts = {
            "item_total": 0.0,
            "freight_total": 0.0,
            "payment_total": 0.0,
            "payment_count": 0,
            "combined_item_freight": 0.0,
            "split_valid": False,
            "reconciled": False,
            "payment_ids": [],
        }
        return {
            "payment_facts": facts,
            "payment_narrative": "Khong tim thay order_id trong du lieu Olist.",
            "trace_events": [event(case_id, "payment", "skip_order_not_found")],
        }

    bundle = get_data().get_bundle(state["claimed_order_id"])
    facts = compute_payment_facts(bundle)

    llm_result = call_json(
        SYSTEM_PROMPT,
        {
            "item_total": facts["item_total"],
            "freight_total": facts["freight_total"],
            "payment_total": facts["payment_total"],
            "payment_count": facts["payment_count"],
            "reconciled": facts["reconciled"],
        },
    )
    narrative = llm_result["data"].get("summary", "") if llm_result["ok"] else ""

    return {
        "payment_facts": facts,
        "payment_narrative": narrative,
        "trace_events": [
            event(
                case_id,
                "payment",
                "analyze",
                detail={
                    "payment_total": facts["payment_total"],
                    "combined_item_freight": facts["combined_item_freight"],
                    "reconciled": facts["reconciled"],
                },
                llm_call=llm_result,
            )
        ],
    }
