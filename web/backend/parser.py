"""
Email parsing via Claude API.
Claude's job: extract AND normalise to standard steel terminology.
Python's job: match the normalised description to the product database.
"""
import re
import json
from typing import Dict, List


def extract_items_from_email(email_text: str, product_list: List[Dict], client) -> Dict:
    """Extract and normalise line items from a customer email.

    Claude interprets steel industry terminology and converts to standard forms
    (e.g. '33mm pipe' -> '33.7 CHS', '6 inch channel' -> '152 x 76 channel').
    Python then matches the normalised description to the database.
    """
    prompt = f"""You are a steel industry expert. Extract and NORMALISE product requests from this customer email into standard UK steel stockholder terminology so they can be matched against a product database.

Customer email:
{email_text}

For each product, extract:
- product: the NORMALISED steel description (apply all rules below)
- length: length in metres (e.g. "6 metre" -> 6, "6000mm" -> 6, "20 foot" -> 6.1). Use 0 if not given.
- qty: quantity number only. Strip prefixes like "3no", "5 off", "x2". Default 1 if not stated.
- tonnage: price per tonne only if stated with a pound sign (e.g. "850/tonne" -> 850). Use 0 otherwise.

CRITICAL - DO NOT confuse dimensions with quantities:
- "50 x 6" is a steel dimension (50mm x 6mm flat bar), NOT qty=50 of "6"
- "200 x 100 x 10mm" is a dimension, NOT qty=200 of "100 x 10mm"
- "100 x 50 x 3 RHS" is a dimension, NOT qty=100 of anything
- Quantity words are: "no", "off", "nr", or a bare "x" immediately before dimensions: "x2 50x50x5 angle" -> qty=2, product="50 x 50 x 5 angle"
- A line with only dimensions and a steel type and no explicit quantity word means qty=1

NORMALISATION RULES for the product field:

1. ROUND BAR / SOLID ROUND - normalise to "X dia":
   - "25mm round bar", "25 dia", "25mm solid round", "25mm RB", "O25" -> "25 dia"

2. ROUND PIPE / TUBE / CHS - map customer's rounded size to nearest standard CHS OD:
   Standard ODs: 21.3, 26.9, 33.7, 42.4, 48.3, 60.3, 76.1, 88.9, 114.3, 139.7, 168.3
   - "21mm pipe/tube" -> "21.3 CHS"
   - "27mm pipe/tube" -> "26.9 CHS"
   - "33mm pipe/tube/CHS" -> "33.7 CHS"
   - "42mm pipe/tube" -> "42.4 CHS"
   - "48mm pipe/tube" -> "48.3 CHS"
   - "60mm pipe/tube" -> "60.3 CHS"
   - "76mm pipe/tube" -> "76.1 CHS"
   - "89mm pipe/tube" -> "88.9 CHS"
   - "114mm pipe/tube" -> "114.3 CHS"
   - "140mm pipe/tube" -> "139.7 CHS"
   - "168mm pipe/tube" -> "168.3 CHS"
   - Already exact (e.g. "33.7 CHS"): leave unchanged

3. CHANNEL / CHANNEL IRON / PFC - convert imperial to metric:
   - "4 inch channel", '4" channel' -> "100 x 50 channel"
   - "5 inch channel" -> "125 x 65 channel"
   - "6 inch channel", '6" channel' -> "152 x 76 channel"
   - "8 inch channel" -> "203 x 76 channel"
   - "10 inch channel" -> "254 x 76 channel"
   - Already metric: leave unchanged. "Channel iron" = "channel"

4. ANGLE / ANGLE IRON - "angle iron" = "angle". Keep dimensions:
   - "60x60x6 angle iron" -> "60 x 60 x 6 angle"
   - "equal angle 60x60x6" -> "60 x 60 x 6 angle"

5. BOX / BOX IRON / SHS - "box iron" or "box" = "SHS":
   - "100x100x5 box iron" -> "100 x 100 x 5 SHS"
   - "60x60x4 box" -> "60 x 60 x 4 SHS"

6. RECTANGULAR HOLLOW SECTION / RHS:
   - "100x50x3 RHS", "100 x 50 x 3 rectangular" -> "100 x 50 x 3 RHS"

7. SHEETS:
   - "8x4" or "8 x 4" sheet -> "2500 x 1250" sheet
   - "10x5" or "10 x 5" sheet -> "3000 x 1500" sheet
   - Sheet products (HR sheet, Galv sheet, Zintec, chequer plate): length = 0

8. GENERAL:
   - "Galvanised" -> "galv"
   - "Checker plate" = "chequer plate"
   - "HR" = Hot Rolled, "CR" = Cold Rolled
   - Use spaces around x: "100 x 50 x 3" not "100x50x3"
   - Remove "mm" from dimensions where it is just clutter (e.g. "60 x 60 x 6" not "60mm x 60mm x 6mm")

Return ONLY valid JSON, no commentary:
{{
  "customer_name": "company or person name, empty string if not found",
  "items": [
    {{"product": "normalised description", "length": 0, "qty": 1, "tonnage": 0}}
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
