"""PocketPricer — FastAPI backend."""
import json
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from .database import ProductDatabase
from .pricer import calculate_line_price
from .db import Database
from . import parser

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # web/
ROOT_DIR     = os.path.dirname(BASE_DIR)                                     # SteelPricer/
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
CONFIG_FILE  = os.path.join(ROOT_DIR, "config.json")

# DATA_DIR: set to Railway volume mount path (e.g. /data) for persistent storage.
# Falls back to the repo root for local runs.
_DATA_DIR = os.environ.get("DATA_DIR", ROOT_DIR)
PRODUCTS_XLS = os.path.join(_DATA_DIR, "products.xlsx")
SQLITE_DB    = os.path.join(_DATA_DIR, "pocketpricer.db")

# On first deploy with a volume, seed products.xlsx from the repo copy
if _DATA_DIR != ROOT_DIR:
    import shutil
    os.makedirs(_DATA_DIR, exist_ok=True)
    _repo_products = os.path.join(ROOT_DIR, "products.xlsx")
    if not os.path.exists(PRODUCTS_XLS) and os.path.exists(_repo_products):
        shutil.copy(_repo_products, PRODUCTS_XLS)

# ── Services ───────────────────────────────────────────────────────────────────
products_db = ProductDatabase(PRODUCTS_XLS)
db          = Database(SQLITE_DB)

# Load Claude client — env var takes priority (Railway), fallback to config.json (local)
_claude_client = None
_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not _key and os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        _cfg = json.load(f)
    _key = _cfg.get("anthropic_api_key", "")
if _key and not _key.startswith("your-"):
    from anthropic import Anthropic
    _claude_client = Anthropic(api_key=_key)

# ── Auth middleware ─────────────────────────────────────────────────────────────
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow login page, login POST, and static assets
        if path == "/login" or path.startswith("/static/"):
            return await call_next(request)

        # Check session cookie
        token = request.cookies.get("session")
        user  = db.get_session_user(token) if token else None

        if not user:
            # Browser page request → redirect; API/fetch request → 401 JSON
            if "text/html" in request.headers.get("accept", "") and request.method == "GET":
                return RedirectResponse("/login", status_code=302)
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        request.state.user = user
        return await call_next(request)


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Tonnage", docs_url="/api/docs")

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))


# ── Auth endpoints ──────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/login")
def login(req: LoginRequest, response: Response):
    user = db.verify_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = db.create_session(user["id"])
    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)
    return {"username": user["username"]}


@app.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session")
    if token:
        db.delete_session(token)
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/me")
def me(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ── Models ─────────────────────────────────────────────────────────────────────
class ExtractRequest(BaseModel):
    email_text: str


class LineItem(BaseModel):
    product:  str
    length:   float = 0.0
    qty:      int   = 1
    tonnage:  float = 0.0


class CalculateRequest(BaseModel):
    items:         List[LineItem]
    customer_name: Optional[str] = ""
    tonnage_price: Optional[float] = 0.0


class ProductRequest(BaseModel):
    code:        str
    description: str
    weight:      float
    type:        str = ""


class SaveQuoteRequest(BaseModel):
    name:          str
    customer_name: Optional[str] = ""
    total_value:   float
    items_count:   int
    quote_data:    list


class RenameRequest(BaseModel):
    name: str


# ── Customer endpoints ──────────────────────────────────────────────────────────
@app.get("/customers")
def search_customers(search: str = ""):
    if not search:
        return {"customers": []}
    customers = db.search_customers(search)
    return {"customers": customers}


@app.get("/customers/{customer_id}/prices")
def get_customer_prices(customer_id: int):
    quotes = db.get_customer_quotes(customer_id)
    return {"quotes": quotes}


# ── Product endpoints ───────────────────────────────────────────────────────────
@app.get("/products")
def get_products():
    all_p = products_db.get_all()
    return {
        "count": len(all_p),
        "products": [{"idx": i, **p} for i, p in enumerate(all_p)],
    }


@app.post("/products")
def create_product(req: ProductRequest):
    product = products_db.add_product(req.code, req.description, req.weight, req.type)
    return {"idx": len(products_db.get_all()) - 1, **product}


@app.put("/products/{idx}")
def update_product(idx: int, req: ProductRequest):
    if idx < 0 or idx >= len(products_db.get_all()):
        raise HTTPException(status_code=404, detail="Product not found")
    product = products_db.update_product(idx, req.code, req.description, req.weight, req.type)
    return {"idx": idx, **product}


@app.delete("/products/{idx}")
def delete_product(idx: int):
    if idx < 0 or idx >= len(products_db.get_all()):
        raise HTTPException(status_code=404, detail="Product not found")
    products_db.delete_product(idx)
    return {"ok": True}


# ── Quote endpoints ─────────────────────────────────────────────────────────────
@app.post("/extract")
def extract(req: ExtractRequest):
    if not _claude_client:
        raise HTTPException(
            status_code=503,
            detail="Claude API key not configured. Add anthropic_api_key to config.json.",
        )
    try:
        result = parser.extract_items_from_email(
            req.email_text, products_db.get_all(), _claude_client
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    enriched = []
    for item in result.get("items", []):
        requested  = item["product"]
        candidates = products_db.find_all_products(requested)

        from .pricer import is_sheet as _is_sheet_fn
        def _is_sheet(p):
            return _is_sheet_fn(p)

        if not candidates:
            # Not in database at all
            enriched.append({**item, "requested": requested, "matched": False,
                             "not_found": True, "ambiguous": False,
                             "weight": 0.0, "is_sheet": False})

        elif len(candidates) == 1:
            # Unambiguous match
            p = candidates[0]
            enriched.append({**item, "requested": requested,
                             "product": p["description"], "weight": p["weight"],
                             "is_sheet": _is_sheet(p), "matched": True,
                             "not_found": False, "ambiguous": False})

        else:
            # Multiple matches — try type-hint auto-resolution first
            hint = products_db.type_hint_from_text(requested)
            if hint:
                filtered = [c for c in candidates
                            if products_db.product_matches_type_hint(c, hint)]
                if len(filtered) == 1:
                    p = filtered[0]
                    enriched.append({**item, "requested": requested,
                                     "product": p["description"], "weight": p["weight"],
                                     "is_sheet": _is_sheet(p), "matched": True,
                                     "not_found": False, "ambiguous": False})
                    continue

            # Still ambiguous — send candidates to the frontend for the user to choose
            enriched.append({
                **item,
                "requested":  requested,
                "matched":    False,
                "not_found":  False,
                "ambiguous":  True,
                "candidates": [{"description": c["description"],
                                "weight": c["weight"],
                                "type": c.get("type", ""),
                                "is_sheet": _is_sheet(c)}
                               for c in candidates],
                "weight":   0.0,
                "is_sheet": False,
            })

    not_found = [e["requested"] for e in enriched if e.get("not_found")]
    ambiguous  = [e["requested"] for e in enriched if e.get("ambiguous")]
    return {
        "customer_name": result.get("customer_name", ""),
        "items":         enriched,
        "not_found":     not_found,
        "ambiguous":     ambiguous,
    }


@app.post("/calculate")
def calculate(req: CalculateRequest):
    lines = []
    grand = 0.0
    calc_items = []

    for item in req.items:
        product = products_db.find_product(item.product)
        if not product:
            lines.append({"product": item.product, "total": None, "error": "Not found"})
            continue

        from .pricer import is_sheet as _is_sheet_fn
        total = calculate_line_price(product, item.length, item.qty, item.tonnage)
        grand += total
        is_sheet = _is_sheet_fn(product)
        line = {
            "product":  product["description"],
            "length":   item.length,
            "qty":      item.qty,
            "tonnage":  item.tonnage,
            "weight":   product["weight"],
            "is_sheet": is_sheet,
            "total":    round(total, 2),
        }
        lines.append(line)
        calc_items.append(line)

    # Auto-save quote snapshot if we have a customer and priced items
    customer_name = (req.customer_name or "").strip()
    customer_id   = None

    if customer_name and calc_items:
        from datetime import datetime
        customer    = db.find_or_create_customer(customer_name)
        customer_id = customer["id"]
        now = datetime.now()
        quote_name  = f"{now.day} {now.strftime('%b %Y')}"
        db.save_quote(customer_id, quote_name, round(grand, 2), len(calc_items), calc_items)

        # Keep only last 3 auto-saved quotes per customer (trim older ones)
        with db._conn() as conn:
            conn.execute(
                """DELETE FROM quotes WHERE customer_id = ?
                   AND id NOT IN (
                       SELECT id FROM quotes WHERE customer_id = ?
                       ORDER BY created_at DESC LIMIT 3
                   )""",
                (customer_id, customer_id),
            )
            conn.commit()

    return {"lines": lines, "grand_total": round(grand, 2), "customer_id": customer_id}


# ── Saved quotes ────────────────────────────────────────────────────────────────
@app.get("/quotes")
def list_quotes():
    return {"quotes": db.list_quotes()}


@app.post("/quotes")
def save_quote(req: SaveQuoteRequest):
    customer_id = None
    if req.customer_name:
        customer = db.find_or_create_customer(req.customer_name)
        customer_id = customer["id"]
    quote = db.save_quote(
        customer_id, req.name, req.total_value, req.items_count, req.quote_data
    )
    return quote


@app.get("/quotes/{quote_id}")
def get_quote(quote_id: int):
    quote = db.get_quote(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@app.put("/quotes/{quote_id}")
def rename_quote(quote_id: int, req: RenameRequest):
    if not db.rename_quote(quote_id, req.name):
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"ok": True}


@app.delete("/quotes/{quote_id}")
def delete_quote(quote_id: int):
    if not db.delete_quote(quote_id):
        raise HTTPException(status_code=404, detail="Quote not found")
    return {"ok": True}
