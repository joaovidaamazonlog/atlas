"""
phase2_ideal_supply.py
======================
Fase 2 — Identificacao dos pontos ideais de parceiros por territorio.

Responsabilidade
----------------
- Ler os territorios persistidos pela Fase 1 (territories_index.json).
- Para cada territorio, rodar o solver CP-SAT para encontrar os pontos
  ideais onde um parceiro logistico deveria estar alocado.
- Persistir ideal_supply.json para consumo das Fases 3-5.

Diferenca critica em relacao ao solver original (optimization_hub.py)
----------------------------------------------------------------------
O solver original rodava sobre a demanda RESIDUAL (apos parceiros existentes
consumirem parte da demanda). Isso distorcia o resultado: areas bem cobertas
produziam menos vagas ideais, mesmo que a cobertura fosse sub-otima.

Aqui o solver roda sobre a demanda TOTAL BRUTA do territorio. Isso define
o cenario verdadeiramente ideal, sem contaminacao pelo estado atual da rede.
A Fase 3 e quem faz o matching de parceiros existentes com essas vagas.

Logica do solver (por territorio)
----------------------------------
Loop greedy com CP-SAT por semente:
  1. Semente = hex com maior demanda residual no territorio.
  2. CP-SAT escolhe o menor raio possivel que permita atingir MIN_CAP,
     maximizando pacotes alocados com penalidade crescente por raio maior.
  3. Alocacoes extraidas e demanda local decrementada.
  4. Repetir ate nao restar demanda >= MIN_CAP em nenhum hex.

Cada iteracao bem-sucedida gera um IdealSlot.

Paralelismo
-----------
O solver roda por territorio. Territorios de bases diferentes sao
processados em paralelo via ProcessPoolExecutor.
Territorios da mesma base rodam sequencialmente (o solver e rapido
o suficiente; paralelismo intra-base causaria conflitos de demanda).

Artefato gerado
---------------
ideal_supply.json
    Dict indexado por territory_id com lista de slots ideais.

    {
      "DSP2_T01": [
        {
          "slot_id":      "DSP2_T01_S01",
          "station_code": "DSP2",
          "territory_id": "DSP2_T01",
          "origin_hex":   "8a2ea...",
          "radius_s":     1000,
          "capacity_s":   42,
          "lat":          -23.55,
          "lon":          -46.63,
          "allocations":  [{"hex_id": "...", "packages_assigned": 10}, ...]
        },
        ...
      ],
      ...
    }

Como usar
---------
    from load_packages import load_packages
    from phase1_territories import load_territories
    from phase2_ideal_supply import run_phase2

    pkg    = load_packages()
    terr   = load_territories()
    supply = run_phase2(terr, pkg, output_dir="output/")
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import h3
from ortools.sat.python import cp_model

from models import Allocation, Config, IdealSlot, TerritoriesResult
from load_packages import PackageData


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class IdealSupplyResult:
    """Output da Fase 2."""

    # territory_id -> lista de slots ideais
    slots_by_territory: Dict[str, List[IdealSlot]] = field(default_factory=dict)

    # Caminho do artefato persistido
    supply_path: Optional[Path] = None

    @property
    def all_slots(self) -> List[IdealSlot]:
        return [s for slots in self.slots_by_territory.values() for s in slots]

    @property
    def open_slots(self) -> List[IdealSlot]:
        return [s for s in self.all_slots if s.is_open]

    def slots_for(self, territory_id: str) -> List[IdealSlot]:
        return self.slots_by_territory.get(territory_id, [])

    def slots_for_station(self, station_code: str) -> List[IdealSlot]:
        return [
            s for s in self.all_slots
            if s.station_code == station_code
        ]

    def summary(self) -> Dict[str, int]:
        """Retorna {territory_id: n_slots} para todos os territorios."""
        return {tid: len(slots) for tid, slots in self.slots_by_territory.items()}


# ---------------------------------------------------------------------------
# WORKER CP-SAT (top-level para compatibilidade com multiprocessing/pickle)
# ---------------------------------------------------------------------------

def _solve_territory_worker(payload: Dict) -> Tuple[str, List[Dict]]:
    """
    Worker que roda o solver CP-SAT para um territorio.
    Deve ser funcao top-level (nao metodo) para ser serializavel pelo pickle
    do ProcessPoolExecutor.

    Parametros (via payload dict)
    -----------------------------
    territory_id : str
    station_code : str
    hex_ids      : List[str]   hexes do territorio
    demand_map   : Dict[str, int]  apenas os hexes deste territorio
    min_cap      : int
    max_cap      : int
    radii_config : List[dict]  Config.RADII

    Retorna
    -------
    (territory_id, lista de dicts de slots)
    """
    territory_id = payload["territory_id"]
    station_code = payload["station_code"]
    hex_ids      = payload["hex_ids"]
    demand_map   = dict(payload["demand_map"])  # copia local — sera decrementada
    min_cap      = payload["min_cap"]
    max_cap      = payload["max_cap"]
    radii_config = payload["radii_config"]

    slots: List[Dict] = []
    seq = 0

    while True:
        # ── 1. Semente: hex com maior demanda residual ─────────────────────
        active_hexes = [h for h in hex_ids if demand_map.get(h, 0) > 0]
        if not active_hexes:
            break

        best_seed = max(active_hexes, key=lambda h: demand_map[h])

        # Verificacao rapida: potencial no raio maximo
        max_hex_dist = radii_config[-1]["hex_distance"]
        potential_vol = sum(
            demand_map[h] for h in hex_ids
            if demand_map.get(h, 0) > 0
            and h3.grid_distance(h, best_seed) <= max_hex_dist
        )
        if potential_vol < min_cap:
            # Nem no maior raio ha demanda suficiente — encerrar
            break

        # ── 2. Modelo CP-SAT ───────────────────────────────────────────────
        model = cp_model.CpModel()

        # r_active[i]: booleano — raio i esta ativo?
        r_active: Dict[int, cp_model.IntVar] = {}
        # allocations[(i, hex)]: pacotes alocados do hex no cenario de raio i
        allocations: Dict[Tuple[int, str], cp_model.IntVar] = {}

        for i, r_conf in enumerate(radii_config):
            r_active[i] = model.NewBoolVar(f"r_{i}")
            hex_dist = r_conf["hex_distance"]

            in_radius = [
                h for h in hex_ids
                if demand_map.get(h, 0) > 0
                and h3.grid_distance(h, best_seed) <= hex_dist
            ]

            radius_load_vars = []
            for h in in_radius:
                var = model.NewIntVar(0, int(demand_map[h]), f"load_{i}_{h}")
                allocations[(i, h)] = var
                radius_load_vars.append(var)

            if radius_load_vars:
                total_r = sum(radius_load_vars)
                # Se ativo: carga entre MIN e MAX
                model.Add(total_r >= min_cap).OnlyEnforceIf(r_active[i])
                model.Add(total_r <= max_cap).OnlyEnforceIf(r_active[i])
                # Se inativo: carga = 0
                model.Add(total_r == 0).OnlyEnforceIf(r_active[i].Not())
            else:
                # Sem hexes com demanda neste raio — nao pode ser ativado
                model.Add(r_active[i] == 0)

        # Exatamente um raio ativo (ou nenhum se inviavel)
        model.Add(sum(r_active.values()) <= 1)

        # ── 3. Objetivo: maximizar pacotes, penalizar raios maiores ────────
        # Peso 100 garante que +1 pacote vale mais que qualquer penalidade
        # de raio pequeno/medio, mas raios menores sao preferidos no empate
        obj_terms = []
        if allocations:
            obj_terms.append(sum(allocations.values()) * 100)
        for i, r_conf in enumerate(radii_config):
            obj_terms.append(r_active[i] * (-r_conf["penalty"]))

        if obj_terms:
            model.Maximize(sum(obj_terms))

        # ── 4. Solver ──────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        # ── 5. Extrair resultado ───────────────────────────────────────────
        chosen_radius_idx = next(
            (i for i in r_active if solver.Value(r_active[i])), -1
        )
        if chosen_radius_idx == -1:
            break  # nenhum raio ativado — inviavel

        r_conf = radii_config[chosen_radius_idx]
        hex_dist = r_conf["hex_distance"]

        final_allocs = []
        total_assigned = 0
        for h in hex_ids:
            key = (chosen_radius_idx, h)
            if key not in allocations:
                continue
            val = solver.Value(allocations[key])
            if val > 0:
                final_allocs.append({"hex_id": h, "packages_assigned": int(val)})
                total_assigned += int(val)

        if not final_allocs:
            break

        # ── 6. Registrar slot e decrementar demanda residual ───────────────
        seq += 1
        slot_id = f"{territory_id}_S{seq:02d}"
        lat, lon = h3.cell_to_latlng(best_seed)

        slots.append({
            "slot_id":      slot_id,
            "station_code": station_code,
            "territory_id": territory_id,
            "origin_hex":   best_seed,
            "radius_s":     r_conf["radius_s"],
            "capacity_s":   total_assigned,
            "lat":          lat,
            "lon":          lon,
            "allocations":  final_allocs,
        })

        for a in final_allocs:
            demand_map[a["hex_id"]] = max(
                0, demand_map[a["hex_id"]] - a["packages_assigned"]
            )

    return territory_id, slots


# ---------------------------------------------------------------------------
# CONVERSAO dict -> IdealSlot
# ---------------------------------------------------------------------------

def _dict_to_ideal_slot(d: Dict) -> IdealSlot:
    return IdealSlot(
        slot_id      = d["slot_id"],
        station_code = d["station_code"],
        bucket_id    = d["territory_id"],
        origin_hex   = d["origin_hex"],
        radius_s     = d["radius_s"],
        capacity_s   = d["capacity_s"],
        lat          = d["lat"],
        lon          = d["lon"],
        allocations  = [
            Allocation(hex_id=a["hex_id"], packages_assigned=a["packages_assigned"])
            for a in d.get("allocations", [])
        ],
    )


# ---------------------------------------------------------------------------
# PERSISTENCIA
# ---------------------------------------------------------------------------

def _save_supply(result: IdealSupplyResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "ideal_supply.json"

    # Serializar: IdealSlot -> dict (sem matched_partner_id — sera preenchido na F3)
    serializable: Dict[str, List[Dict]] = {}
    for tid, slots in result.slots_by_territory.items():
        serializable[tid] = [
            {
                "slot_id":      s.slot_id,
                "station_code": s.station_code,
                "territory_id": s.bucket_id,
                "origin_hex":   s.origin_hex,
                "radius_s":     s.radius_s,
                "capacity_s":   s.capacity_s,
                "lat":          s.lat,
                "lon":          s.lon,
                "allocations":  [
                    {"hex_id": a.hex_id, "packages_assigned": a.packages_assigned}
                    for a in s.allocations
                ],
                "matched_partner_id": s.matched_partner_id,
            }
            for s in slots
        ]

    output = {
        "_metadata": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "n_territories": len(serializable),
            "n_slots": sum(len(v) for v in serializable.values()),
        },
        "slots": serializable,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    result.supply_path = path
    size_kb = path.stat().st_size / 1024
    print(f"  Salvo: {path} ({size_kb:.1f} KB)")


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def run_phase2(
    territories: TerritoriesResult,
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
    max_workers: int = 8,
) -> IdealSupplyResult:
    """
    Executa a Fase 2: identificacao dos pontos ideais de parceiros.

    Parametros
    ----------
    territories  : TerritoriesResult   Output da Fase 1 (ou load_territories()).
    pkg          : PackageData         Output de load_packages() — para demand_map.
    output_dir   : str, opcional       Default: Config.DEST_FOLDER.
    stations     : list, opcional      Filtrar bases especificas. Default: todas.
    max_workers  : int                 Paralelismo entre territorios. Default: 4.

    Retorna
    -------
    IdealSupplyResult com slots_by_territory e caminho do artefato persistido.

    Nota sobre demanda
    ------------------
    Usa pkg.demand_map(station) — totais brutos do periodo, sem divisao por dias.
    O capacity_s de cada slot resultante sera em unidades do mesmo periodo.
    Para exibir em pacotes/dia nos reports: slot.capacity_s / pkg.days.
    """
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    target_stations = stations or territories.stations

    print(f"\n{'='*60}")
    print(f"  FASE 2 — IDENTIFICACAO DE PONTOS IDEAIS")
    print(f"  Bases: {target_stations}")
    print(f"  min_cap={Config.MIN_CAP} max_cap={Config.MAX_CAP}")
    print(f"  Raios configurados: {[r['radius_s'] for r in Config.RADII]} m")
    print(f"{'='*60}")

    result = IdealSupplyResult()

    # Montar payloads: um por territorio
    payloads: List[Dict] = []
    for station in target_stations:
        # demand_map total bruto (pacotes no periodo)
        demand_map_total = pkg.demand_map(station)
        if not demand_map_total:
            print(f"  WARN [{station}] Sem demanda — pulando.")
            continue

        for meta in territories.territories_for(station):
            tid = meta["territory_id"]

            # Converter para demanda DIARIA com inteiro >= 1 para cada hex ativo.
            # Config.MIN_CAP e MAX_CAP estao em pacotes/dia; o solver precisa
            # trabalhar na mesma unidade para gerar o numero correto de slots.
            # max(1, round(...)) preserva hexes de baixa frequencia que seriam
            # zerados pelo arredondamento inteiro da media.
            territory_demand: Dict[str, int] = {}
            for h in meta["hex_ids"]:
                total = demand_map_total.get(h, 0)
                if total > 0:
                    daily = max(1, round(total / pkg.days))
                    territory_demand[h] = daily

            if not territory_demand:
                print(f"  WARN [{tid}] Sem hexes com demanda — pulando.")
                continue

            total_daily = sum(territory_demand.values())
            print(f"  [{tid}] {len(territory_demand)} hexes | "
                  f"demanda diaria: {total_daily:,} pacotes/dia")

            payloads.append({
                "territory_id": tid,
                "station_code": station,
                "hex_ids":      meta["hex_ids"],
                "demand_map":   territory_demand,
                "min_cap":      Config.MIN_CAP,
                "max_cap":      Config.MAX_CAP,
                "radii_config": Config.RADII,
            })

    total = len(payloads)
    print(f"  {total} territorios para processar "
          f"(paralelo com {max_workers} workers)\n")

    # Executar solver em paralelo entre territorios
    completed = 0
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_solve_territory_worker, p): p["territory_id"]
            for p in payloads
        }
        for future in as_completed(futures):
            tid = futures[future]
            try:
                territory_id, slot_dicts = future.result()
                slots = [_dict_to_ideal_slot(d) for d in slot_dicts]
                result.slots_by_territory[territory_id] = slots
                completed += 1

                # Sumario do territorio
                # capacity_s ja esta em pacotes/dia (demand_map diario)
                total_cap = sum(s.capacity_s for s in slots)
                station = slots[0].station_code if slots else "?"
                print(f"  [{territory_id}] {len(slots)} slots | "
                      f"capacidade total: {total_cap:,} pacotes/dia "
                      f"[{completed}/{total}]")

            except Exception as exc:
                print(f"  ERR [{tid}] Falha no solver: {exc}")
                result.slots_by_territory[tid] = []

    # Garantir que todo territorio tenha entrada no resultado
    for p in payloads:
        if p["territory_id"] not in result.slots_by_territory:
            result.slots_by_territory[p["territory_id"]] = []

    # Sumario por base
    print()
    for station in target_stations:
        station_slots = result.slots_for_station(station)
        if not station_slots:
            continue
        total_slots = len(station_slots)
        total_cap   = sum(s.capacity_s for s in station_slots)
        n_terr      = len(territories.territories_for(station))
        print(f"  [{station}] {n_terr} territorios | "
              f"{total_slots} slots ideais | "
              f"capacidade total: {total_cap:,.1f} pacotes/dia")

    # Persistir
    _save_supply(result, out_dir)

    total_slots = len(result.all_slots)
    print(f"\n{'='*60}")
    print(f"  FASE 2 CONCLUIDA")
    print(f"  {total_slots} slots ideais identificados")
    print(f"  Artefato: {result.supply_path.name}")
    print(f"{'='*60}\n")

    return result


# ---------------------------------------------------------------------------
# CARREGAMENTO (para fases subsequentes)
# ---------------------------------------------------------------------------

def load_ideal_supply(output_dir: str = None) -> IdealSupplyResult:
    """
    Carrega ideal_supply.json sem re-rodar o solver.

    Usado pela Fase 3 no modo daily do orquestrador.
    Levanta FileNotFoundError se a Fase 2 ainda nao foi executada.
    """
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    path = out_dir / "ideal_supply.json"

    if not path.exists():
        raise FileNotFoundError(
            f"ideal_supply.json nao encontrado em {out_dir}.\n"
            "Execute o modo 'setup' do orquestrador para rodar a Fase 2."
        )

    print(f"[load_ideal_supply] Carregando {path} ...")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    slots_by_territory: Dict[str, List[IdealSlot]] = {}
    for tid, slot_dicts in raw.get("slots", {}).items():
        slots_by_territory[tid] = [_dict_to_ideal_slot(d) for d in slot_dicts]

    result = IdealSupplyResult(
        slots_by_territory=slots_by_territory,
        supply_path=path,
    )

    meta = raw.get("_metadata", {})
    print(f"  {meta.get('n_territories', '?')} territorios | "
          f"{meta.get('n_slots', '?')} slots | "
          f"gerado em: {meta.get('generated_at', '?')}")
    return result
