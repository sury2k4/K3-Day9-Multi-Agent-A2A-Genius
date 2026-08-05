import re
from decimal import Decimal
from .money import money, reconciles
from .schemas import CaseOutput, OrderFacts, PolicyDecision

EVIDENCE = re.compile(r"^(order:[^:]+|item:[^:]+:\d+|payment:[^:]+:\d+|seller:[^:]+|policy:[A-Z_]+)$")

ALLOWED_ACTIONS = {"issue_full_refund", "refund_freight", "explain_valid_split_payment", "reject_late_refund"}


def verify(output: CaseOutput, facts: OrderFacts, decision: PolicyDecision, expected_case_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if expected_case_id is not None and output.case_id != expected_case_id: errors.append("case id/file mismatch")
    if not output.evidence_ids: errors.append("evidence missing")
    if len(set(output.evidence_ids)) != len(output.evidence_ids): errors.append("duplicate evidence")
    if len(set(output.resolution_actions)) != len(output.resolution_actions): errors.append("duplicate actions")
    if any(action not in ALLOWED_ACTIONS for action in output.resolution_actions): errors.append("unknown action")
    if any(root.rank != index for index, root in enumerate(output.root_cause_analysis.ranked_causes, 1)): errors.append("invalid root cause rank")
    if len(output.root_cause_analysis.responsible_parties) > 3: errors.append("too many responsible parties")
    if len(output.affected_entities.order_ids) > 5 or len(output.affected_entities.item_ids) > 5 or len(output.affected_entities.seller_ids) > 5 or len(output.affected_entities.payment_ids) > 5: errors.append("entity limit exceeded")
    if len(output.evidence_ids) > 10: errors.append("evidence limit exceeded")
    if len(output.resolution_actions) > 5: errors.append("action limit exceeded")
    if output.assessment.confidence != decision.confidence: errors.append("confidence mismatch")
    if output.case_id == "": errors.append("case_id missing")
    if output.assessment.primary_issue != decision.primary_issue: errors.append("primary issue mismatch")
    if output.assessment.case_status != decision.case_status: errors.append("case status mismatch")
    if not output.root_cause_analysis.ranked_causes: errors.append("root cause missing")
    elif output.root_cause_analysis.ranked_causes[0].cause_code != decision.cause_code: errors.append("root cause mismatch")
    if output.root_cause_analysis.responsible_parties != decision.responsible_parties: errors.append("responsible party mismatch")
    if output.affected_entities.order_ids != [facts.order_id]: errors.append("order entity mismatch")
    expected_items = [f"{facts.order_id}:{item.order_item_id}" for item in facts.items]
    expected_sellers = list(dict.fromkeys(item.seller_id for item in facts.items))
    expected_payments = [f"{facts.order_id}:{payment.payment_sequential}" for payment in facts.payments]
    if output.affected_entities.item_ids != expected_items: errors.append("item entity mismatch")
    if output.affected_entities.seller_ids != expected_sellers: errors.append("seller entity mismatch")
    if output.affected_entities.payment_ids != expected_payments: errors.append("payment entity mismatch")
    if output.assessment.confidence != decision.confidence: errors.append("confidence mismatch")
    fin = output.financial_resolution
    expected = (money(facts.item_total), money(facts.freight_total), money(facts.payment_total), money(decision.recommended_refund))
    actual = tuple(money(x) for x in (fin.item_total_brl, fin.freight_total_brl, fin.payment_total_brl, fin.recommended_refund_brl))
    if actual != expected: errors.append("financial resolution mismatch")
    if money(fin.recommended_refund_brl) > 0 and output.assessment.case_status != "action_required": errors.append("refund status mismatch")
    if money(fin.recommended_refund_brl) == 0 and output.assessment.case_status != "no_action": errors.append("no-refund status mismatch")
    valid = {f"order:{facts.order_id}"} | {f"item:{facts.order_id}:{x.order_item_id}" for x in facts.items} | {f"payment:{facts.order_id}:{x.payment_sequential}" for x in facts.payments} | {f"seller:{x.seller_id}" for x in facts.items} | {f"policy:{decision.cause_code}"}
    for evidence_id in output.evidence_ids:
        if not EVIDENCE.fullmatch(evidence_id) or evidence_id not in valid: errors.append(f"invalid evidence: {evidence_id}")
    if output.resolution_actions != [decision.action]: errors.append("action mismatch")
    return errors
