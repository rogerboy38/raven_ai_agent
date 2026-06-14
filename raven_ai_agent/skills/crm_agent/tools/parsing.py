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


def parse_lead_oneliner(text: str) -> Dict:
    """Parse 'Name at Company, email, notes...' loosely."""
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
        out["currency"] = "MXN" if cur in {"MX$", "MN", "MXN", "$"} else cur
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
