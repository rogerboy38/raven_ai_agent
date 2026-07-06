"""Migration gap census (v2) — READ-ONLY.

Censuses the 11 pipeline stages for a folio against ERPNext and stamps the
container C-source each lot would use. Never writes — this module contains no
document-creation or mutation calls at all, and a fixture-level test
(tests/test_migration_fixer_v2.py::TestCensusReadOnly) enforces that.

Stage keys, in pipeline order:
  quotation, sales_order, work_order, bom, batch_amb, native_batch,
  stock_entry_fg, label, delivery_note, sales_invoice, payment

Match keys (doctrine):
  * SO/SI by customer + factura(F-ref) + fecha; migrated SOs also follow the
    proven name pattern  SO-<folio 5d>-<customer>.
  * Batch AMB by golden number (lote_real) incl. leading-zero variants.
  * Item by ITEM_<lote> AND family item.
  * BOM by family (via the SO line's bom_no, else family default).
"""

from .sources import FolioSources, get_sources, lote_variants

STAGES = [
    "quotation", "sales_order", "work_order", "bom", "batch_amb",
    "native_batch", "stock_entry_fg", "label", "delivery_note",
    "sales_invoice", "payment",
]

OK, PARTIAL, MISSING, UNKNOWN = "OK", "PARTIAL", "MISSING", "UNKNOWN"


def _st(status, refs=None, note=""):
    return {"status": status, "refs": refs or [], "note": note}


def _folio5(folio):
    return f"{int(folio):05d}"


def census_folio(folio, src: FolioSources = None):
    """Full 11-stage gap census for one folio. Read-only."""
    import frappe

    src = src or get_sources()
    folio = int(folio)
    data = src.load_folio_json(folio)
    out = {
        "folio": folio,
        "stages": {},
        "lots": {},
        "issues": [],
    }
    if data is None:
        err = src.folio_error_file(folio)
        out["issues"].append(
            f"no COMPLETE JSON for folio {folio}" + (f" (error file: {err})" if err else "")
        )
        header, lines = {}, []
    else:
        header = data.get("invoice_header") or {}
        lines = data.get("invoice_lines") or []
    out["header"] = {
        "cliente": header.get("cliente"),
        "factura": header.get("factura"),
        "fecha": header.get("fecha"),
        "moneda": header.get("moneda"),
        "lineas": len(lines),
    }
    xlsx = src.xlsx_for_folio(folio)
    if not xlsx and data is None:
        out["issues"].append("folio absent from summary xlsx too")

    st = out["stages"]

    # --- Sales Order (anchor for most downstream lookups) ----------------- #
    so = _find_sales_order(frappe, folio, header, lines)
    st["sales_order"] = so["stage"]
    so_name = so.get("name")

    # --- Quotation --------------------------------------------------------- #
    st["quotation"] = _find_quotation(frappe, folio, so_name)

    # --- Work Order ---------------------------------------------------------#
    wos = []
    if so_name:
        wos = frappe.get_all(
            "Work Order", filters={"sales_order": so_name},
            fields=["name", "status", "docstatus", "production_item", "qty"])
    st["work_order"] = (
        _st(OK, [w.name for w in wos], f"{len(wos)} WO(s)") if wos
        else _st(MISSING if so_name else UNKNOWN,
                 note="" if so_name else "no SO to anchor WO lookup")
    )

    # --- BOM ---------------------------------------------------------------- #
    st["bom"] = _find_bom(frappe, so.get("items") or [], lines)

    # --- Batch AMB hierarchy + native Batch + C-source per lot -------------- #
    batch_amb_refs, native_refs = [], []
    batch_states, native_states = [], []
    for line in lines:
        lote = str(line.get("lote_real") or "").strip()
        if not lote:
            continue
        lot_info = _census_lot(frappe, src, lote, header, line)
        out["lots"][lote] = lot_info
        batch_states.append(lot_info["batch_amb"]["status"])
        native_states.append(lot_info["native_batch"]["status"])
        batch_amb_refs += lot_info["batch_amb"]["refs"]
        native_refs += lot_info["native_batch"]["refs"]
    st["batch_amb"] = _rollup(batch_states, batch_amb_refs, "per-lot Batch AMB hierarchy")
    st["native_batch"] = _rollup(native_states, native_refs, "projection twin (native Batch)")

    # --- Stock Entry -> FG/Sell + label -------------------------------------- #
    st["stock_entry_fg"] = _find_stock_entries(frappe, wos, lines)
    st["label"] = _st(
        UNKNOWN, note="label is a print artifact (no doctype on this site); "
        "verify against the printed-label archive / etiqueta PDFs")

    # --- Delivery Note -------------------------------------------------------- #
    if so_name:
        dns = frappe.get_all(
            "Delivery Note Item", filters={"against_sales_order": so_name},
            fields=["parent"], distinct=True)
        dn_names = sorted({d.parent for d in dns})
        st["delivery_note"] = _st(OK if dn_names else MISSING, dn_names)
    else:
        st["delivery_note"] = _st(UNKNOWN, note="no SO anchor")

    # --- Sales Invoice (factura F-ref) ------------------------------------------#
    st["sales_invoice"] = _find_sales_invoice(frappe, so_name, header)

    # --- Payment ------------------------------------------------------------------#
    st["payment"] = _find_payment(frappe, so_name, st["sales_invoice"]["refs"])

    return out


# --------------------------------------------------------------------------- #
# stage finders (all read-only)
# --------------------------------------------------------------------------- #

def _find_sales_order(frappe, folio, header, lines):
    """Primary: migrated-name pattern SO-<folio5>-%. Fallback: customer+total."""
    rows = frappe.get_all(
        "Sales Order", filters=[["name", "like", f"SO-{_folio5(folio)}-%"]],
        fields=["name", "customer", "transaction_date", "grand_total",
                "currency", "status", "docstatus"])
    matched_on = "name-pattern"
    if not rows and header.get("cliente"):
        expected = _expected_total(lines)
        cand = frappe.get_all(
            "Sales Order",
            filters=[["customer", "like", f"%{header['cliente'][:20]}%"]],
            fields=["name", "customer", "transaction_date", "grand_total",
                    "currency", "status", "docstatus"], limit=20)
        rows = [r for r in cand if expected and abs(r.grand_total - expected) <= 0.01 * expected]
        matched_on = "customer+total"
    if not rows:
        return {"stage": _st(MISSING), "name": None, "items": []}
    r = rows[0]
    notes = [f"matched on {matched_on}", f"docstatus={r.docstatus}", r.status]
    expected = _expected_total(lines)
    if expected and abs(r.grand_total - expected) > 0.01 * expected:
        notes.append(f"TOTAL DRIFT: ERPNext {r.grand_total} vs FoxPro {expected}")
    if header.get("fecha") and str(r.transaction_date) != str(header["fecha"])[:10]:
        notes.append(f"date {r.transaction_date} vs factura fecha {header['fecha']}")
    items = frappe.get_all(
        "Sales Order Item", filters={"parent": r.name},
        fields=["item_code", "qty", "rate", "bom_no", "prevdoc_docname", "warehouse"])
    status = OK if r.docstatus == 1 else PARTIAL
    return {"stage": _st(status, [r.name], "; ".join(notes)), "name": r.name, "items": items}


def _find_quotation(frappe, folio, so_name):
    rows = frappe.get_all(
        "Quotation", filters=[["name", "like", f"%-{_folio5(folio)}"]],
        fields=["name", "docstatus", "status"])
    if not rows and so_name:
        links = frappe.get_all(
            "Sales Order Item", filters={"parent": so_name, "prevdoc_docname": ["!=", ""]},
            fields=["prevdoc_docname"], distinct=True)
        names = sorted({l.prevdoc_docname for l in links if l.prevdoc_docname})
        if names:
            return _st(OK, names, "via SO prevdoc")
    if rows:
        r = rows[0]
        return _st(OK if r.docstatus == 1 else PARTIAL, [r.name], f"docstatus={r.docstatus}")
    return _st(MISSING, note="no folio-named Quotation and no SO prevdoc link")


def _find_bom(frappe, so_items, lines):
    refs, notes = [], []
    for it in so_items:
        if it.get("bom_no"):
            if frappe.db.exists("BOM", it["bom_no"]):
                refs.append(it["bom_no"])
            else:
                notes.append(f"SO line points at missing BOM {it['bom_no']}")
    if refs:
        return _st(OK, sorted(set(refs)), "; ".join(notes))
    # family default: BOM on the SO line's family item
    for it in so_items:
        code = it.get("item_code")
        if code:
            bom = frappe.db.get_value(
                "BOM", {"item": code, "is_active": 1, "docstatus": 1}, "name")
            if bom:
                return _st(PARTIAL, [bom], f"no SO-line bom_no; family item {code} has active BOM")
    if notes:
        return _st(PARTIAL, [], "; ".join(notes))
    return _st(MISSING if so_items else UNKNOWN,
               note="" if so_items else "no SO lines to derive family")


def _census_lot(frappe, src, lote, header, line):
    """Batch AMB hierarchy + native projection twin + C-source for one lot."""
    variants = lote_variants(lote)
    info = {"variants": variants}

    ba = frappe.get_all(
        "Batch AMB",
        filters=[["custom_golden_number", "in", variants]],
        fields=["name", "custom_batch_level", "batch_level", "parent_batch_amb",
                "custom_golden_number", "item_code", "batch_id"])
    if not ba:
        ba = frappe.get_all(
            "Batch AMB", filters=[["batch_id", "in", variants]],
            fields=["name", "custom_batch_level", "batch_level", "parent_batch_amb",
                    "custom_golden_number", "item_code", "batch_id"])
    if ba:
        names = [b.name for b in ba]
        kids = frappe.get_all(
            "Batch AMB", filters=[["parent_batch_amb", "in", names]],
            fields=["name", "custom_batch_level"])
        kid_names = [k.name for k in kids]
        grandkids = frappe.get_all(
            "Batch AMB", filters=[["parent_batch_amb", "in", kid_names]],
            pluck="name") if kid_names else []
        all_names = names + kid_names + list(grandkids)
        n_serial = frappe.db.count("Container Barrels", {"parent": ["in", all_names]}) \
            if all_names else 0
        complete = bool(kids) and bool(grandkids) and n_serial > 0
        info["batch_amb"] = _st(
            OK if complete else PARTIAL, names,
            f"L1={len(names)} L2={len(kids)} L3={len(list(grandkids))} serial-rows={n_serial}")
    else:
        info["batch_amb"] = _st(MISSING)

    nb = frappe.get_all(
        "Batch", filters=[["custom_golden_number", "in", variants]], pluck="name")
    if not nb:
        nb = frappe.get_all("Batch", filters=[["name", "in", variants]], pluck="name")
    info["native_batch"] = _st(OK if nb else MISSING, nb,
                               "" if nb else "no projection twin")

    info["c_source"] = src.resolve_containers(
        lote, factura=header.get("factura"), qty_kg=line.get("cantidad"))
    return info


def _rollup(states, refs, what):
    if not states:
        return _st(UNKNOWN, note=f"no lots on folio to census {what}")
    if all(s == OK for s in states):
        return _st(OK, refs, what)
    if all(s == MISSING for s in states):
        return _st(MISSING, refs, what)
    return _st(PARTIAL, refs, f"{what}: {states.count(OK)}/{len(states)} lots OK")


def _find_stock_entries(frappe, wos, lines):
    refs = []
    for w in wos:
        ses = frappe.get_all(
            "Stock Entry", filters={"work_order": w["name"], "docstatus": ["<", 2]},
            fields=["name", "stock_entry_type"])
        refs += [s.name for s in ses]
    variants = []
    for line in lines:
        variants += lote_variants(line.get("lote_real"))
    if variants:
        sed = frappe.get_all(
            "Stock Entry Detail", filters=[["batch_no", "in", variants]],
            fields=["parent"], distinct=True)
        refs += [s.parent for s in sed]
    refs = sorted(set(refs))
    return _st(OK if refs else MISSING, refs,
               "SEs via WO and/or batch_no" if refs else "no Stock Entry to FG/Sell found")


def _find_sales_invoice(frappe, so_name, header):
    refs, notes = [], []
    if so_name:
        rows = frappe.get_all(
            "Sales Invoice Item", filters={"sales_order": so_name},
            fields=["parent"], distinct=True)
        refs = sorted({r.parent for r in rows})
    factura = str(header.get("factura") or "").strip()
    if factura:
        hits = frappe.get_all(
            "Sales Invoice",
            filters=[["remarks", "like", f"%{factura}%"]], pluck="name", limit=5)
        for h in hits:
            if h not in refs:
                refs.append(h)
                notes.append(f"factura {factura} matched in remarks")
    if refs:
        docstatuses = [frappe.db.get_value("Sales Invoice", r, "docstatus") for r in refs]
        status = OK if 1 in docstatuses else PARTIAL
        return _st(status, refs, "; ".join(notes))
    return _st(MISSING if so_name or factura else UNKNOWN,
               note=f"no SI linked to SO and no SI mentioning {factura or '(no factura)'}")


def _find_payment(frappe, so_name, si_refs):
    refs = []
    if si_refs:
        rows = frappe.get_all(
            "Payment Entry Reference",
            filters=[["reference_doctype", "=", "Sales Invoice"],
                     ["reference_name", "in", si_refs]],
            fields=["parent"], distinct=True)
        refs = sorted({r.parent for r in rows})
    if not refs and so_name:
        rows = frappe.get_all(
            "Payment Entry Reference",
            filters={"reference_doctype": "Sales Order", "reference_name": so_name},
            fields=["parent"], distinct=True)
        refs = sorted({r.parent for r in rows})
    return _st(OK if refs else MISSING, refs,
               "" if refs else "no Payment Entry against SI/SO")


def _expected_total(lines):
    try:
        return round(sum(float(l.get("cantidad") or 0) * float(l.get("precio") or 0)
                         for l in lines), 2)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# section aggregate
# --------------------------------------------------------------------------- #

def census_section(year, src: FolioSources = None, folios=None, progress=None):
    """Aggregate census for a year-section (2024/2025). Read-only."""
    src = src or get_sources()
    year = int(year)
    folios = folios if folios is not None else src.folios_for_year(year)
    matrix = {s: {"OK": 0, "PARTIAL": 0, "MISSING": 0, "UNKNOWN": 0} for s in STAGES}
    c_sources = {"extracted-trazab": 0, "extracted-env2": 0, "regenerated": 0}
    details, patterns = [], {}
    for i, folio in enumerate(folios):
        c = census_folio(folio, src)
        details.append(c)
        gap_sig = []
        for s in STAGES:
            stat = c["stages"][s]["status"]
            matrix[s][stat] += 1
            if stat in (MISSING, PARTIAL):
                gap_sig.append(s)
        for lot in c["lots"].values():
            c_sources[lot["c_source"]["source"]] += 1
        sig = "+".join(gap_sig) or "complete"
        patterns[sig] = patterns.get(sig, 0) + 1
        if progress and (i + 1) % 25 == 0:
            progress(i + 1, len(folios))
    top_patterns = sorted(patterns.items(), key=lambda kv: -kv[1])
    return {
        "year": year,
        "folios_censused": len(folios),
        "stage_matrix": matrix,
        "c_sources_lots": c_sources,
        "top_gap_patterns": top_patterns[:15],
        "undated_folios": src.undated_folios(),
        "details": details,
    }


def format_folio_census_md(c):
    """Bilingual gap table for chat / reports."""
    h = c["header"]
    lines = [
        f"## 📋 Migration census — folio {c['folio']} / Censo de migración",
        f"**{h.get('cliente') or '?'}** · factura {h.get('factura') or '?'} · "
        f"{h.get('fecha') or 'sin fecha'} · {h.get('lineas')} line(s)",
        "",
        "| # | Stage | Status | Refs | Note |",
        "|---|-------|--------|------|------|",
    ]
    icon = {"OK": "✅", "PARTIAL": "🟡", "MISSING": "❌", "UNKNOWN": "❔"}
    for i, s in enumerate(STAGES, 1):
        st = c["stages"][s]
        refs = ", ".join(st["refs"][:4]) + ("…" if len(st["refs"]) > 4 else "")
        lines.append(
            f"| {i} | {s} | {icon[st['status']]} {st['status']} | {refs} | {st['note'][:90]} |")
    for lote, info in c["lots"].items():
        cs = info["c_source"]
        lines.append(
            f"\n**Lot {lote}** → container source **{cs['source']}** "
            f"({cs.get('count')} container(s))")
    for issue in c["issues"]:
        lines.append(f"\n⚠️ {issue}")
    lines.append("\n_Read-only census — nothing was written. / Censo de solo lectura; no se escribió nada._")
    return "\n".join(lines)


def format_section_md(res):
    lines = [
        f"# Migration census — {res['year']} section",
        f"Folios censused: **{res['folios_censused']}** (xlsx fecha-year basis)",
        "",
        "| Stage | OK | PARTIAL | MISSING | UNKNOWN |",
        "|-------|----|---------|---------|---------|",
    ]
    for s in STAGES:
        m = res["stage_matrix"][s]
        lines.append(f"| {s} | {m['OK']} | {m['PARTIAL']} | {m['MISSING']} | {m['UNKNOWN']} |")
    lines += ["", "## Container C-sources (per lot)"]
    for k, v in res["c_sources_lots"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Top gap patterns"]
    for sig, n in res["top_gap_patterns"]:
        lines.append(f"- `{sig}` × {n}")
    lines += ["", f"## Undated folios ({len(res['undated_folios'])})",
              ", ".join(str(f) for f in res["undated_folios"])]
    lines.append("\n_Read-only census — nothing was written._")
    return "\n".join(lines)
