"""
phase3_5_cap_optimizer.py
=========================
Fase 3.5 — Identificação de oportunidades de aumento de ADV para parceiros Active.

Responsabilidade
----------------
- Ler o heatmap.geojson enriquecido (com demand_residual e demand_allocated de cada hex H3).
- Para cada parceiro Active com capacity_s < 80, varrer posições candidatas
  dentro de ~300 m do centroid atual usando h3.grid_disk(k=1).
- Para cada posição candidata, testar todos os raios disponíveis em Config.RADII
  usando a mesma lógica do what-if engine do frontend:
    hexes_lost   = hexes no raio atual - hexes no raio candidato
    hexes_gained = hexes no raio candidato - hexes no raio atual
    loss         = soma de demand_allocated dos hexes perdidos
    gain         = soma de demand_residual dos hexes ganhos
    adv_simulated = min(max(capacity - loss + gain, 0), 80)
    adv_gain      = adv_simulated - capacity
- Selecionar a combinação (posição, raio) com maior adv_gain real > 0.
  Em empate, prefere o menor raio.
- Persistir o campo adv_opportunity em dados_mapa.json apenas para parceiros
  com adv_gain > 0.

Artefato modificado
-------------------
dados_mapa.json
    Cada parceiro Active recebe o campo adv_opportunity:
    {
        "suggested_lat": float,
        "suggested_lon": float,
        "suggested_cap": int,
        "suggested_radius": int,
        "estimated_adv_gain": int,
        "distance_from_current": float
    }
    ou null quando não há oportunidade real (adv_gain <= 0).
"""

from __future__ import annotations

import json
import logging
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from typing import Dict, List, Optional

import h3

from shared.models import Config, PartnerMetrics
from vanilla.phase3_partner_fit import FitResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------------------------

# Raio máximo de cap permitido
_CAP_MAX = 80

# Raio de busca de posições candidatas em metros
_SEARCH_RADIUS_M = 300


# ---------------------------------------------------------------------------
# HELPERS INTERNOS
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância geodésica aproximada em metros usando a fórmula de Haversine."""
    R = 6_371_000.0  # raio médio da Terra em metros
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _load_heatmap_index(output_dir: str) -> Dict[str, dict]:
    """
    Carrega heatmap.geojson do output_dir em um dict {hex_id: properties}
    para lookup O(1).

    Levanta FileNotFoundError se o arquivo não existir.
    """
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


def _candidate_positions(
    partner_lat: float,
    partner_lon: float,
    h3_res: int,
) -> List[str]:
    """
    Retorna hexes H3 dentro de ~300 m do ponto (partner_lat, partner_lon).

    Usa h3.grid_disk com k escolhido para cobrir ~300 m na resolução dada:
    - res 8: k=2 (edge ~461 m, disk-2 ≈ 2×461 ≈ 922 m de diâmetro)
    - res 9: k=3 (edge ~174 m, disk-3 ≈ 3×174 ≈ 522 m de diâmetro)
    - outros: k=2 como fallback conservador
    """
    k_map = {8: 2, 9: 3}
    k = k_map.get(h3_res, 2)

    try:
        origin_hex = h3.latlng_to_cell(partner_lat, partner_lon, h3_res)
        return list(h3.grid_disk(origin_hex, k))
    except Exception as exc:
        logger.warning(f"[Phase 3.5] h3.grid_disk falhou para ({partner_lat}, {partner_lon}): {exc}")
        return []


def _build_opportunity(
    partner_lat: float,
    partner_lon: float,
    partner_capacity: int,
    candidate_hex: str,
    heatmap_index: Dict[str, dict],
) -> Optional[dict]:
    """
    Constrói o dict adv_opportunity para uma posição candidata usando a mesma
    lógica do what-if engine do frontend.

    Para cada raio disponível em Config.RADII, calcula:
      - hexes_original : hexes dentro do raio a partir da posição ATUAL do parceiro
      - hexes_simulated: hexes dentro do raio a partir do candidate_hex
      - hexes_lost     : hexes_original - hexes_simulated
      - hexes_gained   : hexes_simulated - hexes_original
      - loss           : soma de demand_allocated dos hexes perdidos (do parceiro)
      - gain           : soma de demand_residual dos hexes ganhos
      - adv_simulated  : min(max(capacity - loss + gain, 0), 80)
      - adv_gain       : adv_simulated - capacity

    Seleciona a combinação (posição, raio) com maior adv_gain.
    Em caso de empate, prefere o menor raio.

    Retorna None se nenhuma combinação produz adv_gain > 0.
    """
    try:
        c_lat, c_lon = h3.cell_to_latlng(candidate_hex)
    except Exception as exc:
        logger.warning(f"[Phase 3.5] cell_to_latlng falhou para {candidate_hex}: {exc}")
        return None

    radii_sorted = sorted(Config.RADII, key=lambda r: r["radius_s"])

    best: Optional[dict] = None

    for radius_entry in radii_sorted:
        radius_m = radius_entry["radius_s"]

        # Hexes dentro do raio a partir da posição ATUAL
        hexes_original: set[str] = set()
        for hex_id, props in heatmap_index.items():
            try:
                h_lat, h_lon = h3.cell_to_latlng(hex_id)
            except Exception:
                continue
            if _haversine_m(partner_lat, partner_lon, h_lat, h_lon) <= radius_m:
                hexes_original.add(hex_id)

        # Hexes dentro do raio a partir da posição CANDIDATA
        hexes_simulated: set[str] = set()
        for hex_id, props in heatmap_index.items():
            try:
                h_lat, h_lon = h3.cell_to_latlng(hex_id)
            except Exception:
                continue
            if _haversine_m(c_lat, c_lon, h_lat, h_lon) <= radius_m:
                hexes_simulated.add(hex_id)

        hexes_lost   = hexes_original - hexes_simulated
        hexes_gained = hexes_simulated - hexes_original

        # loss: soma de demand_allocated do parceiro nos hexes perdidos
        # (usa demand_allocated do heatmap como proxy — o parceiro contribui
        #  proporcionalmente; sem hex_coverage no backend, usamos demand_allocated)
        loss = sum(
            heatmap_index[h].get("demand_allocated", 0.0)
            for h in hexes_lost
            if h in heatmap_index
        )

        # gain: soma de demand_residual dos hexes ganhos
        gain = sum(
            heatmap_index[h].get("demand_residual", 0.0)
            for h in hexes_gained
            if h in heatmap_index
        )

        adv_simulated = min(max(partner_capacity - loss + gain, 0), _CAP_MAX)
        adv_gain = adv_simulated - partner_capacity

        if adv_gain <= 0:
            continue

        distance_from_current = _haversine_m(partner_lat, partner_lon, c_lat, c_lon)

        candidate_opp = {
            "suggested_lat":         c_lat,
            "suggested_lon":         c_lon,
            "suggested_cap":         int(round(adv_simulated)),
            "suggested_radius":      radius_m,
            "estimated_adv_gain":    int(round(adv_gain)),
            "distance_from_current": round(distance_from_current, 2),
        }

        # Seleciona: maior adv_gain; empate → menor raio
        if best is None:
            best = candidate_opp
        elif candidate_opp["estimated_adv_gain"] > best["estimated_adv_gain"]:
            best = candidate_opp
        elif (
            candidate_opp["estimated_adv_gain"] == best["estimated_adv_gain"]
            and candidate_opp["suggested_radius"] < best["suggested_radius"]
        ):
            best = candidate_opp

    return best


def _patch_dados_mapa(
    output_dir: str,
    opportunities: Dict[str, Optional[dict]],
) -> None:
    """
    Lê dados_mapa.json do output_dir, atualiza o campo adv_opportunity
    para cada parceiro cujo salesforce_id está em opportunities, e
    escreve de volta preservando todos os demais campos.
    """
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
) -> None:
    """
    Fase 3.5 — Avaliação de oportunidades de cap para parceiros Active.

    Parâmetros
    ----------
    fit        : FitResult da Fase 3
    output_dir : diretório de saída (onde estão heatmap.geojson e dados_mapa.json)
    stations   : lista de bases a processar; None = todas
    """
    print(f"\n{'='*60}")
    print(f"  FASE 3.5 — OTIMIZAÇÃO DE CAP")
    print(f"  Output: {output_dir}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"{'='*60}\n")

    # 1. Carregar heatmap index
    try:
        heatmap_index = _load_heatmap_index(output_dir)
    except FileNotFoundError as exc:
        logger.warning(f"[Phase 3.5] {exc} — encerrando sem modificar dados_mapa.json.")
        print(f"  WARN {exc}")
        return

    if not heatmap_index:
        logger.warning("[Phase 3.5] heatmap index vazio — encerrando.")
        print("  WARN heatmap index vazio — encerrando.")
        return

    # 2. Iterar parceiros Active
    all_partners: List[PartnerMetrics] = fit.all_partners()
    active_partners = [p for p in all_partners if p.status == "Active"]

    opportunities: Dict[str, Optional[dict]] = {}

    evaluated = 0
    skipped_station = 0
    skipped_cap_max = 0
    skipped_no_hex = 0

    for partner in active_partners:
        sfid = partner.salesforce_id
        if not sfid:
            continue

        # 3. Filtro de base
        if stations is not None and partner.station_code not in stations:
            skipped_station += 1
            continue

        # 4. Cap >= 80: sem oportunidade
        if partner.capacity_s >= _CAP_MAX:
            opportunities[sfid] = None
            skipped_cap_max += 1
            continue

        # 5. Verificar origin_hex
        if not partner.origin_hex:
            logger.warning(f"[Phase 3.5] Parceiro {sfid} sem origin_hex — pulando.")
            skipped_no_hex += 1
            opportunities[sfid] = None
            continue

        # 6. Resolução H3 da base
        h3_res = Config.get_h3_res(partner.station_code)

        # 7. Posições candidatas (~300 m)
        try:
            candidates = _candidate_positions(partner.lat, partner.lon, h3_res)
        except Exception as exc:
            logger.warning(f"[Phase 3.5] _candidate_positions falhou para {sfid}: {exc}")
            opportunities[sfid] = None
            continue

        if not candidates:
            opportunities[sfid] = None
            continue

        # 8. Avaliar cada candidato
        best: Optional[dict] = None
        for candidate_hex in candidates:
            opp = _build_opportunity(
                partner_lat=partner.lat,
                partner_lon=partner.lon,
                partner_capacity=partner.capacity_s,
                candidate_hex=candidate_hex,
                heatmap_index=heatmap_index,
            )
            if opp is None:
                continue
            # 9. Selecionar melhor: max estimated_adv_gain, desempate min raio
            if best is None:
                best = opp
            elif opp["estimated_adv_gain"] > best["estimated_adv_gain"]:
                best = opp
            elif (
                opp["estimated_adv_gain"] == best["estimated_adv_gain"]
                and opp["suggested_radius"] < best["suggested_radius"]
            ):
                best = opp

        opportunities[sfid] = best
        evaluated += 1

    print(
        f"  Parceiros Active avaliados: {evaluated} | "
        f"cap>=80: {skipped_cap_max} | "
        f"filtro base: {skipped_station} | "
        f"sem hex: {skipped_no_hex}"
    )
    with_opp = sum(1 for v in opportunities.values() if v is not None)
    print(f"  Oportunidades identificadas: {with_opp} / {len(opportunities)}")

    # 10. Persistir em dados_mapa.json
    _patch_dados_mapa(output_dir, opportunities)

    print(f"\n{'='*60}")
    print(f"  FASE 3.5 CONCLUÍDA")
    print(f"{'='*60}\n")
