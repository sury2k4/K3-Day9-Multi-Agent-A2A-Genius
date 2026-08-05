from decimal import Decimal
from olist_disputes.money import money, reconciles

def test_round_half_up():
    assert money("1.005") == Decimal("1.01")

def test_reconciliation_tolerance():
    assert reconciles(Decimal("100.10"), Decimal("100"), Decimal("0"))
    assert not reconciles(Decimal("100.11"), Decimal("100"), Decimal("0"))
