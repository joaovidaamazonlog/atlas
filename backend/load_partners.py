"""
load_partners.py
================
Fases 3/4 — Carregamento de parceiros e jurisdições.

Responsabilidades
-----------------
- Ler o JSON de parceiros e separar em grupos por status.
- Calcular o hex H3 de origem de cada parceiro (lat/lon → hex).
- Identificar a base jurisdicional de cada parceiro (GeoJSON de jurisdições).
- Separar web leads do fluxo principal.
- Expor índices auxiliares para as fases seguintes.

O que NÃO é responsabilidade deste módulo
------------------------------------------
- Alocar demanda a parceiros (Fase 3).
- Calcular capacidade/raio sugerido (Fase 3).
- Matching com vagas ideais (Fase 3).

Outputs principais
------------------
PartnerData.partners_df     : DataFrame normalizado de parceiros operacionais.
PartnerData.web_leads_df    : DataFrame de web leads.
PartnerData.jurisdictions   : GeoJSON dict das jurisdições.

Grupos de status suportados
---------------------------
Active, Onboarding, BG Checks, Prospect, Inactive, Exited (Regretted)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import h3
import pandas as pd
from shapely.geometry import Point, shape

from models import Config, PartnerMetrics


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class PartnerData:
    """Resultado do carregamento de parceiros e jurisdições."""

    partners_df: pd.DataFrame       # parceiros operacionais (todos os status)
    web_leads_df: pd.DataFrame      # web leads (leadSource = Website Pardot Form)
    jurisdictions: Dict             # GeoJSON das jurisdições

    # Índice rápido: hex → base (construído a partir das jurisdições)
    # Preenchido por get_base_from_jurisdiction() sob demanda
    _jurisdiction_cache: Dict[str, Optional[str]] = field(
        default_factory=dict, repr=False
    )

    # ---------------------------------------------------------------------------
    # HELPERS DE CONSULTA
    # ---------------------------------------------------------------------------

    def partners_by_station(self, station_code: str) -> pd.DataFrame:
        """Filtra parceiros de uma base específica."""
        return self.partners_df[
            self.partners_df["station_code"] == station_code
        ].copy()

    def partners_by_status(
        self, station_code: str, status: str
    ) -> pd.DataFrame:
        """Filtra parceiros por base e status."""
        return self.partners_df[
            (self.partners_df["station_code"] == station_code)
            & (self.partners_df["status"] == status)
        ].copy()

    def get_base_from_jurisdiction(
        self, lat: float, lon: float
    ) -> Optional[str]:
        """
        Retorna o station_code da jurisdição que contém o ponto (lat, lon).
        Usa cache interno para evitar recalcular para o mesmo ponto.
        """
        key = f"{lat:.6f},{lon:.6f}"
        if key in self._jurisdiction_cache:
            return self._jurisdiction_cache[key]

        pt = Point(float(lon), float(lat))
        result = None
        for feature in self.jurisdictions.get("features", []):
            if shape(feature["geometry"]).contains(pt):
                result = feature["properties"].get("delivery_station")
                break

        self._jurisdiction_cache[key] = result
        return result

    def prospects_in_jurisdiction(self) -> pd.DataFrame:
        """Prospects com base jurisdicional identificada."""
        df = self.partners_df[self.partners_df["status"] == "Prospect"].copy()
        df["identified_base"] = df.apply(
            lambda r: self.get_base_from_jurisdiction(float(r["lat"]), float(r["lon"])),
            axis=1,
        )
        return df

    def prospects_outside_jurisdiction(self) -> pd.DataFrame:
        """Prospects sem cobertura em nenhuma jurisdição conhecida."""
        df = self.partners_df[self.partners_df["status"] == "Prospect"].copy()
        outside = []
        for _, p in df.iterrows():
            base = self.get_base_from_jurisdiction(float(p["lat"]), float(p["lon"]))
            if base is None:
                outside.append(p)
        return pd.DataFrame(outside) if outside else pd.DataFrame(columns=df.columns)


# ---------------------------------------------------------------------------
# LOADER
# ---------------------------------------------------------------------------

_STATUS_OPERATIONAL = {"Active", "Onboarding", "BG Checks", "Inactive"}
_STATUS_PROSPECT    = {"Prospect"}
_STATUS_EXITED      = {"Exited"}   # só regretted é reaproveitado


def load_partners(
    partners_path: str = None,
    jurisdiction_path: str = None,
) -> PartnerData:
    """
    Carrega parceiros e jurisdições.

    Parâmetros
    ----------
    partners_path     : str, opcional. Default: Config.BASE_PARTNERS
    jurisdiction_path : str, opcional. Default: Config.BASE_JURISDICTION

    Fluxo
    -----
    1. Ler JSON de parceiros → DataFrame.
    2. Separar web leads do fluxo operacional.
    3. Normalizar colunas (renomear delivery_station, name).
    4. Limpar linhas sem lat/lon.
    5. Calcular hex H3 de origem.
    6. Carregar GeoJSON de jurisdições.
    """
    p_path = partners_path or Config.BASE_PARTNERS
    j_path = jurisdiction_path or Config.BASE_JURISDICTION

    print(f"[load_partners] Lendo parceiros de {p_path} ...")

    # 1. Ler JSON
    with open(p_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Suporte a dois formatos: lista direta ou wrapper {"allMarkerData": [...]}
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict) and "allMarkerData" in raw:
        records = raw["allMarkerData"]
    else:
        raise ValueError(
            "[load_partners] Formato JSON não reconhecido. "
            "Esperado lista ou {'allMarkerData': [...]}"
        )

    df = pd.DataFrame(records)
    print(f"   {len(df):,} registros carregados.")

    # 2. Separar web leads (antes de qualquer limpeza para não perder registros)
    web_leads_mask = (
        (df.get("leadSource", pd.Series(dtype=str)) == "Website Pardot Form")
        & (df.get("status", pd.Series(dtype=str)) == "New")
    )
    web_leads_df = df[web_leads_mask].copy()
    df = df[~web_leads_mask].copy()
    print(f"   {len(web_leads_df):,} web leads separados.")

    # 3. Normalizar colunas
    for src, dst in [("delivery_station", "station_code"), ("name", "partner_name")]:
        if src in df.columns:
            df.rename(columns={src: dst}, inplace=True)
        if src in web_leads_df.columns:
            web_leads_df.rename(columns={src: dst}, inplace=True)

    # 4. Limpar lat/lon ausentes
    before = len(df)
    df.dropna(subset=["lat", "lon"], inplace=True)
    dropped = before - len(df)
    if dropped:
        print(f"   WARN: {dropped} parceiros removidos por lat/lon ausente.")

    # 5. Normalizar tipos
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)

    if "exitedDate" in df.columns:
        df["exitedDate"] = pd.to_datetime(df["exitedDate"], errors="coerce")

    # CEP limpo (para webleads)
    if "zip_code" in web_leads_df.columns:
        web_leads_df["zip_clean"] = (
            web_leads_df["zip_code"]
            .astype(str)
            .str.replace(r"\D", "", regex=True)
            .str.zfill(8)
        )

    # 6. Hex H3 de origem
    print(f"   Calculando hexágonos H3 de origem (res={Config.H3_RES}) ...")
    df["origin_hex"] = [
        h3.latlng_to_cell(float(la), float(lo), Config.H3_RES)
        for la, lo in zip(df["lat"], df["lon"])
    ]

    # 7. Carregar jurisdições
    print(f"[load_partners] Lendo jurisdições de {j_path} ...")
    with open(j_path, "r", encoding="utf-8") as f:
        jurisdictions = json.load(f)
    n_juris = len(jurisdictions.get("features", []))
    print(f"   {n_juris} jurisdições carregadas.")

    # Sumário por status
    if "status" in df.columns:
        for status, grp in df.groupby("status"):
            print(f"   [{status}] {len(grp):,} parceiros")

    print(f"[load_partners] Concluído: {len(df):,} parceiros operacionais.")

    return PartnerData(
        partners_df=df,
        web_leads_df=web_leads_df,
        jurisdictions=jurisdictions,
    )


# ---------------------------------------------------------------------------
# HELPER: converter linha do DataFrame em PartnerMetrics
# ---------------------------------------------------------------------------

def row_to_partner_metrics(
    row: pd.Series,
    entity_type: str,
    station_code: str,
    decision: str = "",
    optimization_decision: str = "",
    radius_s: int = 0,
    capacity_s: int = 0,
    allocations=None,
) -> PartnerMetrics:
    """
    Converte uma linha do partners_df em PartnerMetrics.

    Centraliza o mapeamento de colunas para evitar repetição nas fases 3/4.
    """
    return PartnerMetrics(
        origin_hex      = str(row.get("origin_hex", "") or ""),
        station_code    = station_code,
        radius_s        = radius_s,
        capacity_s      = capacity_s,
        entity_type     = entity_type,
        status          = str(row.get("status", "")),
        partner_name    = str(row.get("partner_name", "")),
        salesforce_id   = str(row.get("salesforce_id", "")),
        store_id        = str(row.get("store_id", "")) or None,
        decision        = decision,
        lat             = float(row.get("lat", 0.0) or 0.0),
        lon             = float(row.get("lon", 0.0) or 0.0),
        decision_status = str(row.get("decision_status", "")),
        exitedDate      = str(row.get("exitedDate", "")),
        bucket          = row.get("bucket") or None,
        radius_a        = int(row["radius_a"]) if pd.notna(row.get("radius_a")) else None,
        capacity_a      = int(row["capacity_a"]) if pd.notna(row.get("capacity_a")) else None,
        allocations     = allocations or [],
    )
