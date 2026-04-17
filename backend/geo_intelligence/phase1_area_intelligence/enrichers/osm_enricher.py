"""
osm_enricher.py
===============
Extrai features urbanas por H3_Cell usando OpenStreetMap via osmnx.

Features básicas:
  - building_density: número de edifícios / área da célula (km²)
  - avg_building_size_m2: área média das footprints de edifícios (m²)
  - landuse_residential_ratio: fração da área de landuse que é residencial
  - landuse_commercial_ratio: fração da área de landuse que é comercial
  - poi_density: número de POIs / área da célula (km²)
  - road_connectivity_index: grau médio dos nós na rede viária

Features avançadas:
  - landuse_entropy: entropia de Shannon sobre categorias de landuse
  - road_centrality_index: betweenness centralidade média (normalizado)
  - local_clustering_coefficient: coeficiente de clustering médio da rede viária

Degradação graciosa: se OSM indisponível, todas as features retornam None.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# Área de uma célula H3 resolução 9 em km²
_H3_RES9_AREA_KM2 = 0.1052


def _h3_to_bbox(h3_id: str) -> tuple[float, float, float, float]:
    """Converte H3 cell para bounding box (south, west, north, east)."""
    import h3

    boundary = h3.cell_to_boundary(h3_id)  # lista de (lat, lng)
    lats = [p[0] for p in boundary]
    lngs = [p[1] for p in boundary]
    return min(lats), min(lngs), max(lats), max(lngs)


def _compute_landuse_entropy(landuse_gdf) -> Optional[float]:
    """Entropia de Shannon sobre categorias de landuse."""
    if landuse_gdf is None or landuse_gdf.empty:
        return None

    tag_col = None
    for col in ("landuse", "leisure", "natural"):
        if col in landuse_gdf.columns:
            tag_col = col
            break
    if tag_col is None:
        return None

    counts = landuse_gdf[tag_col].dropna().value_counts()
    if counts.empty:
        return None

    total = counts.sum()
    probs = counts / total
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return float(entropy)


def _compute_osm_features(h3_id: str) -> dict:
    """Extrai todas as features OSM para uma única H3 cell."""
    import osmnx as ox

    south, west, north, east = _h3_to_bbox(h3_id)
    bbox = (north, south, east, west)  # osmnx usa (north, south, east, west)

    result: dict[str, Optional[float]] = {
        "building_density": None,
        "avg_building_size_m2": None,
        "landuse_residential_ratio": None,
        "landuse_commercial_ratio": None,
        "poi_density": None,
        "road_connectivity_index": None,
        "landuse_entropy": None,
        "road_centrality_index": None,
        "local_clustering_coefficient": None,
    }

    # --- Edifícios ---
    try:
        buildings = ox.features_from_bbox(
            bbox=bbox,
            tags={"building": True},
        )
        n_buildings = len(buildings)
        result["building_density"] = n_buildings / _H3_RES9_AREA_KM2

        if not buildings.empty and "geometry" in buildings.columns:
            # Projetar para CRS métrico para calcular área em m²
            try:
                buildings_proj = buildings.to_crs(epsg=3857)
                areas = buildings_proj.geometry.area
                areas = areas[areas > 0]
                if not areas.empty:
                    result["avg_building_size_m2"] = float(areas.mean())
            except Exception:
                pass
    except Exception as exc:
        logger.debug("OSM buildings fetch failed for %s: %s", h3_id, exc)

    # --- Landuse ---
    try:
        landuse = ox.features_from_bbox(
            bbox=bbox,
            tags={"landuse": True},
        )
        if not landuse.empty and "landuse" in landuse.columns:
            try:
                landuse_proj = landuse.to_crs(epsg=3857)
                total_area = landuse_proj.geometry.area.sum()
                if total_area > 0:
                    residential_tags = {"residential", "apartments", "housing"}
                    commercial_tags = {"commercial", "retail", "office"}

                    res_mask = landuse["landuse"].isin(residential_tags)
                    com_mask = landuse["landuse"].isin(commercial_tags)

                    res_area = landuse_proj.geometry[res_mask].area.sum()
                    com_area = landuse_proj.geometry[com_mask].area.sum()

                    result["landuse_residential_ratio"] = float(res_area / total_area)
                    result["landuse_commercial_ratio"] = float(com_area / total_area)
            except Exception:
                pass

        result["landuse_entropy"] = _compute_landuse_entropy(
            landuse if not landuse.empty else None
        )
    except Exception as exc:
        logger.debug("OSM landuse fetch failed for %s: %s", h3_id, exc)

    # --- POIs ---
    try:
        pois = ox.features_from_bbox(
            bbox=bbox,
            tags={"amenity": True},
        )
        result["poi_density"] = len(pois) / _H3_RES9_AREA_KM2
    except Exception as exc:
        logger.debug("OSM POI fetch failed for %s: %s", h3_id, exc)

    # --- Rede viária ---
    try:
        import networkx as nx

        G = ox.graph_from_bbox(
            bbox=bbox,
            network_type="drive",
        )

        if G.number_of_nodes() > 0:
            # road_connectivity_index: grau médio dos nós
            degrees = [d for _, d in G.degree()]
            result["road_connectivity_index"] = float(sum(degrees) / len(degrees))

            # local_clustering_coefficient: coeficiente de clustering médio
            G_undirected = G.to_undirected()
            clustering = nx.clustering(G_undirected)
            if clustering:
                result["local_clustering_coefficient"] = float(
                    sum(clustering.values()) / len(clustering)
                )

            # road_centrality_index: betweenness centralidade média (normalizado)
            # Usa apenas subgrafo se muito grande para evitar timeout
            n_nodes = G.number_of_nodes()
            if n_nodes <= 500:
                betweenness = nx.betweenness_centrality(G, normalized=True)
            else:
                # Amostragem para grafos grandes
                k = min(100, n_nodes)
                betweenness = nx.betweenness_centrality(G, normalized=True, k=k)

            if betweenness:
                result["road_centrality_index"] = float(
                    sum(betweenness.values()) / len(betweenness)
                )
    except Exception as exc:
        logger.debug("OSM road network fetch failed for %s: %s", h3_id, exc)

    return result


class OsmEnricher:
    """Enriquece H3 cells com features urbanas extraídas do OpenStreetMap."""

    H3_RES9_AREA_KM2 = _H3_RES9_AREA_KM2

    def get_features_for_h3_cells(self, h3_ids: list[str]) -> dict[str, dict]:
        """
        Retorna {h3_id: {feature_name: value}} para todas as células solicitadas.

        Cada célula é processada individualmente. Se OSM estiver indisponível
        ou ocorrer qualquer erro, a célula recebe todas as features como None
        e o erro é logado — sem bloquear as demais células.
        """
        results: dict[str, dict] = {}

        for h3_id in h3_ids:
            try:
                features = _compute_osm_features(h3_id)
                results[h3_id] = features
            except Exception as exc:
                logger.error(
                    "OSM enrichment failed for cell %s: %s. Filling with None.",
                    h3_id,
                    exc,
                )
                results[h3_id] = {
                    "building_density": None,
                    "avg_building_size_m2": None,
                    "landuse_residential_ratio": None,
                    "landuse_commercial_ratio": None,
                    "poi_density": None,
                    "road_connectivity_index": None,
                    "landuse_entropy": None,
                    "road_centrality_index": None,
                    "local_clustering_coefficient": None,
                }

        return results
