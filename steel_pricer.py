"""
Steel Pricer - Desktop Application for Steel Pricing Quotes
"""
import customtkinter as ctk
from tkinter import messagebox
import openpyxl
import re
import json
import os
from datetime import datetime
from anthropic import Anthropic
from typing import List, Dict, Optional

# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE  = os.path.join(os.path.dirname(__file__), "config.json")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "quote_history.json")
HISTORY_LIMIT = 50


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"config.json not found. Create it at:\n{CONFIG_FILE}\n\n"
            'Contents:\n{"anthropic_api_key": "your-key-here"}'
        )
    with open(CONFIG_FILE) as f:
        return json.load(f)


# ── Appearance ─────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Palette — all colour decisions live here
C = {
    "bg":           "#ECEEF1",   # window / tab background
    "surface":      "#FFFFFF",   # text boxes, inputs
    "panel":        "#F4F5F7",   # inset panels
    "row_even":     "#FFFFFF",
    "row_odd":      "#F3F5F8",
    "tbl_header":   "#2C3440",   # table column-header bar
    "fill_bar":     "#DDE1E7",   # "fill all" strip
    "divider":      "#CDD1D8",

    "text":         "#1C1E22",
    "text_muted":   "#6B7280",
    "text_inv":     "#FFFFFF",   # text on dark backgrounds

    # Buttons
    "btn_primary":  "#2B4C7E",   # Calculate Quote  (steel blue)
    "btn_primary_h":"#1E3557",
    "btn_action":   "#3D4A5C",   # Extract Items     (dark slate)
    "btn_action_h": "#2C3440",
    "btn_ghost":    "#D8DCE2",   # Clear / Copy / minor  (light grey)
    "btn_ghost_h":  "#C4C9D0",

    "input_border": "#BFC4CB",
    "accent":       "#2B4C7E",
}

# Typography
F = {
    "head":   ("Segoe UI", 11, "bold"),
    "label":  ("Segoe UI", 10),
    "small":  ("Segoe UI", 9),
    "mono":   ("Consolas", 10),
    "btn":    ("Segoe UI", 10, "bold"),
    "title":  ("Segoe UI", 12, "bold"),
}

# Shared widget defaults
ENTRY_KW = dict(corner_radius=2, border_width=1, border_color=C["input_border"],
                fg_color=C["surface"], font=F["label"])
BTN_H    = 34   # standard button height
BTN_H_SM = 26   # compact buttons (fill bar, history)


def _btn(parent, text, cmd, style="action", width=160, height=BTN_H, **kw):
    """Consistent button factory."""
    cfg = {
        "primary": (C["btn_primary"],  C["btn_primary_h"],  C["text_inv"]),
        "action":  (C["btn_action"],   C["btn_action_h"],   C["text_inv"]),
        "ghost":   (C["btn_ghost"],    C["btn_ghost_h"],    C["text"]),
    }
    fg, hv, tc = cfg[style]
    return ctk.CTkButton(parent, text=text, command=cmd, width=width, height=height,
                         corner_radius=2, font=F["btn"],
                         fg_color=fg, hover_color=hv, text_color=tc, **kw)



def _section(parent, text):
    """Uppercase section label — thin visual divider."""
    return ctk.CTkLabel(parent, text=text.upper(), font=("Segoe UI", 9, "bold"),
                        text_color=C["text_muted"])


# ── ProductDatabase ─────────────────────────────────────────────────────────────
class ProductDatabase:
    def __init__(self, excel_file: str):
        self.excel_file = excel_file
        self.products: List[Dict] = []
        self.load_products()

    def load_products(self):
        try:
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
        except Exception as e:
            raise Exception(f"Error loading products: {e}")

    def normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", "", text.lower())

    def find_product(self, search_term: str) -> Optional[Dict]:
        sn = self.normalize_text(search_term)
        ss = search_term.lstrip("0") or "0"
        for p in self.products:
            if p["code"] in (search_term, sn, ss):
                return p
        for p in self.products:
            dn = self.normalize_text(p["description"])
            if sn in dn or dn in sn:
                return p
        return None

    def get_all_products(self) -> List[Dict]:
        return self.products


# ── QuoteHistory ────────────────────────────────────────────────────────────────
class QuoteHistory:
    def __init__(self, path: str = HISTORY_FILE, limit: int = HISTORY_LIMIT):
        self.path  = path
        self.limit = limit
        self.entries: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self.entries = json.load(f)
            except Exception:
                self.entries = []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.entries[-self.limit:], f, indent=2)

    def add(self, customer: str, items: List[Dict], total: float):
        self.entries.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "customer":  customer or "Unknown",
            "items":     items,
            "total":     total,
        })
        self._save()

    def get_all(self) -> List[Dict]:
        return list(reversed(self.entries))


# ── ClaudeAI ────────────────────────────────────────────────────────────────────
class ClaudeAI:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

    def extract_items_from_email(self, email_text: str, product_list: List[Dict]) -> Dict:
        product_ref = "\n".join(
            [f"Code {p['code']}: {p['description']}" for p in product_list[:100]]
        )
        prompt = f"""You are analyzing a customer email requesting steel product pricing.

Available products:
{product_ref}

Customer email:
{email_text}

Extract:
1. customer_name: The company or person sending the email (empty string if not found)
2. items: All steel products requested. For each item:
   - product: EXACT FULL DESCRIPTION from the available products list
   - length: numeric metres ONLY if "m", "metres", or "meters" appears (0 if not given)
   - qty: numeric quantity (e.g. "3no" -> 3, "5 off" -> 5). Default 1 if not specified.
   - tonnage: only if "£" and "/ton" explicitly mentioned, else 0

Return ONLY valid JSON:
{{
  "customer_name": "",
  "items": [
    {{"product": "description", "length": 0, "qty": 1, "tonnage": 0}}
  ]
}}"""
        message = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()
        m = re.search(r"\{.*\}", response_text, re.DOTALL)
        return json.loads(m.group(0)) if m else {"customer_name": "", "items": []}

    def extract_quick_quote(self, query: str, product_list: List[Dict]) -> Dict:
        product_ref = "\n".join(
            [f"Code {p['code']}: {p['description']}" for p in product_list[:50]]
        )
        prompt = f"""You are parsing a quick steel pricing request.

Available products:
{product_ref}

User request: {query}

Extract ONLY the code number (e.g., "002", "18") NOT "Code 002".

Examples:
Input: "price 002 6.3m at 1200 tonne"
Output: {{"product": "002", "length": 6.3, "qty": 1, "tonnage": 1200}}

Return ONLY JSON:
{{"product": "code", "length": 0, "qty": 1, "tonnage": 0}}"""
        message = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = message.content[0].text.strip()
        m = re.search(r"\{.*\}", response_text, re.DOTALL)
        return json.loads(m.group(0)) if m else {"product": "", "length": 0, "qty": 1, "tonnage": 0}


# ── Pricing helper ──────────────────────────────────────────────────────────────
def calculate_line_price(product: Dict, length: float, qty: int, tonnage: float) -> float:
    is_sheet = (product.get("type", "").lower() == "sheet"
                or "sheet" in product["description"].lower())
    if is_sheet:
        unit_price = (product["weight"] * length * tonnage) / 1000
    else:
        unit_price = (product["weight"] * tonnage / 1000) * length
    return unit_price * qty


# ── Main App ────────────────────────────────────────────────────────────────────
class SteelPricerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Steel Pricer")
        self.root.geometry("1300x740")
        self.root.minsize(960, 620)
        self.root.configure(bg=C["bg"])

        self.item_widgets: List[Dict] = []
        self._current_customer: str = ""

        try:
            cfg = load_config()
        except FileNotFoundError as e:
            messagebox.showerror("Config missing", str(e))
            self.root.destroy()
            return

        try:
            self.db = ProductDatabase("products.xlsx")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load products: {e}")
            self.root.destroy()
            return

        try:
            self.claude = ClaudeAI(cfg["anthropic_api_key"])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialise Claude API: {e}")
            self.root.destroy()
            return

        self.history = QuoteHistory()
        self._build_ui()

    # ── Top-level UI ───────────────────────────────────────────────────────────
    def _build_ui(self):
        # Thin title bar
        header = ctk.CTkFrame(self.root, fg_color=C["tbl_header"], height=36, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="STEEL PRICER", font=("Segoe UI", 11, "bold"),
                     text_color=C["text_inv"]).pack(side="left", padx=16, pady=8)
        db_count = len(self.db.get_all_products())
        ctk.CTkLabel(header, text=f"{db_count} products loaded",
                     font=F["small"], text_color="#8A9BB0").pack(side="right", padx=16)

        self.tabview = ctk.CTkTabview(
            self.root,
            fg_color=C["bg"],
            segmented_button_fg_color=C["tbl_header"],
            segmented_button_selected_color=C["btn_primary"],
            segmented_button_selected_hover_color=C["btn_primary_h"],
            segmented_button_unselected_color=C["tbl_header"],
            segmented_button_unselected_hover_color=C["btn_action_h"],
            text_color=C["text_inv"],
            corner_radius=0,
        )
        self.tabview.pack(fill="both", expand=True, padx=0, pady=0)

        self.tabview.add("Email Mode")
        self.tabview.add("Quick Quote")
        self.tabview.add("History")

        self._build_email_tab()
        self._build_quick_tab()
        self._build_history_tab()

    # ── Email Mode Tab ─────────────────────────────────────────────────────────
    def _build_email_tab(self):
        tab = self.tabview.tab("Email Mode")
        tab.configure(fg_color=C["bg"])

        self.apply_tonnage_var = ctk.BooleanVar(value=True)
        self.apply_length_var  = ctk.BooleanVar(value=True)

        # ── Top: Email input (left) + Pricing Results (right), equal width ───
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="both", expand=True, padx=14, pady=(12, 0))

        # Left column — email
        left_col = ctk.CTkFrame(top, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 6))

        _section(left_col, "Customer Email").pack(anchor="w", pady=(0, 3))
        self.email_input = ctk.CTkTextbox(
            left_col, font=F["label"],
            fg_color=C["surface"], text_color=C["text"],
            border_width=1, border_color=C["input_border"], corner_radius=2,
        )
        self.email_input.pack(fill="both", expand=True)

        # Right column — results
        right_col = ctk.CTkFrame(top, fg_color="transparent")
        right_col.pack(side="left", fill="both", expand=True, padx=(6, 0))

        res_hdr = ctk.CTkFrame(right_col, fg_color="transparent")
        res_hdr.pack(fill="x", pady=(0, 3))
        _section(res_hdr, "Pricing Results").pack(side="left")
        _btn(res_hdr, "Copy to Clipboard", self._copy_email_results,
             "ghost", width=130, height=BTN_H_SM).pack(side="right")

        self.email_results = ctk.CTkTextbox(
            right_col, font=F["mono"],
            fg_color=C["surface"], text_color=C["text"],
            border_width=1, border_color=C["input_border"], corner_radius=2,
        )
        self.email_results.pack(fill="both", expand=True)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_bar = ctk.CTkFrame(tab, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=8)

        _btn(btn_bar, "Extract Items",   self._extract_items,         "action",  width=180).pack(side="left", padx=(0, 6))
        _btn(btn_bar, "Calculate Quote", self._calculate_and_display, "primary", width=180).pack(side="left", padx=(0, 6))
        _btn(btn_bar, "Clear",           self._clear_all,             "ghost",   width=90 ).pack(side="left")

        # ── Extracted items table ─────────────────────────────────────────────
        _section(tab, "Extracted Items  —  edit any field, then Calculate Quote").pack(
            anchor="w", padx=14, pady=(2, 3))

        COL = [("#", 28), ("Product", 320), ("kg/m", 60),
               ("Qty", 60), ("Length (m)", 100), ("Tonnage (£/t)", 120), ("Line Total", 110)]

        hdr = ctk.CTkFrame(tab, fg_color=C["tbl_header"], corner_radius=0)
        hdr.pack(fill="x", padx=14)
        for text, w in COL:
            ctk.CTkLabel(hdr, text=text, width=w, font=("Segoe UI", 9, "bold"),
                         text_color=C["text_inv"], anchor="w").pack(side="left", padx=6, pady=5)

        fill = ctk.CTkFrame(tab, fg_color=C["fill_bar"], corner_radius=0)
        fill.pack(fill="x", padx=14)

        spacer_w = 28 + 320 + 60 + 60 + (6 * 4)
        ctk.CTkLabel(fill, text="Fill all rows →", width=spacer_w, anchor="e",
                     font=F["small"], text_color=C["text_muted"]).pack(side="left", padx=(6, 0))

        self.default_length  = ctk.CTkEntry(fill, width=100, placeholder_text="length m",   **ENTRY_KW)
        self.default_length.pack(side="left", padx=5, pady=4)

        self.default_tonnage = ctk.CTkEntry(fill, width=120, placeholder_text="tonnage £/t", **ENTRY_KW)
        self.default_tonnage.pack(side="left", padx=5, pady=4)

        _btn(fill, "Apply to all rows", self._on_apply_check, "ghost",
             width=130, height=BTN_H_SM).pack(side="left", padx=8)

        self.items_frame = ctk.CTkScrollableFrame(
            tab, height=180,
            fg_color=C["surface"],
            border_width=1, border_color=C["divider"],
            corner_radius=0,
            scrollbar_button_color=C["divider"],
            scrollbar_button_hover_color=C["input_border"],
        )
        self.items_frame.pack(fill="x", padx=14, pady=(0, 10))

    # ── Quick Quote Tab ────────────────────────────────────────────────────────
    def _build_quick_tab(self):
        tab = self.tabview.tab("Quick Quote")
        tab.configure(fg_color=C["bg"])

        # Centred content card
        card = ctk.CTkFrame(tab, fg_color=C["surface"],
                            border_width=1, border_color=C["divider"], corner_radius=2)
        card.pack(fill="x", padx=20, pady=20)

        _section(card, "Quick Quote").pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(card,
                     text="Type a request and press Enter  —  e.g. '7.6m of 14 at £1200/ton'  or  '002 3m 950'",
                     font=F["small"], text_color=C["text_muted"]).pack(anchor="w", padx=16)

        self.quick_input = ctk.CTkEntry(card, height=36, **ENTRY_KW)
        self.quick_input.pack(fill="x", padx=16, pady=(8, 10))
        self.quick_input.bind("<Return>", lambda _: self._process_quick_quote())

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        _btn(btn_row, "Get Quote",         self._process_quick_quote, "primary", width=140).pack(side="left", padx=(0, 8))
        _btn(btn_row, "Copy to Clipboard", self._copy_quick_results,  "ghost",   width=140).pack(side="left")

        _section(tab, "Result").pack(anchor="w", padx=20, pady=(4, 4))
        self.quick_results = ctk.CTkTextbox(
            tab, font=F["mono"],
            fg_color=C["surface"], text_color=C["text"],
            border_width=1, border_color=C["input_border"], corner_radius=2,
        )
        self.quick_results.pack(fill="both", expand=True, padx=20, pady=(0, 16))

    # ── History Tab ───────────────────────────────────────────────────────────
    def _build_history_tab(self):
        tab = self.tabview.tab("History")
        tab.configure(fg_color=C["bg"])

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        _section(top, "Recent Quotes").pack(side="left")
        _btn(top, "Refresh", self._refresh_history, "ghost",
             width=80, height=BTN_H_SM).pack(side="right")

        # History column header
        hdr = ctk.CTkFrame(tab, fg_color=C["tbl_header"], corner_radius=0)
        hdr.pack(fill="x", padx=14)
        for text, w in [("Date / Time", 165), ("Customer", 270),
                        ("Items", 60), ("Total", 120), ("", 90)]:
            ctk.CTkLabel(hdr, text=text, width=w, font=("Segoe UI", 9, "bold"),
                         text_color=C["text_inv"], anchor="w").pack(side="left", padx=6, pady=5)

        self.history_frame = ctk.CTkScrollableFrame(
            tab,
            fg_color=C["surface"],
            border_width=1, border_color=C["divider"],
            corner_radius=0,
            scrollbar_button_color=C["divider"],
            scrollbar_button_hover_color=C["input_border"],
        )
        self.history_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self._refresh_history()

    # ── Logic: Extract Items ───────────────────────────────────────────────────
    def _extract_items(self):
        email_text = self.email_input.get("1.0", "end").strip()
        if not email_text:
            messagebox.showerror("Error", "Please paste a customer email first.")
            return
        try:
            result = self.claude.extract_items_from_email(email_text, self.db.get_all_products())
        except Exception as e:
            messagebox.showerror("Claude API Error", str(e))
            return

        self._current_customer = result.get("customer_name", "")
        items = result.get("items", [])
        if not items:
            messagebox.showinfo("No Items", "No steel products found in the email.")
            return

        default_ton = self._safe_float(self.default_tonnage.get())
        default_len = self._safe_float(self.default_length.get())
        for item in items:
            if self.apply_tonnage_var.get() and default_ton:
                item["tonnage"] = default_ton
            if self.apply_length_var.get() and default_len:
                item["length"] = default_len

        self._render_items(items)
        self.email_results.delete("1.0", "end")
        self.email_results.insert("1.0", "Items extracted — edit any row, then click Calculate Quote.")

    def _render_items(self, items: List[Dict]):
        for w in self.items_frame.winfo_children():
            w.destroy()
        self.item_widgets = []

        for idx, item in enumerate(items):
            product = self.db.find_product(item["product"])
            kg_m    = f"{product['weight']:.2f}" if product else "?"
            row_bg  = C["row_even"] if idx % 2 == 0 else C["row_odd"]

            row = ctk.CTkFrame(self.items_frame, fg_color=row_bg, corner_radius=0)
            row.pack(fill="x")

            ctk.CTkLabel(row, text=str(idx + 1), width=28, anchor="w",
                         fg_color="transparent", font=F["small"],
                         text_color=C["text_muted"]).pack(side="left", padx=(6, 2), pady=3)
            ctk.CTkLabel(row, text=item["product"], width=320, anchor="w",
                         fg_color="transparent", font=F["label"],
                         text_color=C["text"]).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=kg_m, width=60, anchor="w",
                         fg_color="transparent", font=F["small"],
                         text_color=C["text_muted"]).pack(side="left", padx=4)

            qty_e = ctk.CTkEntry(row, width=60,  height=26, **ENTRY_KW)
            qty_e.insert(0, str(item.get("qty", 1)))
            qty_e.pack(side="left", padx=4)

            len_e = ctk.CTkEntry(row, width=100, height=26, **ENTRY_KW)
            len_e.insert(0, str(item["length"]) if item.get("length") else "")
            len_e.pack(side="left", padx=4)

            ton_e = ctk.CTkEntry(row, width=120, height=26, **ENTRY_KW)
            ton_e.insert(0, str(item["tonnage"]) if item.get("tonnage") else "")
            ton_e.pack(side="left", padx=4)

            total_lbl = ctk.CTkLabel(row, text="—", width=110, anchor="w",
                                     fg_color="transparent", font=("Segoe UI", 10, "bold"),
                                     text_color=C["accent"])
            total_lbl.pack(side="left", padx=4)

            self.item_widgets.append({
                "product":       item["product"],
                "qty_entry":     qty_e,
                "length_entry":  len_e,
                "tonnage_entry": ton_e,
                "total_label":   total_lbl,
            })

    def _calculate_and_display(self):
        lines = []
        grand_total = 0.0
        history_items = []

        for w in self.item_widgets:
            product = self.db.find_product(w["product"])
            if not product:
                w["total_label"].configure(text="NOT FOUND", text_color="#E05252")
                lines.append(f"  {w['product'][:50]:<50}  NOT FOUND")
                continue

            try:
                length  = self._safe_float(w["length_entry"].get())
                tonnage = self._safe_float(w["tonnage_entry"].get())
                qty     = max(1, int(w["qty_entry"].get() or 1))
            except ValueError:
                w["total_label"].configure(text="BAD INPUT", text_color="#E05252")
                continue

            total = calculate_line_price(product, length, qty, tonnage)
            grand_total += total

            w["total_label"].configure(text=f"£{total:,.2f}", text_color=C["accent"])
            lines.append(f"  {product['description'][:50]:<52}  £{total:,.2f}")
            history_items.append({
                "product": product["description"], "length": length,
                "qty": qty, "tonnage": tonnage, "total": total,
            })

        lines.append("")
        lines.append(f"  {'TOTAL':<52}  £{grand_total:,.2f}")

        self.email_results.delete("1.0", "end")
        self.email_results.insert("1.0", "\n".join(lines))

        if history_items:
            self.history.add(self._current_customer, history_items, grand_total)
            self._refresh_history()

    def _on_apply_check(self):
        default_ton = self._safe_float(self.default_tonnage.get())
        default_len = self._safe_float(self.default_length.get())

        if not self.item_widgets:
            messagebox.showwarning("No items", "Extract items first.")
            return

        for w in self.item_widgets:
            if default_ton:
                w["tonnage_entry"].delete(0, "end")
                w["tonnage_entry"].insert(0, str(default_ton))
            if default_len:
                w["length_entry"].delete(0, "end")
                w["length_entry"].insert(0, str(default_len))

    def _clear_all(self):
        self.email_input.delete("1.0", "end")
        self.default_length.delete(0, "end")
        self.default_tonnage.delete(0, "end")
        self.apply_length_var.set(False)
        self.apply_tonnage_var.set(False)
        for w in self.items_frame.winfo_children():
            w.destroy()
        self.item_widgets = []
        self.email_results.delete("1.0", "end")
        self._current_customer = ""

    def _copy_email_results(self):
        text = self.email_results.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Nothing to copy", "Generate a quote first.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ── Logic: Quick Quote ─────────────────────────────────────────────────────
    def _process_quick_quote(self):
        query = self.quick_input.get().strip()
        if not query:
            return
        try:
            extracted = self.claude.extract_quick_quote(query, self.db.get_all_products())
        except Exception as e:
            messagebox.showerror("Claude API Error", str(e))
            return

        product = self.db.find_product(extracted.get("product", ""))
        if not product:
            self.quick_results.delete("1.0", "end")
            self.quick_results.insert(
                "1.0", f"Product not found: {extracted.get('product', '')}\n\nCheck code or description.")
            return

        length  = self._safe_float(str(extracted.get("length", 0)))
        tonnage = self._safe_float(str(extracted.get("tonnage", 0)))
        qty     = max(1, int(extracted.get("qty", 1) or 1))
        total   = calculate_line_price(product, length, qty, tonnage)

        lines = [
            product["description"],
            "",
            f"  Length   {length} m",
            f"  Qty      {qty}",
            f"  Tonnage  £{tonnage}/t",
            f"  kg/m     {product['weight']:.2f}",
            "",
            f"  = £{total:,.2f}",
        ]
        self.quick_results.delete("1.0", "end")
        self.quick_results.insert("1.0", "\n".join(lines))

        self.history.add("", [{"product": product["description"], "length": length,
                                "qty": qty, "tonnage": tonnage, "total": total}], total)
        self._refresh_history()

    def _copy_quick_results(self):
        text = self.quick_results.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Nothing to copy", "Generate a quote first.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # ── Logic: History ─────────────────────────────────────────────────────────
    def _refresh_history(self):
        for w in self.history_frame.winfo_children():
            w.destroy()

        entries = self.history.get_all()
        if not entries:
            ctk.CTkLabel(self.history_frame, text="No quotes yet.",
                         font=F["label"], text_color=C["text_muted"]).pack(pady=20)
            return

        for idx, entry in enumerate(entries):
            self._render_history_row(entry, idx)

    def _render_history_row(self, entry: Dict, idx: int = 0):
        row_bg = C["row_even"] if idx % 2 == 0 else C["row_odd"]
        row = ctk.CTkFrame(self.history_frame, fg_color=row_bg, corner_radius=0)
        row.pack(fill="x")

        ts = entry["timestamp"].replace("T", "  ")
        kw = dict(fg_color="transparent", font=F["label"], text_color=C["text"], anchor="w")

        ctk.CTkLabel(row, text=ts,                           width=165, **kw).pack(side="left", padx=6, pady=5)
        ctk.CTkLabel(row, text=entry["customer"] or "—",     width=270, **kw).pack(side="left", padx=4)
        ctk.CTkLabel(row, text=str(len(entry["items"])),     width=60,  **kw).pack(side="left", padx=4)
        ctk.CTkLabel(row, text=f"£{entry['total']:,.2f}",   width=120,
                     fg_color="transparent", font=("Segoe UI", 10, "bold"),
                     text_color=C["accent"], anchor="w").pack(side="left", padx=4)
        _btn(row, "Reload", lambda e=entry: self._reload_history_entry(e),
             "ghost", width=80, height=BTN_H_SM).pack(side="left", padx=6)

    def _reload_history_entry(self, entry: Dict):
        self._clear_all()
        self.tabview.set("Email Mode")
        self._current_customer = entry["customer"]
        items = [{"product": it["product"], "length": it.get("length", 0),
                  "qty": it.get("qty", 1), "tonnage": it.get("tonnage", 0)}
                 for it in entry["items"]]
        self._render_items(items)
        self._calculate_and_display()

    # ── Utility ────────────────────────────────────────────────────────────────
    @staticmethod
    def _safe_float(val: str) -> float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0


# ── Entry point ─────────────────────────────────────────────────────────────────
def main():
    root = ctk.CTk()
    SteelPricerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
