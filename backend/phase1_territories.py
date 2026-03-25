"""
phase1_territories.py
=====================
Fase 1 — Formacao e persistencia de territorios.

Responsabilidade
----------------
- Receber PackageData (output de load_packages).
- Chamar regionalize_demand_balanced para cada base.
- Atribuir IDs ESTAVEIS aos territorios.
- Persistir dois artefatos:
    territories.geojson   <- hexagonos com territorio atribuido (para visualizacao)
    territories_index.json <- metadados dos territorios (para fases 2-5)

IDs estaveis
------------
Um ID instavel como "bucket-3" muda de significado entre runs se a demanda
muda e a ordenacao das demandas muda junto. Isso quebraria o acompanhamento
diario das Fases 3-5, que leem o arquivo persistido.

Estrategia adotada: ordenacao geografica norte→sul, oeste→leste do centroide
de cada territorio dentro da base. Enquanto a grade de hexagonos nao mudar
substancialmente, o mesmo territorio geografico mantera o mesmo ID.

Formato do ID: "{station_code}_T{seq:02d}"   ex: "DSP2_T01", "DSP2_T02"

Se for necessario re-rodar a Fase 1 (re-territorializacao), basta apagar
os artefatos e rodar novamente. As Fases 3-5 precisarao ser re-rodadas
em seguida para re-associar parceiros aos novos territorios.

Artefatos gerados
-----------------
territories.geojson
    FeatureCollection de poligonos. Cada feature tem:
        territory_id        : str  "DSP2_T01"
        delivery_station    : str  "DSP2"
        bdm_cluster         : str  "SP/SUL"
        daily_demand        : float media diaria de pacotes
        attainment          : float attainment do territorio (para tooltip rapido, embora o valor real seja calculado na Fase 3)
        coverage            : float cobertura das vagas (para tooltip rapido, embora o valor real seja calculado na Fase 3)

territories_index.json
    Dict indexado por territory_id com os mesmos campos + hex_ids (lista completa).
    Usado pelas Fases 2-5 para lookup rapido sem precisar parsear o GeoJSON.

    {
      "DSP2_T01": {
        "territory_id": "DSP2_T01",
        "station_code": "DSP2",
        "bdm_cluster": "SP/SUL",
        "hex_ids": ["8a2...","8a2..."],
        "total_demand": 4820,
        "daily_demand": 160.67,
        "n_hexes": 42,
        "centroid_lat": -23.55,
        "centroid_lon": -46.63,
        "ceps": ["01310100", ...]
      },
      ...
    }

Como usar
---------
    from load_packages import load_packages
    from phase1_territories import run_phase1

    pkg = load_packages()
    result = run_phase1(pkg, output_dir="output/")
    # result.territory_index: Dict[str, dict]
    # result.hex_to_territory: Dict[str, str]  hex -> territory_id
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
from models import Config
from regionalization import regionalize_demand_balanced


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class TerritoriesResult:
    """Output da Fase 1."""

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


# ---------------------------------------------------------------------------
# ATRIBUICAO DE IDS ESTAVEIS
# ---------------------------------------------------------------------------

def _stable_territory_ids(
    station_code: str,
    hex_to_k: Dict[str, int],
    demand_map: Dict[str, int],
    n_clusters: int,
) -> Tuple[Dict[int, str], Dict[int, Tuple[float, float]]]:
    """
    Gera IDs estaveis para os territorios de uma base.

    Estrategia: ordenar territorios pelo centroide geografico
    norte -> sul (lat decrescente), desempate oeste -> leste (lon crescente).
    Resultado: "DSP2_T01" = territorio mais ao norte, etc.

    Retorna
    -------
    k_to_id       : Dict[int, str]              indice -> territory_id
    k_to_centroid : Dict[int, Tuple[float,float]]  indice -> (lat, lon)
    """
    coords_cache: Dict[str, Tuple[float, float]] = {}

    # Calcular centroide de cada territorio
    k_lats: Dict[int, List[float]] = defaultdict(list)
    k_lons: Dict[int, List[float]] = defaultdict(list)

    for h, k in hex_to_k.items():
        if h not in coords_cache:
            coords_cache[h] = h3.cell_to_latlng(h)
        lat, lon = coords_cache[h]
        k_lats[k].append(lat)
        k_lons[k].append(lon)

    k_to_centroid: Dict[int, Tuple[float, float]] = {
        k: (
            sum(k_lats[k]) / len(k_lats[k]),
            sum(k_lons[k]) / len(k_lons[k]),
        )
        for k in range(n_clusters)
        if k in k_lats
    }

    # Ordenar: lat decrescente (norte primeiro), lon crescente (oeste primeiro)
    sorted_ks = sorted(
        k_to_centroid.keys(),
        key=lambda k: (-k_to_centroid[k][0], k_to_centroid[k][1]),
    )

    k_to_id: Dict[int, str] = {
        k: f"{station_code}_T{seq + 1:02d}"
        for seq, k in enumerate(sorted_ks)
    }

    return k_to_id, k_to_centroid


# ---------------------------------------------------------------------------
# CONSTRUCAO DOS METADADOS DE CADA TERRITORIO
# ---------------------------------------------------------------------------

def _build_territory_metadata(
    station_code: str,
    territory_id: str,
    k: int,
    hex_to_k: Dict[str, int],
    demand_map: Dict[str, int],
    hex_to_ceps: Dict[str, Set[str]],
    centroid: Tuple[float, float],
    days: int,
) -> dict:
    """Constroi o dict de metadados de um territorio."""
    hex_ids = [h for h, ki in hex_to_k.items() if ki == k]
    total_demand = sum(demand_map.get(h, 0) for h in hex_ids)
    daily_demand = total_demand / days if days > 0 else 0.0

    # Top-20 CEPs por frequencia no territorio
    cep_counts: Dict[str, int] = defaultdict(int)
    for h in hex_ids:
        for cep in hex_to_ceps.get(h, set()):
            cep_counts[cep] += 1
    top_ceps = [c for c, _ in sorted(cep_counts.items(),
                                      key=lambda x: -x[1])[:20]]

    return {
        "territory_id":  territory_id,
        "station_code":  station_code,
        "bdm_cluster":   Config.get_bdm_cluster(station_code),
        "hex_ids":       hex_ids,
        "n_hexes":       len(hex_ids),
        "total_demand":  int(total_demand),
        "daily_demand":  round(daily_demand, 2),
        "centroid_lat":  round(centroid[0], 6),
        "centroid_lon":  round(centroid[1], 6),
        "ceps":          top_ceps,
        "created_at":    datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# GERACAO DO GEOJSON
# ---------------------------------------------------------------------------

def _build_geojson(
    territory_index: Dict[str, dict],
    hex_to_territory: Dict[str, str],
    demand_map_all: Dict[str, int],
    hex_to_ceps: Dict[str, Set[str]],
) -> dict:
    """
    Constroi o GeoJSON de territorios.

    Cada hexagono e uma Feature do tipo Polygon com propriedades do territorio
    ao qual pertence. O GeoJSON resultante pode ser carregado diretamente em
    ferramentas como Kepler.gl, QGIS ou Google Earth Engine.
    """
    features = []

    for hex_id, territory_id in hex_to_territory.items():
        meta = territory_index.get(territory_id, {})
        boundary = h3.cell_to_boundary(hex_id)
        # H3 retorna (lat, lon); GeoJSON espera [lon, lat]
        coords = [[c[1], c[0]] for c in boundary]
        coords.append(coords[0])  # fechar o anel

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords],
            },
            "properties": {
                "hex_id":        hex_id,
                "territory_id":  territory_id,
                "station_code":  meta.get("station_code", ""),
                "bdm_cluster":   meta.get("bdm_cluster", ""),
                "total_demand":  demand_map_all.get(hex_id, 0),
                "ceps":          list(hex_to_ceps.get(hex_id, set()))[:5],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "n_territories": len(territory_index),
            "n_hexes": len(hex_to_territory),
        },
    }


# ---------------------------------------------------------------------------
# PERSISTENCIA
# ---------------------------------------------------------------------------

def _save_artifacts(
    result: TerritoriesResult,
    geojson_data: dict,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # territories.geojson
    geojson_path = output_dir / "territories.geojson"
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)
    result.geojson_path = geojson_path
    print(f"  Salvo: {geojson_path} "
          f"({geojson_path.stat().st_size / 1024:.1f} KB)")

    # territories_index.json
    # Serializar sem hex_ids no GeoJSON (ja esta la), mas incluir no index
    index_path = output_dir / "territories_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(result.territory_index, f, ensure_ascii=False, indent=2)
    result.index_path = index_path
    print(f"  Salvo: {index_path} "
          f"({index_path.stat().st_size / 1024:.1f} KB)")


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def run_phase1(
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
) -> TerritoriesResult:
    """
    Executa a Fase 1: formacao e persistencia de territorios.

    Parametros
    ----------
    pkg        : PackageData    Output de load_packages().
    output_dir : str            Pasta de saida. Default: Config.DEST_FOLDER.
    stations   : list, opcional Lista de bases a processar.
                                Se None, processa todas em pkg.

    Retorna
    -------
    TerritoriesResult com territory_index, hex_to_territory e caminhos dos
    artefatos persistidos.
    """
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    target_stations = stations or pkg.all_stations

    print(f"\n{'='*60}")
    print(f"  FASE 1 — FORMACAO DE TERRITORIOS")
    print(f"  Bases: {target_stations}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    result = TerritoriesResult()

    # demand_map global (para o GeoJSON — todos os hexes de todas as bases)
    demand_map_all: Dict[str, int] = {}

    for station in target_stations:
        demand_map = pkg.demand_map(station)
        if not demand_map:
            print(f"\n  WARN [{station}] Sem dados de demanda — pulando.")
            continue

        demand_map_all.update(demand_map)

        n_clusters = Config.CLUSTER_PER_STATION.get(station, 5)

        # --- Regionalizacao ---
        hex_to_k = regionalize_demand_balanced(
            station_code=station,
            n_clusters=n_clusters,
            demand_map=demand_map,
        )

        if not hex_to_k:
            print(f"  ERR [{station}] Regionalizacao retornou vazio — pulando.")
            continue

        # --- IDs estaveis ---
        k_to_id, k_to_centroid = _stable_territory_ids(
            station_code=station,
            hex_to_k=hex_to_k,
            demand_map=demand_map,
            n_clusters=n_clusters,
        )

        # --- Metadados e indices ---
        for k, territory_id in k_to_id.items():
            meta = _build_territory_metadata(
                station_code=station,
                territory_id=territory_id,
                k=k,
                hex_to_k=hex_to_k,
                demand_map=demand_map,
                hex_to_ceps=pkg.hex_to_ceps,
                centroid=k_to_centroid[k],
                days=pkg.days,
            )
            result.territory_index[territory_id] = meta

            for h, ki in hex_to_k.items():
                if ki == k:
                    result.hex_to_territory[h] = territory_id

        # Sumario da base
        territories_this = [m for m in result.territory_index.values()
                             if m["station_code"] == station]
        demands = [m["daily_demand"] for m in territories_this]
        print(f"\n  [{station}] {len(territories_this)} territorios | "
              f"demanda diaria: avg={sum(demands)/len(demands):.1f} "
              f"max={max(demands):.1f} min={min(demands):.1f} "
              f"delta={max(demands)-min(demands):.1f}")
        for m in sorted(territories_this, key=lambda x: x["territory_id"]):
            print(f"    {m['territory_id']}: {m['n_hexes']} hexes | "
                  f"{m['daily_demand']:.1f} pacotes/dia")

    # --- Persistencia ---
    geojson_data = _build_geojson(
        territory_index=result.territory_index,
        hex_to_territory=result.hex_to_territory,
        demand_map_all=demand_map_all,
        hex_to_ceps=pkg.hex_to_ceps,
    )
    _save_artifacts(result, geojson_data, out_dir)

    total_territories = len(result.territory_index)
    total_hexes = len(result.hex_to_territory)
    print(f"\n{'='*60}")
    print(f"  FASE 1 CONCLUIDA")
    print(f"  {total_territories} territorios | {total_hexes:,} hexes mapeados")
    print(f"  Artefatos: {result.geojson_path.name}, {result.index_path.name}")
    print(f"{'='*60}\n")

    return result


# ---------------------------------------------------------------------------
# CARREGAMENTO DE ARTEFATOS (para fases subsequentes)
# ---------------------------------------------------------------------------

def load_territories(output_dir: str = None) -> TerritoriesResult:
    """
    Carrega os artefatos persistidos pela Fase 1 sem re-rodar a regionalizacao.

    Usado pelas Fases 2-5 no modo daily do orquestrador.

    Levanta FileNotFoundError se os artefatos nao existirem
    (indica que a Fase 1 ainda nao foi rodada).
    """
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    index_path = out_dir / "territories_index.json"
    geojson_path = out_dir / "territories.geojson"

    if not index_path.exists():
        raise FileNotFoundError(
            f"territories_index.json nao encontrado em {out_dir}.\n"
            "Execute o modo 'setup' do orquestrador para rodar a Fase 1."
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
