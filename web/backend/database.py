"""Product database — loads from products.xlsx in the project root."""
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


class ProductDatabase:
    def __init__(self, excel_file: str):
        self.excel_file = excel_file
        self.products: List[Dict] = []
        self.load_products()

    def load_products(self):
        wb = openpyxl.load_workbook(self.excel_file)
        ws = wb.active
        self.products = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is not None:
                self.products.append({
                    "code":        str(row[0]),
                    "description": row[1] or "",
                    "weight":      float(row[2]) if row[2] else 0.0,
                    "type":        row[3] or "",
                })

    # ── Helpers ────────────────────────────────────────────────────────────────

    _SECTION_TYPES = {'shs', 'rhs', 'chs', 'ub', 'uc', 'pfc', 'ea', 'ua',
                      'tee', 'fb', 'rb', 'hb', 'ms', 'box'}

    # Sheet size shorthand → standard mm dimensions used in DB descriptions
    _SHEET_SIZES = [
        (r'\b8\s*[x×]\s*4\b',   '2500 x 1250'),
        (r'\b10\s*[x×]\s*5\b',  '3000 x 1500'),
    ]

    # Common terminology synonyms
    _TERMINOLOGY = [
        (r'\bgalvanised\b',  'galv'),   # normalise to shorter form first
        (r'\bchequer\b',     'chequer'),
        (r'\bchecker\b',     'chequer'),
        (r'\bhot\s*rolled\b', 'hr'),
        (r'\bcold\s*rolled\b', 'cr'),
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
        """Return (section_type | None, tuple_of_floats) for fuzzy matching.

        Numbers are stored as floats so "6" and "6.0" compare equal.
        """
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
        self.load_products()
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

        # 5. Dimension + type fuzzy match
        s_type, s_nums = self._parse_section(search_term)
        if len(s_nums) >= 2:
            for p in self.products:
                p_type, p_nums = self._parse_section(p["description"])
                if s_nums == p_nums and (not s_type or not p_type or s_type == p_type):
                    return p

        return None

    def find_all_products(self, search_term: str) -> List[Dict]:
        """Return every DB product that shares the same numeric dimensions.

        Used to detect ambiguity (e.g. SHS vs Equal Angle with same dimensions).
        Falls back to find_product() when there are fewer than 2 dimensions.
        """
        self.load_products()
        search_term = self._expand_search(search_term)
        _, s_nums = self._parse_section(search_term)

        if len(s_nums) < 2:
            p = self.find_product(search_term)
            return [p] if p else []

        matches = []
        seen = set()
        for p in self.products:
            _, p_nums = self._parse_section(p["description"])
            if p_nums == s_nums:
                key = self.normalize(p["description"])
                if key not in seen:
                    seen.add(key)
                    matches.append(p)

        return matches

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def get_all(self) -> List[Dict]:
        self.load_products()
        return self.products

    def add_product(self, code: str, description: str, weight: float, type_: str) -> Dict:
        self.load_products()
        product = {"code": code, "description": description, "weight": weight, "type": type_}
        self.products.append(product)
        self._save()
        return product

    def update_product(self, idx: int, code: str, description: str, weight: float, type_: str) -> Dict:
        self.load_products()
        self.products[idx] = {"code": code, "description": description, "weight": weight, "type": type_}
        self._save()
        return self.products[idx]

    def delete_product(self, idx: int):
        self.load_products()
        self.products.pop(idx)
        self._save()

    def _save(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Code", "Description", "Weight (kg/m)", "Type"])
        for p in self.products:
            ws.append([p["code"], p["description"], p["weight"], p["type"]])
        wb.save(self.excel_file)
