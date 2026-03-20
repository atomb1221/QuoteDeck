"""
Email parsing via Claude API.
Claude's job: extract what the customer wrote verbatim (NLP only).
Python's job: match to the product database (deterministic, no guessing).
"""
import re
import json
from typing import Dict, List


def extract_items_from_email(email_text: str, product_list: List[Dict], client) -> Dict:
    """Extract line items from a customer email.

    Claude extracts the raw product descriptions exactly as the customer wrote
    them, plus qty/length/tonnage. Python handles the database matching.
    """
    prompt = f"""Extract steel product requests from this customer email.

Customer email:
{email_text}

For each product the customer is requesting, extract:
- product: ONLY the steel dimensions and type. Strip ONLY explicit quantity words/prefixes (e.g. "3no", "5 off", "1 off", "x2 " at the very start before dimensions). Example: "3no 25x25x3mm angle" → product="25x25x3mm angle", qty=3
- length: length in metres as a number (e.g. "6 metre long" → 6, "6000mm" → 6, "20 foot" → 6.1). Use 0 if no length is given.
- qty: the quantity number only. A quantity prefix is a number immediately followed by "no", "off", "nr", or "x" at the very START before any dimensions. Default 1 if not stated.
- tonnage: price per tonne only if explicitly stated with a £ symbol (e.g. "£850/tonne" → 850). Use 0 otherwise.

CRITICAL — DO NOT confuse dimensions with quantities:
- "50 x 6" is a steel dimension (50mm × 6mm flat bar), NOT qty=50 of "6"
- "200 x 100 x 10mm" is a steel dimension, NOT qty=200 of "100 x 10mm"
- "100 x 50 x 3 RHS" is a steel dimension, NOT qty=100 of anything
- Quantity prefixes always come with words like "no", "off", "nr", or a bare "x" followed by a single small integer BEFORE the dimensions: "x2 50x50x5 angle" → qty=2, product="50x50x5 angle"
- If a line is just dimensions and a steel type with no explicit quantity word, qty=1

TERMINOLOGY TO EXPAND:
- "8x4" or "8 x 4" sheet = 2500 x 1250mm sheet (write as "2500 x 1250")
- "10x5" or "10 x 5" sheet = 3000 x 1500mm sheet (write as "3000 x 1500")
- "Galv" or "Galvanised" are the same — use whichever the customer wrote
- "Chequer" and "Checker" are the same
- "HR" = Hot Rolled, "CR" = Cold Rolled

RULES:
- Extract ONLY products the customer explicitly asked for
- Do NOT include quantity words ("no", "off", "nr") in the product field
- Do NOT substitute or guess — use the customer's exact wording for dimensions and type
- For sheet products (HR sheet, Galv sheet, Zintec etc.), length is 0 — sheets are sold per sheet not per metre
- Return exactly one item per distinct product request

Return ONLY valid JSON, no commentary:
{{
  "customer_name": "company or person name, empty string if not found",
  "items": [
    {{"product": "exact description from email", "length": 0, "qty": 1, "tonnage": 0}}
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
