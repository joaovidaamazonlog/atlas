"""
cnpj_lookup.py
==============
Busca empresas candidatas a parceiro logístico no banco de dados CNPJ
da Receita Federal do Brasil.

Para cada slot ideal sem parceiro vinculado (is_open=True), consulta o
banco SQLite com base nos CEPs cobertos pelo slot e retorna empresas que
atendam aos critérios operacionais de um hub de entrega last-mile.

Critérios de busca
------------------
- CEP presente na lista de CEPs do slot (allocations → hex_to_ceps)
- CNAE principal OU secundário iniciado com "5320" (Atividades de Correio
  e outras atividades de entrega)
- Situação cadastral = "02" (Ativa)
- Data de início de atividade < 01/01/2024 (empresa com histórico mínimo)

Saída
-----
Dict[slot_id, List[ProspectCandidate]] — candidatos por slot em aberto.

Uso
---
    from phase2_ideal_supply import load_ideal_supply
    from load_packages import load_packages
    from cnpj_lookup import run_cnpj_lookup

    supply = load_ideal_supply()
    pkg    = load_packages()
    result = run_cnpj_lookup(supply, pkg)
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from load_packages import PackageData
from models import Config, ProspectCandidate
from phase2_ideal_supply import IdealSupplyResult

# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------

CNAE_PREFIX        = "5320"          # Atividades de entrega / correio
SITUACAO_ATIVA     = "02"
DATA_CORTE         = "20260101"       # formato YYYYMMDD (igual ao banco)
PORTE_DESCRICAO    = {"00": "Não informado", "01": "Micro Empresa", "03": "Empresa de Pequeno Porte", "05": "EPP"}

# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class CnpjLookupResult:
    """Output do cnpj_lookup — candidatos por slot."""

    # slot_id -> lista de candidatos encontrados
    candidates_by_slot: Dict[str, List[ProspectCandidate]] = field(
        default_factory=dict
    )

    @property
    def all_candidates(self) -> List[ProspectCandidate]:
        return [c for cs in self.candidates_by_slot.values() for c in cs]

    @property
    def total_candidates(self) -> int:
        return len(self.all_candidates)

    def candidates_for_station(self, station_code: str) -> List[ProspectCandidate]:
        return [c for c in self.all_candidates if c.station_code == station_code]

    def candidates_for_territory(self, territory_id: str) -> List[ProspectCandidate]:
        return [c for c in self.all_candidates if c.territory_id == territory_id]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _ceps_for_open_slot(slot, pkg: PackageData) -> List[str]:
    """Retorna lista de CEPs cobertos pelo slot (via allocations → hex_to_ceps)."""
    ceps: Set[str] = set()
    for alloc in slot.allocations:
        ceps.update(pkg.hex_to_ceps.get(alloc.hex_id, set()))
    return sorted(ceps)


def _build_sql(ceps: List[str]) -> tuple:
    """
    Monta a query SQL e os parâmetros para buscar candidatos por lista de CEPs.

    Estrutura do JOIN:
        estabelecimentos (e) — dados do endereço, CNAE, situação
        empresas (emp)       — razão social, porte
        socios (s)           — responsável (primeiro sócio por cnpj_basico)

    Filtros:
        - e.cep IN (lista de CEPs do slot)
        - e.situacao_cadastral = '02' (Ativa)
        - e.data_inicio_atividade < '20240101'
        - CNAE principal OU secundário começa com '5320'
    """
    if not ceps:
        return "", []

    placeholders = ",".join("?" * len(ceps))

    sql = f"""
        SELECT
            e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv  AS cnpj,
            emp.razao_social,
            emp.porte_empresa,
            e.tipo_logradouro,
            e.logradouro,
            e.numero,
            e.complemento,
            e.bairro,
            e.cep,
            e.uf,
            e.municipio,
            e.ddd_1 || e.telefone_1                      AS telefone_1,
            CASE WHEN e.telefone_2 != '' AND e.telefone_2 IS NOT NULL
                 THEN e.ddd_2 || e.telefone_2
                 ELSE ''
            END                                          AS telefone_2,
            e.email,
            e.cnae_fiscal_principal,
            COALESCE(
                (SELECT s.nome_socio
                 FROM socios s
                 WHERE s.cnpj_basico = e.cnpj_basico
                 ORDER BY s.qualificacao_socio
                 LIMIT 1),
                ''
            )                                            AS responsavel
        FROM estabelecimentos e
        JOIN empresas emp ON emp.cnpj_basico = e.cnpj_basico
        WHERE
            e.cep IN ({placeholders})
            AND e.situacao_cadastral = ?
            AND e.data_inicio_atividade < ?
            AND (
                e.cnae_fiscal_principal LIKE ?
                OR e.cnae_fiscal_secundaria LIKE ?
            )
        ORDER BY emp.razao_social
    """

    # Parâmetros: CEPs + situação + data + 4 padrões CNAE
    cnae_like_exact  = f"{CNAE_PREFIX}%"   # principal começa com 5320
    cnae_like_start  = f"{CNAE_PREFIX}%"   # secundário: começa com 5320 (primeiro da lista)
    cnae_like_middle = f",{CNAE_PREFIX}%"  # secundário: após vírgula
    cnae_like_any    = f"%,{CNAE_PREFIX}%" # secundário: em qualquer posição

    params = (
        list(ceps)
        + [SITUACAO_ATIVA, DATA_CORTE]
        + [cnae_like_exact, cnae_like_start, cnae_like_middle, cnae_like_any]
    )

    return sql, params


def _row_to_candidate(
    row: tuple,
    slot_id: str,
    territory_id: str,
    station_code: str,
) -> ProspectCandidate:
    """Converte uma linha do resultado SQL em ProspectCandidate."""
    (
        cnpj, razao_social, porte, tipo_log, logradouro, numero,
        complemento, bairro, cep, uf, municipio,
        tel1, tel2, email, cnae_principal, responsavel,
    ) = row

    return ProspectCandidate(
        cnpj            = str(cnpj or "").strip(),
        razao_social    = str(razao_social or "").strip(),
        porte_empresa   = str(porte or "01").strip(),
        tipo_logradouro = str(tipo_log or "").strip(),
        logradouro      = str(logradouro or "").strip(),
        numero          = str(numero or "").strip(),
        complemento     = str(complemento or "").strip(),
        bairro          = str(bairro or "").strip(),
        cep             = str(cep or "").strip(),
        uf              = str(uf or "").strip(),
        municipio       = str(municipio or "").strip(),
        telefone_1      = str(tel1 or "").strip(),
        telefone_2      = str(tel2 or "").strip(),
        email           = str(email or "").strip(),
        cnae_principal  = str(cnae_principal or "").strip(),
        responsavel     = str(responsavel or "").strip(),
        slot_id         = slot_id,
        territory_id    = territory_id,
        station_code    = station_code,
    )


# ---------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ---------------------------------------------------------------------------

def run_cnpj_lookup(
    supply: IdealSupplyResult,
    pkg: PackageData,
    db_path: str = None,
    stations: Optional[List[str]] = None,
) -> CnpjLookupResult:
    """
    Busca empresas candidatas a parceiro para cada slot ideal sem match.

    Parâmetros
    ----------
    supply    : IdealSupplyResult   Output da Fase 2 (com matched_partner_id preenchido).
    pkg       : PackageData         Para resolver hex → CEPs.
    db_path   : str, opcional       Caminho do banco SQLite. Default: Config.CNPJ_DB_PATH.
    stations  : list, opcional      Filtrar bases. Default: todas.

    Retorna
    -------
    CnpjLookupResult com candidates_by_slot.
    """
    resolved_db = db_path or getattr(Config, "CNPJ_DB_PATH", None)
    if not resolved_db:
        raise ValueError(
            "Caminho do banco CNPJ não configurado. "
            "Defina Config.CNPJ_DB_PATH em config.py ou passe db_path."
        )

    db_file = Path(resolved_db)
    if not db_file.exists():
        raise FileNotFoundError(f"Banco CNPJ não encontrado: {db_file}")

    # Filtrar slots em aberto
    open_slots = [s for s in supply.all_slots if s.is_open]
    if stations:
        open_slots = [s for s in open_slots if s.station_code in stations]

    if not open_slots:
        print("  Nenhum slot em aberto para busca CNPJ.")
        return CnpjLookupResult()

    print(f"\n{'='*60}")
    print(f"  CNPJ LOOKUP — Busca de candidatos")
    print(f"  Banco: {db_file.name}")
    print(f"  Slots em aberto: {len(open_slots)}")
    print(f"  CNAE prefixo: {CNAE_PREFIX} | Situação: Ativa | Início < 01/01/2026")
    print(f"{'='*60}")

    result = CnpjLookupResult()
    conn   = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    try:
        cur = conn.cursor()
        total_found = 0

        for slot in open_slots:
            ceps = _ceps_for_open_slot(slot, pkg)
            if not ceps:
                result.candidates_by_slot[slot.slot_id] = []
                continue

            sql, params = _build_sql(ceps)
            try:
                cur.execute(sql, params)
                rows = cur.fetchall()
            except sqlite3.Error as e:
                print(f"  ERR [{slot.slot_id}] SQL falhou: {e}")
                result.candidates_by_slot[slot.slot_id] = []
                continue

            candidates = [
                _row_to_candidate(
                    tuple(row),
                    slot_id      = slot.slot_id,
                    territory_id = slot.bucket_id,
                    station_code = slot.station_code,
                )
                for row in rows
            ]

            result.candidates_by_slot[slot.slot_id] = candidates
            total_found += len(candidates)

            if candidates:
                print(f"  [{slot.slot_id}] {len(ceps)} CEPs → {len(candidates)} candidatos")

    finally:
        conn.close()

    print(f"\n  Total: {total_found} candidatos em {len(open_slots)} slots")
    print(f"{'='*60}\n")

    return result
