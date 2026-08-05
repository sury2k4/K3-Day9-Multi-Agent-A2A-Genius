from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class CaseState(TypedDict, total=False):
    case_id: str
    input_case: dict
    claimed_order_id: str
    customer_message: str

    order_found: bool

    order_facts: dict
    order_seller_narrative: str

    delivery_facts: dict
    delivery_narrative: str

    payment_facts: dict
    payment_narrative: str

    intake_hint: dict
    policy_result: dict
    policy_narrative: str

    draft_output: dict
    verifier_findings: list[str]
    final_output: dict

    trace_events: Annotated[list[dict], operator.add]
