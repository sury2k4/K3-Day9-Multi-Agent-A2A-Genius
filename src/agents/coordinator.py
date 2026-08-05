"""Coordinator Agent: intake (parse case, resolve order, route) and final
aggregation (merge every agent's handoff into the graded output schema).

Access: orders.csv only, via data_loader.get_bundle (existence check). All
financial/entity numbers in the aggregated draft come from the other
agents' deterministic facts -- the coordinator does not recompute them.
"""

from __future__ import annotations

from src.config import CURRENCY, POLICY_VERSION
from src.data_loader import get_data
from src.llm_client import call_json
from src.state import CaseState
from src.tracing import event

INTAKE_SYSTEM_PROMPT = (
    "Ban la Coordinator Agent trong he thong xu ly khieu nai thuong mai dien tu. "
    "Doc tin nhan khach hang va chi phan loai NHAN DINH BE MAT cua khach (khong ket luan dung/sai). "
    "Chi tra ve JSON dung dinh dang: "
    '{"complaint_hint": "late_delivery|cancellation|unavailable|payment_confusion|other", '
    '"customer_tone": "neutral|annoyed|angry"}. '
    "Khong duoc bia thong tin ngoai noi dung tin nhan."
)


def coordinator_intake(state: CaseState) -> dict:
    input_case = state["input_case"]
    case_id = input_case["case_id"]
    claimed_order_id = input_case["customer_request"]["claimed_order_id"]
    customer_message = input_case["customer_request"]["message"]

    data = get_data()
    bundle = data.get_bundle(claimed_order_id)

    llm_result = call_json(
        INTAKE_SYSTEM_PROMPT,
        {"customer_message": customer_message},
    )

    return {
        "claimed_order_id": claimed_order_id,
        "customer_message": customer_message,
        "order_found": bundle.order_found,
        "intake_hint": llm_result["data"] if llm_result["ok"] else {},
        "trace_events": [
            event(
                case_id,
                "coordinator",
                "intake",
                detail={
                    "claimed_order_id": claimed_order_id,
                    "order_found": bundle.order_found,
                    "intake_hint": llm_result["data"] if llm_result["ok"] else None,
                },
                llm_call=llm_result,
            )
        ],
    }


def coordinator_finalize(state: CaseState) -> dict:
    case_id = state["case_id"]
    policy_result: dict = state["policy_result"]

    draft_output = {
        "case_id": case_id,
        "assessment": {
            "primary_issue": policy_result["primary_issue"],
            "case_status": policy_result["case_status"],
            "confidence": round(policy_result["confidence"], 2),
        },
        "affected_entities": {
            "order_ids": policy_result["order_ids"],
            "item_ids": policy_result["item_ids"],
            "seller_ids": policy_result["seller_ids"],
            "payment_ids": policy_result["payment_ids"],
        },
        "root_cause_analysis": {
            "ranked_causes": [{"cause_code": policy_result["root_cause_code"], "rank": 1}],
            "responsible_parties": policy_result["responsible_parties"],
        },
        "evidence_ids": policy_result["evidence_ids"],
        "financial_resolution": {
            "currency": CURRENCY,
            "item_total_brl": round(state["payment_facts"]["item_total"], 2),
            "freight_total_brl": round(state["payment_facts"]["freight_total"], 2),
            "payment_total_brl": round(state["payment_facts"]["payment_total"], 2),
            "recommended_refund_brl": round(policy_result["recommended_refund_brl"], 2),
        },
        "resolution_actions": policy_result["resolution_actions"],
    }

    return {
        "draft_output": draft_output,
        "trace_events": [
            event(
                case_id,
                "coordinator",
                "aggregate",
                detail={
                    "policy_version": POLICY_VERSION,
                    "primary_issue": policy_result["primary_issue"],
                },
            )
        ],
    }
