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
    "Qualificar lead"              hex resolvido, territorio identificado
    "CEP invalido ou nao mapeado"  CEP ausente, vazio ou sem hex no indice
    "Territorio nao identificado"  hex resolvido mas fora de qualquer territorio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import h3
import pandas as pd

from load_packages import PackageData
from load_partners import PartnerData
from models import Config, PartnerMetrics
from phase1_territories import TerritoriesResult


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

def _find_hex_by_cep(cep: str, hex_to_ceps: Dict[str, Set[str]]) -> Optional[str]:
    """
    Localiza o hex mais apropriado para o CEP fornecido.

    Passo 1: correspondencia exata (8 digitos).
    Passo 2: prefixo de 5 digitos — elege o hex com mais CEPs no prefixo.
    """
    if not cep or not str(cep).strip().isdigit():
        return None

    cep = str(cep).zfill(8)

    # Passo 1 — exato
    for h, ceps in hex_to_ceps.items():
        if cep in ceps:
            return h

    # Passo 2 — prefixo
    prefix = cep[:5]
    best_hex, best_count = None, 0
    for h, ceps in hex_to_ceps.items():
        count = sum(1 for c in ceps if c.startswith(prefix))
        if count > best_count:
            best_count = count
            best_hex = h

    return best_hex


def _get_account_manager(
    station_code: str,
    territory_id: str,
    legacy_bucket_names: bool = False,
) -> Optional[str]:
    """
    Retorna o salesforce_id do ADE responsavel pelo territorio.

    Tenta dois formatos de chave no config:
        Novo:   "DSP2_T01"         (padrao desta arquitetura)
        Legado: "DSP2_bucket-1"    (formato do optimization_hub.py original)

    O parametro legacy_bucket_names=True ativa a tentativa do formato legado
    como fallback, util durante periodo de transicao do config.
    """
    managers = Config.ADES_ACCOUNT_MANAGERS
    if not managers:
        return None

    keys_to_try = [territory_id]
    if legacy_bucket_names:
        # Converte "DSP2_T01" -> "DSP2_bucket-1" para compatibilidade
        try:
            seq = int(territory_id.split("_T")[-1])
            legacy_key = f"{station_code}_bucket-{seq}"
            keys_to_try.append(legacy_key)
        except (ValueError, IndexError):
            pass

    for manager in managers:
        buckets = manager.get("buckets", [])
        for key in keys_to_try:
            if key in buckets:
                return manager.get("salesforce_id")

    return None


def _ctl_name_for_territory(territory_id: str) -> str:
    """Retorna o nome do CTL a partir do numero do territorio."""
    try:
        seq = int(territory_id.split("_T")[-1]) - 1
        return f"CTL-{chr(65 + (seq // 5))}"
    except (ValueError, IndexError):
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

    Parametros
    ----------
    partner_data        : PartnerData       Output de load_partners().
    territories         : TerritoriesResult Output da Fase 1.
    pkg                 : PackageData       Output de load_packages()
                                            (usado para hex_to_ceps).
    legacy_bucket_names : bool              Se True, tenta o formato antigo
                                            de nomes de bucket no config de
                                            account managers (compatibilidade).

    Retorna
    -------
    WebleadResult com lista de PartnerMetrics (entity_type="WEB_LEAD").
    """
    print(f"\n{'='*60}")
    print(f"  FASE 4 — QUALIFICACAO DE WEB LEADS")
    print(f"{'='*60}")

    df = partner_data.web_leads_df.copy()

    if df.empty:
        print("  Nenhum web lead encontrado.")
        return WebleadResult()

    print(f"  {len(df):,} web leads para processar...")

    # Normalizar CEP
    zip_col = "zip_clean" if "zip_clean" in df.columns else "zip_code"
    if zip_col not in df.columns:
        df["zip_clean"] = ""
    else:
        df["zip_clean"] = (
            df[zip_col]
            .astype(str)
            .str.replace(r"\D", "", regex=True)
            .str.zfill(8)
        )

    results: List[PartnerMetrics] = []
    n_qualified = 0
    n_no_cep    = 0
    n_no_terr   = 0

    for _, row in df.iterrows():
        sfid         = str(row.get("salesforce_id", ""))
        partner_name = str(row.get("partner_name", ""))
        cep          = str(row.get("zip_clean", "")).strip()

        # ── 1. Resolver CEP → hex ─────────────────────────────────────────
        origin_hex = _find_hex_by_cep(cep, pkg.hex_to_ceps)

        if not origin_hex:
            n_no_cep += 1
            results.append(PartnerMetrics(
                origin_hex    = None,
                station_code  = None,
                radius_s      = 0,
                capacity_s    = 0,
                entity_type   = "WEB_LEAD",
                status        = "New",
                partner_name  = partner_name,
                salesforce_id = sfid,
                decision      = "CEP invalido ou nao mapeado",
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
                decision      = "Territorio nao identificado",
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
            cluster_name  = territory_id,
            ctl_name      = ctl_name,
            bdm_cluster   = bdm_cluster,
            owner_id      = owner_id,
            decision      = "Qualificar lead",
            lat           = lat,
            lon           = lon,
            bucket        = territory_id,
        ))

    print(f"  Qualificados:            {n_qualified:>4}")
    print(f"  CEP invalido/nao mapeado:{n_no_cep:>4}")
    print(f"  Territorio nao encontrado:{n_no_terr:>3}")
    print(f"\n{'='*60}")
    print(f"  FASE 4 CONCLUIDA — {len(results)} leads processados")
    print(f"{'='*60}\n")

    return WebleadResult(leads=results)
