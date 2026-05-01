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
from pathlib import Path
from typing import Dict, List, Optional, Set

import h3
import pandas as pd
from shapely.geometry import Point, shape

from shared.models import Config, PartnerMetrics


# ---------------------------------------------------------------------------
# HELPERS DE COMPOSIÇÃO DE SUBSTITUIÇÕES
# ---------------------------------------------------------------------------

def _compose_replacements(*maps: dict) -> dict:
    """
    Compõe múltiplos mapas de substituição em um único, simulando a
    aplicação sequencial de `.replace(m1).replace(m2)...` do pandas.

    Semântica
    ---------
    A semântica de `pd.Series.replace(dict)` aplica TODAS as substituições
    **simultaneamente** (um dict = uma passagem atômica). Portanto, a
    composição é:

        resultado(k) = mn ∘ ... ∘ m2 ∘ m1 (k)

    Onde cada `mi` é aplicado como um único passo (sem iterar dentro do
    mesmo dict).

    Exemplos
    --------
    >>> _compose_replacements({"A": "B"}, {"B": "C"})
    {'A': 'C', 'B': 'C'}

    >>> _compose_replacements({"A": "B", "B": "A"})  # swap atômico
    {}

    Identidades (`k → k`) após toda a composição são removidas do output.

    Por que isto evita ciclos infinitos?
    -------------------------------------
    Cada `mi` é uma função total sobre strings: `mi(x) = mi.get(x, x)`.
    A aplicação sequencial de `n` funções termina em `n` passos, sem
    iteração dentro de cada passo.
    """
    if not maps:
        return {}

    # Conjunto de chaves que podem sofrer alguma substituição
    # (apenas as que aparecem como chave em algum mapa).
    keys: set = set()
    for m in maps:
        keys.update(m.keys())

    composed: dict = {}
    for k in keys:
        v = k
        for m in maps:
            v = m.get(v, v)  # UMA aplicação por mapa, não iterativa
        if v != k:
            composed[k] = v
    return composed


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
        Bases satélite são resolvidas para a base canônica via STATION_ALIASES.
        Usa cache interno para evitar recalcular para o mesmo ponto.
        """
        from shared.config import STATION_ALIASES

        key = f"{lat:.6f},{lon:.6f}"
        if key in self._jurisdiction_cache:
            return self._jurisdiction_cache[key]

        pt = Point(float(lon), float(lat))
        result = None
        for feature in self.jurisdictions.get("features", []):
            if shape(feature["geometry"]).contains(pt):
                raw_station = feature["properties"].get("delivery_station")
                # Resolver satélite → canônica
                result = STATION_ALIASES.get(raw_station, raw_station)
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
        import shared.config as config
        from shared.data_processing.excel_handler import ExcelHandler
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

    # 3b. Remapear bases satélite → base canônica
    aliases = getattr(Config, "STATION_ALIASES", {})
    if aliases:
        if "station_code" in df.columns:
            df["station_code"] = df["station_code"].replace(aliases)
        if "station_code" in web_leads_df.columns:
            web_leads_df["station_code"] = web_leads_df["station_code"].replace(aliases)

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

    # 6. Hex H3 de origem (vetorizado — substitui list-comprehension)
    from shared.load_packages import _vectorized_latlng_to_cell
    print(f"   Calculando hexágonos H3 de origem (res={Config.H3_RES}) ...")
    df["origin_hex"] = _vectorized_latlng_to_cell(
        df["lat"].astype(float), df["lon"].astype(float), Config.H3_RES
    )

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
        decision_reason_code = str(row.get("decision_reason_code", "")),
        exited_date     = str(row.get("exited_date") or row.get("exitedDate") or ""),
        exitedDate      = str(row.get("exited_date") or row.get("exitedDate") or ""),        bucket          = row.get("bucket") or None,
        radius_a        = int(row["radius_a"]) if pd.notna(row.get("radius_a")) else None,
        capacity_a      = int(row["capacity_a"]) if pd.notna(row.get("capacity_a")) else None,
        allocations     = allocations or [],
    )


# ---------------------------------------------------------------------------
# NOVO PIPELINE — funções privadas (Fase 1: adicionadas sem alterar fluxo atual)
# ---------------------------------------------------------------------------

from shared.models import Partner  # noqa: E402  (import tardio para evitar circular)


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

    active_df      = dfs.get("Active",             _pd.DataFrame()).copy()
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

    # Remap consolidado de DS — passagem única combinando:
    #  - _MAPEAMENTO_DS (HSP2 → DSP2, HRJ3 → DRJ3, ...)
    #  - STATION_ALIASES (XBA1 → DSA8, ...)
    # Fechamento transitivo resolve dependências de ordem (ex.: A→B e B→C
    # viram A→C no mapa composto) — ver `_compose_replacements`.
    import shared.config as _cfg
    _aliases = getattr(_cfg, "STATION_ALIASES", {})
    if "Delivery Station" in consolidated.columns:
        composed = _compose_replacements(_MAPEAMENTO_DS, _aliases)
        if composed:
            consolidated["Delivery Station"] = (
                consolidated["Delivery Station"].replace(composed)
            )
        if _aliases:
            n_sat = consolidated["Delivery Station"].isin(_aliases.keys()).sum()
            if n_sat:
                print(f"[_consolidate_stores] WARN: {n_sat} registros ainda com código satélite após remap.")

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
    from shared.config import DELIVERY_STATIONS

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
        before_drop = len(df)
        df.dropna(subset=["lat", "lon"], inplace=True)
        dropped_operational = before_drop - len(df)

        # WARNING ALTO quando perdemos parceiros operacionais por falta de coords.
        # Sintoma típico: CSV exportado do Salesforce sem as colunas lat/lon
        # preenchidas. Sem coordenadas os parceiros não podem ser geocodificados
        # e ficam de fora das Fases 3/4/5 (matching, webleads, relatórios).
        if dropped_operational:
            print(
                f"  ⚠️  WARN: {dropped_operational:,} parceiro(s) operacional(is) "
                f"(Active/Onboarding/BG Checks/Inactive) descartado(s) por "
                f"latitude/longitude vazias. Verifique se o CSV de parceiros "
                f"contém as colunas `latitude` e `longitude` preenchidas."
            )

        df["lat"] = df["lat"].astype(float)
        df["lon"] = df["lon"].astype(float)

        # Calcular origin_hex (vetorizado — substitui list-comprehension)
        from shared.load_packages import _vectorized_latlng_to_cell
        df["origin_hex"] = _vectorized_latlng_to_cell(
            df["lat"], df["lon"], Config.H3_RES
        )

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


# ---------------------------------------------------------------------------
# CSV PIPELINE — load_partners_csv
# ---------------------------------------------------------------------------

def load_partners_csv(
    csv_path: str,
    jurisdiction_path: str = None,
) -> PartnerData:
    """
    Carrega parceiros a partir de um arquivo CSV exportado do Salesforce
    (ex: partners.csv) e retorna um PartnerData idêntico ao produzido pelo
    modo Excel.

    Uso
    ---
    Passe ``--partnerCSV <caminho>`` na linha de comando e o orquestrador
    chamará esta função em vez de ``load_partners()``.

    Mapeamento de colunas CSV → campos internos
    -------------------------------------------
    O CSV usa underscores onde o Excel usa espaços, e omite o sufixo ``__c``
    dos campos Salesforce.  A tabela abaixo mostra todas as diferenças:

    CSV column                  → Partner.from_row espera
    ─────────────────────────────────────────────────────
    Delivery_Station            → "Delivery Station"
    Jurisdiction_Type           → "Jurisdiction Type"
    Hub_Delivery_Initiatives    → "Hub Delivery Initiatives"
    HCP_Rate_Card               → "HCP Rate Card"
    HCP_host_partner            → "HCP Host Partner"
    Exit_Date                   → "Exit_Date__c"
    Decision_Status             → "Decision_Status__c"
    Decision_Reason_Code        → "Decision_Reason_Code__c"
    Jurisdiction_Name           → "Bucket"  (já é o nome, não um ID)

    Colunas ausentes no CSV (usam defaults)
    ----------------------------------------
    LeadSource  → None  (nenhum web lead esperado neste fluxo)
    Radius      → 1500  (default de _clean_int)
    Volume Cap  → 42    (default de _clean_int)

    Parâmetros
    ----------
    csv_path          : caminho para o arquivo .csv
    jurisdiction_path : caminho para o GeoJSON de jurisdições
                        (default: Config.BASE_JURISDICTION)
    """
    import shared.config as _cfg

    j_path = jurisdiction_path or Config.BASE_JURISDICTION

    print(f"[load_partners_csv] Lendo CSV de parceiros: {csv_path} ...")

    # ------------------------------------------------------------------
    # 1. Ler CSV
    # ------------------------------------------------------------------
    df_raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"   {len(df_raw):,} linhas lidas.")

    # ------------------------------------------------------------------
    # 2. Renomear colunas para o formato esperado por Partner.from_row
    # ------------------------------------------------------------------
    # O mapa cobre dois formatos de export do Salesforce:
    #   (a) snake_case minúsculo com espaços ("volume cap", "supply run",
    #       "launch date") — formato atual do partners.csv de produção.
    #   (b) Title_Case_Underscore ("Delivery_Station", "Volume_Cap__c") —
    #       formato legado de exports antigos. Mantemos por compatibilidade.
    # A chave do dicionário é o nome da coluna no CSV; o valor é o nome
    # que `Partner.from_row` consulta via `row.get(...)`.
    _CSV_RENAME = {
        # Identificadores e nome
        "id":                       "Id",
        "name":                     "Name",
        "storeid":                  "StoreID",

        # Status e decisões
        "status":                   "Status",
        "decision_status":          "Decision_Status__c",
        "decision_reason_code":     "Decision_Reason_Code__c",

        # Localização
        "latitude":                 "Latitude",
        "longitude":                "Longitude",
        "cep":                      "CEP",
        "cidade":                   "Cidade",
        "estado":                   "Estado",

        # Operação
        "delivery_station":         "Delivery Station",
        "supply run":               "Supply Run",
        "volume cap":               "Volume Cap",
        "radius":                   "Radius",

        # Categorização
        "jurisdiction_type":        "Jurisdiction Type",
        "jurisdiction_name":        "Bucket",  # já vem resolvido como nome
        "hub_delivery_initiatives": "Hub Delivery Initiatives",
        "hcp_rate_card":            "HCP Rate Card",
        "hcp_host_partner":         "HCP Host Partner",

        # Datas
        "launch date":              "Launch Date",
        "exit_date":                "Exit_Date__c",

        # Contato e ownership
        "phone":                    "Phone",
        "ownerid":                  "OwnerId",

        # ──────────────────────────────────────────────────────────────
        # Aliases do formato legado Title_Case_Underscore (compat).
        # ──────────────────────────────────────────────────────────────
        "Delivery_Station":         "Delivery Station",
        "Jurisdiction_Type":        "Jurisdiction Type",
        "Hub_Delivery_Initiatives": "Hub Delivery Initiatives",
        "HCP_Rate_Card":            "HCP Rate Card",
        "HCP_host_partner":         "HCP Host Partner",
        "Exit_Date":                "Exit_Date__c",
        "Decision_Status":          "Decision_Status__c",
        "Decision_Reason_Code":     "Decision_Reason_Code__c",
        "Jurisdiction_Name":        "Bucket",
    }

    # Aplica renomeação case-sensitive; colunas não mapeadas são mantidas
    # (ex: account_manager, territory_manager_owner — ignoradas pelo parser
    # intencionalmente, pois a hierarquia BDM/CTL/ADE vem da config TEAM).
    df_raw.rename(columns=_CSV_RENAME, inplace=True)

    # ------------------------------------------------------------------
    # 3. Normalizar valores vazios: strings vazias → NaN
    # ------------------------------------------------------------------
    df_raw.replace({"": None, "nan": None, "NaN": None, "None": None}, inplace=True)

    # ------------------------------------------------------------------
    # 4. Construir objetos Partner via from_row
    #    (station_map / jurisdictions_map / host_map ficam vazios porque
    #     o CSV já traz os valores resolvidos — nomes, não IDs)
    # ------------------------------------------------------------------
    partners: list[Partner] = []
    for _, row in df_raw.iterrows():
        try:
            p = Partner.from_row(row, {}, {}, {})
            partners.append(p)
        except Exception as exc:
            sf_id = row.get("Id", "?")
            print(f"  WARN [load_partners_csv] Erro ao construir Partner {sf_id}: {exc}")

    print(f"[load_partners_csv] {len(partners):,} objetos Partner construídos.")

    # ------------------------------------------------------------------
    # 5. Serializar para dados_mapa.json (mesmo artefato do modo Excel)
    # ------------------------------------------------------------------
    from datetime import datetime
    period = datetime.today().strftime("%Y-%m-%d : %Hh:%Mm")
    output_path = str(_cfg.DEST_FOLDER / "dados_mapa.json")
    serialize_to_json(partners, period, output_path)

    # ------------------------------------------------------------------
    # 6. Construir PartnerData (mesma lógica do modo Excel)
    # ------------------------------------------------------------------
    partner_data = _build_partner_data(partners)

    # ------------------------------------------------------------------
    # 7. Carregar jurisdições
    # ------------------------------------------------------------------
    print(f"[load_partners_csv] Lendo jurisdições de {j_path} ...")
    with open(j_path, "r", encoding="utf-8") as f:
        partner_data.jurisdictions = json.load(f)
    n_juris = len(partner_data.jurisdictions.get("features", []))
    print(f"   {n_juris} jurisdições carregadas.")

    print(
        f"[load_partners_csv] Concluído: "
        f"{len(partner_data.partners_df):,} parceiros operacionais."
    )
    return partner_data


# ---------------------------------------------------------------------------
# PROSPECTS / WEBLEADS CSV LOADERS
# ---------------------------------------------------------------------------
#
# Os CSVs de prospects e webleads são exports simplificados do Salesforce
# com 13 colunas: id, cep, cidade, estado, jurisdiction_name, latitude,
# longitude, name, ownerid, phone, recruitment_representative, status, origem
#
# Diferenças em relação ao partners.csv:
# - Não tem delivery_station, volume cap, radius, supply run, launch date
#   → usamos defaults (radius=1500, capacity=42, station vazia → None).
# - Tem `origem` em vez de `leadSource` → mapeado para lead_source no Partner.
# - Prospects: status forçado a "Prospect"; lead_source = origem (ou None).
# - Webleads: status forçado a "New"; lead_source forçado a
#   "Website Pardot Form" (ignoramos `origem` pois todos os webleads vêm do
#   formulário Pardot por convenção).
#
# A hierarquia BDM/CTL/ADE e a jurisdição são inferidas em fases posteriores
# a partir do TEAM e do GeoJSON — NÃO do CSV (conforme correção explícita
# do usuário: "hierarquia de CTL/ADE/BDM vem do TEAM, não do CSV").
# ---------------------------------------------------------------------------

# Mapa de renomeação para o formato de 13 colunas (prospects/webleads).
# Chave: nome no CSV. Valor: nome esperado por Partner.from_row.
_PROSPECT_WEBLEAD_RENAME = {
    "id":                       "Id",
    "name":                     "Name",
    "status":                   "Status",
    "latitude":                 "Latitude",
    "longitude":                "Longitude",
    "cep":                      "CEP",
    "cidade":                   "Cidade",
    "estado":                   "Estado",
    "phone":                    "Phone",
    "ownerid":                  "OwnerId",
    "origem":                   "LeadSource",
    # jurisdiction_name do CSV é IGNORADO intencionalmente — a jurisdição
    # real vem do GeoJSON via PartnerData.get_base_from_jurisdiction.
    # recruitment_representative também é ignorado (hierarquia = TEAM).
}


def _read_simple_csv(csv_path: str, source_label: str) -> pd.DataFrame:
    """
    Lê um CSV simplificado (formato prospects/webleads) e retorna um
    DataFrame com colunas renomeadas para o que Partner.from_row espera.

    Validação mínima
    ----------------
    Exige as 13 colunas esperadas. Se faltar alguma, loga warning e
    segue com o que houver (permite exports parciais).
    """
    expected = {
        "id", "cep", "cidade", "estado", "jurisdiction_name",
        "latitude", "longitude", "name", "ownerid", "phone",
        "recruitment_representative", "status", "origem",
    }

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    # Normaliza cabeçalhos: remove espaços e lowercase
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = expected - set(df.columns)
    if missing:
        print(
            f"  WARN [{source_label}] colunas ausentes no CSV: "
            f"{sorted(missing)} — campos correspondentes ficarão vazios."
        )

    df.rename(columns=_PROSPECT_WEBLEAD_RENAME, inplace=True)

    # Normalizar vazios → None
    df.replace({"": None, "nan": None, "NaN": None, "None": None}, inplace=True)
    return df


def load_prospects_csv(csv_path: str) -> pd.DataFrame:
    """
    Carrega o CSV de prospects e retorna um DataFrame pronto para ser
    consumido por ``_build_partner_data`` (via merge_partner_sources).

    Regras de negócio
    -----------------
    - ``status`` é forçado a "Prospect" (mesmo que venha diferente no CSV).
    - ``lead_source`` recebe o valor de ``origem`` (ex: "Website Pardot Form",
      "Cold Call") ou None se vazio.
    - Linhas sem lat/lon não são removidas aqui — ficam para o
      ``_build_partner_data`` tratar como `no_coords_prospects_df`.
    - Linhas com parse inválido são puladas com warning (mesma política
      do ``load_partners_csv``).

    Retorna
    -------
    DataFrame com colunas serializadas via ``Partner.to_dict()``.
    Vazio se o arquivo não existir.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"[load_prospects_csv] Arquivo não encontrado: {csv_path}")
        return pd.DataFrame()

    print(f"[load_prospects_csv] Lendo {csv_path} ...")
    df_raw = _read_simple_csv(csv_path, "load_prospects_csv")
    print(f"   {len(df_raw):,} linhas lidas.")

    # Forçar status = "Prospect" independentemente do que vier no CSV.
    # Isto garante que merges futuros de exports inconsistentes não
    # contaminem o fluxo com status inesperados.
    df_raw["Status"] = "Prospect"

    partners: list[Partner] = []
    for _, row in df_raw.iterrows():
        try:
            p = Partner.from_row(row, {}, {}, {})
            partners.append(p)
        except Exception as exc:
            sf_id = row.get("Id", "?")
            print(
                f"  WARN [load_prospects_csv] Erro ao construir Partner "
                f"{sf_id}: {exc}"
            )

    print(f"[load_prospects_csv] {len(partners):,} prospects carregados.")
    return pd.DataFrame([p.to_dict() for p in partners]) if partners else pd.DataFrame()


def load_webleads_csv(csv_path: str) -> pd.DataFrame:
    """
    Carrega o CSV de webleads e retorna um DataFrame pronto para ser
    consumido por ``_build_partner_data`` (via merge_partner_sources).

    Regras de negócio
    -----------------
    - ``status`` é forçado a "New".
    - ``lead_source`` é forçado a "Website Pardot Form" (convenção do CSV
      de webleads — mesmo se ``origem`` vier diferente).
    - Webleads sem lat/lon são mantidos no DataFrame de webleads (o
      ``_build_partner_data`` lida com ``zip_clean`` para esses casos).

    Retorna
    -------
    DataFrame com colunas serializadas via ``Partner.to_dict()``.
    Vazio se o arquivo não existir.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"[load_webleads_csv] Arquivo não encontrado: {csv_path}")
        return pd.DataFrame()

    print(f"[load_webleads_csv] Lendo {csv_path} ...")
    df_raw = _read_simple_csv(csv_path, "load_webleads_csv")
    print(f"   {len(df_raw):,} linhas lidas.")

    # Forçar status e lead_source segundo a convenção de webleads.
    df_raw["Status"]     = "New"
    df_raw["LeadSource"] = "Website Pardot Form"

    partners: list[Partner] = []
    for _, row in df_raw.iterrows():
        try:
            p = Partner.from_row(row, {}, {}, {})
            partners.append(p)
        except Exception as exc:
            sf_id = row.get("Id", "?")
            print(
                f"  WARN [load_webleads_csv] Erro ao construir Partner "
                f"{sf_id}: {exc}"
            )

    print(f"[load_webleads_csv] {len(partners):,} webleads carregados.")
    return pd.DataFrame([p.to_dict() for p in partners]) if partners else pd.DataFrame()


# ---------------------------------------------------------------------------
# MERGE — load_partners_sources
# ---------------------------------------------------------------------------

def load_partners_sources(
    partners_csv: Optional[str] = None,
    prospects_csv: Optional[str] = None,
    webleads_csv: Optional[str] = None,
    jurisdiction_path: Optional[str] = None,
) -> PartnerData:
    """
    Carrega os 3 CSVs do pipeline de parceiros (active/onboarding/inactive +
    prospects + webleads) e consolida em um único ``PartnerData``.

    Cada argumento é opcional. Se um caminho for ``None`` ou o arquivo
    não existir, aquela fonte é silenciosamente pulada (com log informativo).
    Isto permite rodar o pipeline com qualquer subconjunto dos 3 arquivos —
    essencial para evolução gradual enquanto os exports são organizados.

    Uso típico (modo daily)
    -----------------------
    ```python
    partner_data = load_partners_sources(
        partners_csv  = str(Config.BASE_PARTNERS_CSV),
        prospects_csv = str(Config.BASE_PROSPECTS_CSV),
        webleads_csv  = str(Config.BASE_WEBLEADS_CSV),
    )
    ```

    Semântica do merge
    ------------------
    - ``partners_df``        = partners.csv (active/onboarding/inactive) +
                               prospects.csv (status="Prospect").
    - ``web_leads_df``       = webleads.csv (status="New",
                               lead_source="Website Pardot Form").
    - ``no_coords_prospects_df`` = prospects sem lat/lon (pegos do
                               prospects.csv durante o merge).
    - ``jurisdictions``      = GeoJSON de Config.BASE_JURISDICTION.

    Duplicatas
    ----------
    Se um Id aparecer em mais de um CSV, o primeiro vence (ordem:
    partners > prospects > webleads). Emite warning em caso de conflito.

    Fallback
    --------
    Se NENHUM dos 3 CSVs existir, levanta ``FileNotFoundError`` — nesse
    caso o chamador deve cair para o Excel via ``load_partners()``.
    """
    import shared.config as _cfg

    j_path = jurisdiction_path or Config.BASE_JURISDICTION

    # ------------------------------------------------------------------
    # 1. Ler cada fonte; construir lista de Partner objects
    # ------------------------------------------------------------------
    partners_obj: list[Partner] = []
    sources_used: list[str] = []

    # ---- partners.csv (Active/Onboarding/Inactive/BG Checks/Exited) ----
    if partners_csv and Path(partners_csv).exists():
        print(f"[load_partners_sources] Lendo partners: {partners_csv} ...")
        df_raw = pd.read_csv(partners_csv, dtype=str, keep_default_na=False)
        df_raw.rename(columns={
            # Formato atual (snake_case + espaços)
            "id":                       "Id",
            "name":                     "Name",
            "storeid":                  "StoreID",
            "status":                   "Status",
            "decision_status":          "Decision_Status__c",
            "decision_reason_code":     "Decision_Reason_Code__c",
            "latitude":                 "Latitude",
            "longitude":                "Longitude",
            "cep":                      "CEP",
            "cidade":                   "Cidade",
            "estado":                   "Estado",
            "delivery_station":         "Delivery Station",
            "supply run":               "Supply Run",
            "volume cap":               "Volume Cap",
            "radius":                   "Radius",
            "jurisdiction_type":        "Jurisdiction Type",
            "jurisdiction_name":        "Bucket",
            "hub_delivery_initiatives": "Hub Delivery Initiatives",
            "hcp_rate_card":            "HCP Rate Card",
            "hcp_host_partner":         "HCP Host Partner",
            "launch date":              "Launch Date",
            "exit_date":                "Exit_Date__c",
            "phone":                    "Phone",
            "ownerid":                  "OwnerId",
            # Aliases Title_Case (compat)
            "Delivery_Station":         "Delivery Station",
            "Jurisdiction_Type":        "Jurisdiction Type",
            "Hub_Delivery_Initiatives": "Hub Delivery Initiatives",
            "HCP_Rate_Card":            "HCP Rate Card",
            "HCP_host_partner":         "HCP Host Partner",
            "Exit_Date":                "Exit_Date__c",
            "Decision_Status":          "Decision_Status__c",
            "Decision_Reason_Code":     "Decision_Reason_Code__c",
            "Jurisdiction_Name":        "Bucket",
        }, inplace=True)
        df_raw.replace({"": None, "nan": None, "NaN": None, "None": None}, inplace=True)
        for _, row in df_raw.iterrows():
            try:
                partners_obj.append(Partner.from_row(row, {}, {}, {}))
            except Exception as exc:
                sf_id = row.get("Id", "?")
                print(f"  WARN [partners] Erro ao construir {sf_id}: {exc}")
        sources_used.append(f"partners ({len(df_raw):,})")
    else:
        if partners_csv:
            print(f"  INFO partners.csv não encontrado em {partners_csv}")

    # ---- prospects.csv (status forçado a Prospect) ----
    if prospects_csv and Path(prospects_csv).exists():
        print(f"[load_partners_sources] Lendo prospects: {prospects_csv} ...")
        df_raw = _read_simple_csv(prospects_csv, "prospects")
        df_raw["Status"] = "Prospect"
        for _, row in df_raw.iterrows():
            try:
                partners_obj.append(Partner.from_row(row, {}, {}, {}))
            except Exception as exc:
                sf_id = row.get("Id", "?")
                print(f"  WARN [prospects] Erro ao construir {sf_id}: {exc}")
        sources_used.append(f"prospects ({len(df_raw):,})")
    else:
        if prospects_csv:
            print(f"  INFO prospects.csv não encontrado em {prospects_csv}")

    # ---- webleads.csv (status=New, lead_source=Website Pardot Form) ----
    if webleads_csv and Path(webleads_csv).exists():
        print(f"[load_partners_sources] Lendo webleads: {webleads_csv} ...")
        df_raw = _read_simple_csv(webleads_csv, "webleads")
        df_raw["Status"]     = "New"
        df_raw["LeadSource"] = "Website Pardot Form"
        for _, row in df_raw.iterrows():
            try:
                partners_obj.append(Partner.from_row(row, {}, {}, {}))
            except Exception as exc:
                sf_id = row.get("Id", "?")
                print(f"  WARN [webleads] Erro ao construir {sf_id}: {exc}")
        sources_used.append(f"webleads ({len(df_raw):,})")
    else:
        if webleads_csv:
            print(f"  INFO webleads.csv não encontrado em {webleads_csv}")

    if not partners_obj:
        raise FileNotFoundError(
            "Nenhuma fonte de parceiros encontrada. Esperava pelo menos um "
            "dos arquivos: partners.csv, prospects.csv, webleads.csv."
        )

    # ------------------------------------------------------------------
    # 2. Deduplicar por salesforce_id (primeiro vence)
    # ------------------------------------------------------------------
    seen: set = set()
    unique: list[Partner] = []
    dupes = 0
    for p in partners_obj:
        sid = p.salesforce_id or ""
        if sid and sid in seen:
            dupes += 1
            continue
        if sid:
            seen.add(sid)
        unique.append(p)
    if dupes:
        print(f"  INFO {dupes} Id(s) duplicado(s) entre fontes — primeiro registro mantido.")

    print(
        f"[load_partners_sources] Fontes: {', '.join(sources_used)} "
        f"→ {len(unique):,} Partners únicos."
    )

    # ------------------------------------------------------------------
    # 3. Serializar para dados_mapa.json (mesmo artefato do modo Excel)
    # ------------------------------------------------------------------
    from datetime import datetime
    period = datetime.today().strftime("%Y-%m-%d : %Hh:%Mm")
    output_path = str(_cfg.DEST_FOLDER / "dados_mapa.json")
    serialize_to_json(unique, period, output_path)

    # ------------------------------------------------------------------
    # 4. Construir PartnerData
    # ------------------------------------------------------------------
    partner_data = _build_partner_data(unique)

    # ------------------------------------------------------------------
    # 5. Carregar jurisdições
    # ------------------------------------------------------------------
    print(f"[load_partners_sources] Lendo jurisdições de {j_path} ...")
    with open(j_path, "r", encoding="utf-8") as f:
        partner_data.jurisdictions = json.load(f)
    n_juris = len(partner_data.jurisdictions.get("features", []))
    print(f"   {n_juris} jurisdições carregadas.")

    print(
        f"[load_partners_sources] Concluído: "
        f"{len(partner_data.partners_df):,} operacionais | "
        f"{len(partner_data.web_leads_df):,} webleads | "
        f"{len(partner_data.no_coords_prospects_df):,} prospects sem coords."
    )
    return partner_data
