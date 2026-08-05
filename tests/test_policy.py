from datetime import datetime
from decimal import Decimal
from olist_disputes.policy import decide
from olist_disputes.schemas import ItemFact, OrderFacts, PaymentFact

def facts(status="delivered", delivered="2020-01-10", estimated="2020-01-09", carrier="2020-01-03", limit="2020-01-02", payments=("115",)):
    dt = lambda x: datetime.strptime(x, "%Y-%m-%d") if x else None
    return OrderFacts(order_id="o", order_status=status, delivered_carrier_date=dt(carrier), delivered_customer_date=dt(delivered), estimated_delivery_date=dt(estimated), items=[ItemFact(order_id="o", order_item_id=1, product_id="p", seller_id="s", shipping_limit_date=dt(limit), price=Decimal("100"), freight_value=Decimal("15"))], payments=[PaymentFact(order_id="o", payment_sequential=i + 1, payment_value=Decimal(v)) for i, v in enumerate(payments)])

def test_canceled_paid_has_priority():
    result = decide(facts(status="canceled", delivered=None, estimated=None, carrier=None, limit=None))
    assert result.primary_issue == "canceled_order_paid"
    assert result.recommended_refund == Decimal("115.00")

def test_seller_late():
    assert decide(facts()).cause_code == "SELLER_HANDOFF_AFTER_LIMIT"

def test_logistics_late_when_handoff_on_time():
    assert decide(facts(limit="2020-01-03")).cause_code == "CARRIER_DELIVERED_AFTER_ESTIMATE"

def test_split_payment():
    result = decide(facts(delivered="2020-01-09", payments=("50", "65")))
    assert result.primary_issue == "valid_split_payment"
    assert result.recommended_refund == Decimal("0.00")

def test_on_time_reconciled_rejects_claim():
    result = decide(facts(delivered="2020-01-09", payments=("115",)))
    assert result.cause_code == "DELIVERY_WITHIN_ESTIMATE"
