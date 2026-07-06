"""Migration source-of-truth access (v2).

Read-only loaders for the three FoxPro-era sources used by the migration
census and Lesson-One planning:

  * per-folio JSON extracts   migration_folio_<n>_COMPLETE.json
  * the migration summary xlsx (one row per folio/line)
  * FoxPro DBF tables: det_trazab (container/serial truth), tabla_env2
    (packing ranges — separate FOLIO namespace, reconcile via FACTURA/LOTE,
    never via FOLIO alone), lotegen (lot register)

This module never imports frappe at module level so it stays importable in
unit tests and standalone runners. Paths resolve from site config when a
frappe site is active, else from the staging defaults below.
"""

import json
import os
import re
from functools import lru_cache

DEFAULTS = {
    "migration_json_dir": "/mnt/e/Claude/local-agent-mode-sessions/foxpro-staging/json_files",
    "migration_xlsx_path": "/mnt/e/Claude/local-agent-mode-sessions/reports/migration_summary 1 (1).xlsx",
    "foxpro_dbf_dir": "/mnt/e/Claude/local-agent-mode-sessions/foxpro-staging/data",
    "migration_census_dir": "/mnt/e/Claude/migration-close/census",
}

# xlsx column order observed in migration_summary 1 (1).xlsx (no header row)
XLSX_COLS = [
    "filename", "folio", "cliente", "factura", "fecha", "moneda",
    "lote", "item_code", "col8", "descripcion", "cantidad", "col11", "precio",
]

# 25 kg cuñete is the pack-standard default for C-source (c) regeneration
DEFAULT_PACK_KG = 25.0


def _conf(key):
    try:
        import frappe
        return frappe.conf.get(key) or DEFAULTS[key]
    except Exception:
        return DEFAULTS[key]


def lote_variants(lote):
    """All spellings a FoxPro lot shows up under (leading-zero drift)."""
    s = str(lote or "").strip()
    if not s:
        return []
    out = [s]
    stripped = s.lstrip("0")
    if stripped and stripped not in out:
        out.append(stripped)
    padded = s.zfill(10)
    if padded not in out:
        out.append(padded)
    return out


class FolioSources:
    """One instance per census/plan run; caches xlsx and DBF loads."""

    def __init__(self, json_dir=None, xlsx_path=None, dbf_dir=None, census_dir=None):
        self.json_dir = json_dir or _conf("migration_json_dir")
        self.xlsx_path = xlsx_path or _conf("migration_xlsx_path")
        self.dbf_dir = dbf_dir or _conf("foxpro_dbf_dir")
        self.census_dir = census_dir or _conf("migration_census_dir")
        self._xlsx_rows = None
        self._env2_rows = None
        self._lotegen = None
        self._trazab_index = None

    # ---- per-folio JSON ------------------------------------------------ #
    def load_folio_json(self, folio):
        n = int(folio)
        path = os.path.join(self.json_dir, f"migration_folio_{n}_COMPLETE.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return None

    def folio_error_file(self, folio):
        n = int(folio)
        path = os.path.join(self.json_dir, f"migration_error_folio_{n}.json")
        return path if os.path.exists(path) else None

    def list_folios(self):
        rx = re.compile(r"migration_folio_(\d+)_COMPLETE\.json$")
        out = []
        for f in os.listdir(self.json_dir):
            m = rx.match(f)
            if m:
                out.append(int(m.group(1)))
        return sorted(out)

    # ---- summary xlsx --------------------------------------------------- #
    def xlsx_rows(self):
        if self._xlsx_rows is None:
            import openpyxl
            wb = openpyxl.load_workbook(self.xlsx_path, read_only=True)
            ws = wb.worksheets[0]
            rows = []
            for raw in ws.iter_rows(values_only=True):
                if raw is None or raw[1] is None:
                    continue
                row = dict(zip(XLSX_COLS, list(raw) + [None] * (len(XLSX_COLS) - len(raw))))
                rows.append(row)
            wb.close()
            self._xlsx_rows = rows
        return self._xlsx_rows

    def xlsx_for_folio(self, folio):
        n = int(folio)
        return [r for r in self.xlsx_rows() if int(r["folio"]) == n]

    def folios_for_year(self, year):
        """Folio numbers whose xlsx fecha falls in `year` (invoice-date truth)."""
        out = set()
        for r in self.xlsx_rows():
            f = r.get("fecha")
            if f is not None and getattr(f, "year", None) == int(year):
                out.add(int(r["folio"]))
        return sorted(out)

    def undated_folios(self):
        dated = set()
        all_f = set()
        for r in self.xlsx_rows():
            all_f.add(int(r["folio"]))
            if r.get("fecha") is not None:
                dated.add(int(r["folio"]))
        return sorted(all_f - dated)

    # ---- det_trazab index (C-source a: extracted-trazab) ---------------- #
    def trazab_index_path(self):
        return os.path.join(self.census_dir, "det_trazab_index.json")

    def trazab_index(self):
        """LOTE -> {SUBLOTE -> [distinct BARRIL]} built once from the 2.5M-row
        det_trazab.dbf and cached as JSON; never rescanned per folio."""
        if self._trazab_index is None:
            path = self.trazab_index_path()
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"det_trazab index cache missing at {path} — build it once "
                    "with the census runner (build_trazab_index)."
                )
            with open(path, encoding="utf-8") as f:
                self._trazab_index = json.load(f)
        return self._trazab_index

    def containers_from_trazab(self, lote):
        idx = self.trazab_index()
        for v in lote_variants(lote):
            if v in idx:
                return v, idx[v]
        return None, None

    # ---- tabla_env2 (C-source b: packing ranges) ------------------------ #
    def env2_rows(self):
        if self._env2_rows is None:
            from dbfread import DBF
            path = os.path.join(self.dbf_dir, "tabla_env2.dbf")
            self._env2_rows = [
                {k: (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
                for r in DBF(path, char_decode_errors="replace", recfactory=dict)
            ]
        return self._env2_rows

    def env2_for(self, factura=None, lote=None):
        """Rows matched on FACTURA and/or LOTE — the PROVEN keys. tabla_env2's
        FOLIO column is a packing-folio namespace and is deliberately not a key."""
        fact = str(factura or "").strip().lstrip("F")
        variants = set(lote_variants(lote)) if lote else set()
        out = []
        for r in self.env2_rows():
            rl = str(r.get("LOTE") or "")
            rf = str(r.get("FACTURA") or "").strip().lstrip("F")
            hit_l = bool(variants) and rl in variants
            hit_f = bool(fact) and rf == fact
            if hit_l or hit_f:
                r = dict(r)
                r["_matched_on"] = ("LOTE" if hit_l else "") + ("+FACTURA" if hit_f else "")
                out.append(r)
        return out

    # ---- lotegen (lot register) ------------------------------------------ #
    def lotegen_map(self):
        if self._lotegen is None:
            from dbfread import DBF
            path = os.path.join(self.dbf_dir, "lotegen.dbf")
            m = {}
            for r in DBF(path, char_decode_errors="replace", recfactory=dict):
                code = str(r.get("CODIGO") or "").strip()
                if code:
                    m[code] = r
            self._lotegen = m
        return self._lotegen

    def lotegen_for(self, lote):
        m = self.lotegen_map()
        for v in lote_variants(lote):
            if v in m:
                return m[v]
        return None

    # ---- C-source resolution (priority a > b > c) ------------------------ #
    def resolve_containers(self, lote, factura=None, qty_kg=None, pack_kg=DEFAULT_PACK_KG):
        """Which container source would this lot use, per the doctrine order:
        (a) det_trazab distinct barrels, (b) tabla_env2 PROVEN range,
        (c) regenerate per pack standard. Returns a stamped dict; read-only."""
        key, subs = (None, None)
        try:
            key, subs = self.containers_from_trazab(lote)
        except FileNotFoundError:
            pass
        if subs:
            barrels = sorted({b for bars in subs.values() for b in bars})
            if barrels:
                return {
                    "source": "extracted-trazab",
                    "lote_key": key,
                    "sublotes": {s: len(b) for s, b in subs.items()},
                    "containers": barrels,
                    "count": len(barrels),
                }
        rows = self.env2_for(factura=factura, lote=lote)
        proven = [r for r in rows if "LOTE" in (r.get("_matched_on") or "")]
        if proven:
            containers = []
            for r in proven:
                try:
                    lo = int(str(r.get("C_INICIAL") or "").strip() or 0)
                    hi = int(str(r.get("C_FINAL") or "").strip() or 0)
                    if hi >= lo > 0:
                        containers.extend(str(i) for i in range(lo, hi + 1))
                except ValueError:
                    continue
            if containers:
                return {
                    "source": "extracted-env2",
                    "rows": len(proven),
                    "containers": sorted(set(containers), key=lambda x: int(x)),
                    "count": len(set(containers)),
                }
        count = None
        if qty_kg:
            count = max(1, int(round(float(qty_kg) / float(pack_kg or DEFAULT_PACK_KG))))
        return {
            "source": "regenerated",
            "pack_kg": pack_kg or DEFAULT_PACK_KG,
            "count": count,
            "note": "no trazab barrels, no PROVEN env2 range — regenerate per pack standard",
        }


@lru_cache(maxsize=1)
def get_sources():
    return FolioSources()
