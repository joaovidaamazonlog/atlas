"""Exporta a tabela gmaps_leads do Turso para CSV.

Colunas exportadas: nome, endereco, lat, lon, station_code (DS).

Uso:
    python scripts/export_gmaps_leads.py
    python scripts/export_gmaps_leads.py --out caminho/arquivo.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import urllib.request
import json

# Carrega backend/.env se existir
ENV_PATH = Path(__file__).resolve().parents[1] / "backend" / ".env"
if ENV_PATH.exists():
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

TURSO_URL = os.environ.get("TURSO_URL", "")
TURSO_TOKEN = (
    os.environ.get("TURSO_AUTH_TOKEN", "") or os.environ.get("TURSO_TOKEN", "")
)

if not TURSO_URL or not TURSO_TOKEN:
    print("ERRO: TURSO_URL e TURSO_TOKEN/TURSO_AUTH_TOKEN são obrigatórios.", file=sys.stderr)
    sys.exit(1)

HTTP_URL = TURSO_URL.replace("libsql://", "https://") + "/v2/pipeline"


def turso_execute(sql: str, args: list | None = None) -> list[dict]:
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [{"type": "text", "value": str(a)} for a in (args or [])],
                },
            },
            {"type": "close"},
        ]
    }
    req = urllib.request.Request(
        HTTP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TURSO_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = data.get("results", [])
    if not results:
        return []
    first = results[0]
    if first.get("type") == "error":
        raise RuntimeError(f"Turso error: {first.get('error')}")
    response = first.get("response", {}).get("result", {})
    cols = [c["name"] for c in response.get("cols", [])]
    rows: list[dict] = []
    for row in response.get("rows", []):
        rec = {}
        for i, cell in enumerate(row):
            if cell.get("type") == "null":
                rec[cols[i]] = None
            else:
                rec[cols[i]] = cell.get("value")
        rows.append(rec)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent / "gmaps_leads.csv"),
        help="Caminho do CSV de saída.",
    )
    args = parser.parse_args()

    print("Consultando Turso…")
    rows = turso_execute(
        "SELECT nome, endereco, lat, lon, station_code FROM gmaps_leads"
    )
    print(f"  {len(rows)} registros recebidos.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["nome", "endereco", "lat", "lon", "DS"])
        for r in rows:
            writer.writerow([
                r.get("nome") or "",
                r.get("endereco") or "",
                r.get("lat") if r.get("lat") is not None else "",
                r.get("lon") if r.get("lon") is not None else "",
                r.get("station_code") or "",
            ])

    print(f"OK. CSV salvo em: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
