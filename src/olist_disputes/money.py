from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.10")

def decimal(value) -> Decimal:
    return Decimal(str(value or "0"))

def money(value) -> Decimal:
    return decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)

def as_float(value: Decimal) -> float:
    return float(money(value))

def reconciles(payment_total: Decimal, item_total: Decimal, freight_total: Decimal) -> bool:
    return abs(money(payment_total) - money(item_total + freight_total)) <= TOLERANCE
