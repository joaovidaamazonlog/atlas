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

    partners_df: pd.DataFrame       # parceiros operacionais (todos os status, com lat/lon)
    web_leads_df: pd.DataFrame      # web leads (leadSource = Website Pardot Form)
    jurisdictions: Dict             # GeoJSON das jurisdições
    no_coords_prospects_df: pd.DataFrame = field(default_factory=pd.DataFrame)  # prospects sem lat/lon

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
    partners_path     : str, opcional.
                        None  → lê diretamente do Excel (modo produção).
                        str   → lê do JSON indicado (compatibilidade/testes).
    jurisdiction_path : str, opcional. Default: Config.BASE_JURISDICTION

    Fluxo (modo Excel — partners_path=None)
    ----------------------------------------
    1. ExcelHandler lê terra.xlsm e executa macro VBA.
    2. _consolidate_stores consolida Active + Launches + WebLeads.
    3. _build_partners constrói List[Partner].
    4. serialize_to_json gera dados_mapa.json com Schema_Limpo.
    5. _build_partner_data constrói PartnerData para as Fases 3/4/5.
    6. Carregar GeoJSON de jurisdições.

    Fluxo (modo JSON — partners_path=str)
    ---------------------------------------
    Lê o JSON indicado e segue o fluxo legado (compatibilidade).
    """
    j_path = jurisdiction_path or Config.BASE_JURISDICTION

    # ------------------------------------------------------------------
    # MODO EXCEL (novo pipeline)
    # ------------------------------------------------------------------
    if partners_path is None:
        import config
        from data_processing.excel_handler import ExcelHandler
        from datetime import datetime

        excel_path = config.EXCEL_FILE_PATH
        if not excel_path.exists():
            raise FileNotFoundError(
                f"Arquivo Excel não encontrado em {excel_path}. "
                "Verifique config.EXCEL_FILE_PATH."
            )

        print(f"[load_partners] Modo Excel — lendo {excel_path} ...")
        with ExcelHandler(excel_path) as excel:
            dataframes = excel.refresh_and_load_sheets(
                sheets_to_load=config.SHEETS_TO_LOAD,
                macro_name=config.MACRO_NAME,
                timeout=config.MACRO_TIMEOUT_SECONDS,
            )

        consolidated = _consolidate_stores(dataframes)
        partners     = _build_partners(consolidated)

        period = datetime.today().strftime("%Y-%m-%d : %Hh:%Mm")
        output_path = str(config.DEST_FOLDER / "dados_mapa.json")
        serialize_to_json(partners, period, output_path)

        partner_data = _build_partner_data(partners)

        # Carregar jurisdições
        print(f"[load_partners] Lendo jurisdições de {j_path} ...")
        with open(j_path, "r", encoding="utf-8") as f:
            partner_data.jurisdictions = json.load(f)
        n_juris = len(partner_data.jurisdictions.get("features", []))
        print(f"   {n_juris} jurisdições carregadas.")

        print(f"[load_partners] Concluído (Excel): {len(partner_data.partners_df):,} parceiros operacionais.")
        return partner_data

    # ------------------------------------------------------------------
    # MODO JSON (fluxo legado — compatibilidade com testes/manual)
    # ------------------------------------------------------------------
    p_path = partners_path
    print(f"[load_partners] Modo JSON — lendo parceiros de {p_path} ...")

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

    # 4. Separar prospects sem lat/lon (serão avaliados com decision fixa na Fase 3)
    #    Demais parceiros: remover lat/lon ausentes normalmente
    prospects_mask = df["status"] == "Prospect"
    no_coords_mask = df["lat"].isna() | df["lon"].isna()

    no_coords_prospects_df = df[prospects_mask & no_coords_mask].copy()
    before = len(df)
    df = df[~(prospects_mask & no_coords_mask)].copy()  # remove só prospects sem coords
    df.dropna(subset=["lat", "lon"], inplace=True)       # remove demais sem coords
    dropped = before - len(df) - len(no_coords_prospects_df)
    if len(no_coords_prospects_df):
        print(f"   INFO: {len(no_coords_prospects_df)} prospect(s) sem lat/lon — "
              f"receberão decision fixa na Fase 3.")
    if dropped:
        print(f"   WARN: {dropped} parceiros não-prospect removidos por lat/lon ausente.")

    # 5. Normalizar tipos
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)

    # Suporte a ambos os nomes (legado exitedDate + novo exited_date)
    for date_col in ("exited_date", "exitedDate"):
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], format="mixed", errors="coerce")

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
        no_coords_prospects_df=no_coords_prospects_df,
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
        exited_date     = str(row.get("exited_date") or row.get("exitedDate") or ""),
        exitedDate      = str(row.get("exited_date") or row.get("exitedDate") or ""),
        bucket          = row.get("bucket") or None,
        radius_a        = int(row["radius_a"]) if pd.notna(row.get("radius_a")) else None,
        capacity_a      = int(row["capacity_a"]) if pd.notna(row.get("capacity_a")) else None,
        allocations     = allocations or [],
    )


# ---------------------------------------------------------------------------
# NOVO PIPELINE — funções privadas (Fase 1: adicionadas sem alterar fluxo atual)
# ---------------------------------------------------------------------------

from models import Partner  # noqa: E402  (import tardio para evitar circular)


_MAPEAMENTO_DS = {
    "HSP2": "DSP2", "HSP3": "DSP3", "HSP5": "DSP5", "HBH5": "DBH5",
    "HFO3": "DCE3", "HVI2": "DES2", "HRJ3": "DRJ3", "HGO2": "DGO2",
    "HBS5": "DBS5", "HPE4": "DPE4", "HPR2": "DPR2", "HRS5": "DRS5",
    "HPB3": "DPB3", "HSV8": "DSA8",
}


def _consolidate_stores(dfs: dict) -> pd.DataFrame:
    """
    Consolida Active + Launches + WebLeads em um único DataFrame.
    Migrado de DataProcessor.consolidate_stores — mesma lógica, sem dependência externa.
    """
    import pandas as _pd

    active_df      = dfs.get("Active",            _pd.DataFrame()).copy()
    launches_df    = dfs.get("Launches",           _pd.DataFrame()).copy()
    stations_df    = dfs.get("Delivery Stations",  _pd.DataFrame()).copy()
    jurisdictions_df = dfs.get("Jurisdictions",    _pd.DataFrame()).copy()
    webleads_df    = dfs.get("WebLeads",           _pd.DataFrame()).copy()

    if active_df.empty and launches_df.empty:
        raise ValueError("DataFrames 'Active' e 'Launches' estão vazios.")

    active_df["Source"]   = "Active"
    launches_df["Source"] = "Launches"

    for df in [active_df, launches_df]:
        if "Radius" in df.columns:
            df["Radius"] = _pd.to_numeric(df["Radius"], errors="coerce").fillna(1500)
        else:
            df["Radius"] = 1500
        if "Volume Cap" in df.columns:
            df["Volume Cap"] = _pd.to_numeric(df["Volume Cap"], errors="coerce").fillna(42)
        else:
            df["Volume Cap"] = 42

    # Resolver HCP Host Partner: Id → Name (antes do concat)
    if {"Id", "Name", "HCP Host Partner"}.issubset(active_df.columns):
        host_map = dict(zip(active_df["Id"].astype(str), active_df["Name"]))
        active_df["HCP Host Partner"] = active_df["HCP Host Partner"].astype(str).map(host_map)

    consolidated = _pd.concat([active_df, launches_df, webleads_df], ignore_index=True, sort=False)

    # Delivery Station: Id → Name
    if not stations_df.empty and {"Id", "Name"}.issubset(stations_df.columns):
        station_map = dict(zip(stations_df["Id"].astype(str), stations_df["Name"]))
        consolidated["Delivery Station"] = (
            consolidated["Delivery Station"].astype(str).map(station_map)
        )

    # Bucket via Jurisdictions: Id → Name[5:]
    if not jurisdictions_df.empty and {"Id", "Name"}.issubset(jurisdictions_df.columns):
        jur_map = dict(zip(jurisdictions_df["Id"].astype(str), jurisdictions_df["Name"].str[5:]))
        consolidated["Bucket"] = consolidated.get("Jurisdiction", _pd.Series(dtype=str)).astype(str).map(jur_map)

    # Normalizar coordenadas
    for col in ["Latitude", "Longitude"]:
        if col in consolidated.columns:
            consolidated[col] = (
                consolidated[col].astype(str).str.replace(",", ".", regex=False)
            )
            consolidated[col] = _pd.to_numeric(consolidated[col], errors="coerce")

    # Remap legado de DS (HSP2 → DSP2 etc.)
    if "Delivery Station" in consolidated.columns:
        consolidated["Delivery Station"] = consolidated["Delivery Station"].replace(_MAPEAMENTO_DS)

    print(f"[_consolidate_stores] {len(consolidated):,} registros consolidados.")
    return consolidated


def _build_partners(consolidated_df: pd.DataFrame) -> "list[Partner]":
    """
    Constrói objetos Partner a partir do DataFrame consolidado.
    Usa Partner.from_row() para cada linha.
    """
    import pandas as _pd

    # Mapas auxiliares para from_row (já resolvidos em _consolidate_stores,
    # mas passamos vazios pois o consolidado já tem os valores resolvidos)
    station_map     = {}   # já resolvido no consolidado
    jurisdictions_map = {} # já resolvido no consolidado (campo Bucket)
    host_map        = {}   # já resolvido no consolidado

    partners = []
    for _, row in consolidated_df.iterrows():
        try:
            p = Partner.from_row(row, station_map, jurisdictions_map, host_map)
            partners.append(p)
        except Exception as exc:
            sf_id = row.get("Id", "?")
            print(f"  WARN [_build_partners] Erro ao construir Partner {sf_id}: {exc}")

    print(f"[_build_partners] {len(partners):,} objetos Partner construídos.")
    return partners


def serialize_to_json(
    partners: "list[Partner]",
    period: str,
    output_path: str,
) -> None:
    """
    Serializa a lista de Partners para dados_mapa.json com o Schema_Limpo.
    Inclui period e deliveryStations (de config.DELIVERY_STATIONS) na raiz.
    """
    import json as _json
    from config import DELIVERY_STATIONS

    payload = {
        "period":           period,
        "deliveryStations": DELIVERY_STATIONS,
        "allMarkerData":    [p.to_dict() for p in partners],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        _json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[serialize_to_json] {len(partners):,} parceiros → {output_path}")


def _build_partner_data(partners: "list[Partner]") -> PartnerData:
    """
    Constrói PartnerData a partir da lista de Partners.
    - Separa web leads (status='New' AND lead_source='Website Pardot Form')
    - Renomeia delivery_station → station_code, name → partner_name
    - Remove parceiros sem lat/lon (exceto prospects)
    - Calcula origin_hex via H3
    - Adiciona zip_clean em web_leads_df
    """
    import h3 as _h3

    WEB_LEAD_SOURCE = "Website Pardot Form"

    web_lead_dicts  = []
    partner_dicts   = []

    for p in partners:
        d = p.to_dict()
        if p.status == "New" and p.lead_source == WEB_LEAD_SOURCE:
            web_lead_dicts.append(d)
        else:
            partner_dicts.append(d)

    # --- DataFrame de parceiros operacionais ---
    df = pd.DataFrame(partner_dicts) if partner_dicts else pd.DataFrame()

    if not df.empty:
        # Renomear para interface esperada pelas Fases 3/4/5
        df.rename(columns={"delivery_station": "station_code", "name": "partner_name"}, inplace=True)

        # Separar prospects sem coords (tratamento especial na Fase 3)
        prospects_mask  = df["status"] == "Prospect"
        no_coords_mask  = df["lat"].isna() | df["lon"].isna()
        no_coords_df    = df[prospects_mask & no_coords_mask].copy()

        # Remover: prospects sem coords + demais sem coords
        df = df[~(prospects_mask & no_coords_mask)].copy()
        df.dropna(subset=["lat", "lon"], inplace=True)

        df["lat"] = df["lat"].astype(float)
        df["lon"] = df["lon"].astype(float)

        # Calcular origin_hex
        df["origin_hex"] = [
            _h3.latlng_to_cell(float(la), float(lo), Config.H3_RES)
            for la, lo in zip(df["lat"], df["lon"])
        ]

        # Renomear exited_date para compatibilidade com PartnerMetrics
        if "exited_date" in df.columns:
            df["exited_date"] = pd.to_datetime(df["exited_date"], format="mixed", errors="coerce")
    else:
        no_coords_df = pd.DataFrame()

    # --- DataFrame de web leads ---
    wl_df = pd.DataFrame(web_lead_dicts) if web_lead_dicts else pd.DataFrame()

    if not wl_df.empty:
        wl_df.rename(columns={"delivery_station": "station_code", "name": "partner_name"}, inplace=True)
        wl_df["zip_clean"] = (
            wl_df["zip_code"]
            .fillna("")
            .astype(str)
            .str.replace(r"\D", "", regex=True)
            .str.zfill(8)
        )

    # Sumário
    if not df.empty and "status" in df.columns:
        for status, grp in df.groupby("status"):
            print(f"   [{status}] {len(grp):,} parceiros")

    print(f"[_build_partner_data] {len(df):,} operacionais | {len(wl_df):,} web leads")

    return PartnerData(
        partners_df             = df,
        web_leads_df            = wl_df,
        jurisdictions           = {},   # preenchido por load_partners após carregar GeoJSON
        no_coords_prospects_df  = no_coords_df,
    )
