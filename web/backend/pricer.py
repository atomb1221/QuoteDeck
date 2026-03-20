"""Pricing calculations."""
from typing import Dict


def is_sheet(product: Dict) -> bool:
    return "sheet" in product.get("type", "").lower()


def calculate_line_price(product: Dict, length: float, qty: int, tonnage: float) -> float:
    if is_sheet(product):
        # Sheet: weight is kg per whole sheet, no length factor
        return (product["weight"] * qty * tonnage) / 1000
    else:
        # Standard: weight is kg/m, length in metres required
        return (product["weight"] * length * tonnage / 1000) * qty
