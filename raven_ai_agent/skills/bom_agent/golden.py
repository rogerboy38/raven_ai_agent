"""Golden-Number utilities (v2, principle 7).

AMB item/batch codes embed the Golden Number: {product(4)}{folio(3)}{year(2)}{plant(1)}
e.g. 043300001 -> product 0433, folio 300, year 00... (see DQS PLANT_COST_CENTER_MAP).
FEFO must rank by (year, folio) — the true production sequence — NEVER by
manufacturing_date, which on migrated data is the MIGRATION date.
"""
import re
from typing import Optional, Tuple

# Source comments disagree on width (DQS spec says 10 digits incl. plant,
# its own example is 9). Accept both: 10-digit {prod4}{folio3}{yy2}{plant1}
# first, else 9-digit {prod4}{folio3}{yy2}.
GOLDEN10_RE = re.compile(r"\b(\d{4})(\d{3})(\d{2})([1-5])\b")
GOLDEN9_RE = re.compile(r"\b(\d{4})(\d{3})(\d{2})")  # loose tail: tolerates longer runs

PLANTS = {"1": "Mix", "2": "Dry", "3": "Juice", "4": "Laboratory", "5": "Formulated"}


def parse(code: str) -> Optional[dict]:
    m = GOLDEN10_RE.search(code or "")
    if m:
        product, folio, year, plant = m.groups()
        return {"product": product, "folio": int(folio), "year": int(year),
                "plant": PLANTS.get(plant, plant), "golden": m.group(0)}
    m = GOLDEN9_RE.search(code or "")
    if m:
        product, folio, year = m.groups()
        return {"product": product, "folio": int(folio), "year": int(year),
                "plant": None, "golden": m.group(0)}
    return None


def fefo_key(code: str) -> Tuple[int, int]:
    """Sort key: oldest production first. Unparseable codes sort LAST so
    they are consumed only after properly-numbered stock."""
    g = parse(code)
    if not g:
        return (99, 999)
    return (g["year"], g["folio"])
