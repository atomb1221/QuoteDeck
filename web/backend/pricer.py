"""Pricing calculations."""
import re
from typing import Dict


def is_sheet(product: Dict) -> bool:
    return "sheet" in product.get("type", "").lower()


def sheet_area_m2(product: Dict) -> float:
    """Return sheet area in m² by reading the first two dimensions from the description.

    E.g. '2500 x 1250 x 8mm HR Sheet' → (2500/1000) × (1250/1000) = 3.125 m²
    """
    nums = re.findall(r'\d+(?:\.\d+)?', product.get("description", ""))
    if len(nums) >= 2:
        return (float(nums[0]) / 1000) * (float(nums[1]) / 1000)
    return 1.0  # fallback — shouldn't happen for well-formed descriptions


def calculate_line_price(product: Dict, length: float, qty: int, tonnage: float) -> float:
    if is_sheet(product):
        # Sheet: weight is kg/m², multiply by sheet area to get total kg per sheet
        area = sheet_area_m2(product)
        return (product["weight"] * area * qty * tonnage) / 1000
    else:
        # Standard: weight is kg/m, length in metres required
        return (product["weight"] * length * tonnage / 1000) * qty
