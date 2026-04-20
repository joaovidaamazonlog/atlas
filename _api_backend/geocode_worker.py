"""
geocode_worker.py
=================
Geocodifica empresas_alvo → empresas_geo via Nominatim.
- Streaming direto: grava no Turso imediatamente após cada geocoding (sem buffer)
- 5 tentativas com backoff exponencial em toda chamada ao Turso
- Resume automático: pula CNPJs já presentes em empresas_geo
- Particionamento por faixa de CEP ou UF

Uso:
    python geocode_worker.py --cep-min 00000000 --cep-max 19999999 --worker-id 1
    python geocode_worker.py --uf SP --worker-id 2
    python geocode_worker.py --offset 0 --limit 500000 --worker-id 3

Env vars obrigatórias:
    TURSO_URL
    TURSO_TOKEN
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import h3
import requests as req_lib

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _make_logger(worker_id: str) -> logging.Logger:
    fmt = f"%(asctime)s [W{worker_id}] %(levelname)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=fmt, datefmt="%H:%M:%S", stream=sys.stdout)
    return logging.getLogger(f"worker.{worker_id}")


# ---------------------------------------------------------------------------
# Turso client — streaming, 5 tentativas, backoff exponencial
# ---------------------------------------------------------------------------

class TursoClient:
    MAX_RETRIES  = 5
    BACKOFF_BASE = 2.0

    def __init__(self, logger: logging.Logger):
        self.log = logger
        turso_url = os.environ.get("TURSO_URL", "")
        turso_token = os.environ.get("TURSO_TOKEN", "")

        if not turso_url:
            raise RuntimeError("TURSO_URL não definida. Configure a variável de ambiente.")
        if not turso_token:
            raise RuntimeError("TURSO_TOKEN não definido. Configure a variável de ambiente.")

        url = turso_url.replace("libsql://", "https://")
        self.base = url + "/v2/pipeline"
        self.headers = {
            "Authorization": f"Bearer {turso_token}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict, timeout: int = 30) -> dict:
        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                r = req_lib.post(
                    self.base, headers=self.headers,
                    json=payload, timeout=timeout,
                )
                r.raise_for_status()
                return r.json()
            except (req_lib.exceptions.ConnectionError,
                    req_lib.exceptions.Timeout) as e:
                last_exc = e
            except req_lib.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code >= 500:
                    last_exc = e
                else:
                    raise
            wait = self.BACKOFF_BASE ** attempt
            self.log.warning(
                "Turso conexão perdida (tentativa %d/%d). Aguardando %.0fs...",
                attempt, self.MAX_RETRIES, wait,
            )
            time.sleep(wait)
        raise RuntimeError(f"Turso: falha após {self.MAX_RETRIES} tentativas.") from last_exc

    def _arg(self, v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, float):
            return {"type": "float", "value": v}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        return {"type": "text", "value": str(v)}

    def execute(self, sql: str, params: list = None) -> list[dict]:
        stmt = {"sql": sql}
        if params:
            stmt["args"] = [self._arg(p) for p in params]
        data = self._post({"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]})
        result = data["results"][0]
        if result.get("type") == "error":
            raise RuntimeError(result["error"].get("message", "unknown"))
        inner = result.get("response", {}).get("result", {})
        cols  = [c["name"] for c in inner.get("cols", [])]
        return [
            {cols[i]: (cell.get("value") if cell.get("type") != "null" else None)
             for i, cell in enumerate(row)}
            for row in inner.get("rows", [])
        ]

    def batch_upsert(self, rows: list[dict]) -> None:
        """Grava um batch de empresas no Turso em um único pipeline."""
        if not rows:
            return
        sql = """
            INSERT INTO empresas_geo
                (cnpj, razao_social, nome_fantasia, cnae_principal, cnae_secundaria,
                 endereco, bairro, cep, uf, municipio, telefone_1, email,
                 lat, lng, h3_r8_id, h3_r9_id, h3_id, geocode_status, geocoded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(cnpj) DO UPDATE SET
                lat              = excluded.lat,
                lng              = excluded.lng,
                h3_r8_id         = excluded.h3_r8_id,
                h3_r9_id         = excluded.h3_r9_id,
                h3_id            = excluded.h3_r9_id,
                geocode_status   = excluded.geocode_status,
                geocoded_at      = excluded.geocoded_at
        """
        reqs = []
        for row in rows:
            reqs.append({
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": [self._arg(v) for v in [
                        row["cnpj"], row["razao_social"], row["nome_fantasia"],
                        row["cnae_principal"], row["cnae_secundaria"],
                        row["endereco"], row["bairro"], row["cep"],
                        row["uf"], row["municipio"], row["telefone_1"], row["email"],
                        row["lat"], row["lng"],
                        row["h3_r8_id"], row["h3_r9_id"], row["h3_r9_id"],
                        row["geocode_status"], row["geocoded_at"],
                    ]],
                },
            })
        reqs.append({"type": "close"})
        self._post({"requests": reqs}, timeout=120)

    def setup_table(self) -> None:
        self.execute("""
            CREATE TABLE IF NOT EXISTS empresas_geo (
                cnpj TEXT PRIMARY KEY, razao_social TEXT, nome_fantasia TEXT,
                cnae_principal TEXT, cnae_secundaria TEXT, endereco TEXT,
                bairro TEXT, cep TEXT, uf TEXT, municipio TEXT,
                telefone_1 TEXT, email TEXT,
                lat REAL, lng REAL,
                h3_r8_id TEXT, h3_r9_id TEXT, h3_id TEXT,
                geocode_status TEXT, geocoded_at TEXT
            )
        """)
        for ddl in [
            "CREATE INDEX IF NOT EXISTS idx_geo_r9 ON empresas_geo (h3_r9_id)",
            "CREATE INDEX IF NOT EXISTS idx_geo_r8 ON empresas_geo (h3_r8_id)",
            "CREATE INDEX IF NOT EXISTS idx_geo_cep ON empresas_geo (cep)",
        ]:
            try:
                self.execute(ddl)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Nominatim geocoding — 4 estratégias em ordem de precisão
# ---------------------------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT    = "atlas-geocoder/1.0 (logistics geocoding)"
DELAY_S       = 1.1
BATCH_SIZE    = 3000  # ~1h de processamento (3600s / 1.1s ≈ 3270 empresas)


def _geocode(endereco: str, bairro: str, cep: str, municipio: str, uf: str) -> tuple[float, float] | None:
    cep_fmt = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep
    strategies = [
        f"{endereco}, {cep_fmt}, Brasil",
        f"{endereco}, {municipio}, {uf}, Brasil",
        f"{cep_fmt}, Brasil",
        f"{bairro}, {municipio}, {uf}, Brasil",
    ]
    for query in strategies:
        query = query.strip(", ")
        if not query or query == "Brasil":
            continue
        try:
            params = urllib.parse.urlencode({
                "q": query, "format": "json", "limit": 1, "countrycodes": "br",
            })
            request = urllib.request.Request(
                f"{NOMINATIM_URL}?{params}",
                headers={"User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=10) as resp:
                data = json.loads(resp.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            pass
        time.sleep(DELAY_S)
    return None


# ---------------------------------------------------------------------------
# Progress logger
# ---------------------------------------------------------------------------

class ProgressTracker:
    def __init__(self, total: int, worker_id: str, log: logging.Logger):
        self.total      = total
        self.worker_id  = worker_id
        self.log        = log
        self.ok         = 0
        self.fail       = 0
        self.start_time = time.time()

    def update(self, success: bool) -> None:
        if success:
            self.ok += 1
        else:
            self.fail += 1

    def report(self, i: int) -> None:
        done     = self.ok + self.fail
        pct      = done / self.total * 100 if self.total else 0
        elapsed  = time.time() - self.start_time
        rate     = done / elapsed if elapsed > 0 else 0
        eta_s    = (self.total - done) / rate if rate > 0 else 0
        eta_h    = eta_s / 3600
        self.log.info(
            "[%d/%d] %.1f%% | OK=%d FAIL=%d | %.2f/s | ETA %.1fh",
            i, self.total, pct, self.ok, self.fail, rate, eta_h,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", default="?",  help="ID do worker (para logs)")
    parser.add_argument("--cep-min",   default=None, help="CEP mínimo (8 dígitos)")
    parser.add_argument("--cep-max",   default=None, help="CEP máximo (8 dígitos)")
    parser.add_argument("--offset",    type=int, default=None)
    parser.add_argument("--limit",     type=int, default=None)
    parser.add_argument("--uf",        default=None, help="Filtrar por UF")
    parser.add_argument("--no-resume", action="store_true", help="Reprocessar tudo")
    args = parser.parse_args()

    log   = _make_logger(args.worker_id)
    turso = TursoClient(log)

    log.info("Iniciando worker %s", args.worker_id)
    turso.setup_table()

    # CNPJs já processados
    already_done: set[str] = set()
    if not args.no_resume:
        rows = turso.execute("SELECT cnpj FROM empresas_geo WHERE geocode_status IS NOT NULL")
        already_done = {r["cnpj"] for r in rows}
        log.info("%d empresas já processadas (serão puladas).", len(already_done))

    # Query de origem
    conditions, params = [], []
    if args.cep_min:
        conditions.append("cep >= ?"); params.append(args.cep_min)
    if args.cep_max:
        conditions.append("cep <= ?"); params.append(args.cep_max)
    if args.uf:
        conditions.append("uf = ?");   params.append(args.uf.upper())

    sql = "SELECT * FROM empresas_alvo"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if args.limit:
        sql += f" LIMIT {args.limit}"
    if args.offset:
        sql += f" OFFSET {args.offset}"

    log.info("Buscando empresas do Turso...")
    empresas    = turso.execute(sql, params or None)
    to_process  = [
        e for e in empresas
        if (e.get("cnpj_basico","") + e.get("cnpj_ordem","") + e.get("cnpj_dv","")) not in already_done
    ]
    log.info("%d empresas para geocodificar.", len(to_process))

    if not to_process:
        log.info("Nada a fazer. Encerrando.")
        return

    tracker = ProgressTracker(len(to_process), args.worker_id, log)
    batch: list[dict] = []

    for i, emp in enumerate(to_process, 1):
        cnpj = emp.get("cnpj_basico","") + emp.get("cnpj_ordem","") + emp.get("cnpj_dv","")

        result = _geocode(
            emp.get("endereco",""), emp.get("bairro",""),
            emp.get("cep",""),      emp.get("municipio",""),
            emp.get("uf",""),
        )

        if result:
            lat, lng  = result
            h3_r9     = h3.latlng_to_cell(lat, lng, 9)
            h3_r8     = h3.latlng_to_cell(lat, lng, 8)
            status    = "ok"
        else:
            lat = lng = h3_r9 = h3_r8 = None
            status = "failed"

        batch.append({
            "cnpj":            cnpj,
            "razao_social":    emp.get("razao_social"),
            "nome_fantasia":   emp.get("nome_fantasia"),
            "cnae_principal":  emp.get("cnae_principal"),
            "cnae_secundaria": emp.get("cnae_secundaria"),
            "endereco":        emp.get("endereco"),
            "bairro":          emp.get("bairro"),
            "cep":             emp.get("cep"),
            "uf":              emp.get("uf"),
            "municipio":       emp.get("municipio"),
            "telefone_1":      emp.get("telefone_1"),
            "email":           emp.get("email"),
            "lat": lat, "lng": lng,
            "h3_r9_id": h3_r9, "h3_r8_id": h3_r8,
            "geocode_status":  status,
            "geocoded_at":     datetime.now(timezone.utc).isoformat(),
        })

        tracker.update(status == "ok")

        # Flush a cada ~1h de processamento (BATCH_SIZE empresas)
        if len(batch) >= BATCH_SIZE:
            log.info("Gravando batch de %d empresas no Turso...", len(batch))
            turso.batch_upsert(batch)
            batch = []
            log.info("Batch gravado com sucesso.")

        # Log a cada 50 empresas
        if i % 50 == 0 or i == len(to_process):
            tracker.report(i)

    # Flush do restante
    if batch:
        log.info("Gravando batch final de %d empresas no Turso...", len(batch))
        turso.batch_upsert(batch)
        log.info("Batch final gravado.")

    log.info(
        "Worker %s concluído: %d OK | %d falhas | %.1f%% precisão",
        args.worker_id, tracker.ok, tracker.fail,
        tracker.ok / (tracker.ok + tracker.fail) * 100 if (tracker.ok + tracker.fail) else 0,
    )


if __name__ == "__main__":
    main()
