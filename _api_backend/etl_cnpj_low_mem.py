"""
etl_cnpj_low_mem.py
===================
Versão de baixo consumo de memória do ETL da Receita Federal.

Diferenças do etl_cnpj.py original:
- Processa 1 arquivo por vez (sem paralelismo)
- Faz streaming direto: baixa Empresas[i] → filtra → salva em disco (SQLite local)
  depois baixa Estabelecimentos[i] → join com SQLite local → grava no Turso
- Nunca acumula mais de ~50MB em RAM
- Suporta --resume: pula partes já processadas

Uso:
    python etl_cnpj_low_mem.py
    python etl_cnpj_low_mem.py --partes 0 1 2   # só partes específicas
    python etl_cnpj_low_mem.py --resume          # continua de onde parou
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# =============================================================================
# Configurações
# =============================================================================

CNAES_ALVO = {
    "5320", "5611", "9521", "9512", "9511",
    "4784", "4723", "9602", "4724", "9529", "4530",
}
SITUACAO_ATIVA = "02"
PORTES_ALVO = {"00", "01"}
UFS_ALVO = {"CE", "PE", "PB", "BA", "DF", "GO", "MG", "ES", "RJ", "SP", "PR", "AM", "SC", "RS"}

# Códigos de município da Receita Federal para os 134 municípios das DSs ativas
# Gerado por get_rf_municipios.py — não editar manualmente
MUNICIPIOS_CODIGOS_RF = {
    '0255', '0786', '0991', '1247', '1253', '1319', '1373', '1389', '1455', '1585',
    '1937', '1965', '1981', '2051', '2175', '2357', '2435', '2457', '2491', '2513',
    '2531', '2573', '2627', '2629', '2631', '2911', '2951', '3197', '3413', '3515',
    '3685', '3849', '4123', '4239', '4371', '4833', '4895', '5133', '5143', '5453',
    '5625', '5647', '5699', '5701', '5703', '5705', '5757', '5813', '5833', '5849',
    '5863', '5869', '5901', '6001', '6131', '6213', '6269', '6281', '6285', '6291',
    '6293', '6349', '6361', '6377', '6401', '6403', '6415', '6477', '6511', '6529',
    '6543', '6545', '6563', '6569', '6579', '6581', '6589', '6619', '6625', '6639',
    '6647', '6671', '6689', '6713', '6769', '6789', '6831', '6875', '6979', '7005',
    '7035', '7047', '7057', '7075', '7077', '7099', '7107', '7135', '7145', '7149',
    '7157', '7225', '7233', '7237', '7273', '7407', '7435', '7481', '7513', '7535',
    '7769', '7885', '8045', '8105', '8233', '8309', '8327', '8577', '8589', '8649',
    '8651', '8771', '8801', '8877', '8901', '8963', '9213', '9227', '9373', '9389',
    '9625', '9701', '9753', '9983',
}

NEXTCLOUD_BASE = "https://arquivos.receitafederal.gov.br"
CNPJ_PATH = "Dados/Cadastros/CNPJ"
NUM_PARTES = 10
MAX_RETRIES = 3
BATCH_SIZE = 200  # menor batch = menos RAM por vez

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PROPFIND_BODY = '<?xml version="1.0" encoding="utf-8" ?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>'

# Arquivo de progresso local
PROGRESS_FILE = Path("etl_progress.txt")
# SQLite local para lookup de empresas (evita manter dict gigante em RAM)
EMPRESAS_DB = Path("empresas_lookup.db")


# =============================================================================
# Turso
# =============================================================================

class TursoClient:
    MAX_RETRIES = 5
    BACKOFF_BASE = 2.0

    def __init__(self):
        url = os.environ["TURSO_URL"].replace("libsql://", "https://")
        self.base = url + "/v2/pipeline"
        self.headers = {
            "Authorization": f"Bearer {os.environ['TURSO_TOKEN']}",
            "Content-Type": "application/json",
        }

    def _post_with_retry(self, payload: dict, timeout: int) -> dict:
        """POST com retry automático em caso de ConnectionError ou 5xx."""
        last_exc = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                r = requests.post(self.base, headers=self.headers, json=payload, timeout=timeout)
                r.raise_for_status()
                return r.json()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
                wait = self.BACKOFF_BASE ** attempt
                print(f"  [Turso] Conexão perdida (tentativa {attempt}/{self.MAX_RETRIES}). Aguardando {wait:.0f}s...", flush=True)
                time.sleep(wait)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code >= 500:
                    last_exc = e
                    wait = self.BACKOFF_BASE ** attempt
                    print(f"  [Turso] Erro {e.response.status_code} (tentativa {attempt}/{self.MAX_RETRIES}). Aguardando {wait:.0f}s...", flush=True)
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"Turso: falha após {self.MAX_RETRIES} tentativas.") from last_exc

    def execute(self, sql: str, params: list = None) -> list:
        req = {"type": "execute", "stmt": {"sql": sql}}
        if params:
            req["stmt"]["args"] = [
                {"type": "null"} if p is None else {"type": "text", "value": str(p)}
                for p in params
            ]
        data = self._post_with_retry({"requests": [req, {"type": "close"}]}, timeout=30)
        result = data["results"][0]
        if result.get("type") == "error":
            raise RuntimeError(result.get("error", {}).get("message", "unknown"))
        inner = result.get("response", {}).get("result", {})
        cols = [c["name"] for c in inner.get("cols", [])]
        return [dict(zip(cols, row)) for row in inner.get("rows", [])]

    def batch(self, stmts: list[tuple]) -> None:
        reqs = []
        for sql, params in stmts:
            req = {"type": "execute", "stmt": {"sql": sql}}
            if params:
                req["stmt"]["args"] = [
                    {"type": "null"} if p is None else {"type": "text", "value": str(p)}
                    for p in params
                ]
            reqs.append(req)
        reqs.append({"type": "close"})
        self._post_with_retry({"requests": reqs}, timeout=60)


# =============================================================================
# Receita Federal
# =============================================================================

def obter_token_e_periodo() -> tuple[str, str]:
    r = requests.get(NEXTCLOUD_BASE, headers=HEADERS, timeout=15, allow_redirects=True)
    r.raise_for_status()
    for text in [r.url, r.text]:
        m = re.search(r"/s/([A-Za-z0-9]{10,25})", text)
        if m:
            token = m.group(1)
            break
    else:
        raise RuntimeError("Token não encontrado.")

    dav_url = f"{NEXTCLOUD_BASE}/public.php/dav/files/{token}/{CNPJ_PATH}/"
    r2 = requests.request("PROPFIND", dav_url, data=PROPFIND_BODY,
                          headers={**HEADERS, "Depth": "1", "Content-Type": "application/xml"}, timeout=15)
    r2.raise_for_status()
    periodos = sorted(re.findall(r"/(\d{4}-\d{2})/", r2.text))
    if not periodos:
        raise RuntimeError("Nenhum período encontrado.")
    periodo = periodos[-1]
    print(f"Token: {token} | Período: {periodo}")
    return token, periodo


def _fmt_size(b: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def baixar_zip_para_temp(token: str, period: str, tipo: str, parte: int) -> str:
    url = f"{NEXTCLOUD_BASE}/public.php/dav/files/{token}/{CNPJ_PATH}/{period}/{tipo}{parte}.zip"
    label = f"{tipo}{parte}"
    for tentativa in range(1, MAX_RETRIES + 1):
        tmp_path = None
        try:
            r = requests.get(url, headers=HEADERS, timeout=600, stream=True)
            r.raise_for_status()
            total_size = int(r.headers.get("Content-Length", 0))

            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp_path = tmp.name
                with tqdm(
                    total=total_size or None,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"  {label}",
                    ncols=80,
                    leave=True,
                ) as bar:
                    for chunk in r.iter_content(chunk_size=2 * 1024 * 1024):
                        tmp.write(chunk)
                        bar.update(len(chunk))

            return tmp_path

        except Exception as e:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if tentativa == MAX_RETRIES:
                raise
            wait = 2 ** tentativa
            print(f"  [{label}] Erro: {e}. Aguardando {wait}s...", flush=True)
            time.sleep(wait)


def iter_csv_from_zip(zip_path: str):
    with zipfile.ZipFile(zip_path) as z:
        with z.open(z.namelist()[0]) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="latin-1"), delimiter=";")
            yield from reader


# =============================================================================
# SQLite local para lookup de empresas
# =============================================================================

def init_lookup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(EMPRESAS_DB))
    conn.execute("CREATE TABLE IF NOT EXISTS emp (cnpj_basico TEXT PRIMARY KEY, razao_social TEXT, porte TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cnpj ON emp(cnpj_basico)")
    conn.commit()
    return conn


def processar_empresas_parte(token: str, period: str, parte: int, conn: sqlite3.Connection) -> int:
    """Baixa Empresas{parte}.zip e insere no SQLite local. Retorna contagem."""
    zip_path = baixar_zip_para_temp(token, period, "Empresas", parte)
    count = 0
    batch = []
    try:
        for row in iter_csv_from_zip(zip_path):
            if len(row) < 6:
                continue
            porte = row[5].strip()
            if porte not in PORTES_ALVO:
                continue
            batch.append((row[0].strip(), row[1].strip(), porte))
            if len(batch) >= 5000:
                conn.executemany("INSERT OR REPLACE INTO emp VALUES (?,?,?)", batch)
                conn.commit()
                count += len(batch)
                batch = []
        if batch:
            conn.executemany("INSERT OR REPLACE INTO emp VALUES (?,?,?)", batch)
            conn.commit()
            count += len(batch)
    finally:
        os.unlink(zip_path)
    print(f"  [Empresas{parte}] {count:,} registros no lookup.", flush=True)
    return count


def processar_estabelecimentos_parte(
    token: str, period: str, parte: int,
    conn: sqlite3.Connection, turso: TursoClient
) -> int:
    """Baixa Estabelecimentos{parte}.zip, faz join com SQLite e grava no Turso."""
    zip_path = baixar_zip_para_temp(token, period, "Estabelecimentos", parte)
    count = 0
    batch = []

    try:
        for row in iter_csv_from_zip(zip_path):
            if len(row) < 30:
                continue
            situacao = row[5].strip()
            uf = row[19].strip()
            cnae_pri = row[11].strip()
            cnae_sec = row[12].strip()

            if situacao != SITUACAO_ATIVA:
                continue
            if uf not in UFS_ALVO:
                continue
            # Filtro de município (código RF de 4 dígitos)
            municipio = row[20].strip().zfill(4)
            if municipio not in MUNICIPIOS_CODIGOS_RF:
                continue

            cnae_match = any(cnae_pri.startswith(c) for c in CNAES_ALVO)
            if not cnae_match:
                cnae_match = any(
                    sec.startswith(c)
                    for sec in cnae_sec.split(",")
                    for c in CNAES_ALVO
                )
            if not cnae_match:
                continue

            cnpj_basico = row[0].strip()
            empresa = conn.execute(
                "SELECT razao_social, porte FROM emp WHERE cnpj_basico=?", (cnpj_basico,)
            ).fetchone()
            if not empresa:
                continue

            razao_social, porte = empresa
            ddd1, tel1 = row[21].strip(), row[22].strip()
            ddd2, tel2 = row[23].strip(), row[24].strip()
            fones = [(d + t) for d, t in [(ddd1, tel1), (ddd2, tel2)] if d or t]

            endereco = " ".join(filter(None, [row[13].strip(), row[14].strip(), row[15].strip(), row[16].strip()]))

            batch.append((
                "INSERT INTO empresas_alvo "
                "(cnpj_basico, cnpj_ordem, cnpj_dv, razao_social, nome_fantasia, porte, "
                "cnae_principal, cnae_secundaria, endereco, bairro, cep, uf, municipio, "
                "telefone_1, telefone_2, email) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [cnpj_basico, row[1].strip(), row[2].strip(), razao_social, row[4].strip(), porte,
                 cnae_pri, cnae_sec, endereco, row[17].strip(), row[18].strip(),
                 uf, row[20].strip(),
                 fones[0] if fones else "", fones[1] if len(fones) > 1 else "", row[27].strip()],
            ))

            if len(batch) >= BATCH_SIZE:
                turso.batch(batch)
                count += len(batch)
                print(f"  [Estab{parte}] {count:,} gravados no Turso...", flush=True)
                batch = []

        if batch:
            turso.batch(batch)
            count += len(batch)

    finally:
        os.unlink(zip_path)

    print(f"  [Estabelecimentos{parte}] {count:,} registros gravados.", flush=True)
    return count


# =============================================================================
# Progresso
# =============================================================================

def load_progress() -> set[str]:
    if not PROGRESS_FILE.exists():
        return set()
    return set(PROGRESS_FILE.read_text().strip().splitlines())


def save_progress(key: str) -> None:
    with open(PROGRESS_FILE, "a") as f:
        f.write(key + "\n")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partes", nargs="+", type=int, default=list(range(NUM_PARTES)))
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    args = parser.parse_args()

    token, period = obter_token_e_periodo()
    turso = TursoClient()

    # Cria tabela no Turso
    print("Criando tabela empresas_alvo...")
    turso.execute("""CREATE TABLE IF NOT EXISTS empresas_alvo (
        cnpj_basico TEXT, cnpj_ordem TEXT, cnpj_dv TEXT,
        razao_social TEXT, nome_fantasia TEXT, porte TEXT,
        cnae_principal TEXT, cnae_secundaria TEXT,
        endereco TEXT, bairro TEXT, cep TEXT, uf TEXT, municipio TEXT,
        telefone_1 TEXT, telefone_2 TEXT, email TEXT)""")

    progress = load_progress() if args.resume else set()
    if not args.resume:
        PROGRESS_FILE.unlink(missing_ok=True)
        EMPRESAS_DB.unlink(missing_ok=True)
        turso.execute("DELETE FROM empresas_alvo")
        print("Dados anteriores removidos.")

    # SQLite local para lookup
    conn = init_lookup_db()

    partes = args.partes
    total_empresas = 0
    total_estab = 0

    # Fase 1: baixar todas as partes de Empresas
    print(f"\n=== FASE 1: Empresas ({len(partes)} partes) ===")
    for parte in partes:
        key = f"empresas_{parte}"
        if key in progress:
            print(f"  [Empresas{parte}] Já processado, pulando.")
            continue
        n = processar_empresas_parte(token, period, parte, conn)
        total_empresas += n
        save_progress(key)

    print(f"\nTotal no lookup: {conn.execute('SELECT COUNT(*) FROM emp').fetchone()[0]:,} empresas")

    # Fase 2: baixar todas as partes de Estabelecimentos
    print(f"\n=== FASE 2: Estabelecimentos ({len(partes)} partes) ===")
    for parte in partes:
        key = f"estab_{parte}"
        if key in progress:
            print(f"  [Estabelecimentos{parte}] Já processado, pulando.")
            continue
        n = processar_estabelecimentos_parte(token, period, parte, conn, turso)
        total_estab += n
        save_progress(key)

    conn.close()

    # Verifica resultado final
    result = turso.execute("SELECT COUNT(*) as n FROM empresas_alvo")
    final_count = result[0]["n"] if result else "?"
    print(f"\n{'='*50}")
    print(f"ETL concluído!")
    print(f"  Empresas no lookup: {total_empresas:,}")
    print(f"  Registros no Turso: {final_count}")
    print(f"{'='*50}")

    # Limpa arquivos temporários
    EMPRESAS_DB.unlink(missing_ok=True)
    PROGRESS_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
