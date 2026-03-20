"""Product database — loads from products.xlsx in the project root."""
import openpyxl
import re
from typing import List, Dict, Optional


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

    # Section type keywords used in fuzzy dimension matching
    _SECTION_TYPES = {'shs', 'rhs', 'chs', 'ub', 'uc', 'pfc', 'ea', 'ua',
                      'tee', 'fb', 'rb', 'hb', 'ms', 'box'}

    def normalize(self, text: str) -> str:
        return re.sub(r"\s+", "", text.lower())

    def _parse_section(self, text: str):
        """Return (section_type | None, tuple_of_numeric_strings) for fuzzy matching."""
        t = text.lower()
        section_type = next((st for st in self._SECTION_TYPES if re.search(rf'\b{st}\b', t)), None)
        nums = tuple(re.findall(r'\d+(?:\.\d+)?', text))
        return section_type, nums

    def find_product(self, search_term: str) -> Optional[Dict]:
        self.load_products()
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

        # 3. Search term is a substring of description (user abbreviated)
        for p in self.products:
            dn = self.normalize(p["description"])
            if sn and sn in dn:
                return p

        # 4. Description is a substring of search term (only if not too much shorter)
        for p in self.products:
            dn = self.normalize(p["description"])
            if dn and dn in sn and len(dn) >= len(sn) * 0.65:
                return p

        # 5. Dimension + type fuzzy match
        #    e.g. "SHS 40x40x2.5" matches "SHS 40x40x2.5mm box"
        s_type, s_nums = self._parse_section(search_term)
        if len(s_nums) >= 2:
            for p in self.products:
                p_type, p_nums = self._parse_section(p["description"])
                if s_nums == p_nums and (not s_type or not p_type or s_type == p_type):
                    return p

        return None

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
