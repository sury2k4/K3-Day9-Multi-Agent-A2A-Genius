from pathlib import Path
from olist_disputes.facts import load_order_facts

def test_load_real_order_facts():
    facts = load_order_facts(Path("data"), "e481f51cbdc54678b7cc49136f2d6af7")
    assert facts.order_status == "delivered"
    assert facts.items
    assert facts.payments
