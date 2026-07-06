"""Offline census runner — READ-ONLY against ERPNext.

Section censuses are too slow for a chat turn; run them via:

    bench --site <site> execute \
        raven_ai_agent.skills.migration_fixer.census_runner.run_section \
        --kwargs "{'year': 2024}"

Writes JSON + md reports to the census dir (migration_census_dir site-config
key). The only filesystem writes are the report files; nothing touches the DB.
"""

import json
import os

from .census import census_section, format_section_md
from .sources import get_sources


def build_trazab_index(force=False):
    """One-time LOTE -> {SUBLOTE -> [distinct BARRIL]} cache from det_trazab."""
    from dbfread import DBF
    src = get_sources()
    out_path = src.trazab_index_path()
    if os.path.exists(out_path) and not force:
        return {"status": "exists", "path": out_path}
    idx = {}
    n = 0
    dbf = os.path.join(src.dbf_dir, "det_trazab.dbf")
    for r in DBF(dbf, char_decode_errors="replace", recfactory=dict):
        n += 1
        lote = str(r.get("LOTE") or "").strip()
        if not lote:
            continue
        sub = str(r.get("SUBLOTE") or "").strip()
        bar = r.get("BARRIL")
        bar = "" if bar in (None, "", 0) else str(bar).strip()
        subs = idx.setdefault(lote, {})
        bars = subs.setdefault(sub, set())
        if bar and bar != "0":
            bars.add(bar)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({l: {s: sorted(b) for s, b in subs.items()}
                   for l, subs in idx.items()}, f)
    return {"status": "built", "path": out_path, "rows": n, "lots": len(idx)}


def run_section(year, limit=None):
    """Census one year-section and write census/<year>-census.{json,md}."""
    src = get_sources()
    folios = src.folios_for_year(year)
    if limit:
        folios = folios[: int(limit)]
    res = census_section(year, src, folios=folios,
                         progress=lambda i, n: print(f"  {i}/{n} folios", flush=True))
    os.makedirs(src.census_dir, exist_ok=True)
    json_path = os.path.join(src.census_dir, f"{year}-census.json")
    md_path = os.path.join(src.census_dir, f"{year}-census.md")
    with open(json_path, "w") as f:
        json.dump(res, f, indent=1, default=str)
    with open(md_path, "w") as f:
        f.write(format_section_md(res))
    print(f"census {year}: {res['folios_censused']} folios -> {json_path}")
    return {"json": json_path, "md": md_path,
            "folios": res["folios_censused"],
            "stage_matrix": res["stage_matrix"]}
