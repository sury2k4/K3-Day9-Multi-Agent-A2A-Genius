from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class CustomerRequest(BaseModel):
    language: str
    message: str
    claimed_order_id: str

class CaseInput(BaseModel):
    case_id: str
    opened_at: datetime
    customer_request: CustomerRequest
    policy_version: str

    @field_validator("case_id")
    @classmethod
    def valid_case_id(cls, value: str) -> str:
        if not value.startswith("EC_"):
            raise ValueError("case_id must start with EC_")
        return value

class ItemFact(BaseModel):
    order_id: str
    order_item_id: int
    product_id: str
    seller_id: str
    shipping_limit_date: datetime | None = None
    price: Decimal
    freight_value: Decimal

class PaymentFact(BaseModel):
    order_id: str
    payment_sequential: int
    payment_value: Decimal

class OrderFacts(BaseModel):
    order_id: str
    order_status: str
    delivered_carrier_date: datetime | None = None
    delivered_customer_date: datetime | None = None
    estimated_delivery_date: datetime | None = None
    items: list[ItemFact] = Field(default_factory=list)
    payments: list[PaymentFact] = Field(default_factory=list)

    @property
    def item_total(self) -> Decimal:
        return sum((x.price for x in self.items), Decimal("0"))

    @property
    def freight_total(self) -> Decimal:
        return sum((x.freight_value for x in self.items), Decimal("0"))

    @property
    def payment_total(self) -> Decimal:
        return sum((x.payment_value for x in self.payments), Decimal("0"))

class DomainReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Literal["order_seller", "payment", "delivery"]
    order_id: str
    source_refs: list[str] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)
    conclusion: str
    explanation: str = ""

class PolicyDecision(BaseModel):
    primary_issue: str
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)
    cause_code: str
    responsible_parties: list[dict[str, str]] = Field(default_factory=list)
    recommended_refund: Decimal
    action: str

class OutputAssessment(BaseModel):
    primary_issue: str
    case_status: Literal["action_required", "no_action"]
    confidence: float = Field(ge=0, le=1)

class OutputEntities(BaseModel):
    order_ids: list[str] = Field(default_factory=list, max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=5)
    payment_ids: list[str] = Field(default_factory=list, max_length=5)

class RootCause(BaseModel):
    cause_code: str
    rank: int

class RootCauseAnalysis(BaseModel):
    ranked_causes: list[RootCause] = Field(default_factory=list, max_length=3)
    responsible_parties: list[dict[str, str]] = Field(default_factory=list, max_length=3)

class FinancialResolution(BaseModel):
    currency: Literal["BRL"] = "BRL"
    item_total_brl: float
    freight_total_brl: float
    payment_total_brl: float
    recommended_refund_brl: float

class CaseOutput(BaseModel):
    case_id: str
    assessment: OutputAssessment
    affected_entities: OutputEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(max_length=5)
