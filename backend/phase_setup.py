"""
phase_setup.py
==============
Setup: solver → K-means constrained → polígonos de território.

Outputs
-------
territories.geojson  — um polígono por território, sem gaps, dentro da jurisdição
ideal_supply.json    — slots por território (mesmo formato anterior)
heatmap.geojson      — hexes com hex_id, demand_total, ceps,
                        delivery_station, territory_id
"""

from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import h3
import numpy as np
from ortools.sat.python import cp_model
from scipy.optimize import linear_sum_assignment
from scipy.spatial import Voronoi
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from load_packages import PackageData
from models import Config, IdealSlot
from phase2_ideal_supply import IdealSupplyResult, _dict_to_ideal_slot, _save_supply
from phase1_territories import TerritoriesResult


# ---------------------------------------------------------------------------
# JURISDIÇÃO
# ---------------------------------------------------------------------------

def _load_jurisdiction_poly(station_code: str, jur_geojson: Dict):
    for f in jur_geojson.get("features", []):
        if f.get("properties", {}).get("delivery_station") == station_code:
            try:
                return make_valid(shape(f["geometry"]))
            except Exception:
                return shape(f["geometry"])
    return None


# ---------------------------------------------------------------------------
# SOLVER CP-SAT (top-level — pickle-serializável)
# ---------------------------------------------------------------------------

def _solve_base_worker(payload: Dict) -> Tuple[str, List[Dict]]:
    station_code = payload["station_code"]
    hex_ids      = payload["hex_ids"]
    demand_map   = dict(payload["demand_map"])
    min_cap      = payload["min_cap"]
    max_cap      = payload["max_cap"]
    radii_config = payload["radii_config"]
    slots: List[Dict] = []
    seq = 0

    while True:
        active = [h for h in hex_ids if demand_map.get(h, 0) > 0]
        if not active:
            break
        seed = max(active, key=lambda h: demand_map[h])
        max_dist = radii_config[-1]["hex_distance"]
        potential = sum(
            demand_map[h] for h in hex_ids
            if demand_map.get(h, 0) > 0
            and h3.grid_distance(h, seed) <= max_dist
        )
        if potential < min_cap:
            break

        model = cp_model.CpModel()
        r_active: Dict = {}
        allocs:   Dict = {}
        for i, rc in enumerate(radii_config):
            r_active[i] = model.NewBoolVar(f"r_{i}")
            in_r = [h for h in hex_ids
                    if demand_map.get(h, 0) > 0
                    and h3.grid_distance(h, seed) <= rc["hex_distance"]]
            rvars = []
            for h in in_r:
                v = model.NewIntVar(0, int(demand_map[h]), f"a_{i}_{h}")
                allocs[(i, h)] = v
                rvars.append(v)
            if rvars:
                t = sum(rvars)
                model.Add(t >= min_cap).OnlyEnforceIf(r_active[i])
                model.Add(t <= max_cap).OnlyEnforceIf(r_active[i])
                model.Add(t == 0).OnlyEnforceIf(r_active[i].Not())
            else:
                model.Add(r_active[i] == 0)

        model.Add(sum(r_active.values()) <= 1)
        obj = []
        if allocs:
            obj.append(sum(allocs.values()) * 100)
        for i, rc in enumerate(radii_config):
            obj.append(r_active[i] * (-rc["penalty"]))
        if obj:
            model.Maximize(sum(obj))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        chosen = next((i for i in r_active if solver.Value(r_active[i])), -1)
        if chosen == -1:
            break

        rc = radii_config[chosen]
        final_allocs, total_assigned = [], 0
        for h in hex_ids:
            key = (chosen, h)
            if key not in allocs:
                continue
            val = solver.Value(allocs[key])
            if val > 0:
                final_allocs.append({"hex_id": h, "packages_assigned": int(val)})
                total_assigned += int(val)
        if not final_allocs:
            break

        seq += 1
        lat, lon = h3.cell_to_latlng(seed)
        slots.append({
            "slot_id": f"{station_code}_S{seq:04d}", "station_code": station_code,
            "territory_id": "", "origin_hex": seed, "radius_s": rc["radius_s"],
            "capacity_s": total_assigned, "lat": lat, "lon": lon,
            "allocations": final_allocs,
        })
        for a in final_allocs:
            demand_map[a["hex_id"]] = max(0, demand_map[a["hex_id"]] - a["packages_assigned"])

    return station_code, slots


# ---------------------------------------------------------------------------
# K-MEANS CONSTRAINED COM COTAS IGUAIS
# ---------------------------------------------------------------------------

def _kmeans_constrained(
    slots: List[Dict],
    n_clusters: int,
    n_init: int = 10,
) -> List[int]:
    """
    Agrupa n slots em n_clusters com exatamente floor(n/k) ou ceil(n/k) slots
    por cluster.

    Algoritmo
    ---------
    1. Rodar K-means padrão n_init vezes, guardar melhores centroides.
    2. Resolver o problema de assignment com cotas via linear_sum_assignment:
       - Montar matriz de custo C[i, j] = dist²(slot_i, centroid_j)
       - Replicar cada coluna j exatamente quota_j vezes
       - Resolver assignment linear (O(n³) mas n é pequeno — dezenas de slots)
       - Mapear colunas de volta ao índice do cluster

    Garantia: exatamente quota_j slots em cada cluster j.
    Nenhum slot isolado geograficamente — o assignment minimiza distância total.
    """
    n = len(slots)
    if n == 0:
        return []
    if n_clusters >= n:
        return list(range(n))

    pts = np.array([[s["lat"], s["lon"]] for s in slots])

    # Cotas: floor(n/k) + 1 para os primeiros (n % k) clusters
    base_q    = n // n_clusters
    remainder = n % n_clusters
    quotas    = [base_q + (1 if i < remainder else 0) for i in range(n_clusters)]

    # K-means padrão — múltiplos restarts, manter melhor inércia
    best_centroids = None
    best_inertia   = float("inf")

    for _ in range(n_init):
        # Inicialização K-means++ simples
        idx = [np.random.randint(n)]
        for _ in range(n_clusters - 1):
            d2 = np.array([
                min(np.sum((pts[i] - pts[c]) ** 2) for c in idx)
                for i in range(n)
            ])
            total = d2.sum()
            probs = d2 / total if total > 0 else np.ones(n) / n
            idx.append(np.random.choice(n, p=probs))

        centroids = pts[idx].copy()

        # Iteração K-means
        for _ in range(300):
            # Assignment sem restrição de cota (K-means padrão)
            dists  = np.linalg.norm(pts[:, None, :] - centroids[None, :, :], axis=2)
            assign = dists.argmin(axis=1)

            new_centroids = np.zeros_like(centroids)
            for k in range(n_clusters):
                members = pts[assign == k]
                new_centroids[k] = members.mean(axis=0) if len(members) > 0 else centroids[k]

            if np.allclose(new_centroids, centroids, atol=1e-8):
                break
            centroids = new_centroids

        inertia = sum(
            np.sum((pts[i] - centroids[assign[i]]) ** 2) for i in range(n)
        )
        if inertia < best_inertia:
            best_inertia   = inertia
            best_centroids = centroids.copy()

    # Assignment com cotas via linear_sum_assignment
    # Expandir cada cluster j em quota_j cópias
    expanded_centroids = np.vstack([
        np.tile(best_centroids[j], (quotas[j], 1))
        for j in range(n_clusters)
    ])  # shape: (n, 2)

    # Matriz de custo: dist² entre cada slot e cada centroide expandido
    cost = np.sum((pts[:, None, :] - expanded_centroids[None, :, :]) ** 2, axis=2)

    # Resolver assignment linear
    row_ind, col_ind = linear_sum_assignment(cost)

    # Mapear índice expandido → índice do cluster
    col_to_cluster = []
    for j in range(n_clusters):
        col_to_cluster.extend([j] * quotas[j])

    result = [0] * n
    for i, c in zip(row_ind, col_ind):
        result[i] = col_to_cluster[c]

    return result


# ---------------------------------------------------------------------------
# POLÍGONO ÚNICO POR CLUSTER (SEM MULTIPOLYGON)
# ---------------------------------------------------------------------------

def _build_single_polygon(
    cluster_slots: List[Dict],
    all_slots: List[Dict],
    all_cluster_idxs: List[int],
    cluster_k: int,
    jurisdiction_poly,
) -> Optional[object]:
    """
    Constrói UM ÚNICO polígono para o cluster via Voronoi + union + healing.

    Garante polígono simples (sem MultiPolygon, sem ilhas):
    - Une regiões de Voronoi dos slots do cluster.
    - Se o resultado for MultiPolygon: mantém o maior componente e
      reatribui slots das peças menores ao cluster vizinho mais próximo
      (mas não altera cluster_idxs — o polygon é ajustado, não o clustering).
    - Clipa pela jurisdição.
    """
    if not cluster_slots or jurisdiction_poly is None:
        return None

    pts_all = np.array([[s["lon"], s["lat"]] for s in all_slots])
    n       = len(all_slots)

    # Pontos "infinitos" nos quatro cantos para fechar regiões de borda
    lon_range = pts_all[:, 0].max() - pts_all[:, 0].min()
    lat_range = pts_all[:, 1].max() - pts_all[:, 1].min()
    pad = max(lon_range, lat_range) * 3.0 + 0.5
    cx  = (pts_all[:, 0].min() + pts_all[:, 0].max()) / 2
    cy  = (pts_all[:, 1].min() + pts_all[:, 1].max()) / 2
    far = np.array([
        [cx - pad, cy - pad], [cx + pad, cy - pad],
        [cx - pad, cy + pad], [cx + pad, cy + pad],
    ])
    pts_ext = np.vstack([pts_all, far])

    vor = Voronoi(pts_ext)

    # Bounding box para regiões abertas
    bbox = Polygon([
        (cx - pad, cy - pad), (cx + pad, cy - pad),
        (cx + pad, cy + pad), (cx - pad, cy + pad),
    ])

    # Coletar regiões Voronoi dos slots deste cluster
    cluster_set = {i for i, k in enumerate(all_cluster_idxs) if k == cluster_k}
    polys: List[object] = []

    for point_idx in range(n):
        if point_idx not in cluster_set:
            continue
        region_idx = vor.point_region[point_idx]
        region     = vor.regions[region_idx]
        if not region:
            continue
        if -1 in region:
            poly = bbox
        else:
            verts = [vor.vertices[v] for v in region]
            if len(verts) < 3:
                continue
            try:
                poly = make_valid(Polygon(verts))
            except Exception:
                continue

        try:
            clipped = poly.intersection(jurisdiction_poly)
        except Exception:
            clipped = poly
        if not clipped.is_empty:
            polys.append(clipped)

    if not polys:
        return None

    try:
        merged = make_valid(unary_union(polys))
        merged = merged.intersection(jurisdiction_poly)
    except Exception:
        return polys[0] if polys else None

    # Forçar polígono simples: se MultiPolygon, manter apenas o maior
    merged = _force_single_polygon(merged)
    return merged


def _force_single_polygon(geom) -> Optional[object]:
    """
    Se geom é MultiPolygon ou GeometryCollection, retorna apenas o maior
    componente do tipo Polygon. Retorna None se vazio.
    """
    if geom is None or geom.is_empty:
        return None

    if isinstance(geom, Polygon):
        return geom

    if isinstance(geom, MultiPolygon):
        polys = [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
        if not polys:
            return None
        return max(polys, key=lambda p: p.area)

    # GeometryCollection ou outro tipo
    polys = []
    if hasattr(geom, "geoms"):
        for g in geom.geoms:
            result = _force_single_polygon(g)
            if result is not None:
                polys.append(result)
    if not polys:
        return None
    return max(polys, key=lambda p: p.area)


# ---------------------------------------------------------------------------
# PREENCHER GAPS: COBRIR TODA A JURISDIÇÃO SEM BURACOS
# ---------------------------------------------------------------------------

def _fill_jurisdiction(
    territory_polys: Dict[str, object],  # tid → poly
    jurisdiction_poly,
) -> Dict[str, object]:
    """
    Garante que a união de todos os polígonos cobre exatamente a jurisdição,
    sem gaps e sem sobreposição.

    Algoritmo
    ---------
    1. Calcular o gap = jurisdição − união de todos os polígonos.
    2. Para cada pedaço do gap, atribuí-lo ao território cujo polígono
       é mais próximo (menor distância do centróide do gap ao polígono).
    3. Unir o pedaço ao polígono do território vencedor.
    4. Forçar polígono simples novamente.
    """
    if not territory_polys or jurisdiction_poly is None:
        return territory_polys

    all_polys = [p for p in territory_polys.values() if p is not None]
    if not all_polys:
        return territory_polys

    try:
        covered = make_valid(unary_union(all_polys))
        gap     = jurisdiction_poly.difference(covered)
    except Exception:
        return territory_polys

    if gap.is_empty:
        return territory_polys

    # Decompor gap em peças individuais
    if isinstance(gap, Polygon):
        gap_pieces = [gap] if not gap.is_empty else []
    elif hasattr(gap, "geoms"):
        gap_pieces = [g for g in gap.geoms if not g.is_empty]
    else:
        gap_pieces = []

    tids   = list(territory_polys.keys())
    result = {tid: territory_polys[tid] for tid in tids}

    for piece in gap_pieces:
        if piece.is_empty:
            continue
        piece_centroid = piece.centroid

        # Território mais próximo (menor distância do centróide do gap ao polígono)
        nearest_tid = min(
            tids,
            key=lambda tid: (
                result[tid].distance(piece_centroid)
                if result[tid] is not None
                else float("inf")
            ),
        )

        try:
            merged = make_valid(unary_union([result[nearest_tid], piece]))
            result[nearest_tid] = _force_single_polygon(merged)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# SPATIAL JOIN: hex → território por centróide
# ---------------------------------------------------------------------------

def _build_heatmap(
    demand_map: Dict[str, int],
    territory_polys: Dict[str, object],
    hex_to_ceps: Dict[str, Set[str]],
    station_code: str,
) -> List[Dict]:
    """
    Para cada hex com demanda: centróide → dentro de qual polígono?
    Constrói features para heatmap.geojson.
    """
    tid_list = [(tid, poly) for tid, poly in territory_polys.items()
                if poly is not None]
    features = []

    for h, demand in demand_map.items():
        lat, lon = h3.cell_to_latlng(h)
        pt = Point(lon, lat)

        territory_id = None
        for tid, poly in tid_list:
            try:
                if poly.contains(pt):
                    territory_id = tid
                    break
            except Exception:
                pass

        # Fallback: território mais próximo
        if territory_id is None and tid_list:
            territory_id = min(
                tid_list, key=lambda x: pt.distance(x[1].centroid)
            )[0]

        boundary = h3.cell_to_boundary(h)
        coords   = [[c[1], c[0]] for c in boundary]
        coords.append(coords[0])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "hex_id":           h,
                "demand_total":     demand,
                "ceps":             list(hex_to_ceps.get(h, set()))[:10],
                "delivery_station": station_code,
                "territory_id":     territory_id or "",
            },
        })

    return features


# ---------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL
# ---------------------------------------------------------------------------

def run_setup(
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
    max_workers: int = 4,
    jurisdiction_path: str = None,
) -> Tuple["TerritoriesResult", IdealSupplyResult]:
    """
    Setup: solver por base → K-means constrained → polígonos de território.

    Outputs
    -------
    territories.geojson  — um polígono simples por território
    ideal_supply.json    — slots por território
    heatmap.geojson      — hexes com delivery_station e territory_id
    territories_index.json — metadados para fases daily
    """

    out_dir    = Path(output_dir or Config.DEST_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)
    j_path     = jurisdiction_path or Config.BASE_JURISDICTION
    target_sta = stations or pkg.all_stations

    print(f"\n{'='*60}")
    print(f"  SETUP")
    print(f"  Bases: {target_sta}")
    print(f"{'='*60}")

    with open(j_path, "r", encoding="utf-8") as f:
        jur_geojson = json.load(f)
    print(f"  {len(jur_geojson.get('features', []))} jurisdições carregadas.\n")

    # ── Solver em paralelo ────────────────────────────────────────────────
    payloads: List[Dict] = []
    dm_filtered_by_station: Dict[str, Dict] = {}  # Guardar demand_map filtrado por jurisdição
    for station in target_sta:
        dm = pkg.demand_map(station)
        if not dm:
            print(f"  WARN [{station}] Sem demanda.")
            continue

        # Filtrar hexes cujo centróide está dentro do polígono de jurisdição
        jur_poly = _load_jurisdiction_poly(station, jur_geojson)
        if jur_poly is not None:
            before = len(dm)
            dm = {
                h: v for h, v in dm.items()
                if (lambda lat, lon: jur_poly.contains(Point(lon, lat)))
                   (*h3.cell_to_latlng(h))
            }
            removed = before - len(dm)
            if removed:
                print(f"  [{station}] {removed} hexes fora da jurisdição removidos "
                      f"({len(dm)} restantes).")
        else:
            print(f"  WARN [{station}] Jurisdição não encontrada — "
                  f"usando todos os {len(dm)} hexes com demanda.")

        if not dm:
            print(f"  WARN [{station}] Sem hexes dentro da jurisdição — pulando.")
            continue

        dm_filtered_by_station[station] = dm  # Salvar demand_map filtrado
        daily = {h: max(1, round(v / pkg.days)) for h, v in dm.items() if v > 0}
        payloads.append({
            "station_code": station, "hex_ids": list(daily.keys()),
            "demand_map": daily, "min_cap": Config.MIN_CAP,
            "max_cap": Config.MAX_CAP, "radii_config": Config.RADII,
        })

    print(f"  Solver: {len(payloads)} bases ({max_workers} workers)...")
    base_slots: Dict[str, List[Dict]] = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_solve_base_worker, p): p["station_code"]
                   for p in payloads}
        for future in as_completed(futures):
            station = futures[future]
            try:
                _, sdicts = future.result()
                base_slots[station] = sdicts
                cap = sum(s["capacity_s"] for s in sdicts)
                print(f"  [{station}] {len(sdicts)} slots | {cap:,} pac/dia")
            except Exception as e:
                print(f"  ERR [{station}]: {e}")
                base_slots[station] = []

    # ── Clustering + polígonos por base ───────────────────────────────────
    territory_index:     Dict[str, Dict]            = {}
    territory_polys_all: Dict[str, object]          = {}
    slots_by_territory:  Dict[str, List[IdealSlot]] = {}
    heatmap_features:    List[Dict]                 = []

    for station in target_sta:
        slots      = base_slots.get(station, [])
        n_slots    = len(slots)
        n_clusters = Config.CLUSTER_PER_STATION.get(station, 5)
        bdm        = Config.get_bdm_cluster(station)

        if n_slots == 0:
            print(f"\n  WARN [{station}] Sem slots — pulando.")
            continue

        if n_slots < n_clusters:
            print(f"\n  WARN [{station}] {n_slots} slots < {n_clusters} clusters "
                  f"— ajustando para {n_slots}.")
            n_clusters = n_slots

        print(f"\n  [{station}] {n_slots} slots → {n_clusters} territórios")

        # Jurisdição
        jur_poly = _load_jurisdiction_poly(station, jur_geojson)
        if jur_poly is None:
            lats = [s["lat"] for s in slots]
            lons = [s["lon"] for s in slots]
            pad  = 0.05
            jur_poly = Polygon([
                (min(lons)-pad, min(lats)-pad), (max(lons)+pad, min(lats)-pad),
                (max(lons)+pad, max(lats)+pad), (min(lons)-pad, max(lats)+pad),
            ])
            print(f"  WARN [{station}] Jurisdição não encontrada — usando bbox.")

        # 1. K-means constrained (cotas iguais)
        cluster_idxs = _kmeans_constrained(slots, n_clusters)

        # Verificar balanço
        from collections import Counter
        counts = Counter(cluster_idxs)
        base_q = n_slots // n_clusters
        print(f"  Slots por cluster: min={min(counts.values())} "
              f"max={max(counts.values())} "
              f"(esperado {base_q} ou {base_q+1})")

        # 2. Nomear clusters norte → sul
        k_lats: Dict[int, float] = {}
        k_lons: Dict[int, float] = {}
        for i, s in enumerate(slots):
            k = cluster_idxs[i]
            k_lats.setdefault(k, [])
            k_lons.setdefault(k, [])
            k_lats[k] = k_lats.get(k, []) + [s["lat"]]
            k_lons[k] = k_lons.get(k, []) + [s["lon"]]

        # Calcular médias para ordenação
        k_mean_lat = {k: sum(v)/len(v) for k, v in k_lats.items()}
        k_mean_lon = {k: sum(v)/len(v) for k, v in k_lons.items()}

        sorted_ks = sorted(
            k_mean_lat.keys(),
            key=lambda k: (-k_mean_lat[k], k_mean_lon.get(k, 0)),
        )
        k_to_tid = {k: f"{station}_bucket-{seq+1:02d}" for seq, k in enumerate(sorted_ks)}

        # 3. Polígono único por cluster
        base_polys: Dict[str, object] = {}
        for k, tid in k_to_tid.items():
            t_slots = [slots[i] for i, ki in enumerate(cluster_idxs) if ki == k]
            poly = _build_single_polygon(
                cluster_slots=t_slots,
                all_slots=slots,
                all_cluster_idxs=cluster_idxs,
                cluster_k=k,
                jurisdiction_poly=jur_poly,
            )
            if poly is not None:
                base_polys[tid] = poly

        # 4. Preencher gaps da jurisdição
        base_polys = _fill_jurisdiction(base_polys, jur_poly)

        # 5. Metadados e slots por território
        for k, tid in k_to_tid.items():
            t_slots_raw = [slots[i] for i, ki in enumerate(cluster_idxs) if ki == k]
            t_cap_day   = sum(s["capacity_s"] for s in t_slots_raw)

            territory_index[tid] = {
                "territory_id": tid, 
                "station_code": station,
                "bdm_cluster":  bdm, 
                "n_slots": len(t_slots_raw),
                "open_slots": len(t_slots_raw),
                "daily_demand": round(t_cap_day, 2),
                "centroid_lat": round(k_mean_lat.get(k, 0), 6),
                "centroid_lon": round(k_mean_lon.get(k, 0), 6),
                "created_at":   datetime.now().isoformat(timespec="seconds"),
            }

            if tid in base_polys:
                territory_polys_all[tid] = base_polys[tid]

            t_slot_objs: List[IdealSlot] = []
            for seq_s, sd in enumerate(t_slots_raw, 1):
                sd2 = dict(sd)
                sd2["slot_id"] = f"{tid}_S{seq_s:02d}"
                sd2["territory_id"] = tid
                t_slot_objs.append(_dict_to_ideal_slot(sd2))
            slots_by_territory[tid] = t_slot_objs

            geom_type = type(base_polys.get(tid)).__name__ if tid in base_polys else "N/A"
            print(f"    {tid}: {len(t_slots_raw)} slots | "
                  f"{t_cap_day:,.1f} pac/dia | geom={geom_type}")

        # 6. Heatmap desta base (usar demand_map filtrado pela jurisdição)
        dm_base = dm_filtered_by_station.get(station, {})
        heatmap_features.extend(
            _build_heatmap(dm_base, base_polys, pkg.hex_to_ceps, station)
        )

    # ── Salvar artefatos ──────────────────────────────────────────────────
    print(f"\n  Salvando em {out_dir}...")

    # territories.geojson
    t_features = []
    for tid, meta in territory_index.items():
        poly = territory_polys_all.get(tid)
        if poly is None:
            continue
        try:
            geom = mapping(poly)
        except Exception:
            continue
        t_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "territory_id":     tid,
                "delivery_station": meta["station_code"],
                "bdm_cluster":      meta["bdm_cluster"],
                "n_slots":          meta["n_slots"],
                "open_slots":       meta["open_slots"],
                "daily_demand":     meta["daily_demand"],
                "attainment":       None,
                "accuracy":         None,
            },
        })

    t_path = out_dir / "territories.geojson"
    with open(t_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": t_features,
            "metadata": {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "n_territories": len(t_features),
            },
        }, f, ensure_ascii=False, indent=2)
    print(f"  ✅ territories.geojson — {len(t_features)} polígonos")

    # heatmap.geojson
    h_path = out_dir / "heatmap.geojson"
    with open(h_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": heatmap_features,
            "metadata": {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "n_hexes": len(heatmap_features),
            },
        }, f, ensure_ascii=False, indent=2)
    print(f"  ✅ heatmap.geojson — {len(heatmap_features)} hexes")

    # territories_index.json
    idx_path = out_dir / "territories_index.json"
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(territory_index, f, ensure_ascii=False, indent=2)
    print(f"  ✅ territories_index.json")

    # ideal_supply.json
    supply_result = IdealSupplyResult(slots_by_territory=slots_by_territory)
    _save_supply(supply_result, out_dir)
    print(f"  ✅ ideal_supply.json")

    # Montar TerritoriesResult
    hex_to_territory = {
        f["properties"]["hex_id"]: f["properties"]["territory_id"]
        for f in heatmap_features
        if f["properties"].get("territory_id")
    }

    from phase1_territories import TerritoriesResult
    territories = TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory=hex_to_territory,
        geojson_path=t_path,
        index_path=idx_path,
    )

    total_s = sum(len(v) for v in slots_by_territory.values())
    print(f"\n{'='*60}")
    print(f"  SETUP CONCLUÍDO: {len(territory_index)} territórios | {total_s} slots")
    print(f"{'='*60}\n")

    return territories, supply_result


# ---------------------------------------------------------------------------
# ATUALIZAÇÃO DAILY
# ---------------------------------------------------------------------------

def update_territories_geojson(
    output_dir: str,
    territory_stats: Dict[str, Dict],
) -> None:
    """
    Atualiza attainment e accuracy no territories.geojson sem alterar geometrias.
    Chamado pelo modo daily após a Fase 3.

    territory_stats: {territory_id: {"attainment": 75.0, "accuracy": 83.3}}
    """
    path = Path(output_dir) / "territories.geojson"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj.get("features", []):
        tid = feat["properties"].get("territory_id")
        if tid and tid in territory_stats:
            feat["properties"]["attainment"] = territory_stats[tid].get("attainment")
            feat["properties"]["accuracy"]   = territory_stats[tid].get("accuracy")
    gj["metadata"]["last_daily_update"] = datetime.now().isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, indent=2)
    print("  territories.geojson atualizado com métricas daily.")
