"""
satellite_enricher.py
=====================
Extrai features de imagens de satélite por H3_Cell usando Google Earth Engine (GEE).

Features extraídas:
  - ndvi_mean: índice de vegetação NDVI médio (Landsat 8 / Sentinel-2, últimos 12 meses)
  - urban_density_index: densidade urbana via GHSL (Global Human Settlement Layer)
  - built_up_ratio: proporção de área construída (Sentinel-2 / GHSL)
  - morphology_class: classificação visual preliminar da morfologia urbana
    ('high_density_urban', 'low_density_urban', 'informal_settlement',
     'commercial_industrial', 'green_area', 'rural')

Degradação graciosa: se GEE não estiver instalado ou `ee.Initialize()` falhar,
`self._available = False` e todas as chamadas retornam None para todas as features.
O pipeline continua normalmente sem dados de satélite.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Chaves de features retornadas por célula
_SATELLITE_FEATURE_KEYS = (
    "ndvi_mean",
    "urban_density_index",
    "built_up_ratio",
    "morphology_class",
)

_NULL_FEATURES: dict[str, None] = {k: None for k in _SATELLITE_FEATURE_KEYS}


def _classify_morphology(
    ndvi: Optional[float],
    urban_density: Optional[float],
    built_up: Optional[float],
) -> Optional[str]:
    """
    Classifica a morfologia urbana com base nos thresholds definidos no design.

    Ordem de prioridade:
      1. ndvi > 0.4                                    → 'green_area'
      2. urban_density > 0.8                           → 'high_density_urban'
      3. urban_density > 0.4                           → 'low_density_urban'
      4. built_up_ratio > 0.6 and ndvi < 0.1          → 'commercial_industrial'
      5. built_up_ratio > 0.3 and urban_density < 0.3 → 'informal_settlement'
      6. else                                          → 'rural'

    Retorna None se todos os inputs forem None.
    """
    if ndvi is None and urban_density is None and built_up is None:
        return None

    # Usar 0.0 como fallback seguro para comparações quando valor é None
    ndvi_val = ndvi if ndvi is not None else 0.0
    urban_val = urban_density if urban_density is not None else 0.0
    built_val = built_up if built_up is not None else 0.0

    if ndvi_val > 0.4:
        return "green_area"
    if urban_val > 0.8:
        return "high_density_urban"
    if urban_val > 0.4:
        return "low_density_urban"
    if built_val > 0.6 and ndvi_val < 0.1:
        return "commercial_industrial"
    if built_val > 0.3 and urban_val < 0.3:
        return "informal_settlement"
    return "rural"


def _h3_to_ee_geometry(h3_id: str):
    """Converte uma H3 cell para ee.Geometry.Polygon."""
    import ee
    import h3

    boundary = h3.cell_to_boundary(h3_id)  # lista de (lat, lng)
    # GEE espera coordenadas como [lng, lat]
    coords = [[lng, lat] for lat, lng in boundary]
    return ee.Geometry.Polygon(coords)


def _compute_ndvi(geometry) -> Optional[float]:
    """
    Calcula NDVI médio sobre a geometria usando Landsat 8 (últimos 12 meses).

    NDVI = (NIR - Red) / (NIR + Red)
    Landsat 8: B5 = NIR, B4 = Red
    """
    import ee

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)

    collection = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(geometry)
        .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        .filter(ee.Filter.lt("CLOUD_COVER", 20))
    )

    count = collection.size().getInfo()
    if count == 0:
        return None

    def add_ndvi(image):
        nir = image.select("SR_B5").multiply(0.0000275).add(-0.2)
        red = image.select("SR_B4").multiply(0.0000275).add(-0.2)
        ndvi = nir.subtract(red).divide(nir.add(red)).rename("NDVI")
        return image.addBands(ndvi)

    ndvi_collection = collection.map(add_ndvi)
    mean_ndvi = ndvi_collection.select("NDVI").mean()

    stats = mean_ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=30,
        maxPixels=1e9,
    ).getInfo()

    value = stats.get("NDVI")
    return float(value) if value is not None else None


def _compute_urban_density(geometry) -> Optional[float]:
    """
    Calcula índice de densidade urbana via GHSL (Global Human Settlement Layer).

    Usa GHSL Built-Up Surface (GHS_BUILT_S) — proporção de superfície construída.
    Dataset: JRC/GHSL/P2023A/GHS_BUILT_S
    """
    import ee

    ghsl = ee.ImageCollection("JRC/GHSL/P2023A/GHS_BUILT_S").mosaic()

    stats = ghsl.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=100,
        maxPixels=1e9,
    ).getInfo()

    # O valor bruto é em m² de área construída por pixel de 100m²
    # Normalizar para [0, 1] dividindo pela área máxima do pixel (10000 m²)
    raw = stats.get("built_surface") if stats else None
    if raw is None:
        # Tentar chave alternativa
        raw = next(iter(stats.values()), None) if stats else None

    if raw is None:
        return None

    normalized = min(float(raw) / 10000.0, 1.0)
    return normalized


def _compute_built_up_ratio(geometry) -> Optional[float]:
    """
    Calcula proporção de área construída usando GHSL Built-Up Characteristics.

    Dataset: JRC/GHSL/P2023A/GHS_BUILT_C — classifica pixels em categorias de
    uso construído. Retorna fração de pixels classificados como construídos.
    """
    import ee

    ghsl_c = ee.ImageCollection("JRC/GHSL/P2023A/GHS_BUILT_C").mosaic()

    # Pixels com valor > 0 são considerados construídos
    built_mask = ghsl_c.gt(0).rename("built")
    total_mask = ghsl_c.gte(0).rename("total")

    stats = ee.Image.cat([built_mask, total_mask]).reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=100,
        maxPixels=1e9,
    ).getInfo()

    value = stats.get("built") if stats else None
    if value is None:
        return None

    return float(min(value, 1.0))


class SatelliteEnricher:
    """
    Enriquece H3 cells com features de imagens de satélite via Google Earth Engine.

    Se o GEE não estiver disponível (pacote não instalado ou autenticação falhou),
    `self._available = False` e todas as chamadas retornam None para todas as
    features — o pipeline continua com degradação graciosa.
    """

    def __init__(self) -> None:
        self._available = False
        try:
            import ee  # noqa: F401 — verificar se o pacote está instalado
            ee.Initialize()
            self._available = True
            logger.info("Google Earth Engine inicializado com sucesso.")
        except ImportError:
            logger.warning(
                "Pacote 'earthengine-api' não instalado. "
                "Features de satélite serão None. "
                "Instale com: pip install earthengine-api"
            )
        except Exception as exc:
            logger.warning(
                "ee.Initialize() falhou: %s. "
                "Features de satélite serão None. "
                "Verifique a autenticação GEE (ee.Authenticate()).",
                exc,
            )

    def get_features_for_h3_cells(self, h3_ids: list[str]) -> dict[str, dict]:
        """
        Extrai features de satélite para cada H3_Cell fornecida.

        Retorna {h3_id: {feature_name: value}} onde:
          - ndvi_mean: float | None
          - urban_density_index: float | None
          - built_up_ratio: float | None
          - morphology_class: str | None

        Se GEE indisponível, todas as features são None para todas as células.
        Se uma célula individual falhar, ela recebe None e as demais continuam.
        """
        if not self._available:
            return {h3_id: dict(_NULL_FEATURES) for h3_id in h3_ids}

        results: dict[str, dict] = {}

        for h3_id in h3_ids:
            try:
                geometry = _h3_to_ee_geometry(h3_id)
                ndvi = _compute_ndvi(geometry)
                urban = _compute_urban_density(geometry)
                built = _compute_built_up_ratio(geometry)
                morph = _classify_morphology(ndvi, urban, built)

                results[h3_id] = {
                    "ndvi_mean": ndvi,
                    "urban_density_index": urban,
                    "built_up_ratio": built,
                    "morphology_class": morph,
                }
            except Exception as exc:
                logger.error(
                    "Satellite enrichment failed for cell %s: %s. Filling with None.",
                    h3_id,
                    exc,
                )
                results[h3_id] = dict(_NULL_FEATURES)

        return results
