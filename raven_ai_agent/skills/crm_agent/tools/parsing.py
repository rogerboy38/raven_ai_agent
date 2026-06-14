"""
CRM Tools — One-liner parsing
=============================
Turn natural-language fragments into structured tool args.
Examples:
  "Juan Perez at Acme, juan@acme.mx, interested in 5L sanitizer"
    -> {lead_name, company_name, email_id, notes}
  "Renewal Acme Q3, 250000 MXN, closing 2026-09-30"
    -> {party_name, opportunity_amount, currency, expected_closing}
"""
from __future__ import annotations
import re
from typing import Dict


_EMAIL_RE = re.compile(r"[\w\.\+\-]+@[\w\-]+\.[\w\.\-]+")
_PHONE_RE = re.compile(r"(?:\+?\d[\d \-]{7,}\d)")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_AMOUNT_RE = re.compile(
    r"(?P<amt>\d[\d,\.]*)\s*(?P<cur>MXN|USD|EUR|MX\$|\$|MN)\b",
    re.IGNORECASE,
)

# Currency tokens that unambiguously map to MXN.
_MXN_TOKENS = {"MX$", "MN", "MXN"}


def _normalize_currency(token: str) -> str:
    """Map a parsed currency token to a canonical ISO code.

    Fix (M4, PR #16 review): bare ``$`` used to default to MXN unconditionally,
    silently mis-currencying USD-flavored prompts in a bilingual environment.
    It now resolves to the company's ``default_currency`` (via
    ``opportunities._default_currency()``), which on the sandbox is MXN but
    on a USD-configured company will be USD. Explicit ``MXN``, ``MX$``, ``MN``
    still map to MXN regardless of company config.
    """
    token = (token or "").upper()
    if token in _MXN_TOKENS:
        return "MXN"
    if token in {"$", ""}:
        # Ambiguous bare $ — ask the company config.
        try:
            from raven_ai_agent.skills.crm_agent.tools.opportunities import _default_currency
            return _default_currency()
        except Exception:
            return "MXN"
    return token


def parse_lead_oneliner(text: str) -> Dict:
    """Parse 'Name at Company, email, notes...' loosely.

    Fix (N7, PR #16 review): when the input is only an email (no "Name at
    Company" phrase and no comma chunks), fall back to using the local-part
    of the email as ``lead_name`` rather than returning ``lead_name=""``
    which downstream callers treat as invalid.
    """
    out: Dict = {}
    rest = text.strip()

    email_m = _EMAIL_RE.search(rest)
    if email_m:
        out["email_id"] = email_m.group(0)
        rest = rest.replace(email_m.group(0), "")

    phone_m = _PHONE_RE.search(rest)
    if phone_m:
        out["mobile_no"] = phone_m.group(0).strip()
        rest = rest.replace(phone_m.group(0), "")

    # "Name at Company"
    at_m = re.search(r"^(.+?)\s+(?:at|de|@)\s+(.+?)(?:,|$)", rest, re.IGNORECASE)
    if at_m:
        out["lead_name"] = at_m.group(1).strip(" ,")
        out["company_name"] = at_m.group(2).strip(" ,")
        rest = rest[at_m.end():]
    else:
        # First comma-separated chunk is name
        chunks = [c.strip(" ,") for c in rest.split(",") if c.strip(" ,")]
        if chunks:
            out["lead_name"] = chunks[0]
            rest = ",".join(chunks[1:])

    # N7: synthesize a name from the email local-part if still missing.
    if not out.get("lead_name") and out.get("email_id"):
        out["lead_name"] = out["email_id"].split("@", 1)[0]

    notes = re.sub(r"\s+", " ", rest).strip(" ,")
    if notes:
        out["notes"] = notes
    return out


def parse_opp_oneliner(text: str) -> Dict:
    """Parse 'Subject for Customer, 250000 MXN, closing 2026-09-30'."""
    out: Dict = {}
    rest = text.strip()

    date_m = _DATE_RE.search(rest)
    if date_m:
        out["expected_closing"] = date_m.group(1)
        rest = rest.replace(date_m.group(0), "")

    amt_m = _AMOUNT_RE.search(rest)
    if amt_m:
        raw = amt_m.group("amt").replace(",", "")
        try:
            out["opportunity_amount"] = float(raw)
        except ValueError:
            pass
        cur = amt_m.group("cur").upper()
        out["currency"] = _normalize_currency(cur)
        rest = rest.replace(amt_m.group(0), "")

    for_m = re.search(r"\bfor\s+(.+?)(?:,|$)", rest, re.IGNORECASE)
    if for_m:
        out["party_name"] = for_m.group(1).strip(" ,")
        rest = rest[:for_m.start()] + rest[for_m.end():]

    # Anything left = subject; if no party_name yet, treat the whole thing as party_name
    leftover = re.sub(r"\s+", " ", rest).strip(" ,")
    if leftover and "party_name" not in out:
        out["party_name"] = leftover
    return out
