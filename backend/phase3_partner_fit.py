"""
phase3_partner_fit.py
=====================
Fase 3 — Matching de parceiros existentes com vagas ideais.

Responsabilidade
----------------
- Para cada vaga ideal (IdealSlot) gerada pela Fase 2, encontrar o melhor
  parceiro existente que possa supri-la, seguindo a hierarquia de status.
- Classificar parceiros sem vaga proxima (excedentes ou fora de area).
- Atualizar ideal_supply.json com os matched_partner_id preenchidos.
- Retornar FitResult para consumo da Fase 5 (reports).

Criterio de elegibilidade (por vaga)
--------------------------------------
Um parceiro e elegivel para uma vaga se:
    h3.grid_distance(partner.origin_hex, slot.origin_hex) <= 1

Isso corresponde a o parceiro estar no mesmo hex da vaga OU em um dos
6 hexes vizinhos diretos (resolucao 9 ~ raio de 900m). Discutido e
aprovado na arquitetura da Fase 3.

Algoritmo de matching
----------------------
1. Ordenar todas as vagas por demanda decrescente (vagas criticas primeiro).
2. Para cada vaga:
   a. Buscar parceiros elegíveis nao alocados em grid_disk(slot.origin_hex, 1).
   b. Ordenar candidatos por: status_priority (asc) → grid_distance (asc).
   c. Atribuir o primeiro candidato disponível.
   d. Marcar parceiro como alocado (nao pode ser re-atribuido).
3. Parceiros nao alocados ao final sao classificados como:
   - "Excedente no territorio" se seu territorio tem todas as vagas preenchidas.
   - "Sem vaga proxima" se nenhuma vaga do territorio esta em grid_disk=1.
   - "Fora da area de atuacao" se nao pertence a nenhum territorio ativo.

Hierarquia de status (menor numero = maior prioridade)
-------------------------------------------------------
    1 = Active
    2 = Onboarding
    3 = BG Checks
    4 = Prospect        (identificado por jurisdicao, nao por station_code)
    5 = Inactive / Exited - Regretted

Decisoes por tipo de resultado
-------------------------------
    Parceiro matched    → decision = "Vinculado a vaga {slot_id}"
    Excedente           → decision = "Excedente no territorio — sem vaga disponivel"
    Sem vaga proxima    → decision = "Sem vaga ideal na vizinhanca (grid_disk=1)"
    Fora de area        → decision = "Fora da area de atuacao"
    Prospect rejeitado  → decision = "Pouca volumetria na area de atuacao"
    Inactive rejeitado  → decision = "Fora da area de atuacao"

Artefatos atualizados / gerados
---------------------------------
ideal_supply.json   <- matched_partner_id preenchido para slots cobertos
fit_result          <- objeto FitResult em memoria para a Fase 5
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import h3

from load_packages import PackageData
from load_partners import PartnerData, row_to_partner_metrics
from models import Allocation, Config, IdealSlot, PartnerMetrics
from phase1_territories import TerritoriesResult
from phase2_ideal_supply import IdealSupplyResult, load_ideal_supply


# ---------------------------------------------------------------------------
# HIERARQUIA DE STATUS
# ---------------------------------------------------------------------------

STATUS_PRIORITY: Dict[str, int] = {
    "Active":    1,
    "Onboarding": 2,
    "BG Checks": 3,
    "Prospect":  4,
    "Inactive":  5,
    "Exited":    5,   # apenas "Exited - Regretted" chega aqui
}

# Grupos operacionais que sao carregados por station_code diretamente
OPERATIONAL_STATUSES = {"Active", "Onboarding", "BG Checks"}
# Grupos que precisam de identificacao de base via jurisdicao
JURISDICTION_STATUSES = {"Prospect"}
# Grupos reativacao (exigem decisao_status especifico para Exited)
REACTIVATION_STATUSES = {"Inactive"}


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class TerritoryFit:
    """Resultado do matching para um territorio."""
    territory_id: str
    station_code: str
    bdm_cluster: str
    ctl_name: str

    # Vagas (vindas da Fase 2, com matched_partner_id ja preenchido)
    slots: List[IdealSlot] = field(default_factory=list)

    # Parceiros associados a este territorio (matched + excedentes)
    partners: List[PartnerMetrics] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return len(self.slots)

    @property
    def filled_slots(self) -> int:
        return sum(1 for s in self.slots if not s.is_open)

    @property
    def open_slots(self) -> int:
        return sum(1 for s in self.slots if s.is_open)

    @property
    def attainment(self) -> float:
        active = sum(1 for p in self.partners if p.status == "Active")
        return (active / self.total_slots * 100) if self.total_slots > 0 else 0.0
    
    @property
    def accuracy(self) -> float:
        active = sum(1 for p in self.partners if p.status == "Active")
        return ((active / self.filled_slots) * 100) if self.filled_slots > 0 else 0.0

    def partners_by_status(self, status: str) -> List[PartnerMetrics]:
        return [p for p in self.partners if p.status == status]


@dataclass
class FitResult:
    """Output completo da Fase 3."""

    # territory_id -> TerritoryFit
    territories: Dict[str, TerritoryFit] = field(default_factory=dict)

    # Parceiros fora de qualquer jurisdicao conhecida (territory_id = "Out of Jurisdiction")
    outside_jurisdiction: List[PartnerMetrics] = field(default_factory=list)
    
    # Parceiros dentro de jurisdicao mas sem match em vaga (alocados a territory_id)
    unassigned_by_territory: Dict[str, List[PartnerMetrics]] = field(default_factory=dict)

    def fits_for_station(self, station_code: str) -> List[TerritoryFit]:
        return [f for f in self.territories.values()
                if f.station_code == station_code]

    def all_partners(self) -> List[PartnerMetrics]:
        """Retorna TODOS os parceiros: matched + unassigned + out of jurisdiction."""
        partners = [p for fit in self.territories.values() for p in fit.partners]
        partners += [p for ps in self.unassigned_by_territory.values() for p in ps]
        partners += self.outside_jurisdiction
        return partners

    def summary(self) -> Dict[str, dict]:
        """Sumario por base: {station_code: {slots, filled, open, attainment}}"""
        result: Dict[str, dict] = defaultdict(lambda: {
            "slots": 0, "filled": 0, "open": 0,
            "active": 0, "onboarding": 0, "bg": 0,
            "prospects": 0, "inactives": 0,
        })
        for fit in self.territories.values():
            s = fit.station_code
            result[s]["slots"]     += fit.total_slots
            result[s]["filled"]    += fit.filled_slots
            result[s]["open"]      += fit.open_slots
            result[s]["active"]    += len(fit.partners_by_status("Active"))
            result[s]["onboarding"]+= len(fit.partners_by_status("Onboarding"))
            result[s]["bg"]        += len(fit.partners_by_status("BG Checks"))
            result[s]["prospects"] += len(fit.partners_by_status("Prospect"))
            result[s]["inactives"] += len([p for p in fit.partners
                                           if p.status in ("Inactive", "Exited")])
        return dict(result)


# ---------------------------------------------------------------------------
# HELPERS DE MATCHING
# ---------------------------------------------------------------------------

def _partner_eligible_hexes(origin_hex: str) -> Set[str]:
    """Retorna o conjunto de hexes em grid_disk=1 ao redor do parceiro."""
    return set(h3.grid_disk(origin_hex, 1))


def _build_hex_to_slots(
    slots: List[IdealSlot],
) -> Dict[str, List[IdealSlot]]:
    """
    Indice invertido: hex -> lista de slots cuja vizinhanca (grid_disk=1)
    inclui aquele hex.

    Permite lookup O(1): dado o origin_hex de um parceiro, quais slots
    ele pode cobrir?
    """
    index: Dict[str, List[IdealSlot]] = defaultdict(list)
    for slot in slots:
        for nb in h3.grid_disk(slot.origin_hex, 1):
            index[nb].append(slot)
    return index


def _match_station(
    station_code: str,
    territories_meta: List[dict],
    supply: IdealSupplyResult,
    partner_data: PartnerData,
    pkg: PackageData,
) -> Tuple[Dict[str, TerritoryFit], List[PartnerMetrics], Dict[str, List[PartnerMetrics]]]:
    """
    Executa o matching completo para uma base.

    Retorna
    -------
    (territory_fits, outside_jurisdiction_partners, unassigned_by_territory)
    onde unassigned_by_territory é {territory_id: [parceiros sem match]}
    """
    bdm_cluster = Config.get_bdm_cluster(station_code)

    # ── Coletar todos os slots da base ────────────────────────────────────
    all_slots: List[IdealSlot] = []
    for meta in territories_meta:
        all_slots.extend(supply.slots_for(meta["territory_id"]))

    # Ordenar por capacidade decrescente (vagas criticas = maior demanda primeiro)
    all_slots.sort(key=lambda s: s.capacity_s, reverse=True)

    # Indice hex -> slots candidatos
    hex_to_slots = _build_hex_to_slots(all_slots)

    # ── Coletar parceiros candidatos ──────────────────────────────────────
    # Parceiros operacionais (station_code direto)
    op_df = partner_data.partners_by_station(station_code)

    # Prospects identificados por jurisdicao
    all_prospects = partner_data.prospects_in_jurisdiction()
    prospects_df = all_prospects[all_prospects["identified_base"] == station_code].copy()

    # Inactives + Exited-Regretted por station_code
    inactive_df = partner_data.partners_df[
        (partner_data.partners_df["station_code"] == station_code)
        & (
            (partner_data.partners_df["status"] == "Inactive")
            | (
                (partner_data.partners_df["status"] == "Exited")
                & (partner_data.partners_df.get("decision_status", "") == "Exited - Regretted")
            )
        )
    ].copy()

    # Construir lista unificada de candidatos com prioridade
    # Estrutura: (priority, h3_origin, salesforce_id, row, entity_type, station)
    candidates: List[Tuple[int, str, str, object, str, str]] = []

    for _, row in op_df[op_df["status"].isin(OPERATIONAL_STATUSES)].iterrows():
        prio = STATUS_PRIORITY.get(str(row.get("status", "")), 99)
        candidates.append((prio, str(row.get("origin_hex", "")),
                           str(row.get("salesforce_id", "")),
                           row, "EXISTING", station_code))

    for _, row in prospects_df.iterrows():
        candidates.append((STATUS_PRIORITY["Prospect"],
                           str(row.get("origin_hex", "")),
                           str(row.get("salesforce_id", "")),
                           row, "PROSPECT", station_code))

    for _, row in inactive_df.iterrows():
        prio = STATUS_PRIORITY.get(str(row.get("status", "")), 5)
        candidates.append((prio, str(row.get("origin_hex", "")),
                           str(row.get("salesforce_id", "")),
                           row, "INACTIVE_EXITED", station_code))

    # ── Matching greedy ───────────────────────────────────────────────────
    # slot_id -> IdealSlot (modificavel)
    slot_map: Dict[str, IdealSlot] = {s.slot_id: s for s in all_slots}
    allocated_sids: Set[str] = set()   # salesforce_ids ja alocados
    allocated_slots: Set[str] = set()  # slot_ids ja preenchidos

    # Lista de PartnerMetrics resultantes (matched + nao matched)
    partner_results: List[PartnerMetrics] = []

    # Para cada slot (maior demanda primeiro), buscar melhor candidato
    for slot in all_slots:
        if slot.slot_id in allocated_slots:
            continue

        # Candidatos elegiveis: origin_hex em grid_disk(slot.origin_hex, 1)
        slot_neighbors = set(h3.grid_disk(slot.origin_hex, 1))
        eligible = [
            c for c in candidates
            if c[2] not in allocated_sids        # nao alocado
            and c[1] in slot_neighbors            # dentro da vizinhanca
        ]

        if not eligible:
            continue

        # Ordenar: prioridade de status (asc) → distancia H3 (asc)
        eligible.sort(key=lambda c: (
            c[0],
            h3.grid_distance(c[1], slot.origin_hex) if c[1] else 99,
        ))

        best = eligible[0]
        prio, origin_hex, sfid, row, entity_type, p_station = best

        # Determinar decision baseado em status (parceiro MATCHED com vaga)
        status_str = str(row.get("status", ""))
        if entity_type == "INACTIVE_EXITED":
            decision = f"Reavaliar possivel retorno - vaga {slot.slot_id}"
            optDecision = None
        elif entity_type == "PROSPECT":
            decision = f"Seguir cadastro - vaga {slot.slot_id}"
            optDecision = None
        elif status_str == "Active":
            decision = f"Vinculado a vaga {slot.slot_id}"
            optDecision = "Optimization suggested"
        elif status_str in ("Onboarding", "BG Checks"):
            decision = f"Vinculado a vaga {slot.slot_id}"
            optDecision = None
        else:
            decision = f"Vinculado a vaga {slot.slot_id}"
            optDecision = None

        pm = row_to_partner_metrics(
            row=row,
            entity_type=entity_type,
            station_code=p_station,
            decision=decision,
            radius_s=slot.radius_s,
            capacity_s=slot.capacity_s,
            optimization_decision=optDecision,
            allocations=[
                Allocation(hex_id=a.hex_id,
                           packages_assigned=a.packages_assigned)
                for a in slot.allocations
            ],
        )
        pm.matched_slot_id = slot.slot_id

        # Territorio deste slot
        territory_id = slot.bucket_id
        t_meta = next((m for m in territories_meta
                       if m["territory_id"] == territory_id), {})
        bucket_idx = int(territory_id.split("bucket-")[-1]) - 1
        pm.cluster_name = territory_id
        pm.bdm_cluster = bdm_cluster
        pm.ctl_name = f"CTL-{chr(65 + (bucket_idx // 5))}"

        partner_results.append(pm)
        allocated_sids.add(sfid)
        allocated_slots.add(slot.slot_id)
        slot.matched_partner_id = sfid

    # ── Parceiros nao alocados (sem match em vaga) ────────────────────────
    for prio, origin_hex, sfid, row, entity_type, p_station in candidates:
        if sfid in allocated_sids:
            continue

        status_str = str(row.get("status", ""))
        
        # Decision para parceiros NAO-MATCHED (baseado em status)
        if status_str == "Active":
            decision = "Nao esta em uma localizacao ideal"
        elif status_str == "Onboarding":
            decision = "Nao esta em uma localizacao ideal"
        elif status_str == "BG Checks":
            decision = "Nao esta em uma localizacao ideal"
        elif entity_type == "PROSPECT":
            decision = "Não Cadastar - Sem oportunidade proxima"
        elif entity_type == "INACTIVE_EXITED":
            decision = "Finalizar cadastro - Sem oportunidade proxima"
        else:
            decision = "Nao esta em uma localizacao ideal"

        pm = row_to_partner_metrics(
            row=row,
            entity_type=entity_type,
            station_code=p_station,
            decision=decision,
            radius_s=0,
            capacity_s=0,
        )
        pm.bdm_cluster = bdm_cluster

        # Associar ao territorio pelo hex de origem (sempre dentro de jurisdicao neste ponto)
        territory_id = _get_territory_for_partner(origin_hex, territories_meta)
        if territory_id:
            bucket_idx = int(territory_id.split("bucket-")[-1]) - 1
            pm.cluster_name = territory_id
            pm.ctl_name = f"CTL-{chr(65 + (bucket_idx // 5))}"

        partner_results.append(pm)

    # ── Parceiros fora de jurisdicao ──────────────────────────────────────
    outside_list: List[PartnerMetrics] = []
    outside_df = partner_data.prospects_outside_jurisdiction()
    for _, row in outside_df.iterrows():
        pm = row_to_partner_metrics(
            row=row, entity_type="PROSPECT",
            station_code="", decision="Fora de jurisdição",
        )
        pm.cluster_name = "Out of Jurisdiction"  # Territory especial
        outside_list.append(pm)

    # ── Montar TerritoryFit por territorio ────────────────────────────────
    territory_fits: Dict[str, TerritoryFit] = {}
    unassigned_by_tid: Dict[str, List[PartnerMetrics]] = defaultdict(list)
    
    for meta in territories_meta:
        tid = meta["territory_id"]
        bucket_idx = int(tid.split("bucket-")[-1]) - 1
        ctl_name = f"CTL-{chr(65 + (bucket_idx // 5))}"

        t_slots = supply.slots_for(tid)
        # Apenas matched partners (têm matched_slot_id)
        t_partners = [p for p in partner_results if p.cluster_name == tid and p.matched_slot_id]
        
        # Unmatched partners (sem matched_slot_id mas com cluster_name = tid)
        t_unmatched = [p for p in partner_results if p.cluster_name == tid and not p.matched_slot_id]
        
        if t_unmatched:
            unassigned_by_tid[tid] = t_unmatched

        territory_fits[tid] = TerritoryFit(
            territory_id=tid,
            station_code=station_code,
            bdm_cluster=bdm_cluster,
            ctl_name=ctl_name,
            slots=t_slots,
            partners=t_partners,  # Apenas matched
        )

    return territory_fits, outside_list, dict(unassigned_by_tid)


def _find_territory_for_hex(
    origin_hex: str,
    territories_meta: List[dict],
) -> Optional[str]:
    """Retorna o territory_id cujo hex_ids contem origin_hex, ou None."""
    for meta in territories_meta:
        if origin_hex in meta.get("hex_ids", []):
            return meta["territory_id"]
    return None


def _get_territory_for_partner(
    origin_hex: str,
    territories_meta: List[dict],
) -> Optional[str]:
    """
    Encontra o territory_id mais apropriado para um parceiro (dentro de jurisdicao).
    
    Ordem:
    1. Territory que contem o hex
    2. Territory cujo slot esta em grid_disk=1
    3. Territory mais proximo (menor distancia do centroide)
    
    Retorna None se nenhum territory encontrado.
    """
    if not territories_meta:
        return None
    
    # 1. Busca exata: hex pertence ao territory
    tid = _find_territory_for_hex(origin_hex, territories_meta)
    if tid:
        return tid
    
    # 2. Busca por grid_disk=1 (vizinhos)
    partner_neighbors = set(h3.grid_disk(origin_hex, 1))
    for meta in territories_meta:
        for h in meta.get("hex_ids", []):
            if h in partner_neighbors:
                return meta["territory_id"]
    
    # 3. Territory mais proximo (centroide)
    lat, lon = h3.cell_to_latlng(origin_hex)
    min_tid = None
    min_dist = float("inf")
    
    for meta in territories_meta:
        cent_lat = meta.get("centroid_lat", 0)
        cent_lon = meta.get("centroid_lon", 0)
        dist = (lat - cent_lat) ** 2 + (lon - cent_lon) ** 2
        if dist < min_dist:
            min_dist = dist
            min_tid = meta["territory_id"]
    
    return min_tid


# ---------------------------------------------------------------------------
# ATUALIZACAO DO IDEAL_SUPPLY.JSON
# ---------------------------------------------------------------------------

def _update_supply_file(
    supply: IdealSupplyResult,
    output_dir: Path,
) -> None:
    """
    Re-serializa ideal_supply.json com matched_partner_id preenchido.
    Mantem estrutura identica — apenas atualiza o campo de cada slot.
    """
    path = output_dir / "ideal_supply.json"
    if not path.exists():
        return

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Indice rapido slot_id -> matched_partner_id
    slot_match: Dict[str, Optional[str]] = {
        s.slot_id: s.matched_partner_id
        for s in supply.all_slots
    }

    for tid, slot_list in raw.get("slots", {}).items():
        for slot_dict in slot_list:
            sid = slot_dict.get("slot_id")
            if sid in slot_match:
                slot_dict["matched_partner_id"] = slot_match[sid]

    raw["_metadata"]["last_fit_at"] = datetime.now().isoformat(timespec="seconds")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    print(f"  ideal_supply.json atualizado com matched_partner_ids.")


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def run_phase3(
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    partner_data: PartnerData,
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
) -> FitResult:
    """
    Executa a Fase 3: matching de parceiros com vagas ideais.

    Parametros
    ----------
    territories  : TerritoriesResult   Output da Fase 1.
    supply       : IdealSupplyResult   Output da Fase 2 (load_ideal_supply()).
    partner_data : PartnerData         Output de load_partners().
    pkg          : PackageData         Output de load_packages() — para pkg.days.
    output_dir   : str, opcional       Para atualizar ideal_supply.json.
    stations     : list, opcional      Filtrar bases. Default: todas.

    Retorna
    -------
    FitResult com territories (Dict[territory_id, TerritoryFit]) e
    outside_jurisdiction pronto para consumo da Fase 5.
    """
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    target_stations = stations or territories.stations

    print(f"\n{'='*60}")
    print(f"  FASE 3 — MATCHING PARCEIROS x VAGAS IDEAIS")
    print(f"  Hierarquia: Active > Onboarding > BG Checks > Prospect > Inactive")
    print(f"  Elegibilidade: grid_disk(slot.origin_hex, 1)")
    print(f"  Bases: {target_stations}")
    print(f"{'='*60}")

    fit_result = FitResult()

    for station in target_stations:
        territories_meta = territories.territories_for(station)
        if not territories_meta:
            print(f"  WARN [{station}] Sem territorios — pulando.")
            continue

        n_slots_station = sum(
            len(supply.slots_for(m["territory_id"])) for m in territories_meta
        )
        print(f"\n  [{station}] {len(territories_meta)} territorios | "
              f"{n_slots_station} vagas ideais")

        territory_fits, outside, unassigned = _match_station(
            station_code=station,
            territories_meta=territories_meta,
            supply=supply,
            partner_data=partner_data,
            pkg=pkg,
        )

        fit_result.territories.update(territory_fits)
        fit_result.outside_jurisdiction.extend(outside)
        for tid, partners in unassigned.items():
            if tid not in fit_result.unassigned_by_territory:
                fit_result.unassigned_by_territory[tid] = []
            fit_result.unassigned_by_territory[tid].extend(partners)

        # Sumario da base
        for fit in sorted(territory_fits.values(), key=lambda f: f.territory_id):
            active     = len(fit.partners_by_status("Active"))
            onboarding = len(fit.partners_by_status("Onboarding"))
            bg         = len(fit.partners_by_status("BG Checks"))
            prospects  = len(fit.partners_by_status("Prospect"))
            inactives  = len([p for p in fit.partners
                              if p.status in ("Inactive", "Exited")])
            print(
                f"    {fit.territory_id}: "
                f"{fit.filled_slots}/{fit.total_slots} vagas preenchidas | "
                f"Ativos={active} Onb={onboarding} BG={bg} "
                f"Prosp={prospects} Inat={inactives} | "
                f"Attainment={fit.attainment:.1f}%"
                f"Accuracy={fit.accuracy:.1f}%"
            )

    # Atualizar ideal_supply.json com matched_partner_ids
    _update_supply_file(supply, out_dir)

    # Sumario global
    summ = fit_result.summary()
    total_slots  = sum(v["slots"]  for v in summ.values())
    total_filled = sum(v["filled"] for v in summ.values())
    total_open   = sum(v["open"]   for v in summ.values())
    pct = (total_filled / total_slots * 100) if total_slots else 0

    print(f"\n{'='*60}")
    print(f"  FASE 3 CONCLUIDA")
    print(f"  {total_slots} vagas | {total_filled} preenchidas | "
          f"{total_open} em aberto | Attainment global: {pct:.1f}%")
    if fit_result.outside_jurisdiction:
        print(f"  {len(fit_result.outside_jurisdiction)} prospects fora de jurisdicao")
    print(f"{'='*60}\n")

    return fit_result
