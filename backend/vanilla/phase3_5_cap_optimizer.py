"""
phase3_5_cap_optimizer.py
=========================
Fase 3.5 — Identificação de oportunidades de aumento de ADV para parceiros Active.

Responsabilidade
----------------
Para cada parceiro Active com capacity_s < 80, avalia oportunidades em dois modos:

MODO A — Parceiro com slot matched (matched_slot_id não nulo):
  O CP-SAT já calculou a posição ideal para aquele slot. Se o origin_hex do
  parceiro difere do origin_hex do slot, sugere mover para o hex do slot e
  calcula o ADV simulado nessa posição usando todos os raios disponíveis.
  Candidatos: apenas o origin_hex do slot matched (1 candidato).

MODO B — Parceiro sem slot matched (matched_slot_id nulo):
  Sem referência do CP-SAT. Varre grid_disk(k=1) × todos os raios disponíveis
  para encontrar a melhor posição na demanda residual.
  Candidatos: todos os hexes em grid_disk(k=1) do origin_hex do parceiro.

Para cada candidato × raio, usa a mesma lógica do what-if engine:
  hexes_original  = hexes dentro do raio a partir da posição ATUAL
                    (apenas hexes dentro da jurisdição do parceiro)
  hexes_simulated = hexes dentro do raio a partir da posição CANDIDATA
                    (apenas hexes dentro da jurisdição do parceiro)
  loss  = soma de demand_allocated dos hexes perdidos
  gain  = soma de demand_residual dos hexes ganhos
  adv_simulated = min(max(capacity - loss + gain, 0), 80)
  adv_gain      = adv_simulated - capacity

Filtragem por jurisdição
------------------------
Apenas hexes dentro da jurisdição da base do parceiro são considerados.
Estratégia com fallback:
  1. Heatmap pós-setup: usa campo `in_jurisdiction` + `delivery_station` — O(1) por hex.
  2. Heatmap legado: usa shapely point-in-polygon contra o polígono de jurisdição.

Seleciona a combinação com maior adv_gain > 0; empate → menor raio.
Executa em paralelo com ProcessPoolExecutor (max_workers configurável).

Artefato modificado
-------------------
dados_mapa.json — campo adv_opportunity por parceiro Active:
  {"suggested_lat", "suggested_lon", "suggested_cap",
   "suggested_radius", "estimated_adv_gain", "distance_from_current"}
  ou null quando adv_gain <= 0.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import h3

from shared.models import Config, PartnerMetrics
from vanilla.phase3_partner_fit import FitResult

logger = logging.getLogger(__name__)

_CAP_MAX = 80
_DEFAULT_MAX_WORKERS = 6


# ---------------------------------------------------------------------------
# HELPERS INTERNOS
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância geodésica aproximada em metros usando a fórmula de Haversine."""
    R = 6_371_000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _load_jurisdiction_poly(station_code: str, jurisdiction_path: str):
    """
    Carrega o polígono shapely da jurisdição de uma base canônica,
    incluindo a união com os polígonos das áreas satélite (STATION_ALIASES).
    Retorna None se não encontrado ou se shapely não estiver disponível.
    """
    try:
        from shapely.geometry import shape
        from shapely.validation import make_valid
        from shapely.ops import unary_union
    except ImportError:
        return None

    try:
        with open(jurisdiction_path, "r", encoding="utf-8") as f:
            jur_geojson = json.load(f)
    except Exception:
        return None

    # Códigos a incluir: a base canônica + todas as suas satélites
    satellites = Config.get_satellites(station_code)
    codes_to_include = {station_code} | set(satellites)

    polys = []
    for feature in jur_geojson.get("features", []):
        code = feature.get("properties", {}).get("delivery_station")
        if code not in codes_to_include:
            continue
        try:
            polys.append(make_valid(shape(feature["geometry"])))
        except Exception:
            try:
                polys.append(shape(feature["geometry"]))
            except Exception:
                pass

    if not polys:
        return None
    if len(polys) == 1:
        return polys[0]
    try:
        return make_valid(unary_union(polys))
    except Exception:
        return polys[0]


def _is_hex_in_jurisdiction(
    props: dict,
    station_code: str,
    h_lat: float,
    h_lon: float,
    jur_poly,  # shapely polygon ou None
    allowed_stations: Optional[set[str]] = None,
) -> bool:
    """
    Verifica se um hex pertence à jurisdição da base do parceiro.

    Estratégia com fallback:
    1. Heatmap pós-setup: campo `in_jurisdiction` (bool) + `delivery_station`.
       Fast path — sem cálculo geoespacial.
    2. Heatmap legado (sem `in_jurisdiction`): point-in-polygon com shapely.
       Se jur_poly for None (shapely indisponível), aceita todos os hexes.

    ``allowed_stations`` é o conjunto de códigos de station aceitáveis para
    um parceiro da base canônica — tipicamente ``{station_code} ∪
    Config.get_satellites(station_code)``. Um parceiro remapeado de uma
    satélite para sua canônica (ex.: ``XBA1`` → ``DSA8``) precisa enxergar
    os hexes satélites, que no heatmap pós-setup preservam o código original
    em ``props.delivery_station`` (regra "satélite vence canônica" em
    ``write_heatmap_unified``). Quando ``allowed_stations`` não é fornecido,
    cai no comportamento legado de comparação exata com ``station_code``.
    """
    # Fast path: heatmap pós-setup
    if "in_jurisdiction" in props:
        if props.get("in_jurisdiction") is not True:
            return False
        ds = props.get("delivery_station")
        if allowed_stations is not None:
            return ds in allowed_stations
        return ds == station_code

    # Fallback: point-in-polygon
    if jur_poly is None:
        return True  # sem polígono disponível — não filtra
    try:
        from shapely.geometry import Point
        return jur_poly.contains(Point(h_lon, h_lat))
    except Exception:
        return True


def _load_heatmap_index(output_dir: str) -> Dict[str, dict]:
    """Carrega heatmap.geojson em {hex_id: properties}."""
    path = Path(output_dir) / "heatmap.geojson"
    if not path.exists():
        raise FileNotFoundError(f"heatmap.geojson não encontrado em {output_dir}")
    with open(path, "r", encoding="utf-8") as f:
        geojson = json.load(f)
    index: Dict[str, dict] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        hex_id = props.get("hex_id")
        if hex_id:
            index[hex_id] = props
    logger.info(f"[Phase 3.5] heatmap index carregado: {len(index):,} hexes")
    return index


def _evaluate_position(
    partner_lat: float,
    partner_lon: float,
    partner_capacity: int,
    partner_station: str,
    candidate_hex: str,
    heatmap_index: Dict[str, dict],
    jur_poly,  # shapely polygon da jurisdição do parceiro, ou None
    origin_hex: str,
    hex_latlon_cache: Dict[str, Tuple[float, float]],
    allowed_stations: Optional[set[str]] = None,
) -> Optional[dict]:
    """
    Avalia uma posição candidata testando todos os raios de Config.RADII.

    Apenas hexes dentro da jurisdição do parceiro são considerados para
    hexes_original e hexes_simulated — evita contabilizar demanda de
    outras bases.

    Pré-filtro H3
    -------------
    Em vez de varrer todo o heatmap (~100k hexes), restringe a busca aos
    hexes em ``grid_disk(origin_hex, k) ∪ grid_disk(candidate_hex, k)``,
    onde ``k`` cobre o maior raio de ``Config.RADII`` mais uma margem
    para acomodar o deslocamento entre a posição real do parceiro
    (lat/lon) e o centróide do ``origin_hex``.

    Usa a lógica do what-if engine:
      loss  = demand_allocated dos hexes perdidos ao mover para candidate_hex
      gain  = demand_residual dos hexes ganhos ao mover para candidate_hex
      adv_simulated = min(max(capacity - loss + gain, 0), 80)

    Retorna o melhor resultado (maior adv_gain > 0, desempate: menor raio),
    ou None se nenhum raio produz adv_gain > 0.
    """
    try:
        c_lat, c_lon = h3.cell_to_latlng(candidate_hex)
    except Exception:
        return None

    radii_sorted = sorted(Config.RADII, key=lambda r: r["radius_s"])

    # ── Pré-filtro espacial via grid_disk ──────────────────────────────
    # O maior hex_distance em Config.RADII já é dimensionado para cobrir
    # o maior radius_s. Adicionamos uma margem de 2 anéis para absorver:
    #  (1) diferença entre lat/lon real do parceiro e centróide do origin_hex
    #  (2) margem de segurança para Haversine vs. H3 grid distance
    max_hex_distance = max(r.get("hex_distance", 1) for r in radii_sorted)
    k_search = max_hex_distance + 2

    candidate_hex_set: set[str] = set()
    try:
        candidate_hex_set.update(h3.grid_disk(origin_hex, k_search))
    except Exception:
        pass
    try:
        candidate_hex_set.update(h3.grid_disk(candidate_hex, k_search))
    except Exception:
        pass
    # Interseção com o heatmap (hexes fora do heatmap não existem na análise)
    candidate_hex_set &= heatmap_index.keys()

    # Hot-cache de lat/lon para os hexes relevantes (populado sob demanda).
    def _get_hex_latlon(hex_id: str) -> Optional[Tuple[float, float]]:
        coords = hex_latlon_cache.get(hex_id)
        if coords is None:
            try:
                coords = h3.cell_to_latlng(hex_id)
            except Exception:
                return None
            hex_latlon_cache[hex_id] = coords
        return coords

    best: Optional[dict] = None

    for radius_entry in radii_sorted:
        radius_m = radius_entry["radius_s"]

        hexes_original: set[str] = set()
        hexes_simulated: set[str] = set()

        for hex_id in candidate_hex_set:
            coords = _get_hex_latlon(hex_id)
            if coords is None:
                continue
            h_lat, h_lon = coords

            # Filtro de jurisdição: ignora hexes fora da jurisdição do parceiro
            # (incluindo suas áreas satélite, via allowed_stations).
            props = heatmap_index[hex_id]
            if not _is_hex_in_jurisdiction(
                props, partner_station, h_lat, h_lon, jur_poly,
                allowed_stations=allowed_stations,
            ):
                continue

            if _haversine_m(partner_lat, partner_lon, h_lat, h_lon) <= radius_m:
                hexes_original.add(hex_id)
            if _haversine_m(c_lat, c_lon, h_lat, h_lon) <= radius_m:
                hexes_simulated.add(hex_id)

        hexes_lost   = hexes_original - hexes_simulated
        hexes_gained = hexes_simulated - hexes_original

        loss = sum(heatmap_index[h].get("demand_allocated", 0.0) for h in hexes_lost  if h in heatmap_index)
        gain = sum(heatmap_index[h].get("demand_residual",  0.0) for h in hexes_gained if h in heatmap_index)

        adv_simulated = min(max(partner_capacity - loss + gain, 0), _CAP_MAX)
        adv_gain = adv_simulated - partner_capacity

        if adv_gain <= 0:
            continue

        distance = _haversine_m(partner_lat, partner_lon, c_lat, c_lon)
        candidate_opp = {
            "suggested_lat":         c_lat,
            "suggested_lon":         c_lon,
            "suggested_cap":         int(round(adv_simulated)),
            "suggested_radius":      radius_m,
            "estimated_adv_gain":    int(round(adv_gain)),
            "distance_from_current": round(distance, 2),
        }

        if best is None or adv_gain > best["estimated_adv_gain"]:
            best = candidate_opp
        elif adv_gain == best["estimated_adv_gain"] and radius_m < best["suggested_radius"]:
            best = candidate_opp

    return best


def _worker_payload(payload: dict) -> Tuple[str, Optional[dict]]:
    """
    Top-level worker function (picklable) para ProcessPoolExecutor.

    payload keys:
        sfid, partner_lat, partner_lon, partner_capacity, partner_station,
        origin_hex, matched_slot_hex, h3_res, heatmap_index,
        needs_jur_poly, jurisdiction_path (opcional; só usado quando
        needs_jur_poly=True)
    """
    sfid             = payload["sfid"]
    partner_lat      = payload["partner_lat"]
    partner_lon      = payload["partner_lon"]
    partner_capacity = payload["partner_capacity"]
    partner_station  = payload["partner_station"]
    origin_hex       = payload["origin_hex"]
    matched_slot_hex = payload["matched_slot_hex"]  # None se sem slot
    h3_res           = payload["h3_res"]
    heatmap_index    = payload["heatmap_index"]
    needs_jur_poly   = payload.get("needs_jur_poly", False)

    # Polígono de jurisdição: só é necessário quando o heatmap NÃO expõe
    # ``in_jurisdiction`` em cada hex (heatmap legado). No fluxo atual do
    # pipeline, ``write_heatmap_unified`` sempre grava esse campo, então
    # pulamos o carregamento do shapely polygon.
    if needs_jur_poly:
        jur_poly = _load_jurisdiction_poly(
            partner_station, payload["jurisdiction_path"],
        )
    else:
        jur_poly = None

    # Stations aceitáveis no fast-path: canônica + suas satélites.
    # Parceiros remapeados de satélite → canônica (ex.: XBA1 → DSA8 em
    # _consolidate_stores) precisam enxergar os hexes satélites, que no
    # heatmap pós-setup mantêm o código satélite original em
    # ``props.delivery_station`` (regra "satélite vence canônica").
    allowed_stations: set[str] = {partner_station}
    allowed_stations.update(Config.get_satellites(partner_station))

    # MODO A: parceiro com slot matched
    if matched_slot_hex is not None:
        if matched_slot_hex == origin_hex:
            candidates = [origin_hex]
        else:
            candidates = [matched_slot_hex]

    # MODO B: parceiro sem slot matched — grid_disk(k=1)
    else:
        try:
            candidates = list(h3.grid_disk(origin_hex, 1))
        except Exception:
            return sfid, None

    # Cache de lat/lon por hex — compartilhado entre todas as avaliações
    # de candidatos deste parceiro (hexes geralmente se repetem entre o
    # grid_disk da posição atual e o da candidata).
    hex_latlon_cache: Dict[str, Tuple[float, float]] = {}

    best: Optional[dict] = None
    for candidate_hex in candidates:
        opp = _evaluate_position(
            partner_lat=partner_lat,
            partner_lon=partner_lon,
            partner_capacity=partner_capacity,
            partner_station=partner_station,
            candidate_hex=candidate_hex,
            heatmap_index=heatmap_index,
            jur_poly=jur_poly,
            origin_hex=origin_hex,
            hex_latlon_cache=hex_latlon_cache,
            allowed_stations=allowed_stations,
        )
        if opp is None:
            continue
        if best is None or opp["estimated_adv_gain"] > best["estimated_adv_gain"]:
            best = opp
        elif (
            opp["estimated_adv_gain"] == best["estimated_adv_gain"]
            and opp["suggested_radius"] < best["suggested_radius"]
        ):
            best = opp

    return sfid, best



def _patch_dados_mapa(
    output_dir: str,
    opportunities: Dict[str, Optional[dict]],
) -> None:
    path = Path(output_dir) / "dados_mapa.json"
    if not path.exists():
        logger.warning(f"[Phase 3.5] dados_mapa.json não encontrado em {output_dir} — pulando patch.")
        return
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("allMarkerData", [])
    patched = 0
    for record in records:
        sfid = record.get("salesforce_id")
        if sfid in opportunities:
            record["adv_opportunity"] = opportunities[sfid]
            patched += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"[Phase 3.5] dados_mapa.json atualizado: {patched} parceiros com adv_opportunity.")
    print(f"  ✅ dados_mapa.json — {patched} parceiros com adv_opportunity atualizados")


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_phase3_5(
    fit: FitResult,
    output_dir: str,
    stations: Optional[List[str]] = None,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> None:
    """
    Fase 3.5 — Oportunidades de aumento de ADV para parceiros Active.

    Parâmetros
    ----------
    fit         : FitResult da Fase 3
    output_dir  : diretório de saída (heatmap.geojson + dados_mapa.json)
    stations    : bases a processar; None = todas
    max_workers : workers paralelos (default 6)
    """
    print(f"\n{'='*60}")
    print(f"  FASE 3.5 — OPORTUNIDADES DE ADV")
    print(f"  Output: {output_dir} | workers: {max_workers}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"{'='*60}\n")

    # 1. Carregar heatmap index
    try:
        heatmap_index = _load_heatmap_index(output_dir)
    except FileNotFoundError as exc:
        logger.warning(f"[Phase 3.5] {exc} — encerrando.")
        print(f"  WARN {exc}")
        return

    if not heatmap_index:
        logger.warning("[Phase 3.5] heatmap index vazio — encerrando.")
        return

    # Caminho do arquivo de jurisdições (fallback para heatmap legado)
    jurisdiction_path = str(Config.BASE_JURISDICTION)

    # Detectar se o heatmap já tem in_jurisdiction (pós-setup)
    sample_props = next(iter(heatmap_index.values()), {})
    has_in_jurisdiction = "in_jurisdiction" in sample_props
    if has_in_jurisdiction:
        print("  Heatmap pós-setup detectado: usando campo in_jurisdiction (fast path).")
        # Caminho de jurisdição não é necessário — o fast-path usa
        # apenas as properties do heatmap para filtrar.
        jurisdiction_path: Optional[str] = None
    else:
        print("  Heatmap legado: usando point-in-polygon para filtro de jurisdição.")
        jurisdiction_path = str(Config.BASE_JURISDICTION)

    # 2. Construir índice slot_id → origin_hex a partir do FitResult
    slot_hex_index: Dict[str, str] = {}
    for t_fit in fit.territories.values():
        for slot in t_fit.slots:
            if slot.slot_id and slot.origin_hex:
                slot_hex_index[slot.slot_id] = slot.origin_hex

    # 3. Montar payloads para workers
    all_partners: List[PartnerMetrics] = fit.all_partners()
    active_partners = [p for p in all_partners if p.status == "Active"]

    payloads: List[dict] = []
    skipped_station = 0
    skipped_cap_max = 0
    skipped_no_hex  = 0

    for partner in active_partners:
        sfid = partner.salesforce_id
        if not sfid:
            continue
        if stations is not None and partner.station_code not in stations:
            skipped_station += 1
            continue
        if partner.capacity_s >= _CAP_MAX:
            skipped_cap_max += 1
            continue
        if not partner.origin_hex:
            skipped_no_hex += 1
            continue

        # Resolve o hex do slot matched (None se sem slot)
        matched_slot_hex: Optional[str] = None
        if partner.matched_slot_id:
            matched_slot_hex = slot_hex_index.get(partner.matched_slot_id)

        payload = {
            "sfid":              sfid,
            "partner_lat":       partner.lat,
            "partner_lon":       partner.lon,
            "partner_capacity":  partner.capacity_s,
            "partner_station":   partner.station_code,
            "origin_hex":        partner.origin_hex,
            "matched_slot_hex":  matched_slot_hex,
            "h3_res":            Config.get_h3_res(partner.station_code),
            "heatmap_index":     heatmap_index,
            "needs_jur_poly":    not has_in_jurisdiction,
        }
        if not has_in_jurisdiction:
            payload["jurisdiction_path"] = jurisdiction_path
        payloads.append(payload)

    mode_a = sum(1 for p in payloads if p["matched_slot_hex"] is not None)
    mode_b = len(payloads) - mode_a
    print(
        f"  Parceiros a avaliar: {len(payloads)} "
        f"(Modo A com slot: {mode_a} | Modo B sem slot: {mode_b}) | "
        f"cap>=80: {skipped_cap_max} | filtro base: {skipped_station} | sem hex: {skipped_no_hex}"
    )

    # 4. Executar em paralelo
    opportunities: Dict[str, Optional[dict]] = {}

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_worker_payload, p): p["sfid"] for p in payloads}
        done = 0
        for future in as_completed(futures):
            sfid = futures[future]
            try:
                sfid_result, opp = future.result()
                opportunities[sfid_result] = opp
            except Exception as exc:
                logger.warning(f"[Phase 3.5] Worker falhou para {sfid}: {exc}")
                opportunities[sfid] = None
            done += 1
            if done % 50 == 0:
                print(f"  [{done}/{len(payloads)}] avaliados...")

    with_opp = sum(1 for v in opportunities.values() if v is not None)
    print(f"  Oportunidades identificadas: {with_opp} / {len(opportunities)}")

    # 5. Persistir em dados_mapa.json
    _patch_dados_mapa(output_dir, opportunities)

    print(f"\n{'='*60}")
    print(f"  FASE 3.5 CONCLUÍDA")
    print(f"{'='*60}\n")
