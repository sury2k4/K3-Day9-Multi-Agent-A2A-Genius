from .schemas import OrderFacts, PolicyDecision

def build_evidence(facts: OrderFacts, decision: PolicyDecision) -> list[str]:
    """Build stable, source-backed IDs; keep policy proof within ten IDs."""
    ids = [f"order:{facts.order_id}"]
    ids.extend(f"item:{facts.order_id}:{item.order_item_id}" for item in sorted(facts.items, key=lambda item: item.order_item_id))
    ids.extend(f"payment:{facts.order_id}:{payment.payment_sequential}" for payment in sorted(facts.payments, key=lambda payment: payment.payment_sequential))
    ids.extend(f"seller:{seller_id}" for seller_id in sorted({item.seller_id for item in facts.items}))
    policy_id = f"policy:{decision.cause_code}"
    if policy_id not in ids:
        ids.append(policy_id)
    if len(ids) <= 10:
        return ids
    # Policy and order evidence always survive; prioritize responsible seller/payment/item rows.
    keep = [ids[0]]
    responsible = {party["party_id"] for party in decision.responsible_parties if party["party_type"] == "seller"}
    keep.extend(item_id for item_id in ids if item_id.startswith("seller:") and item_id.split(":", 1)[1] in responsible)
    keep.extend(item_id for item_id in ids if item_id.startswith("item:") and item_id not in keep)
    keep.extend(item_id for item_id in ids if item_id.startswith("payment:") and item_id not in keep)
    keep.append(policy_id)
    return list(dict.fromkeys(keep))[:10]
