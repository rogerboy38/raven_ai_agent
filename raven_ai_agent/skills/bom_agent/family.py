"""Product-family resolution for the BOM Agent (v2, principle 2).

Client-side family detection so routing decisions are made HERE, with full
knowledge of which families have amb_w_tds master templates — a family
without a template short-circuits with an honest refusal instead of being
mis-mapped (the old 'juice'->0227 bug) or producing a phantom success (#79).

Registry is data, not code: extend by appending. When amb ships #78
(0705/juice template) flip `template_available` to True — one line.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Family:
    code: str
    label: str
    keywords: tuple          # lowercase substrings, EN + ES
    template_available: bool # amb_w_tds master template exists today
    note: str = ""


FAMILIES = (
    Family("0227", "Aloe Powder 200:1", ("0227", "200:1", "200 to 1"), True),
    Family("0307", "Spray-Dried Powder", ("0307", "spray", "spray-dried"), True,
           note="#81: amb template is flat 1-step; real chain is 3-level "
                "SFG-0307-STEP1-MIX -> 0307-CUNETE -> FG. Verify tree depth."),
    Family("0303", "Aloe Powder 0303", ("0303",), False,
           note="parser family exists, no master template yet"),
    Family("0301", "Aloe Powder 0301", ("0301",), False,
           note="parser family exists, no master template yet"),
    Family("HIGHPOL", "High-Polysaccharide", ("highpol", "high pol", "polisac"), True),
    Family("ACETYPOL", "Acetylated Polymer", ("acetypol", "acety"), True),
    Family("0705", "Aloe Juice / Concentrate", 
           ("0705", "juice", "jugo", "concentrate", "concentrado", "30:1", "1:1"), False,
           note="#78: NO master template in amb_w_tds yet — creation must refuse honestly"),
)

_CODE_RE = re.compile(r"\b(0227|0307|0303|0301|0705)\b")


def resolve(text: str) -> Optional[Family]:
    """Resolve a family from free text / TDS name / item code. Explicit
    4-digit codes win; then keyword hits (longest keyword first so
    'concentrado' beats shorter accidental matches)."""
    t = (text or "").lower()
    m = _CODE_RE.search(t)
    if m:
        code = m.group(1)
        for f in FAMILIES:
            if f.code == code:
                return f
    hits = []
    for f in FAMILIES:
        for kw in f.keywords:
            if kw in t:
                hits.append((len(kw), f))
    if hits:
        hits.sort(key=lambda x: -x[0])
        return hits[0][1]
    return None


def known_codes():
    return [f.code for f in FAMILIES]


def available_codes():
    return [f.code for f in FAMILIES if f.template_available]
