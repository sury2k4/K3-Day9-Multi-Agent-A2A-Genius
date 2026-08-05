from uuid import uuid4
from .evidence import build_evidence
from .facts import load_order_facts
from .llm import LLMClient
from .policy import decide
from .schemas import CaseInput, CaseOutput, DomainReport, FinancialResolution, OutputAssessment, OutputEntities, RootCause, RootCauseAnalysis
from .verifier import verify

def run_case(case: CaseInput, data_dir, llm: LLMClient | None = None, trace=None) -> CaseOutput:
    run_id = str(uuid4())
    order_id = case.customer_request.claimed_order_id
    facts = load_order_facts(data_dir, order_id)
    if trace: trace.event(case.case_id, run_id, "intake", order_id=order_id); trace.event(case.case_id, run_id, "coordinator", order_id=order_id)
    reports = []
    llm = llm or LLMClient()
    for domain, conclusion in (("order_seller", "order and seller facts collected"), ("payment", "payment facts collected"), ("delivery", "delivery facts collected")):
        report = DomainReport(domain=domain, order_id=order_id, source_refs=[f"order:{order_id}"], facts={"item_count": len(facts.items), "payment_count": len(facts.payments)}, conclusion=conclusion, explanation=llm.explain({"order_id": order_id, "domain": domain, "item_count": len(facts.items), "payment_count": len(facts.payments)}, conclusion))
        reports.append(report)
        if trace: trace.event(case.case_id, run_id, f"{domain}_agent", order_id=order_id)
    decision = decide(facts)
    if trace: trace.event(case.case_id, run_id, "policy_agent", order_id=order_id)
    evidence = build_evidence(facts, decision)
    output = CaseOutput(case_id=case.case_id, assessment=OutputAssessment(primary_issue=decision.primary_issue, case_status=decision.case_status, confidence=decision.confidence), affected_entities=OutputEntities(order_ids=[order_id], item_ids=[f"{order_id}:{x.order_item_id}" for x in facts.items], seller_ids=list(dict.fromkeys(x.seller_id for x in facts.items)), payment_ids=[f"{order_id}:{x.payment_sequential}" for x in facts.payments]), root_cause_analysis=RootCauseAnalysis(ranked_causes=[RootCause(cause_code=decision.cause_code, rank=1)], responsible_parties=decision.responsible_parties), evidence_ids=evidence, financial_resolution=FinancialResolution(item_total_brl=float(facts.item_total), freight_total_brl=float(facts.freight_total), payment_total_brl=float(facts.payment_total), recommended_refund_brl=float(decision.recommended_refund)), resolution_actions=[decision.action])
    errors = verify(output, facts, decision)
    if trace: trace.event(case.case_id, run_id, "verifier", "ok" if not errors else "failed", order_id)
    if errors: raise ValueError("; ".join(errors))
    if trace: trace.event(case.case_id, run_id, "output_writer", order_id=order_id)
    return output
