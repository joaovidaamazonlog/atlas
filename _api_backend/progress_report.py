"""
progress_report.py
==================
Exibe o progresso do geocoding no Turso.

Uso:
    python progress_report.py          # resumo geral
    python progress_report.py --by-uf  # breakdown por UF
"""

from __future__ import annotations

import argparse
import os
import requests

def _turso_url() -> str:
    raw = os.environ.get("TURSO_URL", "")
    if not raw:
        raise RuntimeError("TURSO_URL não definida.")
    return raw.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"

def _turso_token() -> str:
    token = os.environ.get("TURSO_TOKEN", "")
    if not token:
        raise RuntimeError("TURSO_TOKEN não definido.")
    return token

def query(sql: str) -> list[dict]:
    url     = _turso_url()
    headers = {"Authorization": f"Bearer {_turso_token()}", "Content-Type": "application/json"}
    payload = {"requests": [{"type": "execute", "stmt": {"sql": sql}}, {"type": "close"}]}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    inner = r.json()["results"][0].get("response", {}).get("result", {})
    cols  = [c["name"] for c in inner.get("cols", [])]
    return [
        {cols[i]: (cell.get("value") if cell.get("type") != "null" else None)
         for i, cell in enumerate(row)}
        for row in inner.get("rows", [])
    ]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--by-uf", action="store_true", help="Breakdown por UF")
    args = parser.parse_args()

    total_alvo = int(query("SELECT COUNT(*) as n FROM empresas_alvo")[0]["n"])
    rows       = query("SELECT geocode_status, COUNT(*) as n FROM empresas_geo GROUP BY geocode_status")

    ok   = next((int(r["n"]) for r in rows if r["geocode_status"] == "ok"),     0)
    fail = next((int(r["n"]) for r in rows if r["geocode_status"] == "failed"), 0)
    done = ok + fail
    pct  = done / total_alvo * 100 if total_alvo else 0

    print("=" * 50)
    print("PROGRESSO GLOBAL")
    print(f"  Total empresas_alvo : {total_alvo:,}")
    print(f"  Geocodificadas OK   : {ok:,}")
    print(f"  Falhas              : {fail:,}")
    print(f"  Total processado    : {done:,} ({pct:.1f}%)")
    print(f"  Restante            : {total_alvo - done:,}")
    print("=" * 50)

    if args.by_uf:
        by_uf = query("""
            SELECT e.uf,
                   COUNT(*) as total,
                   SUM(CASE WHEN g.geocode_status='ok' THEN 1 ELSE 0 END) as ok
            FROM empresas_alvo e
            LEFT JOIN empresas_geo g
                   ON (e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv) = g.cnpj
            GROUP BY e.uf
            ORDER BY total DESC
        """)
        print(f"\n{'UF':<6} {'Total':>10} {'OK':>10} {'%':>8}")
        print("-" * 38)
        for r in by_uf:
            t   = int(r["total"])
            o   = int(r["ok"] or 0)
            pct = o / t * 100 if t else 0
            print(f"{r['uf']:<6} {t:>10,} {o:>10,} {pct:>7.1f}%")

if __name__ == "__main__":
    main()
