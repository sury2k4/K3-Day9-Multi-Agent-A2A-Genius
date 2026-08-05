from decimal import Decimal
from .money import money, reconciles
from .schemas import OrderFacts, PolicyDecision

CONFIDENCE = 0.92


def decide(facts: OrderFacts) -> PolicyDecision:
    """Apply EC_POLICY_V1 in priority order using only source facts."""
    paid = facts.payment_total > 0
    if facts.order_status == "canceled" and paid:
        return PolicyDecision(primary_issue="canceled_order_paid", case_status="action_required", confidence=CONFIDENCE, cause_code="ORDER_CANCELED_AFTER_PAYMENT", responsible_parties=[{"party_type": "platform", "party_id": "OLIST_PLATFORM"}], recommended_refund=money(facts.payment_total), action="issue_full_refund")
    if facts.order_status == "unavailable" and paid:
        return PolicyDecision(primary_issue="unavailable_order_paid", case_status="action_required", confidence=CONFIDENCE, cause_code="ORDER_UNAVAILABLE_AFTER_PAYMENT", responsible_parties=[{"party_type": "platform", "party_id": "OLIST_PLATFORM"}], recommended_refund=money(facts.payment_total), action="issue_full_refund")

    delivery_known = facts.delivered_customer_date is not None and facts.estimated_delivery_date is not None
    late_delivery = delivery_known and facts.delivered_customer_date > facts.estimated_delivery_date
    if late_delivery:
        if facts.delivered_carrier_date is None or not facts.items:
            raise ValueError(f"incomplete delivery facts for order {facts.order_id}")
        missing_limits = [item.order_item_id for item in facts.items if item.shipping_limit_date is None]
        if missing_limits:
            raise ValueError(f"missing shipping limits for order {facts.order_id}: {missing_limits}")
        late_sellers = sorted({item.seller_id for item in facts.items if facts.delivered_carrier_date > item.shipping_limit_date})
        if late_sellers:
            return PolicyDecision(primary_issue="late_delivery_seller", case_status="action_required", confidence=CONFIDENCE, cause_code="SELLER_HANDOFF_AFTER_LIMIT", responsible_parties=[{"party_type": "seller", "party_id": seller_id} for seller_id in late_sellers], recommended_refund=money(facts.freight_total), action="refund_freight")
        return PolicyDecision(primary_issue="late_delivery_logistics", case_status="action_required", confidence=CONFIDENCE, cause_code="CARRIER_DELIVERED_AFTER_ESTIMATE", responsible_parties=[{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}], recommended_refund=money(facts.freight_total), action="refund_freight")

    on_time = delivery_known and not late_delivery
    if len(facts.payments) >= 2 and reconciles(facts.payment_total, facts.item_total, facts.freight_total):
        return PolicyDecision(primary_issue="valid_split_payment", case_status="no_action", confidence=CONFIDENCE, cause_code="MULTIPLE_PAYMENTS_RECONCILED", recommended_refund=Decimal("0.00"), action="explain_valid_split_payment")
    if on_time and reconciles(facts.payment_total, facts.item_total, facts.freight_total):
        return PolicyDecision(primary_issue="unsupported_late_claim", case_status="no_action", confidence=CONFIDENCE, cause_code="DELIVERY_WITHIN_ESTIMATE", recommended_refund=Decimal("0.00"), action="reject_late_refund")
    raise ValueError(f"no supported policy rule for order {facts.order_id}")
