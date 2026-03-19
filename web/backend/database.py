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

    def normalize(self, text: str) -> str:
        return re.sub(r"\s+", "", text.lower())

    def find_product(self, search_term: str) -> Optional[Dict]:
        sn = self.normalize(search_term)
        ss = search_term.lstrip("0") or "0"
        for p in self.products:
            if p["code"] in (search_term, sn, ss):
                return p
        for p in self.products:
            dn = self.normalize(p["description"])
            if sn in dn or dn in sn:
                return p
        return None

    def get_all(self) -> List[Dict]:
        return self.products

    def add_product(self, code: str, description: str, weight: float, type_: str) -> Dict:
        product = {"code": code, "description": description, "weight": weight, "type": type_}
        self.products.append(product)
        self._save()
        return product

    def update_product(self, idx: int, code: str, description: str, weight: float, type_: str) -> Dict:
        self.products[idx] = {"code": code, "description": description, "weight": weight, "type": type_}
        self._save()
        return self.products[idx]

    def delete_product(self, idx: int):
        self.products.pop(idx)
        self._save()

    def _save(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Code", "Description", "Weight (kg/m)", "Type"])
        for p in self.products:
            ws.append([p["code"], p["description"], p["weight"], p["type"]])
        wb.save(self.excel_file)
