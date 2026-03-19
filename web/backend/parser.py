"""
Email parsing via Claude API.
Plug in your API key via config.json at the project root:
  {"anthropic_api_key": "sk-ant-..."}

The extract_items and extract_quick_quote functions below mirror the logic
from the original steel_pricer.py — swap the placeholder bodies for the
real Claude calls once you have the key wired up.
"""
import re
import json
from typing import Dict, List


def extract_items_from_email(email_text: str, product_list: List[Dict], client) -> Dict:
    """Call Claude to extract line items from a customer email.

    Args:
        email_text:   Raw email body.
        product_list: Full product list from ProductDatabase.
        client:       An initialised anthropic.Anthropic client.

    Returns:
        {"customer_name": str, "items": [{"product": str, "length": float,
                                          "qty": int, "tonnage": float}]}
    """
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

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = message.content[0].text.strip()
    m = re.search(r"\{.*\}", response_text, re.DOTALL)
    return json.loads(m.group(0)) if m else {"customer_name": "", "items": []}


def extract_quick_quote(query: str, product_list: List[Dict], client) -> Dict:
    """Parse a natural-language quick quote request.

    Returns:
        {"product": str, "length": float, "qty": int, "tonnage": float}
    """
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

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = message.content[0].text.strip()
    m = re.search(r"\{.*\}", response_text, re.DOTALL)
    return json.loads(m.group(0)) if m else {"product": "", "length": 0, "qty": 1, "tonnage": 0}
