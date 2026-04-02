"""
Email parsing via Claude API.

Claude's job: extract and NORMALISE customer descriptions to standard steel terminology.
Python's job: deterministic database matching — Claude never sees or guesses from the DB.
"""
import re
import json
from typing import Dict, List


def extract_items_from_email(email_text: str, product_list: List[Dict], client) -> Dict:
    prompt = f"""You are a UK steel industry expert. Extract and NORMALISE product requests from this customer email into standard steel dimensions and type names.

Customer email:
{email_text}

For each product, return:
- product: normalised steel description (apply all rules below)
- length: metres. "6000mm"→6, "20 foot"→6.1, 0 if not given
- qty: number only. Strip "3no", "5 off", "1no", "x2" prefixes. Default 1.
- tonnage: only if stated with £. Default 0.

CRITICAL — dimensions vs quantities:
- "50 x 6" = 50mm × 6mm dimension, NOT qty=50
- "200 x 100 x 10mm" = dimension, NOT qty=200
- Quantity words are: no, off, nr, or bare x before dimensions: "x2 50x50x5" → qty=2

NORMALISATION — output standard metric dimensions + type:

1. ROUND BAR: "25mm round bar", "25 dia", "Ø25", "25mm solid round" → "25 dia"
2. SQUARE BAR: "25mm square bar", "25mm solid square", "25 square" → "25 square"
3. AMBIGUOUS BAR: "25mm bar" or "25mm steel bar" (no round/square qualifier) → "25 bar"
   (Python will ask the user to clarify round vs square)
4. PIPE/TUBE/CHS — map to nearest standard OD:
   21mm→21.3, 27mm→26.9, 33mm→33.7, 42mm→42.4, 48mm→48.3,
   60mm→60.3, 76mm→76.1, 89mm→88.9, 114mm→114.3, 140mm→139.7, 168mm→168.3
   Output as: "42.4 CHS" (include OD only, drop wall thickness unless explicitly given)
   If wall thickness given: "42.4 x 3 CHS"
5. IPE BEAMS: "IPE100", "IPE 100", "ipe100", "I.P.E 100", "I.P.E. 100", "IPE beam 100" → "IPE 100"
   Standard depths: 80, 100, 120, 140, 160, 180, 200, 220, 240, 270, 300, 330, 360, 400
   IPE A series (lighter variant): "IPEA 100", "IPE 100A" → "IPEA 100"
6. CHANNEL — imperial to metric:
   4"→100 x 50, 5"→125 x 65, 6"→152 x 76, 8"→203 x 76, 10"→254 x 76
   Output as: "152 x 76 channel"
6. ANGLE IRON = angle: "60x60x6 angle iron" → "60 x 60 x 6 angle"
7. BOX IRON / BOX = SHS: "100x100x5 box iron" → "100 x 100 x 5 SHS"
8. SHEETS: "8x4"=2500x1250, "10x5"=3000x1500. Always include thickness.
   "8 x 4 x 3mm HR sheet" → "2500 x 1250 x 3 HR sheet". length=0
9. Galvanised→galv. Checker/chequer=same. HR=hot rolled, CR=cold rolled.
10. Spacing: use " x " between dims. Remove trailing "mm" clutter.

Return ONLY valid JSON:
{{
  "customer_name": "name if present else empty string",
  "items": [
    {{
      "requested_text": "customer's EXACT words for this product BEFORE normalisation (e.g. '50 x 50 x 5mm', '6 inch channel')",
      "product": "normalised description",
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
