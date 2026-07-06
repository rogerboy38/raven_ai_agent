"""
Migration Fixer Skill v2 — FoxPro -> ERPNext migration close.

v2 discipline (house standard, mirrors bom-agent):
  * dry-run / census by default; `!` prefix executes
  * every write draft-only + frappe.db.exists guards + DoD JSON
  * honesty layer: _verify_row after any create — never report Created
    without a row
  * bilingual EN/ES key lines
  * orchestrates, never duplicates: BOM -> bom-agent, Batch -> amb_w_spc
    Batch AMB controller, COA -> amb_w_tds COA AMB2

Commands (v2):
    migrate scan folio <n>      one-folio 11-stage gap census (read-only)
    migrate scan 2024|2025      section census (read-only, slow -> runner)
    migrate folio <n>           full-chain plan for a folio (dry-run)
    [!]migrate folio <n> stage <s> [date-policy=historical|current]
    migrate help / ayuda migracion

Legacy commands (v1, kept working):
    scan migration 2024 · fix folio 00752 [confirm] · compare folio 00752 ·
    migration report
"""

import re
from typing import Dict, Optional

from raven_ai_agent.skills.framework import SkillBase
from raven_ai_agent.skills.migration_fixer.fixer import MigrationFixer


class MigrationFixerSkill(SkillBase):
    """FoxPro -> ERPNext migration validation, census, and gated repair."""

    name = "migration-fixer"
    description = ("FoxPro to ERPNext migration close: 11-stage gap census, "
                   "sequencing and mapping for quotations/SO/batches (v2)")
    emoji = "🔧"
    version = "2.0.0"
    priority = 70

    triggers = [
        "migrate scan",
        "migrate folio",
        "migrar folio",
        "censo migracion",
        "scan migration",
        "fix folio",
        "compare folio",
        "migration report",
        "validate folio",
        "foxpro",
    ]

    patterns = [
        r"^\s*!?\s*migrate\s+(scan|folio|help)\b",
        r"\bmigrate\s+scan\s+(folio\s+)?\d+",
        r"\bmigrate\s+folio\s+\d+",
        r"\bmigrar\s+folio\s+\d+",
        r"\bcenso\s+migraci[oó]n\b",
        r"\bayuda\s+migraci[oó]n\b",
        # legacy v1
        r"scan\s+migration\s+\d{4}",
        r"fix\s+folio\s+\d{1,5}",
        r"compare\s+folio\s+\d{1,5}",
        r"migration.*report",
        r"folio\s+\d{5}",
    ]

    def __init__(self, agent=None):
        super().__init__(agent)
        self.fixer = MigrationFixer()

    # ------------------------------------------------------------------ #
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        q = (query or "").strip()
        ql = q.lower().lstrip("!").strip()

        try:
            if re.search(r"\bmigrate\s+help\b|\bayuda\s+migraci[oó]n\b", ql):
                return self._help()
            m = re.search(r"\bmigrate\s+scan\s+folio\s+(\d+)", ql) \
                or re.search(r"\bcenso\s+migraci[oó]n\s+folio\s+(\d+)", ql)
            if m:
                return self._scan_folio(int(m.group(1)))
            m = re.search(r"\bmigrate\s+scan\s+(2024|2025)\b", ql) \
                or re.search(r"\bcenso\s+migraci[oó]n\s+(2024|2025)\b", ql)
            if m:
                return self._scan_section(int(m.group(1)))
            if re.search(r"\bmigrate\s+scan\b", ql):
                return self._reply(
                    "📋 Usage: `migrate scan folio <n>` or `migrate scan 2024|2025` "
                    "(read-only census / censo de solo lectura)")
            m = re.search(r"\b(?:migrate|migrar)\s+folio\s+(\d+)", ql)
            if m:
                return self._folio_command(q, int(m.group(1)))

            # ---- legacy v1 handlers (unchanged behavior) ---------------- #
            if "scan migration" in ql:
                return self._handle_scan(ql)
            if "fix folio" in ql:
                return self._handle_fix(ql)
            if "compare folio" in ql:
                return self._handle_compare(ql)
            if "migration report" in ql:
                return self._handle_report(ql)
        except Exception as exc:  # noqa: BLE001
            import frappe
            frappe.logger().error(f"[migration-fixer] {q[:60]}: {exc}", exc_info=True)
            return self._reply(f"❌ migration-fixer error: {exc}")
        return None

    # ---- v2 handlers --------------------------------------------------- #
    def _scan_folio(self, folio: int) -> Dict:
        from raven_ai_agent.skills.migration_fixer import census
        c = census.census_folio(folio)
        return self._reply(census.format_folio_census_md(c), data=c)

    def _scan_section(self, year: int) -> Dict:
        from raven_ai_agent.skills.migration_fixer import census
        from raven_ai_agent.skills.migration_fixer.sources import get_sources
        src = get_sources()
        folios = src.folios_for_year(year)
        if len(folios) > 40:
            return self._reply(
                f"📊 Section {year} has **{len(folios)} folios** — a chat-turn census "
                "would time out. Run the offline runner (read-only):\n\n"
                "```bash\nbench --site <site> execute "
                "raven_ai_agent.skills.migration_fixer.census_runner.run_section "
                f"--kwargs \"{{'year': {year}}}\"\n```\n"
                f"Reports land in `{src.census_dir}/`. / El censo de sección corre "
                "fuera de línea; los reportes quedan en la carpeta census.")
        res = census.census_section(year, src)
        return self._reply(census.format_section_md(res), data=res)

    def _folio_command(self, raw_query: str, folio: int) -> Dict:
        from raven_ai_agent.skills.migration_fixer import executor
        parsed = executor.parse_stage_command(raw_query)
        if parsed and parsed["stage"]:
            text = executor.execute_stage(
                folio, parsed["stage"], execute=parsed["execute"],
                date_policy=parsed["date_policy"])
            return self._reply(text)
        # no stage -> full-chain plan: census + next-gap pointer (read-only)
        from raven_ai_agent.skills.migration_fixer import census
        c = census.census_folio(folio)
        body = census.format_folio_census_md(c)
        gap = next((s for s in census.STAGES
                    if c["stages"][s]["status"] in ("MISSING", "PARTIAL")), None)
        if gap:
            body += (f"\n\n➡️ next gap: **{gap}** — plan it with "
                     f"`@ai migrate folio {folio} stage {gap}` (add `!` to execute "
                     "after Hugh's gate / con `!` ejecuta tras la aprobación)")
        else:
            body += "\n\n🎉 no gaps censused on the 11 stages."
        return self._reply(body, data=c)

    def _help(self) -> Dict:
        return self._reply(
            "🔧 **migration-fixer v2** — honest, census-first, `!` executes\n\n"
            "**Census (read-only)**: `migrate scan folio 752` · `migrate scan 2024|2025`\n"
            "**Plan/Write** (plan by default, `!` executes, drafts only): "
            "`migrate folio 752` · `[!]migrate folio 752 stage so|bom|batch|coa "
            "[date-policy=historical|current]`\n"
            "**Delegates**: BOM→bom-agent · Batch→Batch AMB controller (amb_w_spc) · "
            "COA→COA AMB2 (amb_w_tds)\n"
            "**Never**: submit documents, write on scan, invent containers — C-source "
            "order is det_trazab → tabla_env2 (PROVEN keys) → regenerate 25 kg standard\n"
            "**Legacy**: scan migration 2024 · fix folio 00752 [confirm] · compare folio "
            "00752 · migration report\n"
            "ES: migrar folio 752 · censo migración 2024 · ayuda migración")

    # ---- legacy v1 handlers (verbatim from 1.x) ------------------------- #
    def _handle_scan(self, query: str) -> Dict:
        parts = query.split()
        for p in parts:
            if p in ["2024", "2025"]:
                year = int(p)
                range_info = MigrationFixer.FOLIO_RANGES.get(year, {})
                results = self.fixer.scan_range(
                    range_info.get("start"), range_info.get("end"))
                return self._reply(self._format_scan_results(results, year), data=results)
        if "from" in query and "to" in query:
            try:
                from_idx = parts.index("from")
                to_idx = parts.index("to")
                results = self.fixer.scan_range(parts[from_idx + 1], parts[to_idx + 1])
                return self._reply(self._format_scan_results(results), data=results)
            except (ValueError, IndexError):
                pass
        return self._reply(
            "📋 **Usage:** `scan migration 2024` or `scan migration from 00800 to 00850`",
            confidence=0.7)

    def _handle_fix(self, query: str) -> Dict:
        parts = query.split()
        try:
            folio = parts[parts.index("folio") + 1]
            confirm = "confirm" in parts
            result = self.fixer.fix_quotation(folio, dry_run=not confirm)
            if result.get("error"):
                return self._reply(f"❌ **Error:** {result['error']}", confidence=0.9)
            if not result.get("changes"):
                return self._reply(f"✅ **Folio {folio}:** No fixes needed - data is correct")
            changes_text = "\n".join(
                f"  - `{c['field']}`: '{c['old']}' → '{c['new']}'" for c in result["changes"])
            if result.get("applied"):
                return self._reply(f"✅ **Fixed folio {folio}:**\n{changes_text}", data=result)
            return self._reply(
                f"🔍 **Preview for folio {folio}:**\n{changes_text}\n\n"
                f"*Say `fix folio {folio} confirm` to apply*", data=result)
        except (ValueError, IndexError):
            return self._reply(
                "📋 **Usage:** `fix folio 00752` or `fix folio 00752 confirm`", confidence=0.7)

    def _handle_compare(self, query: str) -> Dict:
        parts = query.split()
        try:
            folio = parts[parts.index("folio") + 1]
            from raven_ai_agent.skills.migration_fixer.api import compare_folio
            result = compare_folio(folio)
            if isinstance(result, dict) and result.get("error"):
                return self._reply(f"❌ {result['error']}", confidence=0.9)
            return self._reply(self._format_comparison(result), data=result)
        except (ValueError, IndexError):
            return self._reply("📋 **Usage:** `compare folio 00752`", confidence=0.7)

    def _handle_report(self, query: str) -> Dict:
        year = 2024 if "2024" in query else 2025 if "2025" in query else None
        return self._reply(self.fixer.generate_report(year=year))

    # ---- formatting (v1, kept) ------------------------------------------ #
    def _format_scan_results(self, results: Dict, year: int = None) -> str:
        year_str = f" ({year})" if year else ""
        output = f"""📊 **Migration Scan Results{year_str}**

| Status | Count |
|--------|-------|
| 📋 Scanned | {results['scanned']} |
| ✅ OK | {results['ok']} |
| ⚠️ Warnings | {results['warnings']} |
| ❌ Errors | {results['errors']} |
| 📭 Missing | {results.get('missing', 0)} |
"""
        if results.get("details"):
            output += "\n**Top Issues:**\n"
            for d in results["details"][:5]:
                issues_str = d["issues"][0] if d["issues"] else "Unknown issue"
                output += f"- `{d['folio']}`: {issues_str}\n"
            remaining = len(results["details"]) - 5
            if remaining > 0:
                output += f"\n*...and {remaining} more issues*"
        return output

    def _format_comparison(self, result: Dict) -> str:
        folio = result.get("folio", "Unknown")
        output = f"📋 **Comparison for Folio {folio}**\n\n"
        if result.get("foxpro"):
            fp = result["foxpro"]
            output += "**FoxPro Source:**\n"
            output += f"- Customer: {fp.get('customer', 'N/A')}\n"
            output += f"- Date: {fp.get('date', 'N/A')}\n"
            if fp.get("total"):
                output += f"- Total: ${float(fp['total']):,.2f}\n"
            output += f"- Lote Real: {fp.get('lote_real', 'N/A')}\n"
            output += f"- Items: {fp.get('items_count', 0)}\n\n"
        else:
            output += "**FoxPro:** ❌ Not found\n\n"
        if result.get("erpnext"):
            erp = result["erpnext"]
            output += f"**ERPNext ({erp.get('name', 'Unknown')}):**\n"
            output += f"- Customer: {erp.get('customer', 'N/A')}\n"
            output += f"- Date: {erp.get('date', 'N/A')}\n"
            output += f"- Total: ${erp.get('total', 0):,.2f}\n"
            output += f"- Lote Real: {erp.get('lote_real', 'N/A')}\n"
            output += f"- Items: {erp.get('items_count', 0)}\n\n"
        else:
            output += "**ERPNext:** ❌ Not found\n\n"
        if result.get("differences"):
            output += "**⚠️ Differences Found:**\n"
            for d in result["differences"]:
                output += f"- `{d['field']}`: FoxPro='{d['foxpro']}' vs ERPNext='{d['erpnext']}'\n"
        else:
            output += "✅ **No differences found**\n"
        return output

    # ------------------------------------------------------------------ #
    @staticmethod
    def _reply(text: str, confidence: float = 0.95, data=None) -> Dict:
        out = {"handled": True, "response": text, "confidence": confidence}
        if data is not None:
            out["data"] = data
        return out


SKILL_CLASS = MigrationFixerSkill
