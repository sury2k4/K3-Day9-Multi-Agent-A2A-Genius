"""Policy Agent.

Access: no CSV access. Consumes only the structured facts handed off by
Order & Seller, Delivery and Payment agents and applies the EC_POLICY_V1
decision table (src.policy_rules.decide) in the exact priority order from
README section 4. The LLM call here only drafts the rationale text stored
in the trace -- it cannot change primary_issue, refund or actions.
"""

from __future__ import annotations

from dataclasses import asdict

from src.llm_client import call_json
from src.policy_rules import decide
from src.state import CaseState
from src.tracing import event

SYSTEM_PROMPT = (
    "Ban la Policy Agent, ap dung chinh sach EC_POLICY_V1. Ban duoc cung cap ket qua "
    "phan loai da duoc tinh toan san (primary_issue, root_cause_code, refund). "
    "Chi viet 1-2 cau giai thich ngan gon bang tieng Viet dua tren du lieu duoc cung cap, "
    "KHONG duoc thay doi hay de xuat ket qua khac. "
    "Tra ve JSON: {\"rationale\": \"<giai thich>\"}."
)


def policy_node(state: CaseState) -> dict:
    case_id = state["case_id"]

    if not state["order_found"]:
        from src.policy_rules import PolicyResult

        result = PolicyResult(
            primary_issue="unsupported_late_claim",
            case_status="no_action",
            confidence=0.05,
            root_cause_code="DELIVERY_WITHIN_ESTIMATE",
            responsible_parties=[],
            recommended_refund_brl=0.0,
            resolution_actions=["reject_late_refund"],
            order_ids=[],
            item_ids=[],
            seller_ids=[],
            payment_ids=[],
            evidence_ids=[],
        )
        return {
            "policy_result": asdict(result),
            "policy_narrative": "Khong co du lieu order xac thuc, khong the dua ket luan co bang chung.",
            "trace_events": [event(case_id, "policy", "skip_order_not_found")],
        }

    result = decide(
        order_id=state["claimed_order_id"],
        order_facts=state["order_facts"],
        delivery_facts=state["delivery_facts"],
        payment_facts=state["payment_facts"],
    )
    result_dict = asdict(result)

    llm_result = call_json(
        SYSTEM_PROMPT,
        {
            "primary_issue": result.primary_issue,
            "root_cause_code": result.root_cause_code,
            "responsible_parties": result.responsible_parties,
            "recommended_refund_brl": result.recommended_refund_brl,
            "order_seller_summary": state.get("order_seller_narrative", ""),
            "delivery_summary": state.get("delivery_narrative", ""),
            "payment_summary": state.get("payment_narrative", ""),
        },
    )
    narrative = llm_result["data"].get("rationale", "") if llm_result["ok"] else ""

    return {
        "policy_result": result_dict,
        "policy_narrative": narrative,
        "trace_events": [
            event(
                case_id,
                "policy",
                "decide",
                detail={
                    "primary_issue": result.primary_issue,
                    "case_status": result.case_status,
                    "confidence": result.confidence,
                    "root_cause_code": result.root_cause_code,
                    "recommended_refund_brl": result.recommended_refund_brl,
                },
                llm_call=llm_result,
            )
        ],
    }
