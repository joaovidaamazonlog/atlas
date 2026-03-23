"""
regionalization.py
==================
Regionalizacao contigua e balanceada de hexagonos H3 por demanda.

Algoritmo (v4 — Voronoi + SLS seeds + SA + restart)
----------------------------------------------------
Pipeline por tentativa (ate max_restarts ou tolerancia atingida):
  1. Spatial Lagged Sum (SLS): suavizar demanda com 1-ring para seeds
  2. K-means++ ponderado por SLS: seeds nos nucleos reais de demanda
  3. Graph Voronoi (BFS multi-source): forma compacta sem bracos
  4. Absorcao de perifericos por centroide geografico
  5. Reparo de exclaves
  6. Balanceamento greedy + Simulated Annealing (tolerancia configuravel)
  7. Reparo de exclaves final
  Se delta% ainda acima da tolerancia: perturbar seeds e reiniciar.

Interface publica
-----------------
    hex_to_k = regionalize_demand_balanced(
        station_code, n_clusters, demand_map,
        tolerance=0.02, max_restarts=3
    )
    # retorna Dict[str, int]: hex -> indice (0..n_clusters-1)
"""

import math
import random
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

import h3

from models import Config


# ---------------------------------------------------------------------------
# GRAFO DE ADJACENCIA H3
# ---------------------------------------------------------------------------

def _build_adjacency(hex_set: Set[str]) -> Dict[str, List[str]]:
    """Grafo de adjacencia restrito ao dominio hex_set."""
    adj: Dict[str, List[str]] = {h: [] for h in hex_set}
    for h in hex_set:
        for nb in h3.grid_disk(h, 1):
            if nb != h and nb in hex_set:
                adj[h].append(nb)
    return adj


# ---------------------------------------------------------------------------
# COMPONENTES CONEXAS
# ---------------------------------------------------------------------------

def _connected_components(
    hex_set: Set[str], adj: Dict[str, List[str]]
) -> List[List[str]]:
    """BFS para encontrar componentes conexas. O(V+E)."""
    visited: Set[str] = set()
    components: List[List[str]] = []
    for start in hex_set:
        if start in visited:
            continue
        comp: List[str] = []
        q = deque([start])
        while q:
            h = q.popleft()
            if h in visited:
                continue
            visited.add(h)
            comp.append(h)
            for nb in adj[h]:
                if nb not in visited:
                    q.append(nb)
        components.append(comp)
    return components


# ---------------------------------------------------------------------------
# 1. SPATIAL LAGGED SUM (SLS)
# ---------------------------------------------------------------------------

def _spatial_lagged_sum(
    hexes: List[str],
    demand_map: Dict[str, int],
    adj: Dict[str, List[str]],
) -> Dict[str, float]:
    """
    Calcula o Spatial Lagged Sum (SLS) para cada hex.

    SLS[h] = demand[h] + sum(demand[nb] for nb in ring-1)

    Por que usar SLS em vez de demanda bruta para os seeds:
    - Um hex com alta demanda isolada (outlier — ex: condominio denso)
      atrai um seed para si, criando um territorio pequeno e denso que
      forca os demais a se esticarem para compensar.
    - SLS suaviza: so atrai seed o hex que TEM alta demanda E ESTA
      rodeado por vizinhos tambem com demanda relevante — i.e., nucleos
      reais de atividade, nao outliers pontuais.
    - Operacao de 1-ring smoothing, custo O(n), sem parametros extras.
    """
    sls: Dict[str, float] = {}
    for h in hexes:
        total = demand_map.get(h, 0)
        for nb in adj.get(h, []):
            total += demand_map.get(nb, 0)
        sls[h] = max(float(total), 1.0)  # minimo 1 para evitar peso zero
    return sls


# ---------------------------------------------------------------------------
# 2. SEEDS VIA K-MEANS++ PONDERADO POR SLS
# ---------------------------------------------------------------------------

def _geo_dist_sq(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2


def _kmeans_seeds(
    hexes: List[str],
    k: int,
    coords: Dict[str, Tuple[float, float]],
    weights: Dict[str, float],
    max_iter: int = 100,
    n_restarts: int = 6,
    perturb_scale: float = 0.0,
) -> List[str]:
    """
    Seleciona k seeds via k-means++ ponderado.

    Parametros
    ----------
    weights       : pesos por hex (usar SLS, nao demanda bruta)
    n_restarts    : numero de inicializacoes independentes
    perturb_scale : se > 0, adiciona ruido gaussiano aos centroides iniciais
                    antes de rodar o k-means — usado nos restarts do pipeline
                    para escapar de minimos locais identicos

    Retorna lista de k hex_ids projetados do espaco continuo para o dominio.
    """
    if k <= 0:
        return []
    if k >= len(hexes):
        return list(hexes)

    w_list = [weights.get(h, 1.0) for h in hexes]
    w_total = sum(w_list)
    probs   = [w / w_total for w in w_list]
    lats    = [coords[h][0] for h in hexes]
    lons    = [coords[h][1] for h in hexes]
    n       = len(hexes)

    # CDF para amostragem ponderada
    cum: List[float] = []
    acc = 0.0
    for p in probs:
        acc += p
        cum.append(acc)

    def _sample_weighted() -> int:
        r = random.random()
        lo, hi = 0, n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < r:
                lo = mid + 1
            else:
                hi = mid
        return lo

    best_seeds: List[str] = []
    best_inertia: float   = float("inf")

    for _restart in range(n_restarts):
        # ── K-means++ ponderado ───────────────────────────────────────────
        chosen: List[int] = [_sample_weighted()]

        for _ in range(k - 1):
            d2 = [
                min(_geo_dist_sq(lats[i], lons[i], lats[c], lons[c])
                    for c in chosen)
                for i in range(n)
            ]
            scores  = [w_list[i] * d2[i] for i in range(n)]
            total_s = sum(scores)
            if total_s == 0:
                chosen.append(_sample_weighted())
                continue
            r = random.random() * total_s
            acc = 0.0
            next_i = n - 1
            for i, s in enumerate(scores):
                acc += s
                if acc >= r:
                    next_i = i
                    break
            chosen.append(next_i)

        # ── Centroides iniciais (com perturbacao opcional) ────────────────
        centroids: List[Tuple[float, float]] = []
        for ci in chosen:
            lat = lats[ci]
            lon = lons[ci]
            if perturb_scale > 0:
                # Ruido gaussiano na escala da area total dividida por k
                lat += random.gauss(0, perturb_scale)
                lon += random.gauss(0, perturb_scale)
            centroids.append((lat, lon))

        # ── Iteracao k-means ponderada ────────────────────────────────────
        assign: List[int] = [0] * n
        for _it in range(max_iter):
            new_assign = [
                min(range(k), key=lambda ki: _geo_dist_sq(
                    lats[i], lons[i], centroids[ki][0], centroids[ki][1]
                ))
                for i in range(n)
            ]
            if new_assign == assign and _it > 0:
                break
            assign = new_assign

            new_centroids: List[Tuple[float, float]] = []
            for ki in range(k):
                members = [i for i in range(n) if assign[i] == ki]
                if not members:
                    # Centroide vazio: mover para hex mais distante dos demais
                    farthest = max(
                        range(n),
                        key=lambda i: min(
                            _geo_dist_sq(lats[i], lons[i],
                                         centroids[kj][0], centroids[kj][1])
                            for kj in range(k) if kj != ki
                        )
                    )
                    new_centroids.append((lats[farthest], lons[farthest]))
                else:
                    w_sum = sum(w_list[i] for i in members)
                    new_centroids.append((
                        sum(lats[i] * w_list[i] for i in members) / w_sum,
                        sum(lons[i] * w_list[i] for i in members) / w_sum,
                    ))
            centroids = new_centroids

        # ── Inertia ponderada ─────────────────────────────────────────────
        inertia = sum(
            w_list[i] * _geo_dist_sq(
                lats[i], lons[i],
                centroids[assign[i]][0], centroids[assign[i]][1]
            )
            for i in range(n)
        )

        if inertia < best_inertia:
            best_inertia = inertia
            # Projetar centroide continuo -> hex mais proximo no dominio
            projected: List[str] = []
            for ki in range(k):
                c_lat, c_lon = centroids[ki]
                projected.append(min(
                    hexes,
                    key=lambda h: _geo_dist_sq(
                        coords[h][0], coords[h][1], c_lat, c_lon
                    )
                ))
            best_seeds = projected

    # Garantir unicidade
    seen: Set[str] = set()
    unique: List[str] = []
    for s in best_seeds:
        if s not in seen:
            unique.append(s)
            seen.add(s)

    # Completar com hexes de maior SLS ainda nao escolhidos
    if len(unique) < k:
        remaining = sorted(
            [h for h in hexes if h not in seen],
            key=lambda h: weights.get(h, 0.0),
            reverse=True,
        )
        for h in remaining:
            if len(unique) >= k:
                break
            unique.append(h)

    return unique[:k]


# ---------------------------------------------------------------------------
# 3. GRAPH VORONOI (BFS MULTI-SOURCE)
# ---------------------------------------------------------------------------

def _voronoi_partition(
    hexes: List[str],
    k: int,
    adj: Dict[str, List[str]],
    coords: Dict[str, Tuple[float, float]],
    seeds: List[str],
) -> Dict[str, int]:
    """
    Particiona hexes em k regioes via BFS multi-source (Voronoi de grafo).

    Todos os seeds sao inseridos na fila simultaneamente — crescimento
    igual para todos. Cada hex vai ao seed que chega primeiro.
    Resultado: regioes compactas e aproximadamente poligonais.
    """
    if k == 1:
        return {h: 0 for h in hexes}

    hex_set = set(hexes)
    assigned: Dict[str, int] = {}
    queue: deque = deque()

    for i, s in enumerate(seeds):
        if s in hex_set:
            assigned[s] = i
            queue.append((i, s))

    while queue:
        k_idx, h = queue.popleft()
        for nb in adj.get(h, []):
            if nb in hex_set and nb not in assigned:
                assigned[nb] = k_idx
                queue.append((k_idx, nb))

    # Fallback para hexes inalcancaveis
    seed_coords = [coords[s] for s in seeds if s in hex_set]
    for h in hexes:
        if h not in assigned:
            h_lat, h_lon = coords[h]
            nearest = min(
                range(len(seed_coords)),
                key=lambda i: _geo_dist_sq(
                    h_lat, h_lon, seed_coords[i][0], seed_coords[i][1]
                )
            )
            assigned[h] = nearest

    return assigned


# ---------------------------------------------------------------------------
# 4. ABSORCAO DE PERIFERICOS
# ---------------------------------------------------------------------------

def _absorb_peripheral_hexes(
    peripheral: List[str],
    hex_to_k: Dict[str, int],
    n_clusters: int,
    coords: Dict[str, Tuple[float, float]],
) -> None:
    """
    Atribui hexes perifericos (componentes desconexas) ao territorio
    cujo centroide geografico e mais proximo. In-place.
    """
    if not peripheral or not hex_to_k:
        return

    clat: Dict[int, float] = defaultdict(float)
    clon: Dict[int, float] = defaultdict(float)
    cnt:  Dict[int, int]   = defaultdict(int)
    for h, k in hex_to_k.items():
        clat[k] += coords[h][0]
        clon[k] += coords[h][1]
        cnt[k]  += 1

    centroids = {
        k: (clat[k] / cnt[k], clon[k] / cnt[k])
        for k in range(n_clusters)
        if cnt[k] > 0
    }

    for h in peripheral:
        h_lat, h_lon = coords[h]
        nearest = min(
            centroids,
            key=lambda k: _geo_dist_sq(
                h_lat, h_lon, centroids[k][0], centroids[k][1]
            )
        )
        hex_to_k[h] = nearest


# ---------------------------------------------------------------------------
# 5. REPARO DE EXCLAVES
# ---------------------------------------------------------------------------

def _repair_contiguity(
    hex_to_k: Dict[str, int],
    adj: Dict[str, List[str]],
    demand_map: Dict[str, int],
    n_clusters: int,
    max_passes: int = 10,
) -> None:
    """
    Detecta exclaves em cada territorio e os reassigna ao vizinho com
    maior deficit de demanda. Modificacao in-place.
    """
    total = sum(demand_map.get(h, 0) for h in hex_to_k)
    target = total / n_clusters if n_clusters else 0.0

    for _ in range(max_passes):
        changed = False
        for k in range(n_clusters):
            t_hexes = {h for h, c in hex_to_k.items() if c == k}
            if len(t_hexes) <= 1:
                continue

            visited: Set[str] = set()
            comps: List[Set[str]] = []
            for start in t_hexes:
                if start in visited:
                    continue
                comp: Set[str] = set()
                q = deque([start])
                while q:
                    h = q.popleft()
                    if h in visited:
                        continue
                    visited.add(h)
                    comp.add(h)
                    for nb in adj.get(h, []):
                        if nb in t_hexes and nb not in visited:
                            q.append(nb)
                comps.append(comp)

            if len(comps) <= 1:
                continue

            cd: Dict[int, float] = defaultdict(float)
            for h, c in hex_to_k.items():
                cd[c] += demand_map.get(h, 0)

            main_comp = max(comps, key=len)
            for exclave in comps:
                if exclave is main_comp:
                    continue
                for h in exclave:
                    neighbor_ks = {
                        hex_to_k[nb]
                        for nb in adj.get(h, [])
                        if nb in hex_to_k and hex_to_k[nb] != k
                    }
                    if not neighbor_ks:
                        continue
                    best_k = max(neighbor_ks,
                                 key=lambda ki: target - cd[ki])
                    cd[k]      -= demand_map.get(h, 0)
                    cd[best_k] += demand_map.get(h, 0)
                    hex_to_k[h] = best_k
                    changed = True

        if not changed:
            break


# ---------------------------------------------------------------------------
# 6. BALANCEAMENTO: GREEDY + SIMULATED ANNEALING
# ---------------------------------------------------------------------------

def _is_cut_vertex(
    h: str, k: int, hex_to_k: Dict[str, int], adj: Dict[str, List[str]]
) -> bool:
    """True se remover h desconectaria o territorio k. BFS O(|territorio|)."""
    territory = {hh for hh, c in hex_to_k.items() if c == k and hh != h}
    if not territory:
        return False
    start = next(iter(territory))
    visited: Set[str] = set()
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        for nb in adj.get(cur, []):
            if nb in territory and nb not in visited:
                q.append(nb)
    return len(visited) < len(territory)


def _current_delta_pct(
    hex_to_k: Dict[str, int], demand_map: Dict[str, int], n_clusters: int
) -> Tuple[float, Dict[int, float]]:
    """Retorna (delta%, cd_dict)."""
    cd: Dict[int, float] = defaultdict(float)
    for h, c in hex_to_k.items():
        cd[c] += demand_map.get(h, 0)
    if not cd:
        return 0.0, cd
    vals = list(cd.values())
    avg  = sum(vals) / len(vals)
    pct  = (max(vals) - min(vals)) / avg * 100 if avg > 0 else 0.0
    return pct, cd


def _balance_boundaries(
    hex_to_k: Dict[str, int],
    adj: Dict[str, List[str]],
    demand_map: Dict[str, int],
    n_clusters: int,
    tolerance: float = 0.02,
    greedy_rounds: int = 1000,
    sa_rounds: int = 500,
    cooling: float = 0.95,
) -> None:
    """
    Balanceia demanda entre territorios em duas fases. Modificacao in-place.

    Fase 1 — Greedy deterministico
        Processa todos os pares adjacentes, mais desequilibrado primeiro.
        Para cada par, transfere o hex de borda com valor mais proximo de
        diff/2 (transferencia ideal). Loop interno por par ate esgotar.

    Fase 2 — Simulated Annealing
        Ativada se o greedy nao atingiu a tolerancia.
        T_inicial = delta_absoluto atual. Resfriamento: T *= cooling.
        Aceita pioras com prob exp(melhoria / T) para escapar de minimos.
        Para quando delta% <= tolerancia ou T <= 0.5.
    """
    tol_pct = tolerance * 100

    # ── Fase 1: Greedy ────────────────────────────────────────────────────
    for _ in range(greedy_rounds):
        delta_pct, cd = _current_delta_pct(hex_to_k, demand_map, n_clusters)
        if delta_pct <= tol_pct:
            return

        pairs: Set[Tuple[int, int]] = set()
        for h, ki in hex_to_k.items():
            for nb in adj.get(h, []):
                kj = hex_to_k.get(nb)
                if kj is not None and kj != ki and cd[ki] > cd[kj]:
                    pairs.add((ki, kj))

        if not pairs:
            break

        sorted_pairs = sorted(pairs, key=lambda p: cd[p[0]] - cd[p[1]],
                              reverse=True)

        moved_any = False
        for max_k, min_k in sorted_pairs:
            while True:
                diff = cd[max_k] - cd[min_k]
                if diff <= 0:
                    break
                border = [
                    h for h, c in hex_to_k.items()
                    if c == max_k
                    and any(hex_to_k.get(nb) == min_k
                            for nb in adj.get(h, []))
                ]
                if not border:
                    break
                ideal = diff / 2.0
                border.sort(key=lambda h: abs(demand_map.get(h, 0) - ideal))
                swapped = False
                for h in border:
                    h_d = demand_map.get(h, 0)
                    new_diff = abs((cd[max_k] - h_d) - (cd[min_k] + h_d))
                    if new_diff >= diff:
                        continue
                    if not _is_cut_vertex(h, max_k, hex_to_k, adj):
                        hex_to_k[h] = min_k
                        cd[max_k]  -= h_d
                        cd[min_k]  += h_d
                        moved_any   = True
                        swapped     = True
                        break
                if not swapped:
                    break

        if not moved_any:
            break

    # ── Fase 2: Simulated Annealing ───────────────────────────────────────
    delta_pct, cd = _current_delta_pct(hex_to_k, demand_map, n_clusters)
    if delta_pct <= tol_pct:
        return

    vals = list(cd.values())
    T    = max(vals) - min(vals)   # temperatura inicial = delta absoluto

    for _ in range(sa_rounds):
        if T <= 0.5:
            break
        delta_pct, cd = _current_delta_pct(hex_to_k, demand_map, n_clusters)
        if delta_pct <= tol_pct:
            break

        border_hexes = [
            h for h, ki in hex_to_k.items()
            if any(hex_to_k.get(nb, ki) != ki for nb in adj.get(h, []))
        ]
        if not border_hexes:
            break

        h  = random.choice(border_hexes)
        ki = hex_to_k[h]
        h_d = demand_map.get(h, 0)

        neighbor_ks = list({
            hex_to_k[nb]
            for nb in adj.get(h, [])
            if nb in hex_to_k and hex_to_k[nb] != ki
        })
        if not neighbor_ks:
            T *= cooling
            continue

        # 80% escolhe o mais vazio, 20% aleatorio (exploracao)
        kj = (min(neighbor_ks, key=lambda k: cd[k])
              if random.random() < 0.8
              else random.choice(neighbor_ks))

        old_delta = max(cd.values()) - min(cd.values())
        cd[ki] -= h_d
        cd[kj] += h_d
        new_delta = max(cd.values()) - min(cd.values())
        improvement = old_delta - new_delta

        accept = (improvement >= 0 or
                  random.random() < math.exp(improvement / T))

        if accept and not _is_cut_vertex(h, ki, hex_to_k, adj):
            hex_to_k[h] = kj
        else:
            # Reverter cd
            cd[ki] += h_d
            cd[kj] -= h_d

        T *= cooling


# ---------------------------------------------------------------------------
# VALIDACAO
# ---------------------------------------------------------------------------

def _validate(
    hex_to_k: Dict[str, int],
    adj: Dict[str, List[str]],
    demand_map: Dict[str, int],
    n_clusters: int,
    station_code: str,
    attempt: int = 1,
) -> float:
    """Imprime relatorio e retorna delta%."""
    missing = set(demand_map.keys()) - set(hex_to_k.keys())
    tag = f"[tentativa {attempt}]" if attempt > 1 else ""
    print(f"   {'OK ' if not missing else 'ERR'} [{station_code}]{tag} Cobertura: "
          f"{'100%' if not missing else str(len(missing)) + ' hexes'}")

    unique_ks = set(hex_to_k.values())
    print(f"   {'OK ' if len(unique_ks) == n_clusters else 'ERR'} [{station_code}]{tag} "
          f"Territorios: {len(unique_ks)} (esperado {n_clusters})")

    n_exclaves = 0
    for k in range(n_clusters):
        t = {h for h, c in hex_to_k.items() if c == k}
        if len(t) <= 1:
            continue
        visited: Set[str] = set()
        comps = 0
        for start in t:
            if start in visited:
                continue
            comps += 1
            q = deque([start])
            while q:
                h = q.popleft()
                if h in visited:
                    continue
                visited.add(h)
                for nb in adj.get(h, []):
                    if nb in t and nb not in visited:
                        q.append(nb)
        if comps > 1:
            n_exclaves += comps - 1

    print(f"   {'OK ' if n_exclaves == 0 else 'WRN'} [{station_code}]{tag} "
          f"{'Zero exclaves' if n_exclaves == 0 else str(n_exclaves) + ' exclaves'}")

    cd: Dict[int, float] = defaultdict(float)
    for h, k in hex_to_k.items():
        cd[k] += demand_map.get(h, 0)
    delta_pct = 0.0
    if cd:
        vals  = list(cd.values())
        avg_d = sum(vals) / len(vals)
        delta_pct = (max(vals) - min(vals)) / avg_d * 100 if avg_d else 0
        status = "OK " if delta_pct <= 2.0 else "WRN"
        print(f"   {status} [{station_code}]{tag} Demanda: "
              f"avg={avg_d:.0f}  max={max(vals):.0f}  min={min(vals):.0f}  "
              f"delta%={delta_pct:.1f}%")
    return delta_pct


# ---------------------------------------------------------------------------
# PIPELINE INTERNO (uma tentativa)
# ---------------------------------------------------------------------------

def _run_attempt(
    station_code: str,
    main_comp: List[str],
    peripheral: List[str],
    n_clusters: int,
    demand_map: Dict[str, int],
    adj: Dict[str, List[str]],
    coords: Dict[str, Tuple[float, float]],
    sls: Dict[str, float],
    tolerance: float,
    attempt: int,
) -> Dict[str, int]:
    """
    Executa uma tentativa completa do pipeline de regionalizacao.

    Na primeira tentativa (attempt=1): perturb_scale=0 (determinismo nos seeds).
    Nas tentativas seguintes: perturb_scale cresce para diversificar seeds
    e escapar do mesmo minimo local.
    """
    # Escala de perturbacao cresce a cada restart
    # Proporcional ao desvio padrao geografico da area
    if attempt == 1:
        perturb = 0.0
    else:
        lats = [coords[h][0] for h in main_comp]
        lons = [coords[h][1] for h in main_comp]
        lat_std = (max(lats) - min(lats)) / (n_clusters * 4)
        lon_std = (max(lons) - min(lons)) / (n_clusters * 4)
        scale   = max(lat_std, lon_std)
        perturb = scale * (0.3 * (attempt - 1))  # 0.3x, 0.6x, 0.9x...

    print(f"   INF [{station_code}] Tentativa {attempt}"
          + (f" (perturb={perturb:.5f})" if perturb > 0 else ""))

    # Seeds: k-means++ ponderado por SLS
    seeds = _kmeans_seeds(
        main_comp, n_clusters, coords, sls,
        perturb_scale=perturb,
    )

    # Voronoi de grafo -> forma compacta
    hex_to_k = _voronoi_partition(main_comp, n_clusters, adj, coords, seeds)

    # Absorver perifericos
    if peripheral:
        _absorb_peripheral_hexes(peripheral, hex_to_k, n_clusters, coords)

    # Reparo inicial de exclaves
    _repair_contiguity(hex_to_k, adj, demand_map, n_clusters)

    # Balanceamento greedy + SA
    _balance_boundaries(hex_to_k, adj, demand_map, n_clusters,
                        tolerance=tolerance)

    # Reparo final de exclaves
    _repair_contiguity(hex_to_k, adj, demand_map, n_clusters)

    return hex_to_k


# ---------------------------------------------------------------------------
# FUNCAO PUBLICA
# ---------------------------------------------------------------------------

def regionalize_demand_balanced(
    station_code: str,
    n_clusters: int,
    demand_map: Dict[str, int],
    tolerance: float = 0.02,
    max_restarts: int = 3,
) -> Dict[str, int]:
    """
    Regionaliza os hexes de uma base em exatamente n_clusters territorios
    contiguos, compactos e balanceados por demanda.

    Pipeline por tentativa (ate max_restarts ou tolerancia atingida)
    ----------------------------------------------------------------
    1. Spatial Lagged Sum (SLS) dos hexes da componente principal
    2. K-means++ ponderado por SLS  →  seeds nos nucleos de demanda
    3. Graph Voronoi (BFS multi-source)  →  forma compacta
    4. Absorcao de perifericos por centroide geografico
    5. Reparo de exclaves
    6. Balanceamento greedy + SA  →  meta: delta% <= tolerance
    7. Reparo de exclaves final
    Se delta% ainda acima da tolerancia: perturbar seeds e reiniciar.
    Retorna a melhor solucao encontrada (menor delta%).

    Parametros
    ----------
    station_code  : str    Codigo da base (ex: "DSP2").
    n_clusters    : int    Numero EXATO de territorios.
    demand_map    : dict   {hex_id: total_packages_no_periodo}
    tolerance     : float  Delta% maximo aceitavel. Default 0.02 = 2%.
    max_restarts  : int    Tentativas antes de aceitar o melhor resultado.
                           Default 3.

    Retorna
    -------
    Dict[str, int]: hex -> indice de territorio (0 .. n_clusters-1).
    """
    if not demand_map or n_clusters <= 0:
        return {}

    total = sum(demand_map.values())
    print(f"\n  Regionalizando [{station_code}] -> {n_clusters} territorios | "
          f"{len(demand_map):,} hexes | demanda: {total:,} | "
          f"tolerancia: {tolerance * 100:.0f}% | max_restarts: {max_restarts}")

    # Pre-computar coordenadas
    coords: Dict[str, Tuple[float, float]] = {
        h: h3.cell_to_latlng(h) for h in demand_map
    }
    hex_set = set(demand_map.keys())

    # Grafo de adjacencia (compartilhado entre todas as tentativas)
    adj = _build_adjacency(hex_set)

    # Componentes conexas
    components = _connected_components(hex_set, adj)
    print(f"   INF [{station_code}] Componentes conexas: {len(components)}")

    main_comp  = max(components, key=len)
    peripheral = [h for comp in components if comp is not main_comp for h in comp]
    if peripheral:
        print(f"   INF [{station_code}] {len(peripheral)} hexes perifericos "
              f"-> absorvidos por centroide")

    # SLS calculado uma vez para a componente principal
    sls = _spatial_lagged_sum(main_comp, demand_map, adj)

    # ── Loop de restarts ──────────────────────────────────────────────────
    best_hex_to_k: Dict[str, int] = {}
    best_delta_pct: float = float("inf")

    for attempt in range(1, max_restarts + 1):
        hex_to_k = _run_attempt(
            station_code=station_code,
            main_comp=main_comp,
            peripheral=peripheral,
            n_clusters=n_clusters,
            demand_map=demand_map,
            adj=adj,
            coords=coords,
            sls=sls,
            tolerance=tolerance,
            attempt=attempt,
        )

        delta_pct = _validate(hex_to_k, adj, demand_map, n_clusters,
                              station_code, attempt)

        if delta_pct < best_delta_pct:
            best_delta_pct = delta_pct
            best_hex_to_k  = dict(hex_to_k)

        if best_delta_pct <= tolerance * 100:
            print(f"   OK  [{station_code}] Tolerancia atingida na tentativa {attempt}")
            break
    else:
        print(f"   WRN [{station_code}] Melhor resultado apos {max_restarts} "
              f"tentativas: delta%={best_delta_pct:.1f}%")

    # Cobertura final (edge case extremo)
    uncovered = hex_set - set(best_hex_to_k.keys())
    if uncovered:
        cd_tmp: Dict[int, float] = defaultdict(float)
        for h, k in best_hex_to_k.items():
            cd_tmp[k] += demand_map.get(h, 0)
        for h in uncovered:
            fallback = min(cd_tmp, key=cd_tmp.get)
            best_hex_to_k[h] = fallback
            cd_tmp[fallback] += demand_map.get(h, 0)
        print(f"   WRN [{station_code}] {len(uncovered)} hexes no fallback")

    return best_hex_to_k
