"""Verifier Agent.

Access: read-only id indices from every CSV (data_loader.valid_*), used
only to confirm evidence ids are real -- never to add new evidence. All
gate checks (array limits, confidence range, rounding, id existence) are
deterministic Python; the LLM call only produces a short audit note for
trace.jsonl and cannot override a failed check.
"""

from __future__ import annotations

from src.data_loader import get_data
from src.llm_client import call_json
from src.state import CaseState
from src.tracing import event

LIMITS = {
    "order_ids": 5,
    "item_ids": 5,
    "seller_ids": 5,
    "payment_ids": 5,
    "evidence_ids": 10,
    "ranked_causes": 3,
    "responsible_parties": 3,
    "resolution_actions": 5,
}

VALID_CASE_STATUS = {"action_required", "no_action"}

SYSTEM_PROMPT = (
    "Ban la Verifier Agent, kiem tra lan cuoi truoc khi ghi file. Ban duoc cung cap output JSON "
    "va danh sach loi da phat hien (neu co). Chi viet 1 cau nhan xet ngan gon bang tieng Viet, "
    "KHONG duoc sua so lieu. Tra ve JSON: {\"note\": \"<nhan xet>\"}."
)


def _valid_evidence_id(eid: str, data) -> bool:
    if eid.startswith("order:"):
        return eid[len("order:") :] in data.valid_order_ids
    if eid.startswith("item:"):
        return eid[len("item:") :] in data.valid_item_keys
    if eid.startswith("payment:"):
        return eid[len("payment:") :] in data.valid_payment_keys
    if eid.startswith("seller:"):
        return eid[len("seller:") :] in data.valid_seller_ids
    if eid.startswith("policy:"):
        return True
    return False


def verifier_node(state: CaseState) -> dict:
    case_id = state["case_id"]
    draft = dict(state["draft_output"])
    findings: list[str] = []
    data = get_data()

    assessment = draft["assessment"]
    if assessment["case_status"] not in VALID_CASE_STATUS:
        findings.append(f"invalid case_status '{assessment['case_status']}', reset to no_action")
        assessment["case_status"] = "no_action"
    assessment["confidence"] = max(0.0, min(1.0, round(float(assessment["confidence"]), 2)))

    entities = draft["affected_entities"]
    for key, limit in (
        ("order_ids", LIMITS["order_ids"]),
        ("item_ids", LIMITS["item_ids"]),
        ("seller_ids", LIMITS["seller_ids"]),
        ("payment_ids", LIMITS["payment_ids"]),
    ):
        if len(entities.get(key, [])) > limit:
            findings.append(f"{key} exceeded limit {limit}, truncated")
            entities[key] = entities[key][:limit]

    rca = draft["root_cause_analysis"]
    if len(rca["ranked_causes"]) > LIMITS["ranked_causes"]:
        findings.append("ranked_causes exceeded limit, truncated")
        rca["ranked_causes"] = rca["ranked_causes"][: LIMITS["ranked_causes"]]
    if len(rca["responsible_parties"]) > LIMITS["responsible_parties"]:
        findings.append("responsible_parties exceeded limit, truncated")
        rca["responsible_parties"] = rca["responsible_parties"][: LIMITS["responsible_parties"]]

    valid_evidence = [e for e in draft["evidence_ids"] if _valid_evidence_id(e, data)]
    if len(valid_evidence) != len(draft["evidence_ids"]):
        findings.append("dropped evidence_ids not backed by CSV data")
    if len(valid_evidence) > LIMITS["evidence_ids"]:
        findings.append("evidence_ids exceeded limit, truncated")
        valid_evidence = valid_evidence[: LIMITS["evidence_ids"]]
    draft["evidence_ids"] = valid_evidence

    if len(draft["resolution_actions"]) > LIMITS["resolution_actions"]:
        findings.append("resolution_actions exceeded limit, truncated")
        draft["resolution_actions"] = draft["resolution_actions"][: LIMITS["resolution_actions"]]

    fin = draft["financial_resolution"]
    for key in ("item_total_brl", "freight_total_brl", "payment_total_brl", "recommended_refund_brl"):
        fin[key] = round(float(fin[key]), 2)
    if fin["recommended_refund_brl"] < 0:
        findings.append("negative refund clamped to 0")
        fin["recommended_refund_brl"] = 0.0
    if assessment["case_status"] == "no_action" and fin["recommended_refund_brl"] != 0.0:
        findings.append("no_action case had nonzero refund, reset to 0")
        fin["recommended_refund_brl"] = 0.0

    llm_result = call_json(
        SYSTEM_PROMPT,
        {"primary_issue": assessment["primary_issue"], "findings": findings},
    )
    note = llm_result["data"].get("note", "") if llm_result["ok"] else ""

    return {
        "final_output": draft,
        "verifier_findings": findings,
        "trace_events": [
            event(
                case_id,
                "verifier",
                "verify",
                detail={"findings": findings, "note": note},
                llm_call=llm_result,
            )
        ],
    }
