"""
etl_geocode_empresas.py
=======================
ETL que geocodifica as empresas da tabela `empresas_alvo` via Nominatim
(OpenStreetMap, gratuito, sem API key) e persiste o resultado em `empresas_geo`
com lat, lng e h3_id (resolução 9).

Uso:
    python -m geo_intelligence.etl_geocode_empresas [--uf SP] [--limit 1000] [--batch 50]

Parâmetros:
    --uf      Filtrar por UF (ex: SP). Padrão: todas.
    --limit   Máximo de empresas a processar. Padrão: sem limite.
    --batch   Tamanho do lote para upsert no Turso. Padrão: 100.
    --resume  Pula empresas que já têm h3_id em empresas_geo. Padrão: True.
"""

from __future__ import annotations

import argparse
import logging
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime

import h3

from geo_intelligence.geo_config import TURSO_URL, TURSO_AUTH_TOKEN
from geo_intelligence.turso_http import TursoHTTP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# DDL da tabela de destino
_DDL_EMPRESAS_GEO = """
CREATE TABLE IF NOT EXISTS empresas_geo (
    cnpj            TEXT PRIMARY KEY,
    razao_social    TEXT,
    nome_fantasia   TEXT,
    cnae_principal  TEXT,
    cnae_secundaria TEXT,
    endereco        TEXT,
    bairro          TEXT,
    cep             TEXT,
    uf              TEXT,
    municipio       TEXT,
    telefone_1      TEXT,
    email           TEXT,
    lat             REAL,
    lng             REAL,
    h3_r8_id        TEXT,
    h3_r9_id        TEXT,
    h3_id           TEXT,
    geocode_status  TEXT,
    geocoded_at     TEXT
)
"""

_DDL_IDX_R8 = "CREATE INDEX IF NOT EXISTS idx_empresas_geo_h3_r8 ON empresas_geo (h3_r8_id)"
_DDL_IDX_R9 = "CREATE INDEX IF NOT EXISTS idx_empresas_geo_h3_r9 ON empresas_geo (h3_r9_id)"

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "atlas-geo-intelligence/1.0 (geocode empresas)"
_DELAY_S = 1.1  # Nominatim: máx 1 req/s


def _build_cnpj(row: dict) -> str:
    return f"{row['cnpj_basico']}{row['cnpj_ordem']}{row['cnpj_dv']}"


def _geocode_nominatim(endereco: str, bairro: str, cep: str, uf: str) -> tuple[float, float] | None:
    """
    Geocodifica um endereço via Nominatim.
    Tenta 3 estratégias em ordem de precisão:
      1. Endereço completo: "RUA X 123, BAIRRO, CEP, BR"
      2. Só CEP: "CEP, BR"
      3. Bairro + UF: "BAIRRO, UF, BR"
    """
    strategies = [
        f"{endereco}, {bairro}, {cep}, Brasil",
        f"{cep}, Brasil",
        f"{bairro}, {uf}, Brasil",
    ]

    for query in strategies:
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "br",
            })
            url = f"{_NOMINATIM_URL}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as exc:
            logger.debug("Nominatim falhou para '%s': %s", query, exc)
        time.sleep(_DELAY_S)

    return None


def run_etl(
    uf: str | None = None,
    limit: int | None = None,
    batch_size: int = 100,
    resume: bool = True,
) -> None:
    client = TursoHTTP(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)

    # Cria tabela de destino
    logger.info("Criando tabela empresas_geo se não existir...")
    client.execute(_DDL_EMPRESAS_GEO)
    client.execute(_DDL_IDX_R8)
    client.execute(_DDL_IDX_R9)

    # Migração: adiciona colunas h3_r8_id / h3_r9_id se a tabela já existia sem elas
    for col, ddl in [
        ("h3_r8_id", "ALTER TABLE empresas_geo ADD COLUMN h3_r8_id TEXT"),
        ("h3_r9_id", "ALTER TABLE empresas_geo ADD COLUMN h3_r9_id TEXT"),
    ]:
        try:
            client.execute(ddl)
            logger.info("Coluna '%s' adicionada (migração).", col)
        except Exception:
            pass  # já existe

    # Carrega CNPJs já geocodificados (para resume)
    already_done: set[str] = set()
    if resume:
        rows = client.execute("SELECT cnpj FROM empresas_geo WHERE h3_r9_id IS NOT NULL")
        already_done = {r["cnpj"] for r in rows}
        logger.info("%d empresas já geocodificadas (serão puladas).", len(already_done))

    # Busca empresas a processar
    sql = "SELECT * FROM empresas_alvo"
    params = []
    if uf:
        sql += " WHERE uf = ?"
        params.append(uf.upper())
    if limit:
        sql += f" LIMIT {limit}"

    logger.info("Buscando empresas%s...", f" da UF {uf}" if uf else "")
    empresas = client.execute(sql, params)
    logger.info("%d empresas encontradas.", len(empresas))

    # Filtra as que já foram processadas
    to_process = [e for e in empresas if _build_cnpj(e) not in already_done]
    logger.info("%d empresas para geocodificar.", len(to_process))

    if not to_process:
        logger.info("Nada a fazer.")
        return

    ok_count = 0
    fail_count = 0
    batch: list[tuple] = []

    for i, empresa in enumerate(to_process, 1):
        cnpj = _build_cnpj(empresa)
        endereco = empresa.get("endereco", "")
        bairro = empresa.get("bairro", "")
        cep = empresa.get("cep", "")
        uf_emp = empresa.get("uf", "")

        result = _geocode_nominatim(endereco, bairro, cep, uf_emp)

        if result:
            lat, lng = result
            h3_r9_id = h3.latlng_to_cell(lat, lng, 9)
            h3_r8_id = h3.latlng_to_cell(lat, lng, 8)
            status = "ok"
            ok_count += 1
        else:
            lat, lng, h3_r9_id, h3_r8_id = None, None, None, None
            status = "failed"
            fail_count += 1

        batch.append((
            "INSERT INTO empresas_geo "
            "(cnpj, razao_social, nome_fantasia, cnae_principal, cnae_secundaria, "
            "endereco, bairro, cep, uf, municipio, telefone_1, email, "
            "lat, lng, h3_r8_id, h3_r9_id, h3_id, geocode_status, geocoded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(cnpj) DO UPDATE SET lat=excluded.lat, lng=excluded.lng, "
            "h3_r8_id=excluded.h3_r8_id, h3_r9_id=excluded.h3_r9_id, "
            "h3_id=excluded.h3_r9_id, "
            "geocode_status=excluded.geocode_status, geocoded_at=excluded.geocoded_at",
            [cnpj, empresa.get("razao_social"), empresa.get("nome_fantasia"),
             empresa.get("cnae_principal"), empresa.get("cnae_secundaria"),
             endereco, bairro, cep, uf_emp, empresa.get("municipio"),
             empresa.get("telefone_1"), empresa.get("email"),
             lat, lng, h3_r8_id, h3_r9_id, h3_r9_id, status, datetime.utcnow().isoformat()],
        ))

        # Flush batch
        if len(batch) >= batch_size:
            client.execute_many([(sql, args) for sql, args in batch])
            logger.info("[%d/%d] Lote salvo. OK=%d FAIL=%d", i, len(to_process), ok_count, fail_count)
            batch = []

        # Progress
        if i % 10 == 0:
            logger.info("[%d/%d] OK=%d FAIL=%d", i, len(to_process), ok_count, fail_count)

    # Flush restante
    if batch:
        client.execute_many([(sql, args) for sql, args in batch])

    logger.info("\n%s", "=" * 50)
    logger.info("ETL concluído: %d geocodificadas, %d falhas", ok_count, fail_count)
    logger.info("%s\n", "=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocodifica empresas_alvo → empresas_geo")
    parser.add_argument("--uf", default=None, help="Filtrar por UF (ex: SP)")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de empresas")
    parser.add_argument("--batch", type=int, default=100, help="Tamanho do lote")
    parser.add_argument("--no-resume", action="store_true", help="Reprocessar tudo")
    args = parser.parse_args()

    run_etl(
        uf=args.uf,
        limit=args.limit,
        batch_size=args.batch,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
