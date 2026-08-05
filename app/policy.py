from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .schemas import (
    AffectedEntities,
    Assessment,
    CaseOutput,
    DeliveryReport,
    FinancialResolution,
    OrderReport,
    PaymentReport,
    PolicyDecision,
    RankedCause,
    ResponsibleParty,
    RootCauseAnalysis,
)

MONEY_QUANT = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")


def decimal_money(value: float | str | Decimal | None) -> Decimal:
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def round_money(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def bounded_unique(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def build_evidence_ids(
    order_report: OrderReport,
    payment_report: PaymentReport,
    policy_code: str,
    primary_issue: str,
    responsible_parties: list[ResponsibleParty],
) -> list[str]:
    source_ids: list[str] = []
    if order_report.found:
        source_ids.append(f"order:{order_report.order_id}")

    item_ids = [
        f"item:{item.order_id}:{item.order_item_id}"
        for item in order_report.items
    ]
    payment_ids = [
        f"payment:{payment.order_id}:{payment.payment_sequential}"
        for payment in payment_report.payments
    ]
    seller_ids = [
        f"seller:{party.party_id}"
        for party in responsible_parties
        if party.party_type == "seller"
    ]

    if primary_issue in {"canceled_order_paid", "unavailable_order_paid"}:
        source_ids.extend(payment_ids[:8])
    elif primary_issue == "late_delivery_seller":
        source_ids.extend(item_ids[:6])
        source_ids.extend(seller_ids[:3])
    elif primary_issue == "late_delivery_logistics":
        source_ids.extend(item_ids[:8])
    elif primary_issue == "valid_split_payment":
        source_ids.extend(item_ids[:4])
        source_ids.extend(payment_ids[:5])
    else:
        source_ids.extend(item_ids[:3])
        source_ids.extend(payment_ids[:3])

    source_ids = bounded_unique(source_ids, 9)
    source_ids.append(f"policy:{policy_code}")
    return bounded_unique(source_ids, 10)


def _responsible_parties(primary_issue: str, seller_ids: list[str]) -> list[ResponsibleParty]:
    if primary_issue in {"canceled_order_paid", "unavailable_order_paid"}:
        return [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")]
    if primary_issue == "late_delivery_seller":
        return [
            ResponsibleParty(party_type="seller", party_id=seller_id)
            for seller_id in seller_ids[:3]
        ]
    if primary_issue == "late_delivery_logistics":
        return [
            ResponsibleParty(
                party_type="logistics_provider",
                party_id="LOGISTICS_PROVIDER",
            )
        ]
    return []


def _decision_type(
    order_report: OrderReport,
    payment_report: PaymentReport,
    delivery_report: DeliveryReport,
) -> tuple[str, str, float, float, list[str], bool]:
    """Return issue, root cause, confidence, refund, actions, fallback flag."""

    status = order_report.order_status or ""
    payment_total = decimal_money(payment_report.payment_total_brl)
    freight_total = decimal_money(order_report.freight_total_brl)

    # This order is authoritative and follows the assignment's priority exactly.
    if status == "canceled" and payment_total > 0:
        return (
            "canceled_order_paid",
            "ORDER_CANCELED_AFTER_PAYMENT",
            0.99,
            round_money(payment_total),
            ["issue_full_refund"],
            False,
        )
    if status == "unavailable" and payment_total > 0:
        return (
            "unavailable_order_paid",
            "ORDER_UNAVAILABLE_AFTER_PAYMENT",
            0.99,
            round_money(payment_total),
            ["issue_full_refund"],
            False,
        )
    if delivery_report.delivery_outcome == "late" and delivery_report.late_seller_ids:
        return (
            "late_delivery_seller",
            "SELLER_HANDOFF_AFTER_LIMIT",
            0.97,
            round_money(freight_total),
            ["refund_freight"],
            False,
        )
    if (
        delivery_report.delivery_outcome == "late"
        and delivery_report.comparable_item_count > 0
        and not delivery_report.late_seller_ids
    ):
        return (
            "late_delivery_logistics",
            "CARRIER_DELIVERED_AFTER_ESTIMATE",
            0.97,
            round_money(freight_total),
            ["refund_freight"],
            False,
        )
    if (
        payment_report.matches_item_plus_freight
        and payment_report.payment_row_count >= 2
    ):
        return (
            "valid_split_payment",
            "MULTIPLE_PAYMENTS_RECONCILED",
            0.98,
            0.0,
            ["explain_valid_split_payment"],
            False,
        )
    if (
        delivery_report.delivery_outcome == "on_time"
        and payment_report.matches_item_plus_freight
    ):
        return (
            "unsupported_late_claim",
            "DELIVERY_WITHIN_ESTIMATE",
            0.97,
            0.0,
            ["reject_late_refund"],
            False,
        )

    # The official 50 cases are expected to follow one of the six paths. This
    # source-backed no-refund fallback keeps every output schema-valid for data
    # outside that official set without fabricating an event or refund.
    return (
        "unsupported_late_claim",
        "DELIVERY_WITHIN_ESTIMATE",
        0.35,
        0.0,
        ["reject_late_refund"],
        True,
    )


def build_policy_decision(
    case_id: str,
    order_report: OrderReport,
    payment_report: PaymentReport,
    delivery_report: DeliveryReport,
) -> PolicyDecision:
    primary_issue, policy_code, confidence, refund, actions, fallback = _decision_type(
        order_report,
        payment_report,
        delivery_report,
    )
    responsible = _responsible_parties(primary_issue, delivery_report.late_seller_ids)
    item_ids = bounded_unique(
        [f"{item.order_id}:{item.order_item_id}" for item in order_report.items],
        5,
    )
    seller_ids = bounded_unique(order_report.seller_ids, 5)
    payment_ids = bounded_unique(
        [f"{payment.order_id}:{payment.payment_sequential}" for payment in payment_report.payments],
        5,
    )
    order_ids = [order_report.order_id] if order_report.found else []
    output = CaseOutput(
        case_id=case_id,
        assessment=Assessment(
            primary_issue=primary_issue,  # type: ignore[arg-type]
            case_status="action_required" if refund > 0 else "no_action",
            confidence=confidence,
        ),
        affected_entities=AffectedEntities(
            order_ids=order_ids[:5],
            item_ids=item_ids,
            seller_ids=seller_ids,
            payment_ids=payment_ids,
        ),
        root_cause_analysis=RootCauseAnalysis(
            ranked_causes=[RankedCause(cause_code=policy_code, rank=1)],
            responsible_parties=responsible,
        ),
        evidence_ids=build_evidence_ids(
            order_report,
            payment_report,
            policy_code,
            primary_issue,
            responsible,
        ),
        financial_resolution=FinancialResolution(
            item_total_brl=round_money(decimal_money(order_report.item_total_brl)),
            freight_total_brl=round_money(decimal_money(order_report.freight_total_brl)),
            payment_total_brl=round_money(decimal_money(payment_report.payment_total_brl)),
            recommended_refund_brl=refund,
        ),
        resolution_actions=actions,
    )
    return PolicyDecision(
        policy_code=policy_code,
        candidate_output=output,
        authoritative=not fallback,
    )


def deterministic_explanation(decision: PolicyDecision) -> str:
    output = decision.candidate_output
    issue = output.assessment.primary_issue
    refund = output.financial_resolution.recommended_refund_brl
    if refund > 0:
        return f"{issue}: source-backed refund recommendation of {refund:.2f} BRL."
    return f"{issue}: no refund is supported by the source data and EC_POLICY_V1."
