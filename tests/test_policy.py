from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents import build_delivery_report, build_order_report, build_payment_report
from app.config import Settings
from app.db import InMemoryRepository
from app.graph import DisputeGraph
from app.policy import build_policy_decision
from app.schemas import CaseInput
from app.tracing import TraceRecorder
from app.verifier import verify_case_output


def repository_for(
    *,
    status: str = "delivered",
    delivered_customer: str | None = "2020-01-04 00:00:00",
    estimated: str | None = "2020-01-05 00:00:00",
    carrier: str | None = "2020-01-02 00:00:00",
    shipping_limit: str | None = "2020-01-03 00:00:00",
    payments: list[dict[str, object]] | None = None,
) -> InMemoryRepository:
    order_id = "order-1"
    orders = {
        order_id: {
            "order_id": order_id,
            "customer_id": "customer-1",
            "order_status": status,
            "order_delivered_carrier_date": carrier,
            "order_delivered_customer_date": delivered_customer,
            "order_estimated_delivery_date": estimated,
        }
    }
    items = {
        order_id: [
            {
                "order_id": order_id,
                "order_item_id": 1,
                "product_id": "product-1",
                "seller_id": "seller-1",
                "shipping_limit_date": shipping_limit,
                "price": "100.00",
                "freight_value": "10.00",
            }
        ]
    }
    payment_rows = payments or [
        {
            "order_id": order_id,
            "payment_sequential": 1,
            "payment_type": "credit_card",
            "payment_installments": 1,
            "payment_value": "110.00",
        }
    ]
    payment_map = {order_id: payment_rows}
    return InMemoryRepository(orders, items, payment_map, {"seller-1"})


def decision_for(repository: InMemoryRepository):
    order = build_order_report(repository, "order-1")
    payment = build_payment_report(repository, "order-1", order)
    delivery = build_delivery_report(repository, "order-1", order)
    return build_policy_decision("EC_001", order, payment, delivery)


@pytest.mark.parametrize(
    ("kwargs", "issue", "cause", "refund", "action"),
    [
        (
            {"status": "canceled", "delivered_customer": None, "estimated": None, "carrier": None},
            "canceled_order_paid",
            "ORDER_CANCELED_AFTER_PAYMENT",
            110.0,
            "issue_full_refund",
        ),
        (
            {"status": "unavailable", "delivered_customer": None, "estimated": None, "carrier": None},
            "unavailable_order_paid",
            "ORDER_UNAVAILABLE_AFTER_PAYMENT",
            110.0,
            "issue_full_refund",
        ),
        (
            {
                "delivered_customer": "2020-01-10 00:00:00",
                "estimated": "2020-01-05 00:00:00",
                "carrier": "2020-01-04 00:00:00",
                "shipping_limit": "2020-01-03 00:00:00",
            },
            "late_delivery_seller",
            "SELLER_HANDOFF_AFTER_LIMIT",
            10.0,
            "refund_freight",
        ),
        (
            {
                "delivered_customer": "2020-01-10 00:00:00",
                "estimated": "2020-01-05 00:00:00",
                "carrier": "2020-01-02 00:00:00",
                "shipping_limit": "2020-01-03 00:00:00",
            },
            "late_delivery_logistics",
            "CARRIER_DELIVERED_AFTER_ESTIMATE",
            10.0,
            "refund_freight",
        ),
        (
            {
                "payments": [
                    {
                        "order_id": "order-1",
                        "payment_sequential": 1,
                        "payment_type": "credit_card",
                        "payment_installments": 1,
                        "payment_value": "50.00",
                    },
                    {
                        "order_id": "order-1",
                        "payment_sequential": 2,
                        "payment_type": "voucher",
                        "payment_installments": 1,
                        "payment_value": "60.00",
                    },
                ]
            },
            "valid_split_payment",
            "MULTIPLE_PAYMENTS_RECONCILED",
            0.0,
            "explain_valid_split_payment",
        ),
        (
            {},
            "unsupported_late_claim",
            "DELIVERY_WITHIN_ESTIMATE",
            0.0,
            "reject_late_refund",
        ),
    ],
)
def test_policy_priority_and_financial_resolution(kwargs, issue, cause, refund, action):
    decision = decision_for(repository_for(**kwargs))
    output = decision.candidate_output
    assert output.assessment.primary_issue == issue
    assert output.root_cause_analysis.ranked_causes[0].cause_code == cause
    assert output.financial_resolution.recommended_refund_brl == refund
    assert output.resolution_actions == [action]


def test_verifier_rejects_fabricated_evidence():
    repository = repository_for()
    decision = decision_for(repository)
    payload = decision.candidate_output.model_dump(mode="json")
    payload["evidence_ids"].insert(0, "payment:order-1:999")
    report = verify_case_output(
        payload,
        decision.candidate_output.model_dump(mode="json"),
        "EC_001",
        "order-1",
        repository,
    )
    assert not report.valid
    assert any("does not exist" in error for error in report.errors)


def test_langgraph_end_to_end_writes_valid_output(tmp_path: Path):
    repository = repository_for(
        payments=[
            {
                "order_id": "order-1",
                "payment_sequential": 1,
                "payment_type": "credit_card",
                "payment_installments": 1,
                "payment_value": "50.00",
            },
            {
                "order_id": "order-1",
                "payment_sequential": 2,
                "payment_type": "voucher",
                "payment_installments": 1,
                "payment_value": "60.00",
            },
        ]
    )
    settings = Settings(
        _env_file=None,
        openrouter_api_key="",
        data_dir=tmp_path / "data",
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        logging_dir=tmp_path / "logging",
    )
    tracer = TraceRecorder(settings.logging_dir)
    tracer.reset()
    graph = DisputeGraph(repository, settings, tracer)
    case = CaseInput(
        case_id="EC_001",
        opened_at="2018-10-18T00:00:00-03:00",
        customer_request={
            "language": "vi",
            "message": "Kiểm tra thanh toán.",
            "claimed_order_id": "order-1",
        },
        policy_version="EC_POLICY_V1",
    )
    result = graph.run_case(case)
    output_path = Path(result["output_path"])
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["assessment"]["primary_issue"] == "valid_split_payment"
    assert result["verification_report"]["valid"] is True
    trace_text = (settings.logging_dir / "trace.jsonl").read_text(encoding="utf-8")
    assert "policy_engine" in trace_text
    assert "output_writer" in trace_text

