"""
phase4_webleads.py
==================
Fase 4 — Qualificacao e roteamento de web leads.

Responsabilidade
----------------
- Receber os web leads separados pelo load_partners (leadSource = Website
  Pardot Form, status = New).
- Localizar o hex H3 de cada lead a partir do CEP (busca exata → prefixo).
- Identificar o territorio e a base correspondentes via territories_index.
- Encontrar o Account Manager (ADE) responsavel pelo territorio.
- Classificar o lead com uma decision acionavel.
- Retornar WebleadResult para consumo da Fase 5 (reports + CSV).

Resolucao de CEP → hex (dois passos, igual ao original)
--------------------------------------------------------
Passo 1 — Busca exata:  CEP (8 digitos) presente em hex_to_ceps[hex].
Passo 2 — Prefixo:      Se nao encontrado, usa os 5 primeiros digitos
          e elege o hex que tiver mais CEPs com aquele prefixo.

Identificacao de territorio
----------------------------
Com o hex resolvido, consulta hex_to_territory (TerritoriesResult) para
obter o territory_id. Entao consulta territories_index para obter
station_code e demais metadados.

Account Manager (owner_id)
--------------------------
Config.ADES_ACCOUNT_MANAGERS e uma lista de dicts:
    [{"salesforce_id": "...", "buckets": ["DSP2_T01", "DSP2_T02", ...]}, ...]

Nota de migracao: o sistema anterior usava "DSP2_bucket-1". Se o seu
config ainda usa o formato antigo, atualize os nomes para o novo padrao
"DSP2_T01" ou use o parametro `legacy_bucket_names=True` que tenta ambos.

Decisions possiveis
-------------------
    "Qualificar lead"                      CEP valido, hex e territorio encontrados
    "CEP invalido"                         CEP nao tem exatamente 8 digitos
    "CEP nao mapeado - analisar manualmente"  CEP valido mas nao existe no indice
    "Territorio nao identificado"          Hex encontrado mas fora de qualquer territorio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import h3
import pandas as pd

from load_packages import PackageData
from load_partners import PartnerData
from models import Config, PartnerMetrics, TerritoriesResult


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class WebleadResult:
    """Output da Fase 4."""

    leads: List[PartnerMetrics] = field(default_factory=list)

    @property
    def qualified(self) -> List[PartnerMetrics]:
        return [l for l in self.leads if l.decision == "Qualificar lead"]

    @property
    def unmapped(self) -> List[PartnerMetrics]:
        return [l for l in self.leads if l.decision != "Qualificar lead"]

    def leads_for_station(self, station_code: str) -> List[PartnerMetrics]:
        return [l for l in self.leads if l.station_code == station_code]

    def leads_for_territory(self, territory_id: str) -> List[PartnerMetrics]:
        return [l for l in self.leads if l.cluster_name == territory_id]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _find_hex_by_cep(
    cep: str,
    hex_to_ceps: Dict[str, Set[str]],
    demand_map_all: Optional[Dict[str, int]] = None,
) -> Tuple[Optional[str], str]:
    """
    Localiza o hex mais apropriado para o CEP fornecido.

    Retorna (hex_id, status) onde status é:
        "ok"          — hex encontrado
        "invalid"     — CEP não tem exatamente 8 dígitos
        "not_mapped"  — CEP válido mas não existe no índice

    Busca: encontra todos os hexes que contêm o CEP e retorna o de maior
    demanda (ou o primeiro, se demand_map_all não disponível).
    Isso corresponde ao hex onde o CEP "se repete mais vezes" na grade.
    """
    # Limpar e validar: remover não-dígitos
    cep_clean = "".join(c for c in str(cep or "") if c.isdigit())

    if len(cep_clean) != 8:
        return None, "invalid"

    # Buscar todos os hexes que contêm este CEP
    matching = [h for h, ceps in hex_to_ceps.items() if cep_clean in ceps]

    if not matching:
        return None, "not_mapped"

    # Se múltiplos hexes contêm o CEP, escolher o de maior demanda
    if len(matching) == 1:
        return matching[0], "ok"

    if demand_map_all:
        best = max(matching, key=lambda h: demand_map_all.get(h, 0))
    else:
        best = matching[0]

    return best, "ok"


def _get_account_manager(
    station_code: str,
    territory_id: str,
    legacy_bucket_names: bool = False,
) -> Optional[str]:
    """
    Retorna o salesforce_id do ADE responsavel pelo territorio.

    Suporta os formatos de territory_id:
        Novo setup:   "DSP2_bucket-01"
        Phase1:       "DSP2_T01"
        Legado:       "DSP2_bucket-1"  (sem zero-padding)
    """
    managers = Config.ADES_ACCOUNT_MANAGERS
    if not managers:
        return None

    keys_to_try = [territory_id]
    if legacy_bucket_names:
        # Tentar extrair sequência e gerar chaves alternativas
        for sep in ("_bucket-", "_T"):
            if sep in territory_id:
                try:
                    seq = int(territory_id.split(sep)[-1])
                    keys_to_try.append(f"{station_code}_bucket-{seq}")
                    keys_to_try.append(f"{station_code}_T{seq:02d}")
                except (ValueError, IndexError):
                    pass
                break

    for manager in managers:
        buckets = manager.get("buckets", [])
        for key in keys_to_try:
            if key in buckets:
                return manager.get("salesforce_id")

    return None


def _ctl_name_for_territory(territory_id: str) -> str:
    """
    Retorna o nome do CTL a partir do territory_id.

    Suporta formatos:
        "DSP2_T01"       → sequência = 1
        "DSP2_bucket-01" → sequência = 1
    """
    for sep in ("_bucket-", "_T"):
        if sep in territory_id:
            try:
                seq = int(territory_id.split(sep)[-1]) - 1
                return f"CTL-{chr(65 + (seq // 5))}"
            except (ValueError, IndexError):
                break
    return "CTL-A"


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def run_phase4(
    partner_data: PartnerData,
    territories: TerritoriesResult,
    pkg: PackageData,
    legacy_bucket_names: bool = False,
) -> WebleadResult:
    """
    Executa a Fase 4: qualificacao e roteamento de web leads.

    Decisoes
    --------
    CEP sem 8 digitos                  → "CEP invalido"
    CEP com 8 digitos, nao encontrado  → "CEP nao mapeado - analisar manualmente"
    Hex encontrado, sem territorio     → "Territorio nao identificado"
    Hex + territorio encontrados       → "Qualificar lead"

    O CSV de saida contem TODOS os webleads carregados, independente da decisao.
    """
    print(f"\n{'='*60}")
    print(f"  FASE 4 — QUALIFICACAO DE WEB LEADS")
    print(f"{'='*60}")

    df = partner_data.web_leads_df.copy()

    if df.empty:
        print("  Nenhum web lead encontrado.")
        return WebleadResult()

    print(f"  {len(df):,} web leads para processar...")

    # Mapa de demanda global para desempate de hex quando CEP aparece em múltiplos hexes
    demand_map_all: Dict[str, int] = {}
    for station in territories.stations:
        demand_map_all.update(pkg.demand_map(station))

    results: List[PartnerMetrics] = []
    n_qualified   = 0
    n_invalid_cep = 0
    n_not_mapped  = 0
    n_no_terr     = 0

    for _, row in df.iterrows():
        sfid         = str(row.get("salesforce_id", ""))
        partner_name = str(row.get("partner_name", ""))

        # Normalizar CEP da linha (remover não-dígitos, sem zfill aqui — validação é em _find_hex)
        raw_cep = str(row.get("zip_code", "") or row.get("zip_clean", "") or "")

        # ── 1. Resolver CEP → hex ─────────────────────────────────────────
        origin_hex, cep_status = _find_hex_by_cep(
            raw_cep, pkg.hex_to_ceps, demand_map_all
        )
        cep_clean = "".join(c for c in raw_cep if c.isdigit())

        if cep_status == "invalid":
            n_invalid_cep += 1
            results.append(PartnerMetrics(
                origin_hex    = None,
                station_code  = None,
                radius_s      = 0,
                capacity_s    = 0,
                entity_type   = "WEB_LEAD",
                status        = "New",
                partner_name  = partner_name,
                salesforce_id = sfid,
                zip_code      = cep_clean or raw_cep,
                decision      = "CEP invalido",
                lat           = float("nan"),
                lon           = float("nan"),
            ))
            continue

        if cep_status == "not_mapped":
            n_not_mapped += 1
            results.append(PartnerMetrics(
                origin_hex    = None,
                station_code  = None,
                radius_s      = 0,
                capacity_s    = 0,
                entity_type   = "WEB_LEAD",
                status        = "New",
                partner_name  = partner_name,
                salesforce_id = sfid,
                zip_code      = cep_clean,
                decision      = "CEP nao mapeado - analisar manualmente",
                lat           = float("nan"),
                lon           = float("nan"),
            ))
            continue

        # ── 2. Resolver hex → territorio ──────────────────────────────────
        territory_id = territories.hex_to_territory.get(origin_hex)
        lat, lon     = h3.cell_to_latlng(origin_hex)

        if not territory_id:
            n_no_terr += 1
            results.append(PartnerMetrics(
                origin_hex    = origin_hex,
                station_code  = None,
                radius_s      = 0,
                capacity_s    = 0,
                entity_type   = "WEB_LEAD",
                status        = "New",
                partner_name  = partner_name,
                salesforce_id = sfid,
                zip_code      = cep_clean,
                decision      = "Out of jurisdiction - analisar manualmente",
                lat           = lat,
                lon           = lon,
            ))
            continue

        # ── 3. Metadados do territorio ────────────────────────────────────
        t_meta       = territories.territory_index.get(territory_id, {})
        station_code = t_meta.get("station_code", "")
        bdm_cluster  = t_meta.get("bdm_cluster", Config.get_bdm_cluster(station_code))
        ctl_name     = _ctl_name_for_territory(territory_id)

        # ── 4. Account manager responsavel ───────────────────────────────
        owner_id = _get_account_manager(
            station_code=station_code,
            territory_id=territory_id,
            legacy_bucket_names=legacy_bucket_names,
        )

        n_qualified += 1
        results.append(PartnerMetrics(
            origin_hex    = origin_hex,
            station_code  = station_code,
            radius_s      = 0,
            capacity_s    = 0,
            entity_type   = "WEB_LEAD",
            status        = "New",
            partner_name  = partner_name,
            salesforce_id = sfid,
            zip_code      = cep_clean,
            cluster_name  = territory_id,
            ctl_name      = ctl_name,
            bdm_cluster   = bdm_cluster,
            owner_id      = owner_id,
            decision      = "Qualificar lead",
            lat           = lat,
            lon           = lon,
            bucket        = territory_id,
        ))

    print(f"  Qualificados:                       {n_qualified:>4}")
    print(f"  CEP invalido (< ou > 8 digitos):    {n_invalid_cep:>4}")
    print(f"  CEP nao mapeado:                    {n_not_mapped:>4}")
    print(f"  Territorio nao identificado:        {n_no_terr:>4}")
    print(f"\n{'='*60}")
    print(f"  FASE 4 CONCLUIDA — {len(results)} leads processados")
    print(f"{'='*60}\n")

    return WebleadResult(leads=results)
