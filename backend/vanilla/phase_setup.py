"""
phase_setup.py
==============
Setup: solver CP-SAT → K-means geoespacial em UTM → polígonos de território.

Pipeline
--------
1. Filtrar hexes H3 cujo centróide está dentro do polígono de jurisdição.
2. Rodar solver CP-SAT por base para gerar pontos ideais (slots) com base
   na demanda diária dos hexes válidos.
3. Agrupar slots em n_clusters com mesma quantidade (±1) via K-means em UTM.
4. Construir polígono por território em UTM (convex hull + buffer).
5. Expandir polígonos até cobrir 100% da jurisdição sem sobreposição.
6. Reprojetar para WGS84 e salvar artefatos.

Outputs
-------
territories.geojson      — um polígono WGS84 por território
ideal_supply.json        — slots ideais por território
heatmap.geojson          — hexes com hex_id, demand_total, ceps,
                           delivery_station, territory_id
territories_index.json   — metadados para fases daily
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import h3
import numpy as np
from ortools.sat.python import cp_model
from scipy.optimize import linear_sum_assignment
from shapely.geometry import MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from shared.load_packages import PackageData
from shared.models import Config, IdealSlot
from vanilla.phase2_ideal_supply import IdealSupplyResult, _dict_to_ideal_slot, _save_supply
from shared.models import Config, IdealSlot, TerritoriesResult

# ---------------------------------------------------------------------------
# PROJEÇÃO UTM  (SIRGAS2000 zona 23S — EPSG:31983, cobre todo o Brasil)
# Todas as operações métricas rodam em metros, não em graus.
# ---------------------------------------------------------------------------
try:
    from pyproj import Transformer as _Transformer
    _to_utm_tr   = _Transformer.from_crs("EPSG:4326", "EPSG:31983", always_xy=True)
    _to_wgs84_tr = _Transformer.from_crs("EPSG:31983", "EPSG:4326", always_xy=True)
    _HAS_PYPROJ  = True
except ImportError:
    _HAS_PYPROJ = False

from shapely.ops import transform as _shapely_transform


def _wgs84_to_utm(geom):
    """WGS84 → UTM (operações métricas)."""
    if not _HAS_PYPROJ:
        return geom
    return _shapely_transform(
        lambda x, y, z=None: _to_utm_tr.transform(x, y), geom
    )


def _utm_to_wgs84(geom):
    """UTM → WGS84 (saída GeoJSON)."""
    if not _HAS_PYPROJ:
        return geom
    return _shapely_transform(
        lambda x, y, z=None: _to_wgs84_tr.transform(x, y), geom
    )


def _slot_utm(slot: Dict) -> Tuple[float, float]:
    """Retorna (easting, northing) de um slot em metros."""
    if _HAS_PYPROJ:
        return _to_utm_tr.transform(slot["lon"], slot["lat"])
    return slot["lon"], slot["lat"]  # fallback sem pyproj


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
# SOLVER CP-SAT  (top-level — pickle-serializável para ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _solve_base_worker(payload: Dict) -> Tuple[str, List[Dict]]:
    """
    Encontra pontos ideais (slots) para uma base via CP-SAT greedy.
    Roda sobre demanda DIÁRIA (já filtrada por jurisdição).
    """
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
            "slot_id": f"{station_code}_S{seq:04d}",
            "station_code": station_code,
            "territory_id": "",
            "origin_hex": seed,
            "radius_s": rc["radius_s"],
            "capacity_s": total_assigned,
            "lat": lat,
            "lon": lon,
            "allocations": final_allocs,
        })
        for a in final_allocs:
            demand_map[a["hex_id"]] = max(0, demand_map[a["hex_id"]] - a["packages_assigned"])

    return station_code, _merge_duplicate_slots(station_code, slots)


def _merge_duplicate_slots(station_code: str, slots: List[Dict]) -> List[Dict]:
    """
    Pós-processamento do CP-SAT: consolida slots com mesmo origin_hex em um único.

    Regras
    ------
    - Mesmo origin_hex + mesmo radius_s → merge: soma capacity_s e allocations.
    - Mesmo origin_hex + radius_s diferentes → mantém apenas o de menor radius_s,
      descarta os demais (raio menor = cobertura mais precisa).
    - Renumera slot_ids sequencialmente após o processamento.
    """
    from collections import defaultdict as _dd

    # Agrupar por origin_hex
    groups: Dict[str, List[Dict]] = _dd(list)
    for s in slots:
        groups[s["origin_hex"]].append(s)

    merged: List[Dict] = []
    n_merged  = 0
    n_dropped = 0

    for origin_hex, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue

        radii = {s["radius_s"] for s in group}

        if len(radii) == 1:
            # Mesmo radius_s → merge: soma capacidades e allocations
            alloc_map: Dict[str, int] = {}
            for s in group:
                for a in s["allocations"]:
                    alloc_map[a["hex_id"]] = alloc_map.get(a["hex_id"], 0) + a["packages_assigned"]

            base = group[0]
            merged.append({
                "slot_id":      base["slot_id"],
                "station_code": base["station_code"],
                "territory_id": base["territory_id"],
                "origin_hex":   origin_hex,
                "radius_s":     base["radius_s"],
                "capacity_s":   sum(s["capacity_s"] for s in group),
                "lat":          base["lat"],
                "lon":          base["lon"],
                "allocations":  [{"hex_id": h, "packages_assigned": v}
                                 for h, v in alloc_map.items()],
            })
            n_merged += len(group) - 1
        else:
            # radius_s diferentes → manter apenas o de menor raio
            best = min(group, key=lambda s: s["radius_s"])
            merged.append(best)
            n_dropped += len(group) - 1

    # Renumerar slot_ids sequencialmente
    for seq, s in enumerate(merged, 1):
        s["slot_id"] = f"{station_code}_S{seq:04d}"

    total_removed = n_merged + n_dropped
    if total_removed > 0:
        print(f"  [{station_code}] dedup: {len(slots)} → {len(merged)} slots "
              f"({n_merged} merged, {n_dropped} descartados por raio diferente)")

    return merged


# ---------------------------------------------------------------------------
# K-MEANS GEOESPACIAL EM UTM COM COTAS IGUAIS
#
# Roda em metros (UTM), não em graus, evitando distorção geográfica.
# Usa linear_sum_assignment para garantir exatamente floor(n/k) ou ceil(n/k)
# slots por cluster — sem desequilíbrio.
# ---------------------------------------------------------------------------

def _kmeans_constrained_utm(
    slots: List[Dict],
    n_clusters: int,
    n_init: int = 15,
) -> List[int]:
    """
    Agrupa slots em n_clusters com cotas iguais (±1), em UTM (metros).

    1. Converter lat/lon → UTM antes de qualquer cálculo de distância.
    2. K-means++ com n_init restarts → melhores centroides.
    3. linear_sum_assignment com cotas → assignment exato sem desequilíbrio.
    """
    n = len(slots)
    if n == 0:
        return []
    if n_clusters >= n:
        return list(range(n))

    # Converter para UTM
    pts = np.array([_slot_utm(s) for s in slots])  # (easting, northing) em metros

    # Cotas
    base_q    = n // n_clusters
    remainder = n % n_clusters
    quotas    = [base_q + (1 if i < remainder else 0) for i in range(n_clusters)]

    best_centroids = None
    best_inertia   = float("inf")

    for _ in range(n_init):
        # K-means++ initialization
        idx = [np.random.randint(n)]
        for _ in range(n_clusters - 1):
            d2 = np.array([
                min(np.sum((pts[i] - pts[c]) ** 2) for c in idx)
                for i in range(n)
            ])
            total = d2.sum()
            probs = d2 / total if total > 0 else np.ones(n) / n
            idx.append(int(np.random.choice(n, p=probs)))

        centroids = pts[idx].copy()

        # K-means iterations
        assign = np.zeros(n, dtype=int)
        for _ in range(300):
            dists  = np.linalg.norm(pts[:, None, :] - centroids[None, :, :], axis=2)
            new_assign = dists.argmin(axis=1)
            if np.array_equal(new_assign, assign):
                break
            assign = new_assign
            new_centroids = np.zeros_like(centroids)
            for k in range(n_clusters):
                members = pts[assign == k]
                new_centroids[k] = (members.mean(axis=0)
                                    if len(members) > 0 else centroids[k])
            centroids = new_centroids

        inertia = float(np.sum([
            np.sum((pts[i] - centroids[assign[i]]) ** 2) for i in range(n)
        ]))
        if inertia < best_inertia:
            best_inertia   = inertia
            best_centroids = centroids.copy()

    # Assignment com cotas via linear_sum_assignment
    expanded = np.vstack([
        np.tile(best_centroids[j], (quotas[j], 1))
        for j in range(n_clusters)
    ])
    cost = np.sum((pts[:, None, :] - expanded[None, :, :]) ** 2, axis=2)
    row_ind, col_ind = linear_sum_assignment(cost)

    col_to_cluster: List[int] = []
    for j in range(n_clusters):
        col_to_cluster.extend([j] * quotas[j])

    result = [0] * n
    for i, c in zip(row_ind, col_ind):
        result[i] = col_to_cluster[c]

    return result


# ---------------------------------------------------------------------------
# CONSTRUÇÃO DE POLÍGONOS DE TERRITÓRIO EM UTM
#
# Abordagem (inspirada em clustering_to_geojson.py):
#   1. Para cada cluster: convex hull dos seus slots em UTM + buffer inicial.
#   2. Remover sobreposições entre clusters (difference: menor cede ao maior).
#   3. Expandir iterativamente com buffer crescente até cobrir toda a jurisdição.
#   4. Reprojetar para WGS84.
#
# Por que não usar Voronoi diretamente:
#   Voronoi gera células por ponto (slot), não por cluster. Quando um cluster
#   tem poucos slots (1-2), a célula pode colapsar em geometria degenerada
#   após clip. A abordagem de convex hull + buffer é robusta mesmo com 1 slot.
# ---------------------------------------------------------------------------

def _build_territory_polygons_utm(
    slots: List[Dict],
    cluster_idxs: List[int],
    n_clusters: int,
    jur_poly_wgs84,
    expand_step_m: float = 200.0,
    max_expand_steps: int = 150,
    smooth_m: float = 50.0,
) -> Dict[int, object]:
    """
    Constrói polígonos de território em UTM e retorna em WGS84.

    Suporte a MultiPolygon
    ----------------------
    Quando a jurisdição é um MultiPolygon (duas ou mais áreas separadas),
    o Voronoi é calculado separadamente dentro de cada componente.
    Isso evita que células de Voronoi cruzem o vazio entre componentes,
    o que causava um cluster cobrindo toda uma componente enquanto a outra
    ficava sem polígono.

    Algoritmo por componente
    -------------------------
    1. Decompor jur_utm em componentes (Polygon individuais).
    2. Para cada componente: identificar os slots dentro dela e calcular
       Voronoi restrito àquela componente.
    3. Acumular células por cluster_idx através de todas as componentes.
    4. Unir células por cluster → polígono bruto de cada território.
    5. Expansão iterativa para cobrir 100% da jurisdição sem gaps.
    6. Suavização e reprojeção para WGS84.
    """
    from scipy.spatial import Voronoi as _Voronoi

    if not slots:
        return {}

    n = len(slots)

    # ── 1. Jurisdição em UTM (pode ser MultiPolygon) ──────────────────────
    jur_utm = None
    if _HAS_PYPROJ and jur_poly_wgs84 is not None:
        try:
            jur_utm = make_valid(_wgs84_to_utm(jur_poly_wgs84))
        except Exception:
            pass

    # Decompor em componentes individuais (Polygon)
    if jur_utm is None:
        components: List[object] = []
    elif jur_utm.geom_type == "Polygon":
        components = [jur_utm]
    else:
        # MultiPolygon ou GeometryCollection
        components = [
            g for g in (jur_utm.geoms if hasattr(jur_utm, "geoms") else [jur_utm])
            if g.geom_type == "Polygon" and not g.is_empty
        ]
    if not components:
        components = []  # sem clip — Voronoi irá rodar sem restrição

    # ── 2. Coordenadas UTM dos slots ──────────────────────────────────────
    pts_utm = np.array([_slot_utm(s) for s in slots])  # (easting, northing)

    # ── 3. Para cada componente: Voronoi restrito àquela área ────────────
    # Acumular células Voronoi por cluster_idx
    cluster_cells: Dict[int, List[object]] = defaultdict(list)

    def _voronoi_for_component(comp_poly, slot_indices):
        """
        Calcula Voronoi para os slots dentro de comp_poly e acumula células.
        slot_indices: índices (em pts_utm / cluster_idxs) dos slots desta componente.
        """
        if not slot_indices:
            return

        sub_pts = pts_utm[slot_indices]  # shape (m, 2)
        m = len(sub_pts)

        # Pontos âncora para fechar células de borda
        rng = max(
            sub_pts[:, 0].max() - sub_pts[:, 0].min(),
            sub_pts[:, 1].max() - sub_pts[:, 1].min(),
            1.0,
        )
        pad  = rng * 4.0 + 50_000
        cx   = (sub_pts[:, 0].min() + sub_pts[:, 0].max()) / 2
        cy   = (sub_pts[:, 1].min() + sub_pts[:, 1].max()) / 2
        anch = np.array([
            [cx - pad, cy - pad], [cx + pad, cy - pad],
            [cx - pad, cy + pad], [cx + pad, cy + pad],
            [cx,       cy - pad], [cx,       cy + pad],
            [cx - pad, cy      ], [cx + pad, cy      ],
        ])
        pts_ext = np.vstack([sub_pts, anch])
        bbox    = Polygon([
            (cx - pad, cy - pad), (cx + pad, cy - pad),
            (cx + pad, cy + pad), (cx - pad, cy + pad),
        ])

        try:
            vor = _Voronoi(pts_ext)
        except Exception as e:
            print(f"  WARN Voronoi falhou na componente ({e}).")
            vor = None

        if vor is not None:
            for local_i, global_i in enumerate(slot_indices):
                k          = cluster_idxs[global_i]
                region_idx = vor.point_region[local_i]
                region     = vor.regions[region_idx]
                if not region:
                    continue
                if -1 in region:
                    cell = bbox
                else:
                    verts = [vor.vertices[v] for v in region]
                    if len(verts) < 3:
                        continue
                    try:
                        cell = make_valid(Polygon(verts))
                    except Exception:
                        continue

                # Clip pela componente específica (não pela jurisdição inteira)
                try:
                    cell = make_valid(cell.intersection(comp_poly))
                except Exception:
                    pass
                if cell is not None and not cell.is_empty:
                    cluster_cells[k].append(cell)
        else:
            # Fallback: buffer do ponto dentro da componente
            for local_i, global_i in enumerate(slot_indices):
                k    = cluster_idxs[global_i]
                x, y = sub_pts[local_i]
                cell = Point(x, y).buffer(pad / max(m, 1))
                try:
                    cell = make_valid(cell.intersection(comp_poly))
                except Exception:
                    pass
                if cell is not None and not cell.is_empty:
                    cluster_cells[k].append(cell)

    if components:
        # Para cada componente, identificar quais slots estão dentro dela
        for comp in components:
            indices_in_comp = [
                i for i in range(n)
                if comp.contains(Point(pts_utm[i][0], pts_utm[i][1]))
            ]
            if not indices_in_comp:
                # Nenhum slot nesta componente — atribuir ao cluster mais
                # próximo diretamente, sem depender da expansão por buffer.
                # Isso evita geometrias degeneradas (triângulos, linhas) que
                # surgem quando o buffer de outro componente é cortado pela
                # jurisdição e resulta em fragmentos minúsculos.
                comp_centroid = comp.centroid
                cx_c, cy_c = comp_centroid.x, comp_centroid.y
                nearest_k = min(
                    range(n),
                    key=lambda i: (pts_utm[i][0] - cx_c) ** 2 + (pts_utm[i][1] - cy_c) ** 2,
                )
                k = cluster_idxs[nearest_k]
                cluster_cells[k].append(comp)
                print(f"  INF componente sem slots → atribuída ao cluster {k}")
                continue
            _voronoi_for_component(comp, indices_in_comp)
    else:
        # Sem jurisdição definida: Voronoi global sem clip
        _voronoi_for_component(
            Polygon([
                (pts_utm[:, 0].min() - 1e5, pts_utm[:, 1].min() - 1e5),
                (pts_utm[:, 0].max() + 1e5, pts_utm[:, 1].min() - 1e5),
                (pts_utm[:, 0].max() + 1e5, pts_utm[:, 1].max() + 1e5),
                (pts_utm[:, 0].min() - 1e5, pts_utm[:, 1].max() + 1e5),
            ]),
            list(range(n)),
        )

    # ── 4. União das células por cluster ──────────────────────────────────
    polys_utm: Dict[int, object] = {}
    for k in range(n_clusters):
        cells = cluster_cells.get(k, [])
        if not cells:
            continue
        try:
            merged = make_valid(unary_union(cells))
        except Exception:
            merged = cells[0] if cells else None
        if merged is not None and not merged.is_empty:
            polys_utm[k] = merged

    if not polys_utm:
        return {}

    # ── 5. Expansão iterativa para cobrir bordas residuais ───────────────
    # Cobre apenas gaps nas bordas de cada componente (área entre o slot
    # mais externo e a borda da jurisdição). Componentes sem slots já foram
    # atribuídas diretamente ao cluster mais próximo no passo anterior.
    effective_jur = jur_utm if jur_utm is not None else None
    if effective_jur is not None:
        for _step in range(max_expand_steps):
            try:
                covered = make_valid(
                    unary_union([p for p in polys_utm.values()
                                 if p is not None and not p.is_empty])
                )
                gap = effective_jur.difference(covered)
            except Exception:
                break

            if gap.is_empty or gap.area < 1.0:
                break

            expanded: Dict[int, object] = {}
            for k, poly in polys_utm.items():
                if poly is None or poly.is_empty:
                    continue
                try:
                    exp = make_valid(
                        poly.buffer(expand_step_m, resolution=16)
                        .intersection(effective_jur)
                    )
                    expanded[k] = exp if not exp.is_empty else poly
                except Exception:
                    expanded[k] = poly

            # Remover sobreposições mantendo todos os clusters
            sorted_ks = sorted(expanded.keys(),
                               key=lambda k: expanded[k].area, reverse=True)
            claimed: Optional[object] = None
            new_polys: Dict[int, object] = {}
            for k in sorted_ks:
                poly = expanded[k]
                if claimed is not None and not claimed.is_empty:
                    try:
                        poly = make_valid(poly.difference(claimed))
                    except Exception:
                        pass
                if poly is None or poly.is_empty:
                    new_polys[k] = polys_utm.get(k)  # manter anterior
                    continue
                new_polys[k] = poly
                try:
                    all_v = [p for p in new_polys.values()
                             if p is not None and not p.is_empty]
                    claimed = make_valid(unary_union(all_v)) if all_v else None
                except Exception:
                    pass

            polys_utm = {k: v for k, v in new_polys.items()
                         if v is not None and not v.is_empty}

    # ── 6. Suavização morfológica ─────────────────────────────────────────
    if smooth_m > 0:
        for k in list(polys_utm.keys()):
            try:
                s = polys_utm[k].buffer(smooth_m).buffer(-smooth_m)
                if not s.is_empty:
                    polys_utm[k] = make_valid(s)
            except Exception:
                pass

    # ── 7. Clip final pela jurisdição completa ────────────────────────────
    # Garante que nenhum polígono ultrapasse a jurisdição após a expansão,
    # e que territórios em jurisdições MultiPolygon sejam corretamente
    # recortados — podendo resultar em MultiPolygon (comportamento esperado).
    if effective_jur is not None:
        for k in list(polys_utm.keys()):
            poly = polys_utm[k]
            if poly is None or poly.is_empty:
                continue
            try:
                clipped = make_valid(poly.intersection(effective_jur))
                if clipped is not None and not clipped.is_empty:
                    polys_utm[k] = clipped
            except Exception:
                pass

    # ── 8. Reprojetar para WGS84 ──────────────────────────────────────────
    # MultiPolygon é preservado — um território pode ter mais de um fragmento
    # quando a jurisdição é composta por áreas separadas.
    result: Dict[int, object] = {}
    for k, poly in polys_utm.items():
        if poly is None or poly.is_empty:
            continue
        if _HAS_PYPROJ:
            try:
                poly = make_valid(_utm_to_wgs84(poly))
            except Exception:
                pass

        if poly is not None and not poly.is_empty:
            result[k] = poly

    return result

    # ── 1. Jurisdição em UTM ──────────────────────────────────────────────
    jur_utm = None
    if _HAS_PYPROJ and jur_poly_wgs84 is not None:
        try:
            jur_utm = make_valid(_wgs84_to_utm(jur_poly_wgs84))
        except Exception:
            pass

    # ── 2. Coordenadas UTM dos slots ──────────────────────────────────────
    pts_utm = np.array([_slot_utm(s) for s in slots])  # (easting, northing)

    # ── 3. Voronoi em UTM ─────────────────────────────────────────────────
    # Adicionar pontos âncora nas bordas para fechar células de borda.
    rng = max(
        pts_utm[:, 0].max() - pts_utm[:, 0].min(),
        pts_utm[:, 1].max() - pts_utm[:, 1].min(),
        1.0,
    )
    pad = rng * 4.0 + 50_000   # 50 km de margem além dos slots
    cx  = (pts_utm[:, 0].min() + pts_utm[:, 0].max()) / 2
    cy  = (pts_utm[:, 1].min() + pts_utm[:, 1].max()) / 2
    anchors = np.array([
        [cx - pad, cy - pad], [cx + pad, cy - pad],
        [cx - pad, cy + pad], [cx + pad, cy + pad],
        [cx,       cy - pad], [cx,       cy + pad],
        [cx - pad, cy      ], [cx + pad, cy      ],
    ])
    pts_ext = np.vstack([pts_utm, anchors])

    try:
        vor = _Voronoi(pts_ext)
    except Exception as e:
        print(f"  WARN Voronoi falhou ({e}) — usando bbox por cluster.")
        vor = None

    # Bounding box para células abertas (com vértice -1)
    bbox_utm = Polygon([
        (cx - pad, cy - pad), (cx + pad, cy - pad),
        (cx + pad, cy + pad), (cx - pad, cy + pad),
    ])

    # ── 4. Reunir células Voronoi por cluster ─────────────────────────────
    cluster_cells: Dict[int, List[object]] = defaultdict(list)

    if vor is not None:
        for pt_idx in range(n):
            k          = cluster_idxs[pt_idx]
            region_idx = vor.point_region[pt_idx]
            region     = vor.regions[region_idx]
            if not region:
                continue
            if -1 in region:
                cell = bbox_utm
            else:
                verts = [vor.vertices[v] for v in region]
                if len(verts) < 3:
                    continue
                try:
                    cell = make_valid(Polygon(verts))
                except Exception:
                    continue

            # Clip imediato pela jurisdição para evitar células gigantes
            if jur_utm is not None:
                try:
                    cell = make_valid(cell.intersection(jur_utm))
                except Exception:
                    pass
            if cell is not None and not cell.is_empty:
                cluster_cells[k].append(cell)
    else:
        # Fallback sem Voronoi: assign cada hex ao cluster mais próximo
        # via partição simples da bounding box
        for k in range(n_clusters):
            pts_k = pts_utm[np.array(cluster_idxs) == k]
            if len(pts_k) == 0:
                continue
            from shapely.geometry import MultiPoint as _MP
            hull = _MP([Point(x, y) for x, y in pts_k]).convex_hull
            cell = hull.buffer(pad / n_clusters)
            if jur_utm is not None:
                try:
                    cell = cell.intersection(jur_utm)
                except Exception:
                    pass
            if cell is not None and not cell.is_empty:
                cluster_cells[k].append(cell)

    # ── 5. União das células por cluster ──────────────────────────────────
    polys_utm: Dict[int, object] = {}
    for k in range(n_clusters):
        cells = cluster_cells.get(k, [])
        if not cells:
            continue
        try:
            merged = make_valid(unary_union(cells))
        except Exception:
            merged = cells[0] if cells else None
        if merged is not None and not merged.is_empty:
            polys_utm[k] = merged

    if not polys_utm:
        return {}

    # ── 6. Expansão iterativa para cobrir 100% da jurisdição ──────────────
    # O Voronoi já cobre toda a área entre slots, mas pode faltar cobertura
    # nas bordas da jurisdição que ficam além do slot mais externo.
    if jur_utm is not None:
        for _step in range(max_expand_steps):
            try:
                covered = make_valid(
                    unary_union([p for p in polys_utm.values()
                                 if p is not None and not p.is_empty])
                )
                gap = jur_utm.difference(covered)
            except Exception:
                break

            if gap.is_empty or gap.area < 1.0:
                break

            # Expandir cada polígono; o vizinho mais próximo ao gap o absorve
            expanded: Dict[int, object] = {}
            for k, poly in polys_utm.items():
                if poly is None or poly.is_empty:
                    continue
                try:
                    exp = make_valid(
                        poly.buffer(expand_step_m, resolution=16)
                        .intersection(jur_utm)
                    )
                    expanded[k] = exp if not exp.is_empty else poly
                except Exception:
                    expanded[k] = poly

            # Retirar sobreposições: cada cluster cede à área já atribuída
            # aos clusters que têm MORE área expandida (mantém proporção)
            sorted_ks = sorted(expanded.keys(),
                               key=lambda k: expanded[k].area, reverse=True)
            claimed: Optional[object] = None
            new_polys: Dict[int, object] = {}
            for k in sorted_ks:
                poly = expanded[k]
                if claimed is not None and not claimed.is_empty:
                    try:
                        poly = make_valid(poly.difference(claimed))
                    except Exception:
                        pass
                if poly is None or poly.is_empty:
                    # Manter polígono anterior para não perder o cluster
                    new_polys[k] = polys_utm.get(k)
                    continue
                new_polys[k] = poly
                try:
                    all_v = [p for p in new_polys.values()
                             if p is not None and not p.is_empty]
                    claimed = make_valid(unary_union(all_v)) if all_v else None
                except Exception:
                    pass

            polys_utm = {k: v for k, v in new_polys.items()
                         if v is not None and not v.is_empty}

    # ── 7. Suavização morfológica ──────────────────────────────────────────
    if smooth_m > 0:
        for k in list(polys_utm.keys()):
            try:
                s = polys_utm[k].buffer(smooth_m).buffer(-smooth_m)
                if not s.is_empty:
                    polys_utm[k] = make_valid(s)
            except Exception:
                pass

    # ── 8. Reprojetar para WGS84 ──────────────────────────────────────────
    result: Dict[int, object] = {}
    for k, poly in polys_utm.items():
        if poly is None or poly.is_empty:
            continue
        if _HAS_PYPROJ:
            try:
                poly = make_valid(_utm_to_wgs84(poly))
            except Exception:
                pass  # mantém em UTM como fallback

        if poly is not None and not poly.is_empty:
            result[k] = poly

    return result


# ---------------------------------------------------------------------------
# SPATIAL JOIN: hex → território pelo centróide do hex
# ---------------------------------------------------------------------------

def _build_heatmap(
    demand_map: Dict[str, int],
    territory_polys: Dict[str, object],   # tid → shapely polygon WGS84
    hex_to_ceps: Dict[str, Set[str]],
    station_code: str,
    days: int = 1,
    jur_poly: object = None,              # shapely polygon da jurisdição desta base
) -> List[Dict]:
    tid_list = [(tid, poly) for tid, poly in territory_polys.items()
                if poly is not None and not poly.is_empty]
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

        if territory_id is None and tid_list:
            territory_id = min(
                tid_list, key=lambda x: pt.distance(x[1].centroid)
            )[0]

        # Verificar se o centróide do hex está dentro da jurisdição desta base
        in_jurisdiction: bool
        if jur_poly is not None:
            try:
                in_jurisdiction = bool(jur_poly.contains(pt))
            except Exception:
                in_jurisdiction = False
        else:
            in_jurisdiction = True  # sem polígono de jurisdição → assume dentro

        boundary = h3.cell_to_boundary(h)
        coords   = [[c[1], c[0]] for c in boundary]
        coords.append(coords[0])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "hex_id":           h,
                "demand_total":     demand,
                "demand_daily":     round(demand / days, 2) if days > 0 else demand,
                "ceps":             list(hex_to_ceps.get(h, set()))[:10],
                "delivery_station": station_code,
                "territory_id":     territory_id or "",
                "in_jurisdiction":  in_jurisdiction,
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
) -> Tuple[TerritoriesResult, IdealSupplyResult]:
    """
    Setup completo: solver → K-means UTM → polígonos de território.
    """
    out_dir    = Path(output_dir or Config.DEST_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)
    j_path     = jurisdiction_path or Config.BASE_JURISDICTION
    target_sta = stations or pkg.all_stations

    print(f"\n{'='*60}")
    print(f"  SETUP")
    print(f"  Bases: {target_sta}")
    print(f"  Projeção UTM: {'EPSG:31983 (pyproj OK)' if _HAS_PYPROJ else 'FALLBACK WGS84 — instale pyproj'}")
    print(f"{'='*60}")

    with open(j_path, "r", encoding="utf-8") as f:
        jur_geojson = json.load(f)
    print(f"  {len(jur_geojson.get('features', []))} jurisdições carregadas.\n")

    # ── Solver em paralelo ────────────────────────────────────────────────
    payloads: List[Dict] = []
    dm_filtered: Dict[str, Dict[str, int]] = {}

    for station in target_sta:
        dm = pkg.demand_map(station)
        if not dm:
            print(f"  WARN [{station}] Sem demanda.")
            continue

        # Filtrar hexes cujo centróide está dentro da jurisdição
        jur_poly = _load_jurisdiction_poly(station, jur_geojson)
        if jur_poly is not None:
            before = len(dm)
            dm = {
                h: v for h, v in dm.items()
                if (lambda c: jur_poly.contains(Point(c[1], c[0])))
                   (h3.cell_to_latlng(h))
            }
            removed = before - len(dm)
            if removed:
                print(f"  [{station}] {removed} hexes fora da jurisdição "
                      f"removidos ({len(dm)} restantes).")
        else:
            print(f"  WARN [{station}] Jurisdição não encontrada — "
                  f"usando todos os {len(dm)} hexes com demanda.")

        if not dm:
            print(f"  WARN [{station}] Sem hexes dentro da jurisdição — pulando.")
            continue

        dm_filtered[station] = dm
        daily = {h: max(1, round(v / pkg.days)) for h, v in dm.items() if v > 0}
        payloads.append({
            "station_code": station,
            "hex_ids":      list(daily.keys()),
            "demand_map":   daily,
            "min_cap":      Config.MIN_CAP,
            "max_cap":      Config.MAX_CAP,
            "radii_config": Config.RADII,
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

    # ── K-means UTM + polígonos por base ─────────────────────────────────
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

        # 1. K-means geoespacial em UTM com cotas iguais
        cluster_idxs = _kmeans_constrained_utm(slots, n_clusters)

        counts = Counter(cluster_idxs)
        base_q = n_slots // n_clusters
        print(f"  Slots/cluster: min={min(counts.values())} "
              f"max={max(counts.values())} (esperado {base_q} ou {base_q+1})")

        # 2. Nomear clusters norte → sul (por lat média dos slots em UTM)
        k_lats: Dict[int, List[float]] = defaultdict(list)
        k_lons: Dict[int, List[float]] = defaultdict(list)
        for i, s in enumerate(slots):
            k = cluster_idxs[i]
            k_lats[k].append(s["lat"])
            k_lons[k].append(s["lon"])

        k_mean_lat = {k: sum(v) / len(v) for k, v in k_lats.items()}
        k_mean_lon = {k: sum(v) / len(v) for k, v in k_lons.items()}

        sorted_ks = sorted(
            k_mean_lat.keys(),
            key=lambda k: (-k_mean_lat[k], k_mean_lon.get(k, 0)),
        )
        k_to_tid = {k: f"{station}_bucket-{seq+1:02d}"
                    for seq, k in enumerate(sorted_ks)}

        # 3. Polígonos UTM → WGS84
        k_to_poly = _build_territory_polygons_utm(
            slots=slots,
            cluster_idxs=cluster_idxs,
            n_clusters=n_clusters,
            jur_poly_wgs84=jur_poly,
        )

        base_polys: Dict[str, object] = {}
        for k, tid in k_to_tid.items():
            if k in k_to_poly:
                poly = k_to_poly[k]
                if poly is not None and not poly.is_empty:
                    base_polys[tid] = poly

        # 4. Metadados e slots por território
        for k, tid in k_to_tid.items():
            t_slots_raw = [slots[i] for i, ki in enumerate(cluster_idxs) if ki == k]
            t_cap_day   = sum(s["capacity_s"] for s in t_slots_raw)

            territory_index[tid] = {
                "territory_id": tid,
                "station_code": station,
                "bdm_cluster":  bdm,
                "n_slots":      len(t_slots_raw),
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
                sd2["slot_id"]      = f"{tid}_S{seq_s:02d}"
                sd2["territory_id"] = tid
                t_slot_objs.append(_dict_to_ideal_slot(sd2))
            slots_by_territory[tid] = t_slot_objs

            if tid in base_polys:
                _p = base_polys[tid]
                _geom_type = type(_p).__name__
                if hasattr(_p, "exterior"):
                    _verts = len(list(_p.exterior.coords))
                    geom_info = f"{_geom_type}, {_verts} vértices"
                elif hasattr(_p, "geoms"):
                    _parts = len(list(_p.geoms))
                    geom_info = f"{_geom_type}, {_parts} partes"
                else:
                    geom_info = _geom_type
            else:
                geom_info = "SEM POLÍGONO"
            print(f"    {tid}: {len(t_slots_raw)} slots | "
                  f"{t_cap_day:,.1f} pac/dia | {geom_info}")

        # 5. Heatmap desta base
        dm_base = dm_filtered.get(station, {})
        base_heatmap = _build_heatmap(
            dm_base, base_polys, pkg.hex_to_ceps, station,
            days=pkg.days,
            jur_poly=_load_jurisdiction_poly(station, jur_geojson),
        )
        heatmap_features.extend(base_heatmap)

        # Popular hex_ids no territory_index a partir do spatial join do heatmap
        for ft in base_heatmap:
            props = ft.get("properties", {})
            tid   = props.get("territory_id")
            h     = props.get("hex_id")
            if tid and h and tid in territory_index:
                territory_index[tid].setdefault("hex_ids", []).append(h)

    # ── Salvar artefatos ──────────────────────────────────────────────────
    # Se --stations foi usado E já existem arquivos de saída, fazer merge:
    # manter dados das demais stations e substituir apenas as processadas.
    print(f"\n  Salvando em {out_dir}...")

    t_path   = out_dir / "territories.geojson"
    h_path   = out_dir / "heatmap.geojson"
    idx_path = out_dir / "territories_index.json"
    sup_path = out_dir / "ideal_supply.json"

    is_partial = bool(stations)  # True quando --stations foi usado

    # ── Merge territories.geojson ─────────────────────────────────────────
    existing_t_features: List[Dict] = []
    if is_partial and t_path.exists():
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # Manter features de stations que NÃO foram reprocessadas
            existing_t_features = [
                ft for ft in existing.get("features", [])
                if ft.get("properties", {}).get("delivery_station") not in stations
            ]
            print(f"  Merge territories.geojson: mantendo "
                  f"{len(existing_t_features)} features de outras stations.")
        except Exception as e:
            print(f"  WARN merge territories.geojson falhou ({e}) — sobrescrevendo.")

    t_features = list(existing_t_features)
    for tid, meta in territory_index.items():
        poly = territory_polys_all.get(tid)
        if poly is None or poly.is_empty:
            print(f"  WARN [{tid}] sem polígono válido — omitido do GeoJSON.")
            continue
        try:
            geom = mapping(poly)
        except Exception as e:
            print(f"  WARN [{tid}] erro ao serializar polígono: {e}")
            continue
        geom_type = geom.get("type", "")
        t_features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "territory_id":     tid,
                "delivery_station": meta["station_code"],
                "bdm_cluster":      meta["bdm_cluster"],
                "n_slots":          meta["n_slots"],
                "daily_demand":     meta["daily_demand"],
                "attainment":       None,
                "coverage":         None,
                "geom_type":        geom_type,
            },
        })

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

    # ── Merge heatmap.geojson ─────────────────────────────────────────────
    existing_h_features: List[Dict] = []
    if is_partial and h_path.exists():
        try:
            with open(h_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_h_features = [
                ft for ft in existing.get("features", [])
                if ft.get("properties", {}).get("delivery_station") not in stations
            ]
            print(f"  Merge heatmap.geojson: mantendo "
                  f"{len(existing_h_features)} hexes de outras stations.")
        except Exception as e:
            print(f"  WARN merge heatmap.geojson falhou ({e}) — sobrescrevendo.")

    all_heatmap = existing_h_features + heatmap_features
    with open(h_path, "w", encoding="utf-8") as f:
        json.dump({
            "type": "FeatureCollection",
            "features": all_heatmap,
            "metadata": {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "n_hexes": len(all_heatmap),
            },
        }, f, ensure_ascii=False, indent=2)
    print(f"  ✅ heatmap.geojson — {len(all_heatmap)} hexes")

    # ── Merge territories_index.json ──────────────────────────────────────
    merged_index: Dict = {}
    if is_partial and idx_path.exists():
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                existing_index = json.load(f)
            # Manter entradas de outras stations
            merged_index = {
                tid: meta for tid, meta in existing_index.items()
                if meta.get("station_code") not in stations
            }
            print(f"  Merge territories_index.json: mantendo "
                  f"{len(merged_index)} territórios de outras stations.")
        except Exception as e:
            print(f"  WARN merge territories_index.json falhou ({e}) — sobrescrevendo.")
    merged_index.update(territory_index)

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(merged_index, f, ensure_ascii=False, indent=2)
    print(f"  ✅ territories_index.json — {len(merged_index)} territórios")

    # ── Merge ideal_supply.json ───────────────────────────────────────────
    merged_slots: Dict = {}
    if is_partial and sup_path.exists():
        try:
            with open(sup_path, "r", encoding="utf-8") as f:
                existing_supply = json.load(f)
            # Manter slots de territories de outras stations
            merged_slots = {
                tid: slot_list
                for tid, slot_list in existing_supply.get("slots", {}).items()
                if not any(tid.startswith(f"{st}_") for st in stations)
            }
            print(f"  Merge ideal_supply.json: mantendo "
                  f"{len(merged_slots)} territórios de outras stations.")
        except Exception as e:
            print(f"  WARN merge ideal_supply.json falhou ({e}) — sobrescrevendo.")

    supply_result = IdealSupplyResult(slots_by_territory=slots_by_territory)
    # Salvar com merge: passar slots existentes + novos para _save_supply via patch
    if merged_slots:
        # Serializar novos slots no mesmo formato
        new_serialized: Dict = {}
        for tid, slot_objs in slots_by_territory.items():
            new_serialized[tid] = [
                {
                    "slot_id":            s.slot_id,
                    "station_code":       s.station_code,
                    "territory_id":       s.bucket_id,
                    "origin_hex":         s.origin_hex,
                    "radius_s":           s.radius_s,
                    "capacity_s":         s.capacity_s,
                    "lat":                s.lat,
                    "lon":                s.lon,
                    "allocations":        [{"hex_id": a.hex_id,
                                           "packages_assigned": a.packages_assigned}
                                          for a in s.allocations],
                    "matched_partner_id": s.matched_partner_id,
                }
                for s in slot_objs
            ]
        all_slots = {**merged_slots, **new_serialized}
        total_slots_count = sum(len(v) for v in all_slots.values())
        output = {
            "_metadata": {
                "generated_at":   datetime.now().isoformat(timespec="seconds"),
                "n_territories":  len(all_slots),
                "n_slots":        total_slots_count,
            },
            "slots": all_slots,
        }
        with open(sup_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  ✅ ideal_supply.json — {len(all_slots)} territórios / "
              f"{total_slots_count} slots")
    else:
        _save_supply(supply_result, out_dir)
        print(f"  ✅ ideal_supply.json")

    # Montar TerritoriesResult com índice completo (merged)
    hex_to_territory = {
        f["properties"]["hex_id"]: f["properties"]["territory_id"]
        for f in all_heatmap
        if f["properties"].get("territory_id")
    }
    territories = TerritoriesResult(
        territory_index=merged_index,
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
    """Atualiza attainment e coverage no territories.geojson sem alterar geometrias."""
    path = Path(output_dir) / "territories.geojson"
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj.get("features", []):
        tid = feat["properties"].get("territory_id")
        if tid and tid in territory_stats:
            feat["properties"]["attainment"] = territory_stats[tid].get("attainment")
            feat["properties"]["coverage"]   = territory_stats[tid].get("coverage")
    gj["metadata"]["last_daily_update"] = datetime.now().isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, indent=2)
    print("  territories.geojson atualizado com métricas daily.")


def rebuild_territory_polygons(
    output_dir: str,
    stations: Optional[List[str]] = None,
    smooth_m: float = 50.0,
) -> None:
    """
    Pós-processamento daily: reconstrói os polígonos de território a partir
    da união real dos hexágonos H3 de cada território.

    Por que fazer isso no daily
    ---------------------------
    O Voronoi do setup gera polígonos suaves mas aproximados — na fronteira
    entre territórios, um hexágono pode ter seu centroide em um território
    mas parte da área visual no polígono do vizinho. Após o daily (quando
    hex_ids estão populados no territories_index.json), reconstruímos os
    polígonos como a união exata dos hexágonos H3, garantindo que o visual
    reflita o que o sistema calculou internamente.

    Pipeline por território
    -----------------------
    1. Para cada hex_id do território: obter o polígono H3 (cell_to_boundary)
    2. União de todos os hexágonos → polígono bruto (bordas dentadas)
    3. Suavização morfológica leve (buffer/erode) → bordas mais suaves
    4. Clip pelo polígono de jurisdição (se disponível)
    5. Atualizar a geometria no territories.geojson preservando as propriedades
    """
    out_dir   = Path(output_dir)
    t_path    = out_dir / "territories.geojson"
    idx_path  = out_dir / "territories_index.json"
    jur_path  = Path(Config.BASE_JURISDICTION)

    if not t_path.exists() or not idx_path.exists():
        print("  WARN rebuild_territory_polygons: arquivos não encontrados — pulando.")
        return

    print(f"\n  Reconstruindo polígonos de território a partir dos hexágonos H3...")

    # Carregar índice e GeoJSON atual
    with open(idx_path, "r", encoding="utf-8") as f:
        territory_index = json.load(f)
    with open(t_path, "r", encoding="utf-8") as f:
        gj = json.load(f)

    # Carregar jurisdições para clip
    jur_polys: Dict[str, object] = {}
    if jur_path.exists():
        try:
            with open(jur_path, "r", encoding="utf-8") as f:
                jur_gj = json.load(f)
            for ft in jur_gj.get("features", []):
                sc = ft.get("properties", {}).get("delivery_station")
                if sc:
                    try:
                        jur_polys[sc] = make_valid(shape(ft["geometry"]))
                    except Exception:
                        pass
        except Exception:
            pass

    # Filtrar territórios a reconstruir
    tids_to_rebuild = set()
    for tid, meta in territory_index.items():
        sc = meta.get("station_code", "")
        if stations and sc not in stations:
            continue
        if meta.get("hex_ids"):
            tids_to_rebuild.add(tid)

    if not tids_to_rebuild:
        print("  WARN rebuild: nenhum território com hex_ids encontrado.")
        return

    rebuilt = 0
    skipped = 0

    for feat in gj.get("features", []):
        tid = feat["properties"].get("territory_id")
        if tid not in tids_to_rebuild:
            continue

        meta       = territory_index[tid]
        hex_ids    = meta.get("hex_ids", [])
        station    = meta.get("station_code", "")
        jur_poly   = jur_polys.get(station)

        if not hex_ids:
            skipped += 1
            continue

        # 1. Construir polígonos H3 em WGS84
        hex_polys = []
        for h in hex_ids:
            try:
                boundary = h3.cell_to_boundary(h)
                coords   = [(c[1], c[0]) for c in boundary]  # lon, lat
                coords.append(coords[0])
                hex_polys.append(Polygon(coords))
            except Exception:
                pass

        if not hex_polys:
            skipped += 1
            continue

        # 2. União dos hexágonos
        try:
            merged = make_valid(unary_union(hex_polys))
        except Exception:
            skipped += 1
            continue

        if merged is None or merged.is_empty:
            skipped += 1
            continue

        # 3. Suavização morfológica leve em UTM
        if smooth_m > 0 and _HAS_PYPROJ:
            try:
                merged_utm = make_valid(_wgs84_to_utm(merged))
                smoothed   = merged_utm.buffer(smooth_m).buffer(-smooth_m)
                if not smoothed.is_empty:
                    merged = make_valid(_utm_to_wgs84(smoothed))
            except Exception:
                pass  # manter sem suavização

        # 4. Clip pela jurisdição
        if jur_poly is not None:
            try:
                clipped = make_valid(merged.intersection(jur_poly))
                if clipped is not None and not clipped.is_empty:
                    merged = clipped
            except Exception:
                pass

        # 5. Atualizar geometria na feature
        try:
            feat["geometry"] = mapping(merged)
            feat["properties"]["geom_type"] = merged.geom_type
            rebuilt += 1
        except Exception:
            skipped += 1

    gj["metadata"]["polygons_rebuilt_at"] = datetime.now().isoformat(timespec="seconds")
    gj["metadata"]["polygons_source"]     = "H3_union"

    with open(t_path, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False, indent=2)

    size_kb = t_path.stat().st_size / 1024
    print(f"  ✅ territories.geojson reconstruído: "
          f"{rebuilt} territórios | {skipped} pulados | {size_kb:.1f} KB")


def run_update_heatmap(
    output_dir: str,
    stations: Optional[List[str]] = None,
) -> None:
    """
    Atualiza heatmap.geojson com a base de pacotes atual sem refazer o setup.

    Útil quando a base de dados de pacotes é atualizada mas os territórios
    e slots ideais permanecem os mesmos.

    Requer que territories_index.json e territories.geojson já existam
    (gerados pelo --mode setup).

    Parâmetros
    ----------
    output_dir : str   Pasta onde estão os artefatos do setup e onde o
                       heatmap.geojson será salvo.
    stations   : list  Filtrar bases. Se None, processa todas do índice.
    """
    from shared.load_packages import load_packages

    out_dir  = Path(output_dir or Config.DEST_FOLDER)
    idx_path = out_dir / "territories_index.json"
    t_path   = out_dir / "territories.geojson"
    h_path   = out_dir / "heatmap.geojson"

    if not idx_path.exists():
        raise FileNotFoundError(
            f"territories_index.json não encontrado em {out_dir}.\n"
            "Execute --mode setup antes de usar --update-heatmap."
        )

    print(f"\n{'='*60}")
    print(f"  UPDATE HEATMAP")
    print(f"  Output: {out_dir}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"{'='*60}")

    # Carregar índice de territórios
    with open(idx_path, "r", encoding="utf-8") as f:
        territory_index = json.load(f)

    # Carregar polígonos de território para spatial join
    territory_polys: Dict[str, object] = {}
    if t_path.exists():
        with open(t_path, "r", encoding="utf-8") as f:
            t_gj = json.load(f)
        for ft in t_gj.get("features", []):
            tid = ft.get("properties", {}).get("territory_id")
            if tid:
                try:
                    territory_polys[tid] = shape(ft["geometry"])
                except Exception:
                    pass

    # Carregar nova base de pacotes
    j_path = Config.BASE_JURISDICTION
    jur_geojson: Dict = {}
    try:
        with open(j_path, "r", encoding="utf-8") as f:
            jur_geojson = json.load(f)
        print(f"  {len(jur_geojson.get('features', []))} jurisdições carregadas.")
    except Exception as e:
        print(f"  WARN jurisdição não carregada ({e}) — in_jurisdiction será True para todos.")

    pkg = load_packages(jurisdiction_geojson=jur_geojson or None)

    # Filtrar stations
    target_stations = stations or list({
        meta["station_code"] for meta in territory_index.values()
    })

    # Merge com heatmap existente se --stations foi usado
    existing_features: List[Dict] = []
    if stations and h_path.exists():
        try:
            with open(h_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_features = [
                ft for ft in existing.get("features", [])
                if ft.get("properties", {}).get("delivery_station") not in stations
            ]
            print(f"  Merge: mantendo {len(existing_features)} hexes de outras stations.")
        except Exception as e:
            print(f"  WARN merge heatmap falhou ({e}) — sobrescrevendo.")

    # Construir polígonos por base (apenas os necessários para o spatial join)
    new_features: List[Dict] = []
    for station in sorted(target_stations):
        dm = pkg.demand_map(station)
        if not dm:
            print(f"  WARN [{station}] Sem demanda — pulando.")
            continue

        # Polígonos desta base
        base_polys = {
            tid: poly for tid, poly in territory_polys.items()
            if territory_index.get(tid, {}).get("station_code") == station
        }

        base_features = _build_heatmap(
            dm, base_polys, pkg.hex_to_ceps, station,
            days=pkg.days,
            jur_poly=_load_jurisdiction_poly(station, jur_geojson),
        )
        new_features.extend(base_features)
        print(f"  [{station}] {len(base_features)} hexes | {pkg.days} dias")

    all_features = existing_features + new_features
    heatmap_gj = {
        "type": "FeatureCollection",
        "features": all_features,
        "metadata": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "n_hexes":      len(all_features),
        },
    }

    with open(h_path, "w", encoding="utf-8") as f:
        json.dump(heatmap_gj, f, ensure_ascii=False, indent=2)

    size_kb = h_path.stat().st_size / 1024
    print(f"\n  ✅ heatmap.geojson — {len(all_features)} hexes | {size_kb:.1f} KB")
    print(f"{'='*60}\n")
