"""Product matching engine — pure in-memory, no file I/O.

Storage (SQLite) is handled by db.py.
Use load_from_xlsx() once at startup to seed the DB, then pass the list to ProductDatabase.
"""
import openpyxl
import re
from typing import List, Dict, Optional, Tuple


# Type-hint keywords: maps a category key → list of trigger words
_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "shs":    ["shs", "box", "hollow section", "square hollow"],
    "rhs":    ["rhs", "rectangular hollow"],
    "chs":    ["chs", "tube", "pipe", "circular hollow"],
    "angle":  ["angle", "equal angle", "unequal angle", " ea ", " ua "],
    "flat":   ["flat bar", "flat ", " fb "],
    "ub":     ["ub ", "universal beam", " beam"],
    "uc":     ["uc ", "universal column", " column"],
    "pfc":    ["pfc", "channel"],
    "round":  ["round bar", "round ", " rb "],
}


def load_from_xlsx(excel_file: str) -> List[Dict]:
    """Read products from an xlsx file and return as a list of dicts."""
    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active
    products = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is not None:
            products.append({
                "code":        str(row[0]),
                "description": row[1] or "",
                "weight":      float(row[2]) if row[2] else 0.0,
                "type":        row[3] or "",
            })
    return products


class ProductDatabase:
    """In-memory product matcher. Pass a list of product dicts from the DB."""

    def __init__(self, products: List[Dict]):
        self.products = products

    # ── Helpers ────────────────────────────────────────────────────────────────

    _SECTION_TYPES = {'shs', 'rhs', 'chs', 'ub', 'uc', 'pfc', 'ea', 'ua',
                      'tee', 'fb', 'rb', 'hb', 'ms', 'box'}

    # Sheet size shorthand → standard mm dimensions used in DB descriptions
    _SHEET_SIZES = [
        (r'\b8\s*[x×]\s*4\b',   '2500 x 1250'),
        (r'\b10\s*[x×]\s*5\b',  '3000 x 1500'),
    ]

    # Common terminology synonyms (applied to search terms before matching)
    _TERMINOLOGY = [
        (r'\bgalvanised\b',       'galv'),
        (r'\bchecker\b',          'chequer'),
        (r'\bhot\s*rolled\b',     'hr'),
        (r'\bcold\s*rolled\b',    'cr'),
        # type synonyms
        (r'\bround\s+bar\b',      'dia'),
        (r'\bsolid\s+round\b',    'dia'),
        (r'\bflat\s+bar\b',       'fb'),
        (r'\bangle\s+iron\b',     'angle'),
        (r'\bbox\s+iron\b',       'SHS'),
        (r'\bchannel\s+iron\b',   'channel'),
        (r'\bround\s+pipe\b',     'CHS'),
        (r'\bround\s+tube\b',     'CHS'),
    ]

    @staticmethod
    def is_sheet(product: Dict) -> bool:
        return "sheet" in product.get("type", "").lower()

    def _expand_search(self, text: str) -> str:
        """Normalise shorthand and synonyms in a search term before matching."""
        t = text
        for pattern, replacement in self._SHEET_SIZES:
            t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)
        for pattern, replacement in self._TERMINOLOGY:
            t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)
        return t

    def normalize(self, text: str) -> str:
        return re.sub(r"\s+", "", text.lower())

    def _parse_section(self, text: str) -> Tuple[Optional[str], tuple]:
        """Return (section_type | None, tuple_of_floats) for fuzzy matching."""
        t = text.lower()
        section_type = next(
            (st for st in self._SECTION_TYPES if re.search(rf'\b{st}\b', t)), None
        )
        nums = tuple(float(n) for n in re.findall(r'\d+(?:\.\d+)?', text))
        return section_type, nums

    def type_hint_from_text(self, text: str) -> Optional[str]:
        """Detect a section-type hint in a customer's description."""
        t = " " + text.lower() + " "
        for category, keywords in _TYPE_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                return category
        return None

    def product_matches_type_hint(self, product: Dict, hint: str) -> bool:
        """True if a DB product belongs to the hint category."""
        combined = " " + product["description"].lower() + " " + product.get("type", "").lower() + " "
        return any(kw in combined for kw in _TYPE_KEYWORDS.get(hint, []))

    # ── Core lookup ────────────────────────────────────────────────────────────

    def find_product(self, search_term: str) -> Optional[Dict]:
        search_term = self._expand_search(search_term)
        sn = self.normalize(search_term)
        ss = search_term.lstrip("0") or "0"

        # 1. Exact code match
        for p in self.products:
            if p["code"] in (search_term, sn, ss):
                return p

        # 2. Exact normalised description match
        for p in self.products:
            if self.normalize(p["description"]) == sn:
                return p

        # 3. Search term is a substring of description
        for p in self.products:
            dn = self.normalize(p["description"])
            if sn and sn in dn:
                return p

        # 4. Description is substring of search term (length ratio guard)
        for p in self.products:
            dn = self.normalize(p["description"])
            if dn and dn in sn and len(dn) >= len(sn) * 0.65:
                return p

        # 5. Dimension + type fuzzy match (expand DB descriptions too)
        s_type, s_nums = self._parse_section(search_term)
        if len(s_nums) >= 2:
            for p in self.products:
                p_type, p_nums = self._parse_section(self._expand_search(p["description"]))
                if s_nums == p_nums and (not s_type or not p_type or s_type == p_type):
                    return p

        # 5b. Single-dimension + type match (e.g. "12mm round bar" → "12 RB")
        if len(s_nums) == 1 and s_type:
            for p in self.products:
                p_type, p_nums = self._parse_section(self._expand_search(p["description"]))
                if p_type and s_nums == p_nums and s_type == p_type:
                    return p

        return None

    @staticmethod
    def _dims_match(s_nums: tuple, p_nums: tuple, tol: float = 0.05) -> bool:
        """True if s_nums matches the start of p_nums within a percentage tolerance.

        Prefix match: "152 x 76" (s) matches "150 x 75 x 18kg PFC" (p).
        Fuzzy tolerance: handles imperial-to-metric rounding (152 ≈ 150, 76 ≈ 75).
        Exact match: "50 x 50 x 5" must NOT match "50 x 50 x 2.5" (50% off > tol).
        """
        if not s_nums or not p_nums:
            return False
        if len(s_nums) > len(p_nums):
            return False
        for s, p in zip(s_nums, p_nums):
            denom = max(s, p, 0.001)
            if abs(s - p) / denom > tol:
                return False
        return True

    def find_all_products(self, search_term: str) -> List[Dict]:
        """Return every DB product whose dimensions match the search term."""
        search_term = self._expand_search(search_term)
        _, s_nums = self._parse_section(search_term)

        if len(s_nums) < 2:
            p = self.find_product(search_term)
            return [p] if p else []

        matches = []
        seen = set()
        for p in self.products:
            _, p_nums = self._parse_section(p["description"])
            if self._dims_match(s_nums, p_nums):
                key = self.normalize(p["description"])
                if key not in seen:
                    seen.add(key)
                    matches.append(p)

        return matches
