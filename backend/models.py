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

import config as configuration


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

class Config:
    """Configurações centralizadas do sistema."""

    BASE_PACKAGES        = configuration.BASE_PACKAGES
    BASE_PARTNERS        = configuration.BASE_PARTNERS
    BASE_JURISDICTION    = configuration.BASE_JURISDICTION
    DEST_FOLDER          = configuration.DEST_FOLDER
    CNPJ_DB_PATH         = getattr(configuration, "DB_EMPRESAS", None)
    H3_RES               = configuration.H3_RESOLUTION
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
    ADES_ACCOUNT_MANAGERS = configuration.ADES_ACCOUNT_MANAGERS
    BONUS_PER_OPEN       = 1500
    CLUSTER_PER_STATION  = getattr(configuration, "CLUSTER_PER_STATION", {})

    BDM_CLUSTERS: Dict[str, List[str]] = {
        "SP/SUL":              ["DBR9", "DSP2", "DSP4", "DSP5", "DPR2", "DFR2", "DRS5"],
        "RJ/CW":               ["DRJ3", "DBS5", "DGO2"],
        "BH":                  ["DMG2", "DBH5"],
        "RECIFE/JOAO PESSOA":  ["DPE4", "DPB3"],
        "FORTALEZA":           ["DCE3"],
        "ES/BA":               ["DES2", "DSA8"],
    }

    @staticmethod
    def get_bdm_cluster(station_code: str) -> str:
        for cluster, bases in Config.BDM_CLUSTERS.items():
            if station_code in bases:
                return cluster
        return "OUTROS"


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
    exitedDate: str         = ""
    decision_status: str    = ""
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
