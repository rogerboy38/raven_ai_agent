"""Lesson-One stage executor (v2) — plan by default, `!` executes.

migration-fixer owns SEQUENCING + MAPPING only. Creation is delegated:
  * BOM        -> bom-agent (bom plan / create bom from tds, via the router)
  * Batch AMB  -> amb_w_spc Batch AMB controller APIs (golden generator,
                  create_child_batch, generate_serial_numbers)
  * COA        -> amb_w_tds COA AMB2 (create_coa_from_tds)

Discipline (v2):
  * every write is DRAFT-only, guarded by frappe.db.exists
  * after any executed create, _verify_row re-checks the row exists —
    never report Created without a row (honesty layer)
  * stages that are not yet automated REFUSE honestly and point at the
    Desk path; a refusal is a correct result, not a failure
  * D-M1 (posting-date policy) is Hugh's gate-1 decision: execution of any
    dated document refuses until policy is passed explicitly.
"""

import json
import re
from datetime import datetime, timezone

from .census import census_folio, STAGES
from .sources import get_sources

EXEC_STAGES = ("quotation", "sales_order", "bom", "batch_amb", "coa")
DATE_POLICIES = ("historical", "current")

STAGE_ALIASES = {
    "so": "sales_order", "sales_order": "sales_order", "pedido": "sales_order",
    "quotation": "quotation", "cotizacion": "quotation",
    "bom": "bom",
    "batch": "batch_amb", "batch_amb": "batch_amb", "lote": "batch_amb",
    "coa": "coa",
    "se": "stock_entry_fg", "stock_entry": "stock_entry_fg",
    "dn": "delivery_note", "delivery": "delivery_note",
    "si": "sales_invoice", "invoice": "sales_invoice", "factura": "sales_invoice",
    "payment": "payment", "pago": "payment",
}


def _dod(op, target, verified, extra=None):
    import frappe
    dod = {"op": op, "target": target, "verified": bool(verified),
           "actor": getattr(getattr(frappe, "session", None), "user", "unknown"),
           "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        dod.update(extra)
    return "\n\n```json\n" + json.dumps(dod, indent=1, default=str) + "\n```"


def _verify_row(doctype, name):
    """Honesty layer: a create only counts if the row exists afterwards."""
    import frappe
    try:
        return bool(name and frappe.db.exists(doctype, name))
    except Exception:
        return False


def execute_stage(folio, stage, execute=False, date_policy=None):
    """Plan (default) or execute one stage for one folio. Returns md text."""
    import frappe

    folio = int(folio)
    stage = STAGE_ALIASES.get(str(stage).lower().strip(), str(stage).lower().strip())
    src = get_sources()
    data = src.load_folio_json(folio)
    if data is None:
        return (f"🚫 **REFUSED / RECHAZADO** — no COMPLETE JSON for folio {folio}; "
                "cannot plan or execute without the FoxPro source of truth.")
    c = census_folio(folio, src)

    if stage == "sales_order":
        return _stage_sales_order(frappe, folio, data, c, execute, date_policy)
    if stage == "quotation":
        return _stage_readonly_note(
            "quotation", c, "Quotation upstream is censused only; create via Desk "
            "if the section needs it (most migrated folios have SAL-QTN twins already).")
    if stage == "bom":
        return _stage_bom(frappe, data, c, execute)
    if stage == "batch_amb":
        return _stage_batch_amb(frappe, folio, data, c, execute)
    if stage == "coa":
        return _stage_coa(frappe, folio, data, c, execute)
    if stage in STAGES:
        return (
            f"🚫 **Stage `{stage}` is not automated yet / Etapa aún no automatizada** — "
            "honest refusal (v2 doctrine). Route: Desk on dev, with the census row as "
            "evidence; automation lands after Lesson-One graduates the earlier stages.\n"
            + _dod("refuse_unautomated_stage", f"folio-{folio}:{stage}", verified=True))
    return (f"❓ Unknown stage `{stage}`. Stages: " + ", ".join(STAGES))


def _stage_readonly_note(stage, c, note):
    st = c["stages"][stage]
    return (f"ℹ️ **{stage}** census: {st['status']} {st['refs'] or ''} — {st['note']}\n\n{note}")


# --------------------------------------------------------------------------- #
# Sales Order
# --------------------------------------------------------------------------- #

def _stage_sales_order(frappe, folio, data, c, execute, date_policy):
    header = data["invoice_header"]
    lines = data["invoice_lines"]
    st = c["stages"]["sales_order"]

    if st["refs"]:
        name = st["refs"][0]
        body = (
            f"✅ **SO already exists / El pedido ya existe: {name}** — nothing to create.\n"
            f"- census: {st['note']}\n"
            "- Lesson-One action here is VERIFY, not create; differences (dates, totals) "
            "are findings for Hugh's gate, not silent patches.")
        if execute:
            body += _dod("noop_so_exists", name, verified=_verify_row("Sales Order", name))
        return body

    # Mapping plan (reference set: the migrated SO-00xxx twins)
    customer = frappe.db.get_value(
        "Customer", {"customer_name": ["like", f"%{header['cliente'][:25]}%"]}, "name")
    plan = [
        f"🧭 **SO stage plan — folio {folio}** ({header['cliente']}, factura {header['factura']})",
        "",
        "| Field | Source | Value |",
        "|-------|--------|-------|",
        f"| customer | Customer match on cliente | {customer or '❌ NO MATCH'} |",
        f"| transaction_date | D-M1 policy | {'PENDING DECISION' if not date_policy else date_policy} |",
        f"| po_no / po_date | factura ref | {header['factura']} / {header['fecha']} |",
        f"| currency | moneda | {header.get('moneda')} |",
        f"| naming | reference-set pattern | SO-{int(folio):05d}-{{customer}} |",
    ]
    for i, l in enumerate(lines, 1):
        item = _resolve_item(frappe, l)
        plan.append(f"| line {i} item | family else ITEM_<lote> | {item or '❌ NO ITEM'} |")
        plan.append(f"| line {i} qty@rate | cantidad@precio | {l.get('cantidad')} @ {l.get('precio')} |")

    if not execute:
        plan.append("\n🔍 _Plan only — nothing was created. / Solo plan; no se creó nada._ "
                    f"Execute with `@ai !migrate folio {folio} stage so date-policy=<historical|current>`")
        return "\n".join(plan)

    # ---- guarded execution (draft-only) ---------------------------------- #
    if date_policy not in DATE_POLICIES:
        return ("🚫 **REFUSED / RECHAZADO** — D-M1 posting-date policy is undecided. "
                "Pass `date-policy=historical` or `date-policy=current` (Hugh's gate-1 "
                "decision) before any dated document is created."
                + _dod("refuse_no_date_policy", f"folio-{folio}:so", verified=True))
    if not customer:
        return (f"🚫 **REFUSED** — no Customer matches '{header['cliente']}'; create/alias the "
                "customer first (Track A), then re-run."
                + _dod("refuse_no_customer", f"folio-{folio}:so", verified=True))
    items = []
    for l in lines:
        item = _resolve_item(frappe, l)
        if not item:
            return (f"🚫 **REFUSED** — no Item for lot {l.get('lote_real')} "
                    f"(tried family + ITEM_{l.get('lote_real')}). Route to Track A."
                    + _dod("refuse_no_item", f"folio-{folio}:so", verified=True))
        items.append((item, l))

    doc = frappe.new_doc("Sales Order")
    doc.customer = customer
    doc.order_type = "Sales"
    fecha = str(header.get("fecha"))[:10]
    doc.transaction_date = fecha if date_policy == "historical" else frappe.utils.today()
    doc.delivery_date = doc.transaction_date
    doc.po_no = header.get("factura")
    doc.currency = header.get("moneda") or "USD"
    for item, l in items:
        doc.append("items", {
            "item_code": item,
            "qty": float(l.get("cantidad") or 0),
            "rate": float(l.get("precio") or 0),
            "delivery_date": doc.transaction_date,
        })
    doc.insert()  # DRAFT only — never submit from the skill
    verified = _verify_row("Sales Order", doc.name)
    if not verified:
        return ("❌ **NOT CREATED / NO SE CREÓ** — insert() returned but no Sales Order "
                "row exists." + _dod("create_so_draft", doc.name or "-", verified=False))
    return (f"✅ **VERIFIED**: draft Sales Order **{doc.name}** created (docstatus=0). "
            "Review + submit is a human step."
            + _dod("create_so_draft", doc.name, verified=True,
                   extra={"folio": folio, "date_policy": date_policy}))


def _resolve_item(frappe, line):
    """Doctrine: family item AND ITEM_<lote> both count as matches; prefer the
    family item (what the reference set uses), fall back to ITEM_<lote>."""
    desc = (line.get("descripcion") or "").strip()
    lote = str(line.get("lote_real") or "").strip()
    fam = lote[:4] if len(lote) >= 4 else None
    if fam and frappe.db.exists("Item", fam):
        return fam
    if desc:
        by_desc = frappe.db.get_value("Item", {"item_name": ["like", f"%{desc[:30]}%"]}, "name")
        if by_desc:
            return by_desc
    if lote and frappe.db.exists("Item", f"ITEM_{lote}"):
        return f"ITEM_{lote}"
    return None


# --------------------------------------------------------------------------- #
# BOM — delegate to bom-agent (orchestrate, don't duplicate)
# --------------------------------------------------------------------------- #

def _stage_bom(frappe, data, c, execute):
    st = c["stages"]["bom"]
    if st["status"] == "OK":
        return (f"✅ **BOM already in place**: {', '.join(st['refs'])} — nothing to create."
                + (_dod("noop_bom_exists", st["refs"][0], verified=True) if execute else ""))
    line = (data.get("invoice_lines") or [{}])[0]
    lote = str(line.get("lote_real") or "")
    fam = lote[:4]
    cmd = f"bom plan create {fam} {line.get('descripcion', '')}".strip()
    body = [
        f"🧭 **BOM stage** — delegated to **bom-agent** (family {fam}).",
        f"- census: {st['status']} {st['note']}",
        f"- plan command: `@ai {cmd}`",
        "- execute (after Hugh gate): `@ai !create bom from tds <TDS for "
        f"{fam}>` — bom-agent enforces its own template/honesty gates; "
        "a template-missing refusal is the CORRECT result → record + route to Track A.",
    ]
    if execute:
        from raven_ai_agent.skills import get_router
        result = get_router().route(cmd) or {}
        body.append("\n**bom-agent replied:**\n\n" + (result.get("response") or "(no response)"))
    return "\n".join(body)


# --------------------------------------------------------------------------- #
# Batch AMB — delegate to amb_w_spc controller APIs
# --------------------------------------------------------------------------- #

BATCH_API = "amb_w_spc.sfc_manufacturing.doctype.batch_amb.batch_amb"


def _stage_batch_amb(frappe, folio, data, c, execute):
    header = data["invoice_header"]
    out = []
    for lote, info in c["lots"].items():
        st = info["batch_amb"]
        cs = info["c_source"]
        out.append(f"### Lot {lote}")
        if st["status"] == "OK":
            out.append(f"✅ hierarchy complete: {st['note']} ({', '.join(st['refs'])})")
            continue
        out += [
            f"- census: {st['status']} — {st['note'] or 'no Batch AMB'}",
            f"- container source: **{cs['source']}** → {cs.get('count')} container(s)"
            + (f" ({cs.get('note')})" if cs.get("note") else ""),
            "- sequence (each step Hugh-gated, drafts only):",
            f"  1. L1 golden batch `{lote}` via Batch AMB insert "
            "(controller mints/validates golden on save)",
            f"  2. `{BATCH_API}.create_child_batch(parent, '2')` → L2 sub-lot",
            f"  3. `{BATCH_API}.create_child_batch(l2, '3')` → L3 container batch",
            f"  4. `{BATCH_API}.generate_serial_numbers(l3, quantity={cs.get('count') or '?'})`"
            " → container/serial children",
            "  5. projection flag is ON on dev → native Batch should auto-emit; "
            "VERIFY with `bench batch-amb-reconcile` — any orphan/drift is a task-#9 "
            "finding to REPORT, never patch silently.",
        ]
        if execute:
            if st["refs"]:
                out.append("↳ L1 exists; per-step child/serial execution stays Hugh-gated "
                           "— run the numbered API calls one gate at a time.")
                continue
            item = _resolve_item(frappe, (data.get("invoice_lines") or [{}])[0])
            if not item:
                out.append("🚫 **REFUSED** — no Item resolvable for the L1 batch."
                           + _dod("refuse_no_item", f"folio-{folio}:batch_amb", verified=True))
                continue
            # work_order_ref is mandatory on Batch AMB (Lesson-One gate-3
            # finding, 2026-07-06): anchor to the censused WO or refuse.
            wo_refs = c["stages"]["work_order"]["refs"]
            if not wo_refs:
                out.append("🚫 **REFUSED / RECHAZADO** — Batch AMB requires work_order_ref "
                           "and the census shows no Work Order for this folio; "
                           "migrate the WO stage first."
                           + _dod("refuse_no_work_order", f"folio-{folio}:batch_amb",
                                  verified=True))
                continue
            doc = frappe.new_doc("Batch AMB")
            doc.work_order_ref = wo_refs[0]
            so_refs = c["stages"]["sales_order"]["refs"]
            if so_refs:
                doc.sales_order_related = so_refs[0]
            doc.item_code = item
            doc.custom_golden_number = lote
            doc.batch_id = lote
            doc.custom_batch_level = "1"
            doc.planned_qty = float((data.get("invoice_lines") or [{}])[0].get("cantidad") or 0)
            doc.insert()
            verified = _verify_row("Batch AMB", doc.name)
            if verified:
                out.append(f"✅ **VERIFIED**: L1 Batch AMB **{doc.name}** created (draft)."
                           + _dod("create_batch_amb_l1", doc.name, verified=True,
                                  extra={"lote": lote, "c_source": cs["source"]}))
            else:
                out.append("❌ **NOT CREATED / NO SE CREÓ** — insert() returned but no row."
                           + _dod("create_batch_amb_l1", doc.name or "-", verified=False))
    if not execute:
        out.append(f"\n🔍 _Plan only — nothing was created._ Execute L1 with "
                   f"`@ai !migrate folio {folio} stage batch`")
    return "\n".join(out) if out else "❔ folio has no lots to batch."


# --------------------------------------------------------------------------- #
# COA — readings -> COA AMB2 draft linked to Batch AMB
# --------------------------------------------------------------------------- #

def _stage_coa(frappe, folio, data, c, execute):
    coa_data = data.get("coa_data") or {}
    if not coa_data:
        return ("ℹ️ folio carries no coa_data — stage N/A."
                + (_dod("noop_no_coa_data", f"folio-{folio}", verified=True) if execute else ""))
    out = []
    for lote, cd in coa_data.items():
        revs = cd.get("revisions") or []
        n_read = sum(len(r.get("readings") or []) for r in revs)
        batch_refs = (c["lots"].get(lote) or {}).get("batch_amb", {}).get("refs") or []
        out += [
            f"### COA for lot {lote}",
            f"- {len(revs)} revision(s), {n_read} reading(s) in FoxPro extract",
            f"- Batch AMB link target: {batch_refs[0] if batch_refs else '❌ none — create batch stage first'}",
            "- path: COA AMB2 draft (amb_w_tds) with batch_reference set; readings map "
            "into the COA test child rows; validation stays with the COA AMB2/QI workflow.",
        ]
        if execute:
            if not batch_refs:
                out.append("🚫 **REFUSED** — no Batch AMB to link; run the batch stage first."
                           + _dod("refuse_no_batch_for_coa", f"folio-{folio}:{lote}", verified=True))
                continue
            if frappe.db.exists("COA AMB2", {"batch_reference": batch_refs[0]}):
                existing = frappe.db.get_value("COA AMB2", {"batch_reference": batch_refs[0]}, "name")
                out.append(f"✅ COA AMB2 **{existing}** already linked — nothing to create."
                           + _dod("noop_coa_exists", existing, verified=True))
                continue
            doc = frappe.new_doc("COA AMB2")
            doc.batch_reference = batch_refs[0]
            doc.insert()
            verified = _verify_row("COA AMB2", doc.name)
            if verified:
                out.append(f"✅ **VERIFIED**: COA AMB2 draft **{doc.name}** created; readings "
                           "load is the next gated step."
                           + _dod("create_coa_draft", doc.name, verified=True))
            else:
                out.append("❌ **NOT CREATED / NO SE CREÓ** — insert() returned but no row."
                           + _dod("create_coa_draft", doc.name or "-", verified=False))
    if not execute:
        out.append(f"\n🔍 _Plan only._ Execute with `@ai !migrate folio {folio} stage coa`")
    return "\n".join(out)


def parse_stage_command(query):
    """'[!]migrate folio 752 [stage so] [date-policy=historical]' -> parts."""
    q = query.strip()
    execute = q.lstrip().startswith("!")
    q = q.lstrip("!").strip()
    m = re.search(r"\bfolio\s+(\d+)", q, re.IGNORECASE)
    if not m:
        return None
    folio = int(m.group(1))
    sm = re.search(r"\bstage\s+([a-z_]+)", q, re.IGNORECASE)
    stage = sm.group(1).lower() if sm else None
    pm = re.search(r"date-?policy\s*=\s*(\w+)", q, re.IGNORECASE)
    policy = pm.group(1).lower() if pm else None
    return {"folio": folio, "stage": stage, "execute": execute, "date_policy": policy}
