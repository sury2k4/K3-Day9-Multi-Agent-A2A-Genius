from datetime import datetime
from decimal import Decimal
from olist_disputes.evidence import build_evidence
from olist_disputes.policy import decide
from olist_disputes.schemas import ItemFact, OrderFacts, PaymentFact

def test_evidence_ids_are_source_shaped():
    facts = OrderFacts(order_id="order", order_status="canceled", items=[ItemFact(order_id="order", order_item_id=1, product_id="p", seller_id="seller", price=Decimal("1"), freight_value=Decimal(".10"))], payments=[PaymentFact(order_id="order", payment_sequential=1, payment_value=Decimal("1.10"))])
    decision = decide(facts)
    ids = build_evidence(facts, decision)
    assert "order:order" in ids
    assert "item:order:1" in ids
    assert "payment:order:1" in ids
    assert "seller:seller" in ids
    assert "policy:ORDER_CANCELED_AFTER_PAYMENT" in ids
