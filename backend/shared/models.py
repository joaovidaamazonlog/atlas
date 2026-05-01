"""
models.py
=========
Modelos de dados centrais do sistema de otimização.

Contém todas as dataclasses e a classe Config extraídas de optimization_hub.py.
Todos os demais módulos importam daqui — nunca de optimization_hub.py diretamente.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import shared.config as configuration


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

class Config:
    """Configurações centralizadas do sistema."""

    BASE_PACKAGES        = configuration.BASE_PACKAGES
    BASE_PARTNERS        = configuration.BASE_PARTNERS
    BASE_PARTNERS_CSV    = getattr(configuration, "BASE_PARTNERS_CSV", None)
    BASE_PROSPECTS_CSV   = getattr(configuration, "BASE_PROSPECTS_CSV", None)
    BASE_WEBLEADS_CSV    = getattr(configuration, "BASE_WEBLEADS_CSV", None)
    BASE_JURISDICTION    = configuration.BASE_JURISDICTION
    DEST_FOLDER          = configuration.DEST_FOLDER
    CNPJ_DB_PATH         = getattr(configuration, "DB_EMPRESAS", None)
    H3_RES               = configuration.H3_RESOLUTION

    # Janela de dias considerada pela Fase 6 (deliveries — IHS vs DSP).
    # Usada em load_deliveries e em outros lugares que agregam pacotes
    # por canal/parceiro. Default 15 dias se não houver config.
    PACKAGE_HISTORY_DAYS = getattr(configuration, "PACKAGE_HISTORY_DAYS", 15)

    # Aliases de bases satélite → canônica (ex: XBA1 → DSA8, HSP5 → DSP5).
    # Re-exportado da config de módulo para que load_deliveries e outros
    # consumidores que usam `Config.STATION_ALIASES` enxerguem o mapa.
    # A SATELLITE_MAP derivada abaixo permanece como índice reverso.
    STATION_ALIASES: Dict[str, str] = getattr(
        configuration, "STATION_ALIASES", {}
    )
    # Resolucao H3 por base — permite usar res 8 em bases grandes (menos hexes
    # perifericos, poligonos mais limpos) e res 9 em bases menores (granularidade).
    # Formato: {"DSP2": 8, "DSP4": 8}  — bases nao listadas usam H3_RES global.
    H3_RES_PER_STATION: Dict[str, int] = getattr(
        configuration, "H3_RES_PER_STATION", {}
    )

    @staticmethod
    def get_h3_res(station_code: str) -> int:
        """Retorna a resolucao H3 para uma base especifica."""
        return Config.H3_RES_PER_STATION.get(station_code, Config.H3_RES)
    MIN_CAP              = configuration.MIN_CAPACITY
    MAX_CAP              = configuration.MAX_CAPACITY
    CAPACITIES           = configuration.CAPACITIES
    RADII                = configuration.RADII_M
    BONUS_PER_OPEN       = 1500
    CLUSTER_PER_STATION  = getattr(configuration, "CLUSTER_PER_STATION", {})

    # BDM_CLUSTERS derivado do TEAM — não editar manualmente.
    # Formato: {region: [station_code, ...]}
    BDM_CLUSTERS: Dict[str, List[str]] = {
        bdm["region"]: bdm["stations"]
        for bdm in configuration.TEAM
        if bdm.get("region") and bdm.get("stations")
    }

    # Índice reverso: base canônica → lista de satélites
    # Ex: {"DSA8": ["XBA1"], "DRJ3": ["XRJ2", "XRJ3", "XRJ4"], ...}
    SATELLITE_MAP: Dict[str, List[str]] = {}
    for _sat, _canonical in configuration.STATION_ALIASES.items():
        SATELLITE_MAP.setdefault(_canonical, []).append(_sat)

    @staticmethod
    def get_satellites(station_code: str) -> List[str]:
        """Retorna a lista de bases satélite de uma base canônica."""
        return Config.SATELLITE_MAP.get(station_code, [])

    @staticmethod
    def get_bdm_cluster(station_code: str) -> str:
        """Retorna a região (nome do BDM) responsável pela base."""
        info = configuration.get_bdm_for_station(station_code)
        region = info.get("region", "")
        if region:
            return region
        # fallback: varrer BDM_CLUSTERS
        for cluster, bases in Config.BDM_CLUSTERS.items():
            if station_code in bases:
                return cluster
        return "OUTROS"

    # Atalhos para as funções utilitárias do TEAM
    get_ade_for_territory      = staticmethod(configuration.get_ade_for_territory)
    get_ctl_for_station        = staticmethod(configuration.get_ctl_for_station)
    get_bdm_for_station        = staticmethod(configuration.get_bdm_for_station)
    get_owner_id_for_territory = staticmethod(configuration.get_owner_id_for_territory)
    get_name_for_alias         = staticmethod(configuration.get_name_for_alias)


# ---------------------------------------------------------------------------
# DATACLASSES DE ALOCAÇÃO
# ---------------------------------------------------------------------------

@dataclass
class Allocation:
    """Demanda de um hexágono atribuída a um parceiro/vaga."""
    hex_id: str
    packages_assigned: int


# ---------------------------------------------------------------------------
# VAGA IDEAL (output da Fase 2)
# ---------------------------------------------------------------------------

@dataclass
class IdealSlot:
    """
    Ponto ideal de parceiro identificado pelo solver na Fase 2.

    Cada slot representa UMA oportunidade de parceiro dentro de um território.
    A Fase 3 tentará associar um parceiro existente a cada slot.
    """
    slot_id: str                        # identificador único: "{station}_{bucket}_{seq}"
    station_code: str
    bucket_id: str                      # ID estável do território (ex: "DSP2_T03")
    origin_hex: str                     # hex centróide da área de atuação ideal
    radius_s: int                       # raio sugerido em metros
    capacity_s: int                     # capacidade sugerida em pacotes/dia
    lat: float
    lon: float
    allocations: List[Allocation] = field(default_factory=list)
    matched_partner_id: Optional[str] = None   # preenchido na Fase 3

    @property
    def total_load(self) -> int:
        return sum(a.packages_assigned for a in self.allocations)

    @property
    def is_open(self) -> bool:
        """True se o slot ainda não tem parceiro associado."""
        return self.matched_partner_id is None


# ---------------------------------------------------------------------------
# PARCEIRO
# ---------------------------------------------------------------------------

@dataclass
class PartnerMetrics:
    """Dados detalhados de um parceiro (existente ou potencial)."""

    origin_hex: str
    station_code: str
    radius_s: int
    capacity_s: int
    entity_type: str    # "EXISTING" | "INACTIVE_EXITED" | "PROSPECT" | "NEW PARTNER" | "WEB_LEAD"
    status: str         # "Active" | "Onboarding" | "BG Checks" | "Prospect" | "Inactive" | "Exited"

    partner_name: str       = ""
    decision: str           = ""
    reason: str             = ""
    cluster_name: str       = "N/A"
    ctl_name: str           = "N/A"
    bdm_cluster: str        = "N/A"
    lat: float              = 0.0
    lon: float              = 0.0
    popup: str              = ""
    tooltip: str            = ""
    telefone: str           = ""
    salesforce_id: str      = ""
    jurisdiction_type: str  = ""
    launch_date: str        = ""
    exitedDate: str         = ""   # mantido por compatibilidade — use exited_date em código novo
    exited_date: str        = ""
    decision_status: str    = ""
    decision_reason_code: str = ""
    supply_run: str         = ""
    hub_delivey_initiatives: str = ""
    HCP_rate_card: str      = ""
    HCP_host_partner: str   = ""
    zip_code: str           = ""
    city: str               = ""
    owner_id: Optional[str] = None
    store_id: Optional[str] = None
    radius_a: Optional[int] = None
    capacity_a: Optional[int] = None
    bucket: Optional[str]   = None
    matched_slot_id: Optional[str] = None   # preenchido na Fase 3
    allocations: List[Allocation] = field(default_factory=list)
    adv_opportunity: Optional[dict] = None  # preenchido na Fase 3.5

    @property
    def total_load(self) -> int:
        return sum(a.packages_assigned for a in self.allocations)

    # Prioridade para matching na Fase 3 (menor = maior prioridade)
    STATUS_PRIORITY: Dict[str, int] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        # field com default_factory não funciona para Dict em class body, por isso aqui
        object.__setattr__(self, "STATUS_PRIORITY", {
            "Active":    1,
            "Onboarding": 2,
            "BG Checks": 3,
            "Prospect":  4,
            "Inactive":  5,
            "Exited":    6,
        })

    @property
    def match_priority(self) -> int:
        return self.STATUS_PRIORITY.get(self.status, 99)


# ---------------------------------------------------------------------------
# MÉTRICAS AGREGADAS
# ---------------------------------------------------------------------------

@dataclass
class TerritoryMetrics:
    """
    Métricas de um território (bucket) — usado em reports das Fases 3-5.

    Substitui ClusterMetrics com nomenclatura mais clara e campos
    alinhados à nova arquitetura de fases.
    """
    station_code: str
    bucket_id: str          # ID estável (ex: "DSP2_T03")
    bucket_name: str        # nome legível (ex: "bucket-3")
    bdm_cluster: str
    ctl_name: str

    # Demanda
    total_demand: int       # pacotes/período (total bruto, não média)
    total_demand_daily: float  # total_demand / dias do período

    # Vagas ideais (Fase 2)
    ideal_slots: int

    # Cobertura por parceiros (Fase 3)
    active_partners: int        = 0
    onboarding_partners: int    = 0
    bg_checks_partners: int     = 0
    prospects_to_approve: int   = 0
    inactives_to_reactivate: int = 0
    open_slots: int             = 0   # slots sem parceiro associado

    partners: List[PartnerMetrics] = field(default_factory=list)

    @property
    def total_existing(self) -> int:
        return (self.active_partners + self.onboarding_partners +
                self.bg_checks_partners + self.prospects_to_approve +
                self.inactives_to_reactivate)

    @property
    def attainment(self) -> float:
        if self.ideal_slots == 0:
            return 0.0
        return self.active_partners / self.ideal_slots * 100
    
    @property
    def accuracy(self) -> float:
        if self.ideal_slots == 0:
            return 0.0
        return (self.ideal_slots - self.open_slots) / self.ideal_slots * 100


# Mantido para compatibilidade com ReportGenerator existente durante migração
@dataclass
class ClusterMetrics:
    """Métricas de uma carteira operacional (Bucket). Mantido por compatibilidade."""
    base: str
    bdm_cluster: str
    ctl_name: str
    cluster_name: str
    total_demand: int
    total_expected_partners: int
    active_partners: int
    onboarding_partners: int
    bg_chacks_partners: int
    prospects_to_approve: int
    inactives_to_reactivate: int
    new_partners: int
    attainment_percentage: float
    partners: List[PartnerMetrics] = field(default_factory=list)


@dataclass
class BaseMetrics:
    """Métricas consolidadas de uma base operacional."""
    total_demand: int
    existing_absorbed: int
    prospect_reserved: int
    inactive_reserved: int
    new_allocated: int
    residual: int
    active_partners_count: int
    onboarding_partners_count: int
    inactive_partners_count: int
    vetting_partners_count: int
    new_partners_count: int
    avg_load: float
    avg_radius: float
    cluster_count: int
    avg_partners_per_cluster: float


@dataclass
class OptimizationReport:
    """Relatório final de otimização por base."""
    station_code: str
    bdm_cluster: str
    existing_partners: List[PartnerMetrics]
    inactive_partners: List[PartnerMetrics]
    prospect_partners: List[PartnerMetrics]
    new_partners: List[PartnerMetrics]
    demand_summary: Dict[str, Dict]
    hex_to_cluster: Dict[str, str]
    base_metrics: BaseMetrics
    cluster_metrics: Dict[str, ClusterMetrics] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# TERRITORIES RESULT  (movido de phase1_territories.py)
# ---------------------------------------------------------------------------

@dataclass
class TerritoriesResult:
    """Resultado do setup de territórios — carregado pelo modo daily."""

    # Indice principal: territory_id -> metadados
    territory_index: Dict[str, dict] = field(default_factory=dict)

    # Lookup rapido: hex_id -> territory_id  (usado pelas fases seguintes)
    hex_to_territory: Dict[str, str] = field(default_factory=dict)

    # Caminhos dos artefatos persistidos
    geojson_path: Optional[Path] = None
    index_path: Optional[Path] = None

    @property
    def stations(self) -> List[str]:
        seen = []
        for meta in self.territory_index.values():
            s = meta["station_code"]
            if s not in seen:
                seen.append(s)
        return seen

    def territories_for(self, station_code: str) -> List[dict]:
        return [m for m in self.territory_index.values()
                if m["station_code"] == station_code]

    def territory_demand_map(self, station_code: str) -> Dict[str, int]:
        """Retorna {territory_id: total_demand} para uma base."""
        return {
            tid: meta["total_demand"]
            for tid, meta in self.territory_index.items()
            if meta["station_code"] == station_code
        }


def load_territories(output_dir: str = None) -> "TerritoriesResult":
    """
    Carrega territories_index.json sem re-rodar o setup.
    Usado pelo modo daily do orquestrador.
    Levanta FileNotFoundError se o setup ainda não foi executado.

    Remap de satélites
    ------------------
    Territórios cujo station_code é uma base satélite (ex: XBA1) têm o
    station_code substituído pela base canônica (ex: DSA8) em memória,
    via STATION_ALIASES. O arquivo em disco não é alterado.
    Isso permite que os buckets das satélites apareçam como buckets da
    base canônica em todos os filtros e relatórios, sem rodar setup novamente.
    """
    out_dir    = Path(output_dir or Config.DEST_FOLDER)
    index_path = out_dir / "territories_index.json"
    geojson_path = out_dir / "territories.geojson"

    if not index_path.exists():
        raise FileNotFoundError(
            f"territories_index.json nao encontrado em {out_dir}.\n"
            "Execute o modo 'setup' do orquestrador para gerar os territorios."
        )

    print(f"[load_territories] Carregando {index_path} ...")
    with open(index_path, "r", encoding="utf-8") as f:
        territory_index = json.load(f)

    # Remap em memória: satélite → canônica
    # Fonte primária: campo `canonical_base` (novo, escrito pelo setup).
    # Fallback: STATION_ALIASES (retrocompatibilidade com arquivos antigos).
    aliases = getattr(configuration, "STATION_ALIASES", {})
    n_remapped = 0
    for meta in territory_index.values():
        original = meta.get("station_code", "")
        # Fonte primária: campo canonical_base presente no arquivo
        canonical = meta.get("canonical_base")
        # Fallback para arquivos antigos sem canonical_base
        if not canonical and aliases:
            canonical = aliases.get(original)
        if canonical and canonical != original:
            meta["station_code"] = canonical
            # Preservar canonical_base explicitamente após o remap
            meta["canonical_base"] = canonical
            # Atualizar bdm_cluster para refletir a base canônica
            bdm_info = configuration.get_bdm_for_station(canonical)
            if bdm_info.get("region"):
                meta["bdm_cluster"] = bdm_info["region"]
            n_remapped += 1
    if n_remapped:
        print(f"  Satélites: {n_remapped} territórios remapeados para "
              f"bases canônicas (em memória).")

    hex_to_territory: Dict[str, str] = {}
    for territory_id, meta in territory_index.items():
        for hex_id in meta.get("hex_ids", []):
            hex_to_territory[hex_id] = territory_id

    result = TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory=hex_to_territory,
        geojson_path=geojson_path if geojson_path.exists() else None,
        index_path=index_path,
    )

    print(f"  {len(territory_index)} territorios | "
          f"{len(hex_to_territory):,} hexes carregados.")
    return result


# ---------------------------------------------------------------------------
# PROSPECT CANDIDATE  (output do cnpj_lookup.py)
# ---------------------------------------------------------------------------

@dataclass
class ProspectCandidate:
    """
    Empresa encontrada no banco CNPJ da Receita Federal como candidata
    a parceiro logístico para um slot ideal sem match.
    """
    cnpj:              str
    razao_social:      str
    porte_empresa:     str          # "01"=N/I, "03"=ME, "05"=EPP
    tipo_logradouro:   str
    logradouro:        str
    numero:            str
    complemento:       str
    bairro:            str
    cep:               str
    uf:                str
    municipio:         str
    telefone_1:        str
    telefone_2:        str
    email:             str
    responsavel:       str          # nome do sócio/responsável principal
    cnae_principal:    str
    slot_id:           str          # slot ideal que originou a busca
    territory_id:      str
    station_code:      str

    @property
    def porte_descricao(self) -> str:
        return {"01": "Não informado", "03": "ME", "05": "EPP"}.get(
            self.porte_empresa, self.porte_empresa
        )

    @property
    def endereco_completo(self) -> str:
        parts = [
            f"{self.tipo_logradouro} {self.logradouro}".strip(),
            self.numero,
            self.complemento,
            self.bairro,
            f"{self.municipio}/{self.uf}",
            f"CEP {self.cep}",
        ]
        return ", ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# PARTNER  (modelo unificado — pipeline refatorado)
# ---------------------------------------------------------------------------

_PHONE_TRANS = str.maketrans({"(": "", ")": "", " ": "", "-": "", "+": ""})

_DS_REMAP = {
    "HSP2": "DSP2", "HSP3": "DSP3", "HSP5": "DSP5", "HBH5": "DBH5",
    "HFO3": "DCE3", "HVI2": "DES2", "HRJ3": "DRJ3", "HGO2": "DGO2",
    "HBS5": "DBS5", "HPE4": "DPE4", "HPR2": "DPR2", "HRS5": "DRS5",
    "HPB3": "DPB3", "HSV8": "DSA8",
}


def _clean(value, default=None):
    """Converte NaN/NaT/None para default; preserva demais valores."""
    try:
        import pandas as _pd
        if _pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _clean_str(value) -> Optional[str]:
    """Retorna string limpa ou None — nunca 'nan'/'None'/'NaN'."""
    v = _clean(value)
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in ("nan", "none", "nat", "") else s


def _clean_float(value) -> Optional[float]:
    """Retorna float ou None."""
    v = _clean(value)
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _clean_int(value, default: int = 0) -> int:
    """Retorna int ou default."""
    v = _clean(value)
    if v is None:
        return default
    try:
        f = float(str(v).replace(",", "."))
        return int(f)
    except (ValueError, TypeError):
        return default


@dataclass
class Partner:
    """
    Modelo unificado de parceiro — construído a partir do Excel e
    serializado diretamente para dados_mapa.json (Schema_Limpo).

    Substitui a cadeia DataProcessor → JsonGenerator → load_partners(JSON).
    """
    salesforce_id:          str
    store_id:               Optional[str]
    name:                   str
    status:                 str
    lead_source:            Optional[str]
    lat:                    Optional[float]
    lon:                    Optional[float]
    zip_code:               Optional[str]
    city:                   Optional[str]
    state:                  Optional[str]
    delivery_station:       str
    supply_run:             Optional[str]
    radius:                 int
    capacity:               int
    bucket:                 Optional[str]
    jurisdiction_type:      Optional[str]
    hub_delivey_initiatives: Optional[str]
    HCP_rate_card:          Optional[str]
    HCP_host_partner:       Optional[str]
    launch_date:            Optional[str]
    exited_date:            Optional[str]
    decision_status:        Optional[str]
    decision_reason_code:   Optional[str]
    telefone:               Optional[str]
    owner_id:               Optional[str]
    tooltip:                str
    adv_opportunity:        Optional[dict] = None  # preenchido na Fase 3.5

    # ------------------------------------------------------------------
    # Construção a partir de uma linha do DataFrame consolidado
    # ------------------------------------------------------------------

    @classmethod
    def from_row(
        cls,
        row,                        # pd.Series
        station_map: dict,          # {station_id: station_name}
        jurisdictions_map: dict,    # {jurisdiction_id: bucket_name}
        host_map: dict,             # {salesforce_id: name}  (active partners)
    ) -> "Partner":
        from shared.utils.formatters import format_date_to_str

        # Coordenadas
        lat = _clean_float(row.get("Latitude"))
        lon = _clean_float(row.get("Longitude"))

        # Delivery Station: Id → Name → remap legado
        raw_ds = _clean_str(row.get("Delivery Station")) or ""
        ds = station_map.get(raw_ds, raw_ds)
        ds = _DS_REMAP.get(ds, ds)

        # Bucket via Jurisdiction Id → Name[5:]
        raw_jur = _clean_str(row.get("Jurisdiction"))
        bucket = jurisdictions_map.get(raw_jur) if raw_jur else None
        # fallback: campo Bucket já resolvido
        if bucket is None:
            bucket = _clean_str(row.get("Bucket"))

        # HCP Host Partner: Id → Name
        raw_host = _clean_str(row.get("HCP Host Partner"))
        hcp_host = host_map.get(raw_host, raw_host) if raw_host else None

        # Telefone normalizado
        raw_phone = _clean_str(row.get("Phone"))
        telefone = raw_phone.translate(_PHONE_TRANS) if raw_phone else None

        # Datas
        launch_date = format_date_to_str(row.get("Launch Date"))
        launch_date = None if launch_date == "TBC" else launch_date
        exited_date = format_date_to_str(row.get("Exit_Date__c"))
        exited_date = None if exited_date == "TBC" else exited_date

        # Campos simples
        sf_id   = _clean_str(row.get("Id")) or ""
        name    = _clean_str(row.get("Name")) or ""
        status  = _clean_str(row.get("Status")) or ""
        store_id = _clean_str(row.get("StoreID"))

        hub_init = _clean_str(row.get("Hub Delivery Initiatives"))

        tooltip = (
            f"ID: {store_id or ''} | "
            f"Name: {name} | "
            f"HUB Delivery Initiatives: {hub_init or ''}"
        )

        return cls(
            salesforce_id           = sf_id,
            store_id                = store_id,
            name                    = name,
            status                  = status,
            lead_source             = _clean_str(row.get("LeadSource")),
            lat                     = lat,
            lon                     = lon,
            zip_code                = _clean_str(row.get("CEP")),
            city                    = _clean_str(row.get("Cidade")),
            state                   = _clean_str(row.get("Estado")),
            delivery_station        = ds,
            supply_run              = _clean_str(row.get("Supply Run")),
            radius                  = _clean_int(row.get("Radius"), default=1500),
            capacity                = _clean_int(row.get("Volume Cap"), default=42),
            bucket                  = bucket,
            jurisdiction_type       = _clean_str(row.get("Jurisdiction Type")),
            hub_delivey_initiatives = hub_init,
            HCP_rate_card           = _clean_str(row.get("HCP Rate Card")),
            HCP_host_partner        = hcp_host,
            launch_date             = launch_date,
            exited_date             = exited_date,
            telefone                = telefone,
            owner_id                = _clean_str(row.get("OwnerId")),
            decision_status         = _clean_str(row.get("Decision_Status__c")),
            decision_reason_code    = _clean_str(row.get("Decision_Reason_Code__c")),
            tooltip                 = tooltip,
        )

    # ------------------------------------------------------------------
    # Serialização para o Schema_Limpo
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa para o formato exato do Schema_Limpo (JSON-safe)."""
        return {
            "salesforce_id":           self.salesforce_id,
            "store_id":                self.store_id,
            "name":                    self.name,
            "status":                  self.status,
            "lead_source":             self.lead_source,
            "lat":                     self.lat,
            "lon":                     self.lon,
            "zip_code":                self.zip_code,
            "city":                    self.city,
            "state":                   self.state,
            "delivery_station":        self.delivery_station,
            "supply_run":              self.supply_run,
            "radius":                  self.radius,
            "capacity":                self.capacity,
            "bucket":                  self.bucket,
            "jurisdiction_type":       self.jurisdiction_type,
            "hub_delivey_initiatives": self.hub_delivey_initiatives,
            "HCP_rate_card":           self.HCP_rate_card,
            "HCP_host_partner":        self.HCP_host_partner,
            "launch_date":             self.launch_date,
            "exited_date":             self.exited_date,
            "telefone":                self.telefone,
            "owner_id":                self.owner_id,
            "decision_status":         self.decision_status,
            "decision_reason_code":    self.decision_reason_code,
            "tooltip":                 self.tooltip,
            "adv_opportunity":         self.adv_opportunity,
        }
