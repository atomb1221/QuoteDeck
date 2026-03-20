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
- product: the product description EXACTLY as written in the email (e.g. "200x100x8 RHS", "50x50x5 SHS box section")
- length: length in metres as a number (e.g. "6 metre long" → 6, "6000mm" → 6, "20 foot" → 6.1). Use 0 if no length is given.
- qty: quantity requested as a number (e.g. "3no" → 3, "5 off" → 5, "x2" → 2). Default 1 if not stated.
- tonnage: price per tonne only if explicitly stated with a £ symbol (e.g. "£850/tonne" → 850). Use 0 otherwise.

RULES:
- Extract ONLY products the customer explicitly asked for
- Do NOT add products not mentioned in the email
- Do NOT substitute or guess — use the customer's exact wording
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
