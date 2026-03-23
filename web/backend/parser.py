"""
Email parsing via Claude API.

Architecture:
- Claude receives the FULL product database and the customer email.
- Claude interprets steel terminology AND picks the best matching product by index.
- Python uses the returned index to look up the product directly — no string matching needed.
"""
import re
import json
from typing import Dict, List


def _build_product_list(products: List[Dict]) -> str:
    lines = []
    for i, p in enumerate(products):
        weight_str = f"{p['weight']:.2f} kg/m"
        type_str   = f" | {p['type']}" if p.get("type") else ""
        lines.append(f"#{i}: {p['description']} ({weight_str}{type_str})")
    return "\n".join(lines)


def extract_items_from_email(email_text: str, product_list: List[Dict], client) -> Dict:
    """Extract line items from a customer email.

    Claude receives the full product list and returns the best-matching product
    index (#) for each item, along with a match_type so the UI can ask the user
    to confirm approximate matches.
    """
    db_text = _build_product_list(product_list)

    prompt = f"""You are a UK steel stockholder's quoting assistant. You have the customer's email AND our complete product database below.

Your job for each product the customer requests:
1. Understand what they are asking for (interpret slang, imperial sizes, abbreviations)
2. Scan the ACTUAL product database and find the best matching product
3. Return that product's INDEX NUMBER (the # before the colon)

PRODUCT DATABASE:
{db_text}

CUSTOMER EMAIL:
{email_text}

INTERPRETATION KNOWLEDGE:
- Round bar / solid round / "dia" → look for "dia", "RB", "round bar" in the database
- Round pipe / tube / CHS → standard ODs: 21.3, 26.9, 33.7, 42.4, 48.3, 60.3, 76.1, 88.9, 114.3, 139.7, 168.3. "33mm pipe" → find 33.7 OD
- Channel / channel iron / PFC → "6 inch channel" ≈ 152×76 → look for 150×75 or 152×76 PFC in the database
- Angle iron = angle. Box iron = SHS. Channel iron = channel/PFC
- "8x4" or "8 x 4" sheet = 2500×1250. "10x5" sheet = 3000×1500
- Galvanised = galv. Checker/chequer plate = same thing
- HR = hot rolled, CR = cold rolled

MATCHING RULES:
- Search the database for the closest product. Near misses are fine — flag them as approximate.
- For imperial channels (4", 5", 6", 8", 10"), find the nearest metric PFC/channel in the database
- For "box iron" find SHS with matching dimensions
- For rounded pipe ODs find the nearest standard CHS
- If no reasonable match exists at all, return product_idx: null

QUANTITY / LENGTH RULES:
- Strip quantity prefixes: "5no", "10no", "1 off", "x2" at the START → qty field. Never include in product.
- "50 x 6" is a DIMENSION not qty=50. "200 x 100 x 10" is a DIMENSION not qty=200.
- length: metres. "6000mm" → 6. "20 foot" → 6.1. 0 if not given.
- tonnage: only if stated with £ symbol. 0 otherwise.
- For sheets: length = 0

MATCH TYPE:
- "exact": customer's dimensions clearly match the database product
- "approximate": interpreted/rounded (e.g. 6" channel → 150×75 PFC, 33mm pipe → 33.7 CHS)
- "not_found": no reasonable match in the database

Return ONLY valid JSON, no commentary:
{{
  "customer_name": "company or person name if present, else empty string",
  "items": [
    {{
      "product_idx": 47,
      "product": "exact description from the database for that index",
      "match_type": "exact",
      "length": 0,
      "qty": 1,
      "tonnage": 0
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = message.content[0].text.strip()
    m = re.search(r"\{.*\}", response_text, re.DOTALL)
    return json.loads(m.group(0)) if m else {"customer_name": "", "items": []}
