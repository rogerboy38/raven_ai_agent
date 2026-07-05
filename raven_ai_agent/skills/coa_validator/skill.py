"""
COA Validator Skill (T141)
==========================
On-demand COA validation from Raven chat. Delegates to the SINGLE canonical
server validator in amb_w_tds (validate_all_tests -> evaluate_overall_result +
save), which persists per-row `status` + `overall_result` on the COA, then
replies with the pass/fail summary. Identical logic to the COA form
"Validate All Tests" button — no duplicated validation here.

Trigger examples:  "validate COA-26-0011"  /  "validar coa COA-26-0011"
First cut: one named COA on demand.
"""
import re
import frappe
from typing import Dict, Optional

from raven_ai_agent.skills.framework import SkillBase

COA_RE = re.compile(r"\bCOA[-\s]?(\d{2})[-\s]?(\d{3,4})\b", re.IGNORECASE)

# logical doctype -> the canonical whitelisted validator in amb_w_tds
VALIDATORS = {
    "COA AMB":  "amb_w_tds.amb_w_tds.doctype.coa_amb.coa_amb.validate_all_tests",
    "COA AMB2": "amb_w_tds.amb_w_tds.doctype.coa_amb2.coa_amb2.validate_all_tests",
}


class COAValidatorSkill(SkillBase):
    """Validate a COA's test parameters on demand; persist status + overall_result."""

    name = "coa_validator"
    description = "Validate a COA's test parameters on demand and persist status/overall result"
    emoji = "🧪"
    version = "1.0.0"
    priority = 75  # above generic skills so an explicit COA-id wins routing

    triggers = [
        "validate coa", "validar coa", "valida coa", "coa validate",
        "validate certificate", "validate the coa", "check coa", "revalidate coa",
    ]
    patterns = [
        r"valid(?:ate|ar|a)\s+(?:the\s+)?coa",
        r"\bCOA[-\s]?\d{2}[-\s]?\d{3,4}\b",
    ]

    def can_handle(self, query: str):
        """Explicit COA id (or 'validate coa') must outrank generic
        'validate'/'scan' triggers from data_quality_scanner (T141 parity
        for the V2 framework router)."""
        if COA_RE.search(query or ""):
            return True, 0.95
        return super().can_handle(query)

    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        name = self._extract_coa_name(query)
        if not name:
            return self._reply(
                "🧪 **COA Validator** — which COA? e.g. `validate COA-26-0011`.", 0.8
            )

        doctype = self._resolve_doctype(name)
        if not doctype:
            return self._reply(
                f"⚠️ COA **{name}** not found as COA AMB or COA AMB2.", 0.9
            )

        try:
            fn = frappe.get_attr(VALIDATORS[doctype])
            result = fn(name)  # evaluates + saves; returns {message, summary} or {error}
        except Exception as e:
            frappe.logger().error(f"[coa_validator] {name}: {e}")
            return self._reply(f"❌ Validation failed for **{name}**: {e}", 0.9)

        if isinstance(result, dict) and result.get("error"):
            return self._reply(f"❌ {name}: {result['error']}", 0.9)

        result = result if isinstance(result, dict) else {}
        summary = result.get("summary", {}) or {}
        msg = result.get("message", "") or ""
        overall = frappe.db.get_value(doctype, name, "overall_result") or "?"
        emoji = {"Pass": "✅", "Fail": "❌", "Partial": "⏳", "Pending": "⏳"}.get(overall, "📋")
        pct = summary.get("pass_rate")
        pct_str = f" · {pct:.1f}% pass" if isinstance(pct, (int, float)) else ""

        return self._reply(
            f"{emoji} **{doctype} {name}** — overall: **{overall}**{pct_str}\n"
            f"{msg}\n_(status + overall_result saved on the COA)_",
            0.95,
        )

    # --- helpers -----------------------------------------------------------
    def _extract_coa_name(self, query: str) -> Optional[str]:
        m = COA_RE.search(query or "")
        if not m:
            return None
        return f"COA-{m.group(1)}-{m.group(2)}".upper()

    def _resolve_doctype(self, name: str) -> Optional[str]:
        for dt in ("COA AMB", "COA AMB2"):
            if frappe.db.exists(dt, name):
                return dt
        return None

    def _reply(self, text: str, confidence: float) -> Dict:
        return {"handled": True, "response": text, "confidence": confidence}


# Legacy hook kept for parity; live loading is the hardcoded block in
# SkillRouter._load_skills (see router.py). Harmless if called.
def register_skill(router):
    try:
        router.register_skill(COAValidatorSkill())
    except Exception:
        pass
