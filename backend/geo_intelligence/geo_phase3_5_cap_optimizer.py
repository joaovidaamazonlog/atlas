"""
geo_intelligence/geo_phase3_5_cap_optimizer.py
===============================================
Fase 3.5 do pipeline GeoIntelligence daily — Cap Optimization.

Identifica oportunidades de aumento de cap para parceiros Active com
capacity < 80, com base na demanda não coberta derivada de geo_h3_cells
(resolução 9). Persiste os resultados em geo_partner_cap_opportunities
via TursoWriter.

Nunca propaga exceções ao orquestrador — falhas são logadas internamente.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Set

import h3

from shared.models import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers geoespaciais
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distância geodésica em metros entre dois pontos (fórmula de Haversine).

    Usada para determinar cobertura de parceiros e distância de candidatos.

    Args:
        lat1: Latitude do ponto A em graus decimais.
        lon1: Longitude do ponto A em graus decimais.
        lat2: Latitude do ponto B em graus decimais.
        lon2: Longitude do ponto B em graus decimais.

    Returns:
        Distância em metros entre os dois pontos.
    """
    R = 6_371_000.0  # raio médio da Terra em metros

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c


def _disaggregate_r8_to_r9(h3_id_r8: str, density_r8: float) -> Dict[str, float]:
    """
    Desagrega delivery_density_r8 de um hexágono res 8 para seus filhos res 9.

    Usa h3.cell_to_children(h3_id_r8, 9) — tipicamente 7 filhos.
    Distribui density_r8 proporcionalmente (density_r8 / n_children) por filho.

    Args:
        h3_id_r8: Identificador H3 do hexágono na resolução 8.
        density_r8: Densidade de entregas do hexágono pai (res 8).

    Returns:
        Dicionário {h3_id_r9: density_r9} com a densidade distribuída
        igualmente entre os filhos res 9.
    """
    children: List[str] = list(h3.cell_to_children(h3_id_r8, 9))
    n_children = len(children)
    if n_children == 0:
        return {}
    density_r9 = density_r8 / n_children
    return {child: density_r9 for child in children}


def _load_h3_index(
    reader,
    station_code: str,
    run_id: str,
) -> Dict[str, float]:
    """
    Carrega geo_h3_cells para a base/run_id e constrói o índice
    {h3_id_r9: delivery_density_r9} via desagregação res 8 → res 9.

    Retorna dict vazio se não houver registros (log de aviso emitido).

    Args:
        reader: TursoReader com método get_h3_cells_for_station.
        station_code: Código da base (ex: 'DSP2').
        run_id: Identificador da execução do pipeline.

    Returns:
        Dicionário {h3_id_r9: density_r9}.
    """
    records = reader.get_h3_cells_for_station(station_code, run_id)

    if not records:
        logger.warning(
            "[%s] _load_h3_index: nenhum registro em geo_h3_cells para run_id=%s.",
            station_code,
            run_id,
        )
        return {}

    h3_index: Dict[str, float] = {}
    for record in records:
        h3_id_r8 = record.get("h3_id") or record.get("h3_id_r8") or ""
        if not h3_id_r8:
            continue
        # Req 7.3: delivery_density_r8 null/None → treat as 0.0
        raw_density = record.get("delivery_density_r8")
        density_r8 = float(raw_density) if raw_density is not None else 0.0

        children = _disaggregate_r8_to_r9(h3_id_r8, density_r8)
        h3_index.update(children)

    return h3_index


def _build_coverage_index(
    active_partners: List,
    h3_index: Dict[str, float],
    exclude_partner_id: Optional[str] = None,
) -> Set[str]:
    """
    Constrói o conjunto de hexágonos res 9 cobertos por pelo menos um parceiro
    Active (exceto exclude_partner_id, se fornecido).

    Um hexágono é "coberto" se a distância geodésica (Haversine) entre seu
    centro (h3.cell_to_latlng) e o centroid do parceiro é <= raio do parceiro.

    Args:
        active_partners: Lista de GeoPartnerMatch com status Active.
        h3_index: Dicionário {h3_id_r9: density_r9} com todos os hexes.
        exclude_partner_id: salesforce_id/partner_id do parceiro a excluir
            da cobertura (usado para auto-exclusão ao avaliar o próprio parceiro).

    Returns:
        Set de h3_id_r9 cobertos por pelo menos um parceiro Active.
    """
    covered: Set[str] = set()

    for partner in active_partners:
        pid = partner.partner_id
        if exclude_partner_id is not None and pid == exclude_partner_id:
            continue

        p_lat = partner.lat
        p_lon = partner.lon
        p_radius = partner.radius

        for h3_id_r9 in h3_index:
            try:
                hex_lat, hex_lon = h3.cell_to_latlng(h3_id_r9)
            except Exception:
                continue

            dist = _haversine_m(p_lat, p_lon, hex_lat, hex_lon)
            if dist <= p_radius:
                covered.add(h3_id_r9)

    return covered


def _uncovered_demand(
    candidate_hex: str,
    radius_m: int,
    h3_index: Dict[str, float],
    coverage_index: Set[str],
) -> float:
    """
    Soma delivery_density_r9 dos hexágonos res 9 dentro de radius_m do centro
    de candidate_hex que NÃO estão em coverage_index.

    Usa Haversine para determinar se cada hex está dentro do raio.
    Trata density None/ausente como 0.0.

    Args:
        candidate_hex: Identificador H3 (res 9) da posição candidata.
        radius_m: Raio em metros para busca de hexes vizinhos.
        h3_index: Dicionário {h3_id_r9: density_r9} com todos os hexes.
        coverage_index: Set de h3_id_r9 já cobertos por parceiros Active.

    Returns:
        Soma de delivery_density_r9 dos hexes não cobertos dentro do raio.
    """
    try:
        cand_lat, cand_lon = h3.cell_to_latlng(candidate_hex)
    except Exception:
        return 0.0

    total = 0.0
    for h3_id, density in h3_index.items():
        if h3_id in coverage_index:
            continue
        try:
            hex_lat, hex_lon = h3.cell_to_latlng(h3_id)
        except Exception:
            continue
        dist = _haversine_m(cand_lat, cand_lon, hex_lat, hex_lon)
        if dist <= radius_m:
            total += density if density is not None else 0.0

    return total


def _smallest_radius_for_cap(
    candidate_hex: str,
    target_cap: int,
    h3_index: Dict[str, float],
    coverage_index: Set[str],
) -> Optional[int]:
    """
    Retorna o menor valor de Config.RADII cujo raio cobre
    Demanda_Não_Coberta >= target_cap a partir de candidate_hex.

    Itera Config.RADII em ordem crescente (por radius_s).
    Retorna None se nenhum raio de Config.RADII for suficiente.

    Args:
        candidate_hex: Identificador H3 (res 9) da posição candidata.
        target_cap: Cap alvo (suggested_cap) a ser coberto pela demanda.
        h3_index: Dicionário {h3_id_r9: density_r9} com todos os hexes.
        coverage_index: Set de h3_id_r9 já cobertos por parceiros Active.

    Returns:
        O menor radius_s (int, em metros) de Config.RADII cujo
        _uncovered_demand >= target_cap, ou None se nenhum for suficiente.
    """
    sorted_radii = sorted(Config.RADII, key=lambda r: r["radius_s"])
    for radius_entry in sorted_radii:
        radius_m = radius_entry["radius_s"]
        demand = _uncovered_demand(candidate_hex, radius_m, h3_index, coverage_index)
        if demand >= target_cap:
            return radius_m
    return None


# ---------------------------------------------------------------------------
# Seleção de candidatos e varredura por parceiro
# ---------------------------------------------------------------------------

def _select_best_candidate(candidates: List[Dict]) -> Optional[Dict]:
    """
    Seleciona o melhor candidato da lista de candidatos viáveis.

    Critério primário: maior `estimated_adv_gain`.
    Critério de desempate: menor `distance_from_current`.

    Args:
        candidates: Lista de dicts com campos `estimated_adv_gain` e
            `distance_from_current`.

    Returns:
        O dict do melhor candidato, ou None se a lista estiver vazia.
    """
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda c: (-c["estimated_adv_gain"], c["distance_from_current"]),
    )


def _scan_partner(
    partner,
    h3_index: Dict[str, float],
    coverage_index: Set[str],
) -> Optional[Dict]:
    """
    Varre posições candidatas para um parceiro under-cap e retorna a melhor
    oportunidade encontrada, ou None se nenhuma posição for viável.

    Algoritmo:
    1. Obtém candidatos via h3.grid_disk(origin_hex_r9, k=3) — res 9.
    2. Para cada candidato, calcula Demanda_Não_Coberta usando o maior raio
       de Config.RADII (para verificar se há demanda suficiente).
    3. Se demanda > partner.capacity, calcula suggested_cap = min(int(demanda), 80)
       e chama _smallest_radius_for_cap para encontrar o menor raio suficiente.
    4. Descarta candidato se suggested_radius for None.
    5. Chama _select_best_candidate nos candidatos viáveis.

    Args:
        partner: GeoPartnerMatch com campos partner_id, origin_hex, lat, lon,
            capacity.
        h3_index: Dicionário {h3_id_r9: density_r9} com todos os hexes.
        coverage_index: Set de h3_id_r9 já cobertos por parceiros Active
            (excluindo o próprio parceiro).

    Returns:
        Dict com campos da oportunidade, ou None se nenhum candidato for viável.
        Campos: partner_id, station_code, suggested_lat, suggested_lon,
        suggested_cap, suggested_radius, estimated_adv_gain, distance_from_current.
    """
    origin_hex = partner.origin_hex
    if not origin_hex:
        return None

    # Maior raio de Config.RADII para avaliação inicial de demanda
    sorted_radii = sorted(Config.RADII, key=lambda r: r["radius_s"])
    largest_radius = sorted_radii[-1]["radius_s"]

    try:
        candidate_hexes = list(h3.grid_disk(origin_hex, k=3))
    except Exception:
        logger.warning(
            "[_scan_partner] h3.grid_disk falhou para partner_id=%s origin_hex=%s",
            partner.partner_id,
            origin_hex,
        )
        return None

    viable: List[Dict] = []

    for cand_hex in candidate_hexes:
        # Calcula demanda com o maior raio para verificar se há demanda suficiente
        demand = _uncovered_demand(cand_hex, largest_radius, h3_index, coverage_index)

        if demand <= partner.capacity:
            continue

        suggested_cap = min(int(demand), 80)
        suggested_radius = _smallest_radius_for_cap(
            cand_hex, suggested_cap, h3_index, coverage_index
        )

        if suggested_radius is None:
            continue

        # Coordenadas do candidato
        try:
            cand_lat, cand_lon = h3.cell_to_latlng(cand_hex)
        except Exception:
            continue

        distance = _haversine_m(partner.lat, partner.lon, cand_lat, cand_lon)
        estimated_adv_gain = suggested_cap - partner.capacity

        viable.append({
            "partner_id": partner.partner_id,
            "station_code": getattr(partner, "station_code", None),
            "suggested_lat": cand_lat,
            "suggested_lon": cand_lon,
            "suggested_cap": suggested_cap,
            "suggested_radius": suggested_radius,
            "estimated_adv_gain": estimated_adv_gain,
            "distance_from_current": distance,
        })

    return _select_best_candidate(viable)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_geo_phase3_5(
    daily_result,
    run_id: str,
    station_code: str,
    writer,
    reader,
) -> int:
    """
    Fase 3.5 do pipeline GeoIntelligence.

    Avalia todos os parceiros Active do daily_result, identifica oportunidades
    de aumento de cap com base na demanda não coberta de geo_h3_cells (res 9),
    e persiste os resultados em geo_partner_cap_opportunities via TursoWriter.

    Retorna o número de oportunidades identificadas (suggested_cap não nulo).
    Nunca propaga exceções ao chamador — erros são logados internamente.

    Args:
        daily_result: GeoDailyResult com listas matched/unmatched de parceiros.
        run_id: Identificador da execução do pipeline.
        station_code: Código da base (ex: 'DSP2').
        writer: TursoWriter com método upsert_cap_opportunities.
        reader: TursoReader com método get_h3_cells_for_station.

    Returns:
        Número de oportunidades não nulas (registros com suggested_cap não nulo).
    """
    from datetime import datetime, timezone

    # Req 1.10, 7.5: carrega índice H3; encerra sem persistir se vazio
    h3_index = _load_h3_index(reader, station_code, run_id)
    if not h3_index:
        logger.warning(
            "[%s] run_geo_phase3_5: h3_index vazio para run_id=%s — encerrando sem persistir.",
            station_code,
            run_id,
        )
        return 0

    # Req 1.2: coleta todos os parceiros Active de matched + unmatched
    all_partners = daily_result.matched + daily_result.unmatched
    active_partners = [p for p in all_partners if p.status == "Active"]

    opportunities: List[Dict] = []
    created_at = datetime.now(timezone.utc).isoformat()

    def _null_opportunity(partner_id: str) -> Dict:
        """Constrói registro de oportunidade nula para um parceiro."""
        return {
            "partner_id": partner_id,
            "station_code": station_code,
            "suggested_lat": None,
            "suggested_lon": None,
            "suggested_cap": None,
            "suggested_radius": None,
            "estimated_adv_gain": None,
            "distance_from_current": None,
            "created_at": created_at,
        }

    for partner in active_partners:
        try:
            # Req 1.3: parceiros com capacity >= 80 → oportunidade nula
            if partner.capacity >= 80:
                opportunities.append(_null_opportunity(partner.partner_id))
                continue

            # Req 1.11: parceiro sem origin_hex ou coordenadas válidas → oportunidade nula
            if not partner.origin_hex or not partner.lat or not partner.lon:
                logger.warning(
                    "[%s] run_geo_phase3_5: parceiro %s sem origin_hex/coordenadas válidas — persistindo null.",
                    station_code,
                    partner.partner_id,
                )
                opportunities.append(_null_opportunity(partner.partner_id))
                continue

            # Req 1.4, 2.4: constrói índice de cobertura excluindo o próprio parceiro
            coverage_index = _build_coverage_index(
                active_partners, h3_index, exclude_partner_id=partner.partner_id
            )

            # Req 1.5, 1.6, 1.7: varre posições candidatas
            result = _scan_partner(partner, h3_index, coverage_index)

            if result is not None:
                # Garante que station_code e created_at estão presentes
                result["station_code"] = station_code
                result["created_at"] = created_at
                opportunities.append(result)
            else:
                # Req 1.9: nenhuma posição candidata viável → oportunidade nula
                opportunities.append(_null_opportunity(partner.partner_id))

        except Exception as exc:
            # Req 9.5: captura exceção por parceiro individualmente
            logger.warning(
                "[%s] run_geo_phase3_5: erro ao processar parceiro %s — persistindo null. Erro: %s",
                station_code,
                partner.partner_id,
                exc,
            )
            opportunities.append(_null_opportunity(partner.partner_id))

    # Req 1.8, 9.4: persiste oportunidades; captura exceção sem propagar
    try:
        writer.upsert_cap_opportunities(run_id, opportunities)
    except Exception as exc:
        logger.error(
            "[%s] run_geo_phase3_5: upsert_cap_opportunities falhou — encerrando sem propagar. Erro: %s",
            station_code,
            exc,
        )
        return 0

    # Retorna contagem de oportunidades não nulas (suggested_cap não nulo)
    n_opportunities = sum(1 for opp in opportunities if opp.get("suggested_cap") is not None)
    return n_opportunities
