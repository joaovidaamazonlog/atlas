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
  hexes_simulated = hexes dentro do raio a partir da posição CANDIDATA
  loss  = soma de demand_allocated dos hexes perdidos
  gain  = soma de demand_residual dos hexes ganhos
  adv_simulated = min(max(capacity - loss + gain, 0), 80)
  adv_gain      = adv_simulated - capacity

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
    candidate_hex: str,
    heatmap_index: Dict[str, dict],
) -> Optional[dict]:
    """
    Avalia uma posição candidata testando todos os raios de Config.RADII.
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
    best: Optional[dict] = None

    for radius_entry in radii_sorted:
        radius_m = radius_entry["radius_s"]

        hexes_original: set[str] = set()
        hexes_simulated: set[str] = set()

        for hex_id, props in heatmap_index.items():
            try:
                h_lat, h_lon = h3.cell_to_latlng(hex_id)
            except Exception:
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
        sfid, partner_lat, partner_lon, partner_capacity,
        origin_hex, matched_slot_hex, h3_res, heatmap_index
    """
    sfid             = payload["sfid"]
    partner_lat      = payload["partner_lat"]
    partner_lon      = payload["partner_lon"]
    partner_capacity = payload["partner_capacity"]
    origin_hex       = payload["origin_hex"]
    matched_slot_hex = payload["matched_slot_hex"]  # None se sem slot
    h3_res           = payload["h3_res"]
    heatmap_index    = payload["heatmap_index"]

    # MODO A: parceiro com slot matched
    if matched_slot_hex is not None:
        if matched_slot_hex == origin_hex:
            # Já está no hex ideal — avalia apenas essa posição para ver se há
            # ganho de cap com raio menor (posição não muda, mas raio pode mudar)
            candidates = [origin_hex]
        else:
            # Sugere mover para o hex do slot
            candidates = [matched_slot_hex]

    # MODO B: parceiro sem slot matched — grid_disk(k=1)
    else:
        try:
            candidates = list(h3.grid_disk(origin_hex, 1))
        except Exception:
            return sfid, None

    best: Optional[dict] = None
    for candidate_hex in candidates:
        opp = _evaluate_position(
            partner_lat=partner_lat,
            partner_lon=partner_lon,
            partner_capacity=partner_capacity,
            candidate_hex=candidate_hex,
            heatmap_index=heatmap_index,
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

        payloads.append({
            "sfid":             sfid,
            "partner_lat":      partner.lat,
            "partner_lon":      partner.lon,
            "partner_capacity": partner.capacity_s,
            "origin_hex":       partner.origin_hex,
            "matched_slot_hex": matched_slot_hex,
            "h3_res":           Config.get_h3_res(partner.station_code),
            "heatmap_index":    heatmap_index,
        })

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
