"""Pricing calculations."""
from typing import Dict


def calculate_line_price(product: Dict, length: float, qty: int, tonnage: float) -> float:
    is_sheet = (
        product.get("type", "").lower() == "sheet"
        or "sheet" in product["description"].lower()
    )
    if is_sheet:
        unit_price = (product["weight"] * length * tonnage) / 1000
    else:
        unit_price = (product["weight"] * tonnage / 1000) * length
    return unit_price * qty
