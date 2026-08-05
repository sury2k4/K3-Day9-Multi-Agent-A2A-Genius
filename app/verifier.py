from __future__ import annotations

import re
from math import isclose
from typing import Any

from pydantic import ValidationError

from .schemas import CaseOutput, VerificationReport

EVIDENCE_PATTERN = re.compile(r"^(order|item|payment|seller|policy):[^:]+(?::[^:]+)?$")
ALLOWED_ACTIONS = {
    "issue_full_refund",
    "refund_freight",
    "explain_valid_split_payment",
    "reject_late_refund",
}


def _same_money(left: float, right: float) -> bool:
    return isclose(left, right, rel_tol=0, abs_tol=0.005)


def _check_entity_ids(output: CaseOutput, repository: Any, order_id: str) -> list[str]:
    errors: list[str] = []
    entities = output.affected_entities
    if len(set(entities.order_ids)) != len(entities.order_ids):
        errors.append("affected_entities.order_ids contains duplicates")
    if len(set(entities.item_ids)) != len(entities.item_ids):
        errors.append("affected_entities.item_ids contains duplicates")
    if len(set(entities.seller_ids)) != len(entities.seller_ids):
        errors.append("affected_entities.seller_ids contains duplicates")
    if len(set(entities.payment_ids)) != len(entities.payment_ids):
        errors.append("affected_entities.payment_ids contains duplicates")

    source_seller_ids = {
        str(row.get("seller_id"))
        for row in repository.get_items(order_id)
        if row.get("seller_id")
    }
    if any(value != order_id for value in entities.order_ids):
        errors.append("affected_entities.order_ids contains an unexpected order")
    for item_id in entities.item_ids:
        parts = item_id.split(":")
        if len(parts) != 2 or parts[0] != order_id:
            errors.append(f"invalid item entity ID: {item_id}")
        elif not repository.evidence_exists(f"item:{parts[0]}:{parts[1]}"):
            errors.append(f"item entity does not exist: {item_id}")
    for seller_id in entities.seller_ids:
        if not repository.evidence_exists(f"seller:{seller_id}"):
            errors.append(f"seller entity does not exist: {seller_id}")
        elif seller_id not in source_seller_ids:
            errors.append(f"seller entity is not attached to the claimed order: {seller_id}")
    for payment_id in entities.payment_ids:
        parts = payment_id.split(":")
        if len(parts) != 2 or parts[0] != order_id:
            errors.append(f"invalid payment entity ID: {payment_id}")
        elif not repository.evidence_exists(f"payment:{parts[0]}:{parts[1]}"):
            errors.append(f"payment entity does not exist: {payment_id}")
    return errors


def verify_case_output(
    candidate_payload: dict[str, Any],
    expected_payload: dict[str, Any],
    case_id: str,
    order_id: str,
    repository: Any,
) -> VerificationReport:
    errors: list[str] = []
    try:
        candidate = CaseOutput.model_validate(candidate_payload)
        expected = CaseOutput.model_validate(expected_payload)
    except ValidationError as exc:
        return VerificationReport(valid=False, errors=[f"schema validation: {exc}"])

    if candidate.case_id != case_id:
        errors.append("case_id does not match the input filename")

    if len(set(candidate.evidence_ids)) != len(candidate.evidence_ids):
        errors.append("evidence_ids contains duplicates")
    ranks = [cause.rank for cause in candidate.root_cause_analysis.ranked_causes]
    if len(set(ranks)) != len(ranks):
        errors.append("ranked_causes contains duplicate ranks")
    if len(set(candidate.resolution_actions)) != len(candidate.resolution_actions):
        errors.append("resolution_actions contains duplicates")

    # All policy-bearing fields must remain identical to the deterministic engine.
    if candidate.assessment.primary_issue != expected.assessment.primary_issue:
        errors.append("primary_issue differs from deterministic Policy Engine")
    if candidate.assessment.case_status != expected.assessment.case_status:
        errors.append("case_status differs from deterministic Policy Engine")
    if candidate.root_cause_analysis != expected.root_cause_analysis:
        errors.append("root_cause_analysis differs from deterministic Policy Engine")
    if candidate.resolution_actions != expected.resolution_actions:
        errors.append("resolution_actions differs from deterministic Policy Engine")
    if candidate.affected_entities != expected.affected_entities:
        errors.append("affected_entities differs from deterministic source join")

    candidate_money = candidate.financial_resolution
    expected_money = expected.financial_resolution
    for field in (
        "item_total_brl",
        "freight_total_brl",
        "payment_total_brl",
        "recommended_refund_brl",
    ):
        if not _same_money(getattr(candidate_money, field), getattr(expected_money, field)):
            errors.append(f"financial_resolution.{field} is incorrect")

    if any(action not in ALLOWED_ACTIONS for action in candidate.resolution_actions):
        errors.append("resolution_actions contains an unsupported action")
    if candidate.assessment.case_status == "action_required" and candidate_money.recommended_refund_brl <= 0:
        errors.append("action_required requires a positive refund")
    if candidate.assessment.case_status == "no_action" and candidate_money.recommended_refund_brl != 0:
        errors.append("no_action requires a zero refund")

    errors.extend(_check_entity_ids(candidate, repository, order_id))
    if not candidate.affected_entities.order_ids and repository.get_order(order_id) is not None:
        errors.append("known order must appear in affected_entities.order_ids")

    for evidence_id in candidate.evidence_ids:
        if not EVIDENCE_PATTERN.match(evidence_id):
            errors.append(f"invalid evidence ID format: {evidence_id}")
        elif not repository.evidence_exists(evidence_id):
            errors.append(f"evidence ID does not exist in source data: {evidence_id}")

    policy_evidence = [
        evidence_id for evidence_id in candidate.evidence_ids if evidence_id.startswith("policy:")
    ]
    cause_codes = [cause.cause_code for cause in candidate.root_cause_analysis.ranked_causes]
    if len(policy_evidence) != 1:
        errors.append("exactly one policy evidence ID is required")
    elif cause_codes and policy_evidence[0].split(":", 1)[1] != cause_codes[0]:
        errors.append("policy evidence does not match the ranked root cause")

    return VerificationReport(
        valid=not errors,
        errors=errors,
        checked_evidence_count=len(candidate.evidence_ids),
    )
