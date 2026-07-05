"""
BOM Agent skill — bridges the help-card BOM/serial command family to real
handlers. Closes the gap found in the 2026-07-05 audit: `bom health`,
`bom inspect/status/issues` and `serial *` were advertised in @ai help but
implemented NOWHERE (LLM guessed); `validate bom` was hijacked by the
data-quality-scanner help card; `create bom from tds` by formulation-advisor.

Scope discipline:
- READ-ONLY reports implemented here (health/inspect/status/issues/serial/*).
- `create bom from tds` delegates to BOMCreatorAgent (inserts DRAFT only).
- `validate bom` delegates to BOMCreatorAgent.validate_bom_creator (read-only).
- Write ops (!submit / !cancel / !revert / create bom for batch) are NOT
  claimed — they stay with the workflow stage and its confirmation gating.
- `simulate blend FMIX-…` bridges to amb_w_tds BOMFormula.simulate_blend
  (whitelisted doc method, read-only compute) when that app is installed.
"""

import re
from typing import Dict, Optional

import frappe

from raven_ai_agent.skills.framework import SkillBase

FMIX_RE = re.compile(r"\b(FMIX-[\w-]+)\b", re.IGNORECASE)
BOM_ID_RE = re.compile(r"\b(BOM-[\w./-]+)\b", re.IGNORECASE)


class BOMAgentSkill(SkillBase):
    name = "bom-agent"
    description = ("BOM & serial tracking: health, inspect, status, issues, "
                   "serial reports, TDS-driven BOM Creator drafts, blend simulation")
    emoji = "📦"
    priority = 80

    # No bare "bom" trigger on purpose — precision over greed.
    triggers = [
        "bom health", "bom inspect", "bom issues", "create bom from tds",
        "serial health", "simulate blend",
    ]
    patterns = [
        r"\bbom\s+(health|inspect|status|issues)\b",
        r"\bserial\s+(health|status|batch)\b",
        r"\bvalidate\s+bom\b",
        r"\bcreate\s+bom\s+from\s+tds\b",
        r"\bsimulate\s+blend\b",
        r"\bFMIX-[\w-]+\b",
    ]

    # ------------------------------------------------------------------ #
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        q = (query or "").strip()
        ql = q.lower()
        try:
            if "create bom from tds" in ql or ("create bom" in ql and "tds" in ql):
                return self._delegate_creator(q)
            if "validate" in ql and "bom" in ql:
                return self._validate(q)
            if re.search(r"\bbom\s+health\b", ql):
                return self._bom_health()
            if re.search(r"\bbom\s+inspect\b", ql):
                return self._bom_inspect(q)
            if re.search(r"\bbom\s+status\b", ql):
                return self._bom_status(q)
            if re.search(r"\bbom\s+issues\b", ql):
                return self._bom_issues()
            if re.search(r"\bserial\s+health\b", ql):
                return self._serial_health()
            if re.search(r"\bserial\s+batch\b", ql):
                return self._serial_batch(q)
            if re.search(r"\bserial\s+status\b", ql):
                return self._serial_status(q)
            if "simulate blend" in ql or FMIX_RE.search(q):
                return self._simulate_blend(q)
        except Exception as exc:  # noqa: BLE001
            frappe.logger().error(f"[bom-agent] {q[:60]}: {exc}", exc_info=True)
            return self._reply(f"❌ BOM agent error: {exc}")
        return None

    # ---- delegates to existing agent --------------------------------- #
    AMB_BOM_SKILL_API = "amb_w_tds.raven.bom_creator_agent.bom_skill_api"

    def _delegate_creator(self, q: str) -> Dict:
        """TDS-driven BOM creation. Preferred path: the amb_w_tds AI-BOM
        pipeline (per-product master templates, dry-run-first whitelisted
        API). Fallback: raven's template-copy agent.

        Convention: without `!` -> DRY RUN preview (no writes); with `!`
        -> real draft creation. Matches the existing ! execute discipline."""
        dry_run = not q.lstrip().startswith("!")
        request_text = q.lstrip("!").strip()

        fn = None
        try:
            fn = frappe.get_attr(self.AMB_BOM_SKILL_API)
        except Exception:
            fn = None

        if fn is not None:
            try:
                result = fn(request_text=request_text, dry_run=dry_run)
            except Exception as exc:  # noqa: BLE001
                return self._reply(f"❌ AI-BOM pipeline error: {exc}")
            body = self._format_amb_result(result)
            if dry_run:
                body += ("\n\n🔍 _Dry run — nothing was created._ "
                         f"Execute with `@ai !{request_text}`")
            return self._reply(body)

        # Fallback: raven-side agent (multi-word TDS names supported)
        from raven_ai_agent.agents.bom_creator_agent import BOMCreatorAgent

        m = re.search(r"(?:from\s+)?tds\s+(.+)$", request_text, re.IGNORECASE)
        if m:
            tds_name = m.group(1).strip().strip("'\"")
            result = BOMCreatorAgent().create_bom_from_tds(tds_name)
        else:
            result = BOMCreatorAgent().handle_bom_request(request_text)
        if result.get("success"):
            msg = result.get("message") or "Done."
            name = result.get("bom_creator_name") or result.get("name")
            if name:
                msg += f"\n\n📝 Draft created: **{name}** — review & submit with `@ai !submit bom {name}`"
            return self._reply(msg)
        return self._reply(f"❌ {result.get('error', 'BOM request failed')}")

    @staticmethod
    def _format_amb_result(result) -> str:
        if isinstance(result, dict):
            if result.get("error"):
                return f"❌ {result['error']}"
            parts = []
            if result.get("message"):
                parts.append(str(result["message"]))
            name = result.get("bom_creator_name") or result.get("name")
            if name:
                parts.append(f"📝 BOM Creator: **{name}**")
            if not parts:
                parts.append(frappe.as_json(result, indent=1)[:1200])
            return "\n\n".join(parts)
        return str(result)[:1500]

    def _validate(self, q: str) -> Dict:
        from raven_ai_agent.agents.bom_creator_agent import BOMCreatorAgent

        m = BOM_ID_RE.search(q)
        if not m:
            return self._reply("Usage: `@ai validate bom BOM-XXXX`")
        name = m.group(1)
        if frappe.db.exists("BOM Creator", name):
            result = BOMCreatorAgent().validate_bom_creator(name)
            ok = result.get("success")
            body = result.get("message") or result.get("error") or ""
            return self._reply(f"{'✅' if ok else '❌'} **BOM Creator {name}** validation\n\n{body}")
        if frappe.db.exists("BOM", name):
            bom = frappe.get_doc("BOM", name)
            issues = []
            if not bom.items:
                issues.append("no items")
            zero = [i.item_code for i in bom.items if not i.qty]
            if zero:
                issues.append(f"zero-qty items: {', '.join(zero[:5])}")
            missing = [i.item_code for i in bom.items
                       if not frappe.db.exists("Item", i.item_code)]
            if missing:
                issues.append(f"unknown items: {', '.join(missing[:5])}")
            if issues:
                return self._reply(f"❌ **BOM {name}** issues:\n\n- " + "\n- ".join(issues))
            return self._reply(
                f"✅ **BOM {name}** structure OK — {len(bom.items)} items, "
                f"qty {bom.quantity}, total cost {bom.total_cost or 0:,.2f}"
            )
        return self._reply(f"⚠️ **{name}** not found as BOM or BOM Creator.")

    # ---- read-only reports (implemented here, previously fictional) --- #
    def _bom_health(self) -> Dict:
        total = frappe.db.count("BOM")
        active = frappe.db.count("BOM", {"is_active": 1})
        default = frappe.db.count("BOM", {"is_default": 1})
        draft = frappe.db.count("BOM", {"docstatus": 0})
        cancelled = frappe.db.count("BOM", {"docstatus": 2})
        multi_default = frappe.db.sql("""
            SELECT item, COUNT(*) c FROM `tabBOM`
            WHERE is_default=1 AND docstatus=1 GROUP BY item HAVING c>1 LIMIT 5""")
        creators = frappe.db.count("BOM Creator") if frappe.db.exists("DocType", "BOM Creator") else 0
        lines = [
            "📦 **BOM Health**", "",
            f"- Total BOMs: **{total}** (active {active} · default {default} · draft {draft} · cancelled {cancelled})",
            f"- BOM Creators: **{creators}**",
        ]
        if multi_default:
            lines.append(f"- ⚠️ Items with MULTIPLE default BOMs: {', '.join(r[0] for r in multi_default)}")
        else:
            lines.append("- ✅ No items with duplicate default BOMs")
        return self._reply("\n".join(lines))

    def _bom_inspect(self, q: str) -> Dict:
        m = BOM_ID_RE.search(q)
        if not m:
            return self._reply("Usage: `@ai bom inspect BOM-XXXX`")
        from raven_ai_agent.api.bom_fixer import get_bom_details

        result = get_bom_details(m.group(1))
        if result.get("success"):
            return self._reply(result.get("message", "OK"))
        return self._reply(f"⚠️ {result.get('message', 'BOM not found')}")

    def _bom_status(self, q: str) -> Dict:
        item = q.split("bom status", 1)[-1].strip() or None
        if not item:
            return self._reply("Usage: `@ai bom status <ITEM-CODE>`")
        rows = frappe.get_all(
            "BOM", filters={"item": item},
            fields=["name", "is_active", "is_default", "docstatus", "total_cost"],
            order_by="modified desc", limit=10,
        )
        if not rows:
            return self._reply(f"⚠️ No BOMs found for item **{item}**.")
        lines = [f"📦 **BOM status for {item}** ({len(rows)} shown)", ""]
        for r in rows:
            st = {0: "📝 Draft", 1: "✅ Submitted", 2: "❌ Cancelled"}[r.docstatus]
            flags = ("⭐default " if r.is_default else "") + ("active" if r.is_active else "inactive")
            lines.append(f"- **{r.name}** · {st} · {flags} · cost {r.total_cost or 0:,.2f}")
        return self._reply("\n".join(lines))

    def _bom_issues(self) -> Dict:
        issues = []
        multi_default = frappe.db.sql("""
            SELECT item, COUNT(*) c FROM `tabBOM`
            WHERE is_default=1 AND docstatus=1 GROUP BY item HAVING c>1 LIMIT 10""")
        for item, c in multi_default:
            issues.append(f"⚠️ **{item}** has {c} default BOMs")
        inactive_default = frappe.get_all(
            "BOM", filters={"is_default": 1, "is_active": 0}, pluck="name", limit=10)
        for n in inactive_default:
            issues.append(f"⚠️ **{n}** is default but inactive")
        drafts_old = frappe.db.sql("""
            SELECT name FROM `tabBOM` WHERE docstatus=0
            AND modified < DATE_SUB(NOW(), INTERVAL 90 DAY) LIMIT 10""")
        for (n,) in drafts_old:
            issues.append(f"🕸️ **{n}** draft untouched >90 days")
        if not issues:
            return self._reply("✅ **BOM issues scan** — nothing found.")
        return self._reply("📦 **BOM issues** (" + str(len(issues)) + ")\n\n" + "\n".join(f"- {i}" for i in issues))

    def _serial_health(self) -> Dict:
        total = frappe.db.count("Serial No")
        by_status = frappe.db.sql(
            "SELECT status, COUNT(*) FROM `tabSerial No` GROUP BY status")
        lines = [f"🔢 **Serial health** — total **{total}**", ""]
        for status, c in by_status:
            lines.append(f"- {status or '(none)'}: {c}")
        return self._reply("\n".join(lines))

    def _serial_status(self, q: str) -> Dict:
        serial = q.split("serial status", 1)[-1].strip()
        if not serial:
            return self._reply("Usage: `@ai serial status <SERIAL>`")
        if not frappe.db.exists("Serial No", serial):
            return self._reply(f"⚠️ Serial **{serial}** not found.")
        s = frappe.db.get_value(
            "Serial No", serial,
            ["item_code", "status", "batch_no", "warehouse"], as_dict=True)
        return self._reply(
            f"🔢 **Serial {serial}**\n\n- Item: {s.item_code}\n- Status: {s.status}"
            f"\n- Batch: {s.batch_no or '—'}\n- Warehouse: {s.warehouse or '—'}")

    def _serial_batch(self, q: str) -> Dict:
        batch = q.split("serial batch", 1)[-1].strip()
        if not batch:
            return self._reply("Usage: `@ai serial batch <BATCH>`")
        rows = frappe.get_all(
            "Serial No", filters={"batch_no": batch},
            fields=["name", "status"], limit=25)
        if not rows:
            return self._reply(f"⚠️ No serials found for batch **{batch}**.")
        lines = [f"🔢 **Serials in {batch}** ({len(rows)} shown)", ""]
        lines += [f"- {r.name} · {r.status}" for r in rows]
        return self._reply("\n".join(lines))

    # ---- amb_w_tds bridge (guarded) ----------------------------------- #
    def _simulate_blend(self, q: str) -> Dict:
        m = FMIX_RE.search(q)
        if not m:
            return self._reply("Usage: `@ai simulate blend FMIX-XXXX-XXX`")
        name = m.group(1)
        if not frappe.db.exists("DocType", "BOM Formula"):
            return self._reply("⚠️ BOM Formula doctype not installed on this site (amb_w_tds).")
        if not frappe.db.exists("BOM Formula", name):
            return self._reply(f"⚠️ BOM Formula **{name}** not found.")
        doc = frappe.get_doc("BOM Formula", name)
        if not hasattr(doc, "simulate_blend"):
            return self._reply("⚠️ simulate_blend not available on this amb_w_tds version.")
        try:
            result = doc.simulate_blend()
        except frappe.ValidationError as exc:
            return self._reply(f"⚠️ **{name}** cannot simulate yet: {exc}")
        if isinstance(result, dict):
            body = result.get("message") or frappe.as_json(result, indent=1)[:1500]
        else:
            body = str(result)[:1500]
        return self._reply(f"🧪 **Blend simulation — {name}** (read-only)\n\n{body}")

    # ------------------------------------------------------------------ #
    @staticmethod
    def _reply(text: str, confidence: float = 0.95) -> Dict:
        return {"handled": True, "response": text, "confidence": confidence}


SKILL_CLASS = BOMAgentSkill
