"""
etl_geocode_empresas.py
=======================
ETL que geocodifica as empresas da tabela `empresas_alvo` via Nominatim
(instância local Docker, sem rate limiting) e persiste o resultado em
`empresas_geo` com lat, lng e h3_id (resolução 9).

Uso:
    python -m geo_intelligence.etl_geocode_empresas [--uf SP] [--limit 1000] [--batch 50]

Parâmetros:
    --uf      Filtrar por UF (ex: SP). Padrão: todas.
    --limit   Máximo de empresas a processar. Padrão: sem limite.
    --batch   Tamanho do lote para upsert. Padrão: 100.
    --no-resume  Reprocessar tudo (ignora empresas já geocodificadas).
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone

import h3

from geo_intelligence.local_writer import LocalWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_USER_AGENT = "atlas-geo-intelligence/1.0 (geocode empresas local)"

_NOMINATIM_LOCAL_URL_DEFAULT = "http://localhost:8080"


def _get_nominatim_url() -> str:
    url = os.environ.get("NOMINATIM_LOCAL_URL", "")
    if not url:
        logger.warning(
            "NOMINATIM_LOCAL_URL not set — using default %s",
            _NOMINATIM_LOCAL_URL_DEFAULT,
        )
        return _NOMINATIM_LOCAL_URL_DEFAULT
    return url.rstrip("/")


def _geocode_local_nominatim(
    nominatim_base_url: str,
    endereco: str,
    bairro: str,
    cep: str,
    uf: str,
) -> tuple[float, float] | None:
    """
    Geocodifica um endereço via instância local do Nominatim.
    Tenta 3 estratégias em ordem de precisão:
      1. Endereço completo: "RUA X 123, BAIRRO, CEP, Brasil"
      2. Só CEP: "CEP, Brasil"
      3. Bairro + UF: "BAIRRO, UF, Brasil"
    Sem rate limiting (instância local).
    """
    search_url = f"{nominatim_base_url}/search"
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
            url = f"{search_url}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as exc:
            logger.debug("Nominatim falhou para '%s': %s", query, exc)

    return None


def sync_empresas_alvo(writer: LocalWriter, turso_client) -> dict:
    """
    Downloads all empresas_alvo records from Turso and upserts them into
    the local empresas_alvo table in SQLite.

    Returns {"inserted": int, "updated": int, "total": int}.
    Uses pagination (PAGE_SIZE=5000) to avoid Turso query timeouts.
    """
    PAGE_SIZE = 5000
    offset = 0
    total = 0
    inserted = 0
    updated = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    # Get existing CNPJs from local SQLite to distinguish inserts vs updates
    conn = writer._conn
    existing_cnpjs: set[str] = set()
    try:
        cur = conn.execute("SELECT cnpj FROM empresas_alvo")
        existing_cnpjs = {row[0] for row in cur.fetchall()}
    except Exception as exc:
        logger.warning("Não foi possível carregar CNPJs existentes: %s", exc)

    while True:
        sql = f"SELECT * FROM empresas_alvo LIMIT {PAGE_SIZE} OFFSET {offset}"
        logger.info("Buscando página offset=%d (PAGE_SIZE=%d)...", offset, PAGE_SIZE)
        try:
            rows = turso_client.execute(sql)
        except Exception as exc:
            logger.error("Erro ao buscar empresas_alvo do Turso (offset=%d): %s", offset, exc)
            raise

        if not rows:
            break

        # Add synced_at timestamp to each row
        for row in rows:
            row["synced_at"] = now_iso

        # Count inserts vs updates
        for row in rows:
            cnpj = row.get("cnpj")
            if cnpj in existing_cnpjs:
                updated += 1
            else:
                inserted += 1
                existing_cnpjs.add(cnpj)

        writer.upsert_empresas_alvo(rows)
        total += len(rows)
        logger.info("Página offset=%d: %d registros processados (total=%d).", offset, len(rows), total)

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    summary = {"inserted": inserted, "updated": updated, "total": total}
    logger.info(
        "sync_empresas_alvo concluído: inserted=%d updated=%d total=%d",
        inserted,
        updated,
        total,
    )
    return summary


def run_etl(
    uf: str | None = None,
    limit: int | None = None,
    batch_size: int = 100,
    resume: bool = True,
) -> None:
    writer = LocalWriter()
    nominatim_base_url = _get_nominatim_url()

    # Determine db_path from writer's connection
    db_path = writer._conn.execute("PRAGMA database_list").fetchone()[2]

    # Carrega CNPJs já geocodificados (para resume)
    already_done: set[str] = set()
    if resume:
        try:
            rows = writer._conn.execute(
                "SELECT cnpj FROM empresas_geo WHERE h3_r9_id IS NOT NULL"
            ).fetchall()
            already_done = {row[0] for row in rows}
            logger.info("%d empresas já geocodificadas (serão puladas).", len(already_done))
        except Exception as exc:
            logger.warning("Não foi possível carregar CNPJs geocodificados: %s", exc)

    # Busca empresas a processar diretamente do SQLite local
    sql = "SELECT * FROM empresas_alvo"
    params: list = []
    if uf:
        sql += " WHERE uf = ?"
        params.append(uf.upper())
    if limit:
        sql += f" LIMIT {limit}"

    logger.info("Buscando empresas%s do SQLite local...", f" da UF {uf}" if uf else "")
    try:
        cur = writer._conn.execute(sql, params)
        cur.row_factory = None
        cols = [desc[0] for desc in cur.description]
        empresas = [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as exc:
        logger.error("Erro ao buscar empresas_alvo do SQLite: %s", exc)
        raise

    logger.info("%d empresas encontradas.", len(empresas))

    # Filtra as que já foram processadas
    to_process = [e for e in empresas if e.get("cnpj") not in already_done]
    logger.info("%d empresas para geocodificar.", len(to_process))

    if not to_process:
        logger.info("Nada a fazer.")
        return

    ok_count = 0
    fail_count = 0
    batch: list[dict] = []

    for i, empresa in enumerate(to_process, 1):
        cnpj = empresa.get("cnpj", "")
        endereco = empresa.get("endereco", "") or ""
        bairro = empresa.get("bairro", "") or ""
        cep = empresa.get("cep", "") or ""
        uf_emp = empresa.get("uf", "") or ""

        result = _geocode_local_nominatim(nominatim_base_url, endereco, bairro, cep, uf_emp)

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

        batch.append({
            "cnpj": cnpj,
            "razao_social": empresa.get("razao_social"),
            "nome_fantasia": empresa.get("nome_fantasia"),
            "cnae_principal": empresa.get("cnae_principal"),
            "cnae_secundaria": empresa.get("cnae_secundaria"),
            "endereco": endereco,
            "bairro": bairro,
            "cep": cep,
            "uf": uf_emp,
            "municipio": empresa.get("municipio"),
            "telefone_1": empresa.get("telefone_1"),
            "email": empresa.get("email"),
            "lat": lat,
            "lng": lng,
            "h3_r8_id": h3_r8_id,
            "h3_r9_id": h3_r9_id,
            "h3_id": h3_r9_id,
            "geocode_status": status,
            "geocoded_at": datetime.now(timezone.utc).isoformat(),
        })

        # Flush batch
        if len(batch) >= batch_size:
            writer.upsert_empresas_geo(batch)
            logger.info("[%d/%d] Lote salvo. OK=%d FAIL=%d", i, len(to_process), ok_count, fail_count)
            batch = []

        # Progress
        if i % 10 == 0:
            logger.info("[%d/%d] OK=%d FAIL=%d", i, len(to_process), ok_count, fail_count)

    # Flush restante
    if batch:
        writer.upsert_empresas_geo(batch)

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
