from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: str = "vi"
    message: str = ""
    claimed_order_id: str = Field(min_length=1)


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(min_length=1)
    opened_at: str
    customer_request: CustomerRequest
    policy_version: str = "EC_POLICY_V1"


PrimaryIssue = Literal[
    "canceled_order_paid",
    "unavailable_order_paid",
    "late_delivery_seller",
    "late_delivery_logistics",
    "valid_split_payment",
    "unsupported_late_claim",
]
CaseStatus = Literal["action_required", "no_action"]


class Assessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_issue: PrimaryIssue
    case_status: CaseStatus
    confidence: float = Field(ge=0, le=1)


class AffectedEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_ids: list[str] = Field(default_factory=list, max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=5)
    payment_ids: list[str] = Field(default_factory=list, max_length=5)


class RankedCause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause_code: str
    rank: int = Field(ge=1, le=3)


class ResponsibleParty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_type: Literal["seller", "platform", "logistics_provider"]
    party_id: str


class RootCauseAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranked_causes: list[RankedCause] = Field(default_factory=list, max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(default_factory=list, max_length=3)


class FinancialResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: Literal["BRL"] = "BRL"
    item_total_brl: float = Field(ge=0)
    freight_total_brl: float = Field(ge=0)
    payment_total_brl: float = Field(ge=0)
    recommended_refund_brl: float = Field(ge=0)


class CaseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_be_nonempty(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("evidence_ids cannot contain empty strings")
        return values


class OrderItemFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_date: str | None = None
    price_brl: float = Field(ge=0)
    freight_brl: float = Field(ge=0)


class OrderReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    found: bool
    order_status: str | None = None
    customer_id: str | None = None
    items: list[OrderItemFact] = Field(default_factory=list)
    seller_ids: list[str] = Field(default_factory=list)
    item_total_brl: float = Field(ge=0, default=0.0)
    freight_total_brl: float = Field(ge=0, default=0.0)
    evidence_ids: list[str] = Field(default_factory=list)


class PaymentFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    payment_sequential: int
    payment_type: str
    payment_installments: int
    payment_value_brl: float = Field(ge=0)


class PaymentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    payments: list[PaymentFact] = Field(default_factory=list)
    payment_row_count: int = Field(ge=0)
    payment_total_brl: float = Field(ge=0, default=0.0)
    item_total_brl: float = Field(ge=0, default=0.0)
    freight_total_brl: float = Field(ge=0, default=0.0)
    reconciliation_difference_brl: float = 0.0
    matches_item_plus_freight: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class DeliveryReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    delivery_outcome: Literal["late", "on_time", "unknown"]
    estimated_delivery_date: str | None = None
    delivered_customer_date: str | None = None
    delivered_carrier_date: str | None = None
    late_seller_ids: list[str] = Field(default_factory=list)
    comparable_item_count: int = Field(ge=0, default=0)
    evidence_ids: list[str] = Field(default_factory=list)


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_code: str
    candidate_output: CaseOutput
    authoritative: bool = True


class PolicyExplanation(BaseModel):
    """Non-authoritative model output kept out of the scored JSON schema."""

    summary: str = Field(min_length=1, max_length=2000)


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    checked_evidence_count: int = Field(ge=0, default=0)
