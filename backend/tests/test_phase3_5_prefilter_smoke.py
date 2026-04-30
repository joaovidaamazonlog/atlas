"""
Smoke test para a otimização de pré-filtro H3 em phase3_5.

Objetivo: garantir que _evaluate_position continua produzindo o mesmo
resultado após o pré-filtro H3 (comparado a uma implementação de
referência que varre o heatmap inteiro).
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional, Tuple

import h3

# Garante que o diretório raiz do backend está no path
_THIS = os.path.abspath(os.path.dirname(__file__))
_BACKEND = os.path.abspath(os.path.join(_THIS, os.pardir))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from vanilla.phase3_5_cap_optimizer import _evaluate_position, _haversine_m
from shared.models import Config


def _make_heatmap_index(center_hex: str, k: int = 10) -> Dict[str, dict]:
    """
    Constrói um heatmap index artificial cobrindo grid_disk(center_hex, k).
    Cada hex tem demand_daily=10, demand_residual=5, demand_allocated=5,
    is_covered=True, in_jurisdiction=True, delivery_station="DSP2".
    """
    hexes = list(h3.grid_disk(center_hex, k))
    return {
        h: {
            "hex_id": h,
            "demand_daily": 10.0,
            "demand_residual": 5.0,
            "demand_allocated": 5.0,
            "is_covered": True,
            "in_jurisdiction": True,
            "delivery_station": "DSP2",
        }
        for h in hexes
    }


def _evaluate_reference(
    partner_lat, partner_lon, partner_capacity, partner_station,
    candidate_hex, heatmap_index,
):
    """
    Implementação de referência SEM pré-filtro H3 — varre todo o heatmap.
    Serve como ground truth para comparar com o _evaluate_position otimizado.
    """
    CAP_MAX = 80
    try:
        c_lat, c_lon = h3.cell_to_latlng(candidate_hex)
    except Exception:
        return None
    radii_sorted = sorted(Config.RADII, key=lambda r: r["radius_s"])
    best = None

    for radius_entry in radii_sorted:
        radius_m = radius_entry["radius_s"]
        hexes_original = set()
        hexes_simulated = set()

        for hex_id, props in heatmap_index.items():
            try:
                h_lat, h_lon = h3.cell_to_latlng(hex_id)
            except Exception:
                continue
            if not (props.get("in_jurisdiction") is True and
                    props.get("delivery_station") == partner_station):
                continue
            if _haversine_m(partner_lat, partner_lon, h_lat, h_lon) <= radius_m:
                hexes_original.add(hex_id)
            if _haversine_m(c_lat, c_lon, h_lat, h_lon) <= radius_m:
                hexes_simulated.add(hex_id)

        hexes_lost = hexes_original - hexes_simulated
        hexes_gained = hexes_simulated - hexes_original
        loss = sum(heatmap_index[h].get("demand_allocated", 0.0) for h in hexes_lost)
        gain = sum(heatmap_index[h].get("demand_residual", 0.0) for h in hexes_gained)

        adv_simulated = min(max(partner_capacity - loss + gain, 0), CAP_MAX)
        adv_gain = adv_simulated - partner_capacity
        if adv_gain <= 0:
            continue

        distance = _haversine_m(partner_lat, partner_lon, c_lat, c_lon)
        cand = {
            "suggested_lat": c_lat,
            "suggested_lon": c_lon,
            "suggested_cap": int(round(adv_simulated)),
            "suggested_radius": radius_m,
            "estimated_adv_gain": int(round(adv_gain)),
            "distance_from_current": round(distance, 2),
        }
        if best is None or adv_gain > best["estimated_adv_gain"]:
            best = cand
        elif adv_gain == best["estimated_adv_gain"] and radius_m < best["suggested_radius"]:
            best = cand

    return best


def test_prefilter_matches_reference_when_candidate_differs_from_origin():
    """
    Quando candidate_hex != origin_hex (simulação real de mover o parceiro),
    o pré-filtro H3 deve retornar a mesma best opportunity que a
    implementação de referência.
    """
    # São Paulo approx
    origin_hex = h3.latlng_to_cell(-23.55, -46.63, 9)
    # Mover 1 hex para nordeste como candidato
    neighbors = list(h3.grid_disk(origin_hex, 1))
    candidate_hex = [h for h in neighbors if h != origin_hex][0]

    heatmap_index = _make_heatmap_index(origin_hex, k=12)

    partner_lat, partner_lon = h3.cell_to_latlng(origin_hex)

    optimized = _evaluate_position(
        partner_lat=partner_lat,
        partner_lon=partner_lon,
        partner_capacity=40,
        partner_station="DSP2",
        candidate_hex=candidate_hex,
        heatmap_index=heatmap_index,
        jur_poly=None,
        origin_hex=origin_hex,
        hex_latlon_cache={},
    )

    reference = _evaluate_reference(
        partner_lat, partner_lon, 40, "DSP2", candidate_hex, heatmap_index,
    )

    assert optimized == reference, (
        f"Pré-filtro H3 diverge da referência.\n"
        f"  optimized: {optimized}\n"
        f"  reference: {reference}"
    )


def test_prefilter_matches_reference_when_candidate_equals_origin():
    """
    Quando candidate_hex == origin_hex, não há hexes ganhos nem perdidos,
    então adv_gain == 0 e ambas as implementações retornam None.
    """
    origin_hex = h3.latlng_to_cell(-23.55, -46.63, 9)
    heatmap_index = _make_heatmap_index(origin_hex, k=12)
    partner_lat, partner_lon = h3.cell_to_latlng(origin_hex)

    optimized = _evaluate_position(
        partner_lat=partner_lat, partner_lon=partner_lon,
        partner_capacity=40, partner_station="DSP2",
        candidate_hex=origin_hex, heatmap_index=heatmap_index,
        jur_poly=None, origin_hex=origin_hex, hex_latlon_cache={},
    )

    reference = _evaluate_reference(
        partner_lat, partner_lon, 40, "DSP2", origin_hex, heatmap_index,
    )

    assert optimized == reference


def test_prefilter_handles_partner_offset_from_origin_centroid():
    """
    Partner lat/lon pode não ser exatamente o centróide do origin_hex.
    O pré-filtro deve incluir margem suficiente para que hexes no limite
    do raio não sejam perdidos.
    """
    origin_hex = h3.latlng_to_cell(-23.55, -46.63, 9)
    o_lat, o_lon = h3.cell_to_latlng(origin_hex)

    # Offset de ~200m para sudoeste (dentro do raio do hex mas não no centróide)
    partner_lat = o_lat - 0.002
    partner_lon = o_lon - 0.002

    candidate_hex = list(h3.grid_disk(origin_hex, 2))[-1]  # hex distante
    heatmap_index = _make_heatmap_index(origin_hex, k=12)

    optimized = _evaluate_position(
        partner_lat=partner_lat, partner_lon=partner_lon,
        partner_capacity=30, partner_station="DSP2",
        candidate_hex=candidate_hex, heatmap_index=heatmap_index,
        jur_poly=None, origin_hex=origin_hex, hex_latlon_cache={},
    )

    reference = _evaluate_reference(
        partner_lat, partner_lon, 30, "DSP2", candidate_hex, heatmap_index,
    )

    assert optimized == reference, (
        f"Pré-filtro diverge quando parceiro está offset do centróide.\n"
        f"  optimized: {optimized}\n"
        f"  reference: {reference}"
    )


def test_prefilter_respects_jurisdiction_filter():
    """
    Hexes com in_jurisdiction=False são descartados mesmo estando dentro
    do grid_disk. Ambas as implementações devem respeitar isso.
    """
    origin_hex = h3.latlng_to_cell(-23.55, -46.63, 9)
    heatmap_index = _make_heatmap_index(origin_hex, k=12)

    # Marca metade dos hexes como fora da jurisdição
    for i, (h, props) in enumerate(heatmap_index.items()):
        if i % 2 == 0:
            props["in_jurisdiction"] = False

    candidate_hex = list(h3.grid_disk(origin_hex, 1))[-1]
    partner_lat, partner_lon = h3.cell_to_latlng(origin_hex)

    optimized = _evaluate_position(
        partner_lat=partner_lat, partner_lon=partner_lon,
        partner_capacity=30, partner_station="DSP2",
        candidate_hex=candidate_hex, heatmap_index=heatmap_index,
        jur_poly=None, origin_hex=origin_hex, hex_latlon_cache={},
    )
    reference = _evaluate_reference(
        partner_lat, partner_lon, 30, "DSP2", candidate_hex, heatmap_index,
    )

    assert optimized == reference



# ---------------------------------------------------------------------------
# Satellite coverage: parceiros remapeados de satélite para canônica precisam
# enxergar hexes cujo `delivery_station` no heatmap é o código satélite
# original (regra "satélite vence canônica" em write_heatmap_unified).
# ---------------------------------------------------------------------------

def test_partner_remapped_to_canonical_sees_satellite_hexes():
    """
    Parceiro originalmente em XBA1 (satélite) tem station_code="DSA8"
    (canônica) após _consolidate_stores. Mas os hexes dele no heatmap
    estão com delivery_station="XBA1". Sem o fix allowed_stations, esses
    hexes eram descartados pelo fast-path — o que fazia hexes_original
    e hexes_simulated ficarem AMBOS vazios.

    O teste valida indiretamente que o fix funciona comparando o número
    de hexes aceitos pelo filtro quando partner_station é a canônica e
    os hexes estão com o código satélite.
    """
    from vanilla.phase3_5_cap_optimizer import _is_hex_in_jurisdiction

    # Um hex do heatmap com delivery_station="XBA1" (área satélite de DSA8)
    props_satellite = {
        "in_jurisdiction": True,
        "delivery_station": "XBA1",
    }

    # Sem allowed_stations: comparação exata — o parceiro DSA8 NÃO vê o hex XBA1
    accepted_without_fix = _is_hex_in_jurisdiction(
        props_satellite, "DSA8", 0.0, 0.0, None,
    )
    assert accepted_without_fix is False, (
        "Sem allowed_stations, comparação exata deveria rejeitar XBA1 "
        "para partner_station=DSA8."
    )

    # Com allowed_stations={DSA8, XBA1}: parceiro DSA8 agora vê hex XBA1
    accepted_with_fix = _is_hex_in_jurisdiction(
        props_satellite, "DSA8", 0.0, 0.0, None,
        allowed_stations={"DSA8", "XBA1"},
    )
    assert accepted_with_fix is True, (
        "Com allowed_stations incluindo XBA1, o parceiro DSA8 deveria ver "
        "hexes XBA1 no fast-path."
    )


def test_allowed_stations_rejects_unrelated_delivery_station():
    """allowed_stations deve rejeitar hexes de stations não incluídas."""
    from vanilla.phase3_5_cap_optimizer import _is_hex_in_jurisdiction

    props_unrelated = {
        "in_jurisdiction": True,
        "delivery_station": "DSP2",  # base não relacionada a DSA8
    }

    accepted = _is_hex_in_jurisdiction(
        props_unrelated, "DSA8", 0.0, 0.0, None,
        allowed_stations={"DSA8", "XBA1"},
    )
    assert accepted is False, (
        "Hex com delivery_station='DSP2' não deve ser aceito por um parceiro "
        "DSA8 (com allowed_stations={DSA8, XBA1})."
    )


def test_allowed_stations_respects_in_jurisdiction_false():
    """Mesmo com delivery_station ok, se in_jurisdiction=False, rejeita."""
    from vanilla.phase3_5_cap_optimizer import _is_hex_in_jurisdiction

    props_out = {
        "in_jurisdiction": False,
        "delivery_station": "DSA8",
    }

    accepted = _is_hex_in_jurisdiction(
        props_out, "DSA8", 0.0, 0.0, None,
        allowed_stations={"DSA8", "XBA1"},
    )
    assert accepted is False
