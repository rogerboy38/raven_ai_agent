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

import json
import re
from datetime import datetime, timezone
from typing import Dict, Optional

import frappe

from raven_ai_agent.skills.bom_agent import family as family_mod
from raven_ai_agent.skills.bom_agent import golden
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
        "serial health", "simulate blend", "bom help", "bom plan", "bom repair",
        "bom lots", "salud bom", "ayuda bom", "reparar wo", "lotes bom",
        "crear bom desde tds",
    ]
    patterns = [
        r"\bbom\s+(health|inspect|status|issues|help|plan|lots)\b",
        r"\bbom\s+repair\b|\brepair\s+wo\b|\breparar\s+(wo|orden)\b",
        r"\bserial\s+(health|status|batch)\b",
        r"\bvalidate\s+bom\b|\bvalidar\s+bom\b",
        r"\bcreate\s+bom\s+from\s+tds\b|\bcrear\s+bom\s+desde\s+tds\b",
        r"\bsimulate\s+blend\b|\bsimular\s+mezcla\b",
        r"\bsalud\s+(de\s+)?bom\b|\bayuda\s+bom\b|\blotes\s+bom\b",
        r"\bFMIX-[\w-]+\b",
    ]

    # ------------------------------------------------------------------ #
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        q = (query or "").strip()
        ql = q.lower()
        try:
            if re.search(r"\bbom\s+help\b|\bayuda\s+bom\b", ql):
                return self._help()
            if re.search(r"\bbom\s+repair\b|\brepair\s+wo\b|\breparar\s+(wo|orden)\b", ql):
                return self._repair_wo(q)
            if re.search(r"\bbom\s+lots\b|\blotes\s+bom\b", ql):
                return self._bom_lots(q)
            if re.search(r"\bbom\s+plan\b", ql):
                # explicit dry-run alias: strip 'plan', force preview
                return self._delegate_creator(re.sub(r"\bbom\s+plan\b", "create bom", ql, count=1))
            if "create bom from tds" in ql or "crear bom desde tds" in ql or ("create bom" in ql and "tds" in ql):
                return self._delegate_creator(q)
            if ("validate" in ql or "validar" in ql or "valida " in ql) and "bom" in ql:
                return self._validate(q)
            if re.search(r"\bbom\s+health\b|\bsalud\s+(de\s+)?bom\b", ql):
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
            if "simulate blend" in ql or "simular mezcla" in ql or FMIX_RE.search(q):
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

        # Principle 2: resolve family HERE. A family without an amb master
        # template refuses honestly BEFORE any pipeline call — no silent
        # mis-mapping (old juice->0227), no phantom success (#79).
        fam = family_mod.resolve(request_text)
        if fam is not None and not fam.template_available:
            return self._reply(
                f"🚫 **No BOM template for family {fam.code} ({fam.label})** — "
                f"nothing was created. / No existe plantilla para la familia "
                f"{fam.code}; no se creó nada.\n\n"
                f"- {fam.note or 'Template pending in amb_w_tds ai_bom_agent/templates.'}\n"
                f"- Families with templates today: {', '.join(family_mod.available_codes())}\n"
                f"- Tracking: #78 (0705/juice master template)"
            )

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
                body += ("\n\n🔍 _Dry run — nothing was created. / Simulación; "
                         f"no se creó nada._ Execute with `@ai !{request_text}`")
                return self._reply(body)
            # Principle 1 — HONESTY: trust rows, not labels (#79). Verify.
            verified, name = self._verify_created(result, request_text)
            if verified:
                body += f"\n\n✅ **VERIFIED**: BOM Creator row **{name}** exists."
                body += self._dod_json("create_bom_creator", name, verified=True)
            else:
                body = (
                    "❌ **NOT CREATED / NO SE CREÓ** — the pipeline replied but no "
                    "BOM Creator row exists (known label bug #79).\n\n"
                    "Pipeline transcript:\n\n" + body
                )
                body += self._dod_json("create_bom_creator", name or "-", verified=False)
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
        if not isinstance(result, dict):
            return str(result)[:1500]
        errors = result.get("errors") or []
        if isinstance(errors, dict):
            errors = [errors]
        # Friendly rendering for structured rule errors (live ref 02:19:
        # raw dict dump for PARSE 'unknown product family').
        if errors:
            lines = ["❌ **AI-BOM pipeline rejected the request:**", ""]
            for e in errors[:5]:
                if isinstance(e, dict):
                    lines.append(f"- **{e.get('rule_name') or e.get('ruleid') or 'Error'}**: "
                                 f"{e.get('message', '')}")
                else:
                    lines.append(f"- {e}")
            if any("product family" in str(e).lower() for e in errors):
                lines += ["",
                          "💡 This product family has no master template in the AI-BOM "
                          "pipeline yet (amb_w_tds). Ask the amb team to register it, or "
                          "retry naming a known family/keyword (0227, 0307, 0303, 0301, "
                          "HIGHPOL, ACETYPOL, 'concentrate', 'powder', '30:1', '200:1')."]
            return "\n".join(lines)
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
            lines.append(f"- ⚠️ Items with MULTIPLE default BOMs (B009): {', '.join(r[0] for r in multi_default)}")
        else:
            lines.append("- ✅ No items with duplicate default BOMs (B009)")
        # v2: WOs pointing at missing BOMs — the #70 failure mode the old
        # health check missed entirely.
        broken_wos = frappe.db.sql("""
            SELECT wo.name, wo.bom_no, wo.docstatus FROM `tabWork Order` wo
            LEFT JOIN `tabBOM` b ON b.name = wo.bom_no
            WHERE wo.bom_no IS NOT NULL AND wo.bom_no != '' AND b.name IS NULL
              AND wo.docstatus < 2 LIMIT 10""")
        if broken_wos:
            lines.append(f"- 🚨 **{len(broken_wos)} Work Orders point at MISSING BOMs** (#70 class):")
            for name, bom_no, ds in broken_wos:
                state = "draft" if ds == 0 else "submitted"
                fix = f" → `@ai bom repair wo {name}`" if ds == 0 else " (submitted — human decision)"
                lines.append(f"    - {name} ({state}) → {bom_no}{fix}")
        else:
            lines.append("- ✅ No Work Orders pointing at missing BOMs")
        # v2: self-referencing BOMs (B008)
        self_ref = frappe.db.sql("""
            SELECT bi.parent FROM `tabBOM Item` bi
            JOIN `tabBOM` b ON b.name = bi.parent
            WHERE bi.item_code = b.item LIMIT 5""")
        if self_ref:
            lines.append(f"- 🚨 Self-referencing BOMs (B008): {', '.join(r[0] for r in self_ref)}")
        else:
            lines.append("- ✅ No self-referencing BOMs (B008)")
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

    # ---- v2: verification, repair, lots, help, DoD -------------------- #
    def _verify_created(self, result, request_text: str):
        """Row-existence check after an executed create (#79 neutralizer)."""
        name = None
        if isinstance(result, dict):
            name = result.get("bom_creator_name") or result.get("name")
        try:
            if name and frappe.db.exists("BOM Creator", name):
                return True, name
            fam = family_mod.resolve(request_text)
            if fam is not None:
                recent = frappe.get_all(
                    "BOM Creator",
                    filters={"item_code": ["like", f"%{fam.code}%"],
                             "creation": [">", frappe.utils.add_to_date(None, minutes=-5)]},
                    pluck="name", limit=1, order_by="creation desc")
                if recent:
                    return True, recent[0]
        except Exception:  # noqa: BLE001
            frappe.logger().warning("[bom-agent] verify_created failed", exc_info=True)
        return False, name

    def _repair_wo(self, q: str) -> Dict:
        """Principle 5: repair a DRAFT WO pointing at a missing BOM.
        Plan by default; '!' executes. Refuses non-draft WOs, always."""
        execute = q.lstrip().startswith("!")
        m = re.search(r"\b(MFG-WO-[\w-]+|WO-[\w-]+)\b", q, re.IGNORECASE)
        if not m:
            return self._reply("Usage: `@ai bom repair wo MFG-WO-XXXXX` "
                               "(add `!` to execute after reviewing the plan)")
        wo_name = m.group(1).upper()
        if not frappe.db.exists("Work Order", wo_name):
            return self._reply(f"⚠️ Work Order **{wo_name}** not found. / Orden no encontrada.")
        wo = frappe.db.get_value(
            "Work Order", wo_name,
            ["docstatus", "status", "bom_no", "production_item", "qty"], as_dict=True)
        if wo.docstatus != 0:
            return self._reply(
                f"🚫 **REFUSED / RECHAZADO** — {wo_name} is {wo.status} "
                f"(docstatus={wo.docstatus}). Repair only touches DRAFT work orders; "
                "submitted/in-process WOs need a human decision.")
        bom_exists = bool(wo.bom_no and frappe.db.exists("BOM", wo.bom_no))
        lines = [f"🔧 **WO repair plan — {wo_name}** (item {wo.production_item}, qty {wo.qty})", ""]
        if bom_exists:
            docstatus = frappe.db.get_value("BOM", wo.bom_no, "docstatus")
            if docstatus == 1:
                return self._reply(
                    f"✅ {wo_name} already points at submitted BOM **{wo.bom_no}** — nothing to repair.")
            lines.append(f"- Current BOM **{wo.bom_no}** exists but docstatus={docstatus} (not submitted).")
        else:
            lines.append(f"- Current bom_no **{wo.bom_no or '(empty)'}** does NOT exist (the #70 failure mode).")
        candidate = frappe.db.get_value(
            "BOM", {"item": wo.production_item, "is_active": 1, "docstatus": 1,
                    "is_default": 1}, "name") or frappe.db.get_value(
            "BOM", {"item": wo.production_item, "is_active": 1, "docstatus": 1}, "name")
        if candidate:
            lines.append(f"- Candidate replacement: active submitted BOM **{candidate}** ✔")
            if execute:
                before = wo.bom_no
                frappe.db.set_value("Work Order", wo_name, "bom_no", candidate)
                frappe.db.commit()
                lines.append(f"\n✅ **EXECUTED**: {wo_name}.bom_no re-pointed → **{candidate}**")
                return self._reply("\n".join(lines) + self._dod_json(
                    "repoint_wo_bom", wo_name, verified=True,
                    extra={"before": before, "after": candidate}))
            lines.append(f"\n🔍 _Plan only — nothing changed._ Execute: `@ai !bom repair wo {wo_name}`")
            return self._reply("\n".join(lines))
        draft_bom = frappe.db.get_value(
            "BOM", {"item": wo.production_item, "docstatus": 0}, "name")
        if draft_bom:
            lines.append(
                f"- 📝 DRAFT BOM **{draft_bom}** exists for {wo.production_item} — the quick-win path:\n"
                f"  1. review + submit it (Desk, or `@ai !submit bom {draft_bom}` if it is a BOM Creator)\n"
                f"  2. then `@ai !bom repair wo {wo_name}` to re-point")
            lines.append(f"\n🔍 _Plan only — nothing changed. / Solo plan; nada cambió._")
            return self._reply("\n".join(lines))
        fam = family_mod.resolve(wo.production_item or "")
        if fam and fam.template_available:
            lines.append(
                f"- No usable BOM exists. Family **{fam.code}** has a template — recreate first:\n"
                f"  1. `@ai !create bom from tds <TDS for {wo.production_item}>` (draft)\n"
                f"  2. review + `@ai !submit bom <BOM-Creator>` (generates the BOM)\n"
                f"  3. `@ai !bom repair wo {wo_name}` (re-point)")
        elif fam:
            lines.append(f"- No usable BOM and family **{fam.code}** has NO template yet (#78) — blocked on amb_w_tds.")
        else:
            lines.append("- No usable BOM and product family unrecognized — manual review needed.")
        return self._reply("\n".join(lines))

    def _bom_lots(self, q: str) -> Dict:
        """Principle 7: Golden-Number FEFO ranking — never manufacturing_date.

        rvnv2r1 evidence-pack finding (vpt executor, 2026-07-05): golden codes
        do NOT live in tabBatch.name on prod substrates — they live in
        Batch AMB.custom_golden_number (prod 12/12, vpt 15/17, batch names
        0/104). Source-of-truth order: Batch AMB golden -> parseable batch
        name -> no-golden (consume last)."""
        item = re.sub(r".*\b(?:bom\s+lots|lotes\s+bom)\b", "", q, flags=re.IGNORECASE).strip()
        if not item:
            return self._reply("Usage: `@ai bom lots <ITEM-CODE>`")

        # PRIMARY SOURCE (rvnv2r1 executor probes): Batch AMB rows ARE the
        # production lots and carry the goldens. tabBatch<->Batch AMB has NO
        # working row-level link on prod (two-hop join = 0; batch_id and
        # generated_batch_name empty). The one provable key is the golden's
        # product prefix (first 4 digits) == product family of the item.
        m = re.match(r"\D*?(\d{4})", item)
        prod4 = m.group(1) if m else None
        if prod4:
            amb = self._amb_lots_by_product(prod4)
            if amb:
                ranked = sorted(amb, key=lambda r: golden.fefo_key(r.get("custom_golden_number") or ""))
                lines = [f"📦 **FEFO lots for {item}** — Batch AMB production lots, "
                         f"Golden-Number order (YY+FFF), NOT manufacturing_date", ""]
                for r in ranked[:15]:
                    g = golden.parse(r.get("custom_golden_number") or "")
                    tag = (f"Y{g['year']:02d}·F{g['folio']:03d}"
                           + (f"·{g['plant']}" if g.get("plant") else "")) if g else "golden unparseable"
                    ref = r.get("lote_amb_reference") or ""
                    lines.append(f"- **{r['name']}** · {tag} · golden {r.get('custom_golden_number')}"
                                 + (f" · ref {ref}" if ref else ""))
                lines.append("")
                lines.append("_Source: Batch AMB.custom_golden_number (authoritative)._")
                return self._reply("\n".join(lines))

        # FALLBACK: tabBatch listing (non-AMB items/sites), decorated with any
        # Batch AMB goldens reachable by name/link joins.
        rows = frappe.get_all(
            "Batch", filters={"item": ["like", f"%{item}%"]},
            fields=["name", "batch_qty", "item"], limit=50)
        if not rows:
            return self._reply(f"⚠️ No batches found for **{item}**.")
        goldens = self._amb_goldens([r.name for r in rows])

        def key(r):
            src = goldens.get(r.name)
            return golden.fefo_key(src) if src else golden.fefo_key(r.name)

        ranked = sorted(rows, key=key)
        lines = [f"📦 **FEFO lots for {item}** — Golden-Number order (YY+FFF), "
                 f"NOT manufacturing_date", ""]
        for r in ranked[:15]:
            src = goldens.get(r.name)
            g = golden.parse(src) if src else golden.parse(r.name)
            if g and src:
                tag = f"Y{g['year']:02d}·F{g['folio']:03d} (golden {src} · Batch AMB)"
            elif g:
                tag = f"Y{g['year']:02d}·F{g['folio']:03d} (from batch name)"
            else:
                tag = "no-golden (consume last)"
            lines.append(f"- **{r.name}** · {tag} · qty {r.batch_qty or 0}")
        return self._reply("\n".join(lines))

    @staticmethod
    def _amb_lots_by_product(prod4: str):
        """Batch AMB lots for a product family via golden prefix. Fails open."""
        try:
            if not frappe.db.exists("DocType", "Batch AMB"):
                return []
            return frappe.get_all(
                "Batch AMB",
                filters={"custom_golden_number": ["like", f"{prod4}%"]},
                fields=["name", "custom_golden_number", "lote_amb_reference"],
                limit=50)
        except Exception:  # noqa: BLE001
            frappe.logger().warning("[bom-agent] _amb_lots_by_product failed", exc_info=True)
            return []

    @staticmethod
    def _amb_goldens(batch_names) -> Dict:
        """batch name -> golden code via Batch AMB.custom_golden_number.
        Name-join first, then common link fields. Fails open (empty dict)."""
        try:
            if not frappe.db.exists("DocType", "Batch AMB"):
                return {}
        except Exception:  # noqa: BLE001
            return {}
        out = {}
        try:
            rows = frappe.get_all(
                "Batch AMB", filters={"name": ["in", list(batch_names)]},
                fields=["name", "custom_golden_number"])
            out.update({r["name"]: r["custom_golden_number"]
                        for r in rows if r.get("custom_golden_number")})
            if out:
                return out
        except Exception:  # noqa: BLE001
            pass
        for link_field in ("batch", "batch_no", "erpnext_batch", "batch_id"):
            try:
                rows = frappe.get_all(
                    "Batch AMB", filters={link_field: ["in", list(batch_names)]},
                    fields=[link_field, "custom_golden_number"])
                out.update({r[link_field]: r["custom_golden_number"]
                            for r in rows if r.get("custom_golden_number")})
                if out:
                    return out
            except Exception:  # noqa: BLE001
                continue
        return out

    def _help(self) -> Dict:
        fams = ", ".join(
            f"{f.code}{'✅' if f.template_available else '🚫#78'}" for f in family_mod.FAMILIES)
        return self._reply(
            "📦 **BOM Agent v2** — honest, dry-run-first, draft-only\n\n"
            "**Read**: `bom health` · `bom inspect <BOM>` · `bom status <ITEM>` · "
            "`bom issues` · `bom lots <ITEM>` (Golden-Number FEFO) · `serial health|status|batch` · "
            "`validate bom <BOM>` · `simulate blend FMIX-…`\n"
            "**Plan/Write** (plan by default, `!` executes): `bom plan …` · "
            "`create bom from tds <TDS>` · `bom repair wo <WO>` (draft WOs only)\n"
            "**Never**: auto-submit, touch non-draft WOs, write BOM Formula (gated on #77 lifecycle)\n\n"
            f"Families / Familias: {fams}\n"
            "ES: salud bom · reparar wo · lotes bom · crear bom desde tds · validar bom")

    @staticmethod
    def _dod_json(op: str, target: str, verified: bool, extra: dict = None) -> str:
        dod = {"op": op, "target": target, "verified": verified,
               "actor": getattr(frappe.session, "user", "unknown") if hasattr(frappe, "session") else "unknown",
               "ts": datetime.now(timezone.utc).isoformat()}
        if extra:
            dod.update(extra)
        return "\n\n```json\n" + json.dumps(dod, indent=1) + "\n```"

    # ------------------------------------------------------------------ #
    @staticmethod
    def _reply(text: str, confidence: float = 0.95) -> Dict:
        return {"handled": True, "response": text, "confidence": confidence}


SKILL_CLASS = BOMAgentSkill
