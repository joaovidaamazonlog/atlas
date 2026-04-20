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
from pathlib import Path

def _load_env():
    env = Path(__file__).parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

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
    _load_env()
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
            SELECT uf, geocode_status, COUNT(*) as n
            FROM empresas_geo
            GROUP BY uf, geocode_status
            ORDER BY uf
        """)
        # agrupa por UF
        from collections import defaultdict
        uf_data: dict = defaultdict(lambda: {"ok": 0, "failed": 0})
        for r in by_uf:
            uf_data[r["uf"]][r["geocode_status"]] += int(r["n"])

        print(f"\n{'UF':<6} {'OK':>10} {'Falhas':>10}")
        print("-" * 30)
        for uf, d in sorted(uf_data.items()):
            print(f"{uf:<6} {d['ok']:>10,} {d['failed']:>10,}")

if __name__ == "__main__":
    main()
