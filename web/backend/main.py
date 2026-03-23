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

from .database import ProductDatabase, load_from_xlsx
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
PRODUCTS_XLS = os.path.join(ROOT_DIR, "products.xlsx")   # always the repo copy (seed only)
SQLITE_DB    = os.path.join(_DATA_DIR, "pocketpricer.db")

os.makedirs(_DATA_DIR, exist_ok=True)

# ── Services ───────────────────────────────────────────────────────────────────
db = Database(SQLITE_DB)

# Load the xlsx once at startup — used only to seed the DB for users with no products
_xlsx_products = load_from_xlsx(PRODUCTS_XLS) if os.path.exists(PRODUCTS_XLS) else []

db.seed_admin_if_empty(_xlsx_products)   # creates admin/admin + seeds products on first deploy

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


def _products_db(user_id: int) -> ProductDatabase:
    """Return a matcher loaded with the current user's product list."""
    return ProductDatabase(db.get_products(user_id))


# ── Auth middleware ─────────────────────────────────────────────────────────────
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow login page, login POST, health check, and static assets
        if path in ("/login", "/health") or path.startswith("/static/"):
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


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


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
def search_customers(request: Request, search: str = ""):
    if not search:
        return {"customers": []}
    user_id = request.state.user["id"]
    customers = db.search_customers(search, user_id)
    return {"customers": customers}


@app.get("/customers/{customer_id}/prices")
def get_customer_prices(customer_id: int):
    quotes = db.get_customer_quotes(customer_id)
    return {"quotes": quotes}


# ── Product endpoints ───────────────────────────────────────────────────────────
@app.get("/products")
def get_products(request: Request):
    user_id = request.state.user["id"]
    products = db.get_products(user_id)
    # Return id as idx so the frontend's existing edit/delete calls work unchanged
    return {
        "count": len(products),
        "products": [{"idx": p["id"], **p} for p in products],
    }


@app.post("/products")
def create_product(request: Request, req: ProductRequest):
    user_id = request.state.user["id"]
    product = db.add_product(user_id, req.code, req.description, req.weight, req.type)
    return {"idx": product["id"], **product}


@app.put("/products/{product_id}")
def update_product(product_id: int, request: Request, req: ProductRequest):
    user_id = request.state.user["id"]
    product = db.update_product(product_id, user_id, req.code, req.description, req.weight, req.type)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"idx": product["id"], **product}


@app.delete("/products/{product_id}")
def delete_product(product_id: int, request: Request):
    user_id = request.state.user["id"]
    if not db.delete_product(product_id, user_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return {"ok": True}


# ── Quote endpoints ─────────────────────────────────────────────────────────────
@app.post("/extract")
def extract(request: Request, req: ExtractRequest):
    if not _claude_client:
        raise HTTPException(
            status_code=503,
            detail="Claude API key not configured. Add anthropic_api_key to config.json.",
        )
    user_id   = request.state.user["id"]
    pdb       = _products_db(user_id)

    try:
        result = parser.extract_items_from_email(req.email_text, pdb.products, _claude_client)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from .pricer import is_sheet as _is_sheet_fn

    enriched = []

    for item in result.get("items", []):
        requested  = item.get("product", "")
        candidates = pdb.find_all_products(requested)

        if not candidates:
            enriched.append({**item, "requested": requested, "matched": False,
                             "not_found": True, "ambiguous": False,
                             "weight": 0.0, "is_sheet": False})
            continue

        # ── Ambiguity guard: same dims, different types, no type keyword ──────
        customer_words = item.get("requested_text", requested)
        hint = pdb.type_hint_from_text(customer_words)
        if len(candidates) > 1 and not hint:
            diff_types = {c.get("type", "").lower() for c in candidates}
            if len(diff_types) > 1:
                enriched.append({
                    **item, "requested": requested,
                    "matched": False, "not_found": False, "ambiguous": True,
                    "candidates": [{"description": c["description"], "weight": c["weight"],
                                    "type": c.get("type", ""), "is_sheet": _is_sheet_fn(c)}
                                   for c in candidates],
                    "weight": 0.0, "is_sheet": False,
                })
                continue

        # ── Narrow by type hint if multiple candidates remain ─────────────────
        if len(candidates) > 1 and hint:
            filtered = [c for c in candidates if pdb.product_matches_type_hint(c, hint)]
            if filtered:
                candidates = filtered

        # ── Single match: classify exact vs approximate ───────────────────────
        p  = candidates[0]
        sn = pdb.normalize(pdb._expand_search(requested))
        dn = pdb.normalize(pdb._expand_search(p["description"]))
        match_type = "exact" if sn == dn else "approximate"

        enriched.append({**item, "requested": requested,
                         "product": p["description"], "weight": p["weight"],
                         "is_sheet": _is_sheet_fn(p), "matched": True,
                         "match_type": match_type,
                         "not_found": False, "ambiguous": False})

    not_found = [e["requested"] for e in enriched if e.get("not_found")]
    ambiguous = [e["requested"] for e in enriched if e.get("ambiguous")]
    return {
        "customer_name": result.get("customer_name", ""),
        "items":         enriched,
        "not_found":     not_found,
        "ambiguous":     ambiguous,
    }


@app.post("/calculate")
def calculate(request: Request, req: CalculateRequest):
    user_id = request.state.user["id"]
    pdb     = _products_db(user_id)

    lines      = []
    grand      = 0.0
    calc_items = []

    for item in req.items:
        product = pdb.find_product(item.product)
        if not product:
            lines.append({"product": item.product, "total": None, "error": "Not found"})
            continue

        from .pricer import is_sheet as _is_sheet_fn
        total    = calculate_line_price(product, item.length, item.qty, item.tonnage)
        grand   += total
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
        customer    = db.find_or_create_customer(customer_name, user_id)
        customer_id = customer["id"]
        now         = datetime.now()
        quote_name  = f"{now.day} {now.strftime('%b %Y')}"
        db.save_quote(customer_id, quote_name, round(grand, 2), len(calc_items),
                      calc_items, user_id=user_id)

        # Keep only last 3 auto-saved quotes per customer
        with db._conn() as conn:
            conn.execute(
                """DELETE FROM quotes WHERE customer_id = ? AND user_id = ?
                   AND id NOT IN (
                       SELECT id FROM quotes WHERE customer_id = ? AND user_id = ?
                       ORDER BY created_at DESC LIMIT 3
                   )""",
                (customer_id, user_id, customer_id, user_id),
            )
            conn.commit()

    return {"lines": lines, "grand_total": round(grand, 2), "customer_id": customer_id}


# ── Saved quotes ────────────────────────────────────────────────────────────────
@app.get("/quotes")
def list_quotes(request: Request):
    user_id = request.state.user["id"]
    return {"quotes": db.list_quotes(user_id)}


@app.post("/quotes")
def save_quote(request: Request, req: SaveQuoteRequest):
    user_id     = request.state.user["id"]
    customer_id = None
    if req.customer_name:
        customer    = db.find_or_create_customer(req.customer_name, user_id)
        customer_id = customer["id"]
    quote = db.save_quote(customer_id, req.name, req.total_value, req.items_count,
                          req.quote_data, user_id=user_id)
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
