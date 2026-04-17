"""
ibge_enricher.py
================
Associa setores censitários IBGE às H3_Cells por interseção geográfica,
retornando `avg_income` e `population_density` por H3_Cell.

Download automático: se o arquivo local não existir, baixa os setores
censitários do IBGE (Censo 2022) via API do IBGE ou arquivo pré-processado
do repositório de dados abertos.

Degradação graciosa: se o arquivo não for encontrado e o download falhar,
todas as features retornam None e o pipeline continua normalmente.

Requirements: 1.4, 2.3
"""

from __future__ import annotations

import logging
import os
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Campos aceitos no GeoDataFrame do IBGE
# ---------------------------------------------------------------------------

_INCOME_FIELDS: tuple[str, ...] = (
    "renda_media", "renda_nom_media", "v005", "income_mean",
    "V005", "RENDA_MEDIA",
)
_POP_DENSITY_FIELDS: tuple[str, ...] = (
    "densidade_pop", "dens_pop", "densidade_demografica", "pop_density",
    "DENS_POP", "densidade",
)

_NULL_CELL: dict[str, None] = {"avg_income": None, "population_density": None}

# ---------------------------------------------------------------------------
# URLs de download dos setores censitários IBGE (Censo 2022)
# Fonte: IBGE Malhas Territoriais
# Formato: GeoPackage (.gpkg) por UF — mais leve que o shapefile nacional
# ---------------------------------------------------------------------------

# Mapeamento UF → código IBGE (para montar a URL de download)
_UF_CODES: dict[str, str] = {
    "AC": "12", "AL": "27", "AM": "13", "AP": "16", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MG": "31", "MS": "50", "MT": "51", "PA": "15", "PB": "25",
    "PE": "26", "PI": "22", "PR": "41", "RJ": "33", "RN": "24",
    "RO": "11", "RR": "14", "RS": "43", "SC": "42", "SE": "28",
    "SP": "35", "TO": "17",
}

# URL base do IBGE para malhas de setores censitários 2022
_IBGE_BASE_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/"
    "censo_2022/setores_censitarios_shp/{uf}/"
    "SC_Setores_2022_{uf}.zip"
)

# Diretório padrão para cache local dos arquivos IBGE
_DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "ibge"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _null_result(h3_ids: list[str]) -> dict[str, dict]:
    return {h3_id: dict(_NULL_CELL) for h3_id in h3_ids}


def _find_field(columns: list[str], candidates: tuple[str, ...]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in cols_lower:
            return cols_lower[candidate.lower()]
    return None


def _h3_to_shapely_polygon(h3_id: str):
    import h3
    from shapely.geometry import Polygon
    boundary = h3.cell_to_boundary(h3_id)
    return Polygon([(lng, lat) for lat, lng in boundary])


def _weighted_average(values: list[Optional[float]], weights: list[float]) -> Optional[float]:
    total_weight = 0.0
    weighted_sum = 0.0
    for value, weight in zip(values, weights):
        if value is not None and weight > 0:
            weighted_sum += value * weight
            total_weight += weight
    return weighted_sum / total_weight if total_weight > 0 else None


def _detect_uf_from_h3_ids(h3_ids: list[str]) -> Optional[str]:
    """
    Detecta a UF predominante a partir das coordenadas dos hexágonos H3.
    Usa a centróide do primeiro hexágono para fazer reverse geocoding leve
    via nominatim (sem API key).
    """
    if not h3_ids:
        return None
    try:
        import h3
        import urllib.request
        import json

        lat, lng = h3.cell_to_latlng(h3_ids[0])
        url = (
            f"https://nominatim.openstreetmap.org/reverse"
            f"?lat={lat}&lon={lng}&format=json&zoom=5"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "atlas-geo-intelligence/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        state = data.get("address", {}).get("state_code") or data.get("address", {}).get("ISO3166-2-lvl4", "")
        # state_code pode vir como "BR-SP" ou "SP"
        uf = state.replace("BR-", "").upper()
        if uf in _UF_CODES:
            return uf
    except Exception as exc:
        logger.debug("Não foi possível detectar UF via nominatim: %s", exc)
    return None


def download_ibge_sectors(
    uf: str,
    cache_dir: Path = _DEFAULT_CACHE_DIR,
) -> Optional[Path]:
    """
    Baixa os setores censitários do IBGE para uma UF e retorna o caminho
    do arquivo extraído (.shp).

    O arquivo é cacheado em `cache_dir/ibge_{uf}/` para evitar downloads
    repetidos.

    Parâmetros
    ----------
    uf : str
        Sigla da UF (ex: "SP", "RJ").
    cache_dir : Path
        Diretório de cache local.

    Retorna
    -------
    Path para o .shp extraído, ou None se o download falhar.
    """
    import urllib.request

    uf = uf.upper()
    if uf not in _UF_CODES:
        logger.error("UF '%s' não reconhecida.", uf)
        return None

    uf_dir = cache_dir / f"ibge_{uf}"
    uf_dir.mkdir(parents=True, exist_ok=True)

    # Verifica se já existe arquivo extraído
    existing_shp = list(uf_dir.glob("*.shp"))
    if existing_shp:
        logger.info("IBGE: usando arquivo em cache: %s", existing_shp[0])
        return existing_shp[0]

    url = _IBGE_BASE_URL.format(uf=uf)
    zip_path = uf_dir / f"SC_Setores_2022_{uf}.zip"

    logger.info("IBGE: baixando setores censitários de %s ...", url)
    logger.info("IBGE: isso pode levar alguns minutos dependendo da UF.")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "atlas-geo-intelligence/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 256  # 256 KB
            with open(zip_path, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        logger.info("IBGE: %.1f%% (%d MB / %d MB)", pct, downloaded // 1_000_000, total // 1_000_000)

        logger.info("IBGE: download concluído. Extraindo...")

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(uf_dir)

        zip_path.unlink(missing_ok=True)  # remove o zip após extração

        shp_files = list(uf_dir.glob("**/*.shp"))
        if not shp_files:
            logger.error("IBGE: nenhum .shp encontrado após extração.")
            return None

        logger.info("IBGE: setores extraídos em %s", shp_files[0])
        return shp_files[0]

    except Exception as exc:
        logger.error("IBGE: falha no download — %s. Features IBGE serão None.", exc)
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)
        return None


# ---------------------------------------------------------------------------
# IbgeEnricher
# ---------------------------------------------------------------------------

class IbgeEnricher:
    """
    Enriquece H3_Cells com dados socioeconômicos dos setores censitários IBGE.

    Se `census_sectors_path` for vazio ou o arquivo não existir, tenta
    baixar automaticamente os setores da UF correspondente aos hexágonos.

    Parâmetros
    ----------
    census_sectors_path : str
        Caminho para o arquivo GeoJSON/Shapefile dos setores censitários.
        Se vazio (""), o enricher detecta a UF e baixa automaticamente.
    cache_dir : Path, opcional
        Diretório de cache para downloads automáticos.
        Padrão: backend/data/ibge/
    auto_download : bool
        Se True (padrão), tenta baixar automaticamente quando o arquivo
        não for encontrado.
    """

    def __init__(
        self,
        census_sectors_path: str = "",
        cache_dir: Optional[Path] = None,
        auto_download: bool = True,
    ) -> None:
        self._path = census_sectors_path
        self._cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        self._auto_download = auto_download
        self._gdf = None
        self._income_field: Optional[str] = None
        self._pop_density_field: Optional[str] = None
        self._load_error: Optional[str] = None
        self._download_attempted = False

    def get_features_for_h3_cells(self, h3_ids: list[str]) -> dict[str, dict]:
        """Returns {h3_id: {"avg_income": float|None, "population_density": float|None}}"""
        if not h3_ids:
            return {}

        if self._gdf is None and self._load_error is None:
            self._load_census_sectors(h3_ids)

        if self._load_error is not None:
            return _null_result(h3_ids)

        results: dict[str, dict] = {}
        for h3_id in h3_ids:
            try:
                results[h3_id] = self._compute_cell_features(h3_id)
            except Exception as exc:
                logger.error("IbgeEnricher: falha ao processar célula %s — %s.", h3_id, exc)
                results[h3_id] = dict(_NULL_CELL)
        return results

    def _load_census_sectors(self, h3_ids: list[str] = []) -> None:
        """Carrega o GeoDataFrame, com download automático se necessário."""
        try:
            import geopandas as gpd
        except ImportError as exc:
            self._load_error = str(exc)
            logger.error("IbgeEnricher: geopandas não instalado — %s.", exc)
            return

        path_to_load = self._path

        # Se o caminho está vazio ou o arquivo não existe, tenta download automático
        if (not path_to_load or not Path(path_to_load).exists()) and self._auto_download and not self._download_attempted:
            self._download_attempted = True
            logger.info("IbgeEnricher: arquivo não encontrado. Tentando download automático...")

            uf = _detect_uf_from_h3_ids(h3_ids)
            if uf:
                logger.info("IbgeEnricher: UF detectada: %s", uf)
                downloaded = download_ibge_sectors(uf, self._cache_dir)
                if downloaded:
                    path_to_load = str(downloaded)
                else:
                    self._load_error = "Download automático do IBGE falhou."
                    logger.warning("IbgeEnricher: %s. Features IBGE serão None.", self._load_error)
                    return
            else:
                self._load_error = "Não foi possível detectar a UF para download automático."
                logger.warning("IbgeEnricher: %s. Features IBGE serão None.", self._load_error)
                return

        if not path_to_load or not Path(path_to_load).exists():
            self._load_error = f"Arquivo IBGE não encontrado: {path_to_load}"
            logger.warning("IbgeEnricher: %s. Features IBGE serão None.", self._load_error)
            return

        try:
            gdf = gpd.read_file(path_to_load)
        except Exception as exc:
            self._load_error = str(exc)
            logger.error("IbgeEnricher: erro ao ler arquivo IBGE — %s.", exc)
            return

        if gdf.empty:
            self._load_error = "GeoDataFrame IBGE vazio."
            logger.warning("IbgeEnricher: %s.", self._load_error)
            return

        try:
            if gdf.crs is None:
                gdf = gdf.set_crs(epsg=4326)
            elif gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)
        except Exception as exc:
            logger.warning("IbgeEnricher: não foi possível reprojetar — %s.", exc)

        columns = list(gdf.columns)
        self._income_field = _find_field(columns, _INCOME_FIELDS)
        self._pop_density_field = _find_field(columns, _POP_DENSITY_FIELDS)
        self._gdf = gdf
        logger.info(
            "IbgeEnricher: %d setores carregados. income_field=%s, pop_density_field=%s",
            len(gdf), self._income_field, self._pop_density_field,
        )

    def _compute_cell_features(self, h3_id: str) -> dict:
        cell_polygon = _h3_to_shapely_polygon(h3_id)
        minx, miny, maxx, maxy = cell_polygon.bounds

        gdf = self._gdf
        try:
            candidate_idx = list(gdf.sindex.intersection((minx, miny, maxx, maxy)))
            candidates = gdf.iloc[candidate_idx]
        except Exception:
            candidates = gdf

        if candidates.empty:
            return dict(_NULL_CELL)

        areas, incomes, pop_densities = [], [], []
        for _, sector in candidates.iterrows():
            geom = sector.geometry
            if geom is None or geom.is_empty:
                continue
            try:
                intersection = cell_polygon.intersection(geom)
            except Exception:
                continue
            if intersection.is_empty:
                continue
            area = intersection.area
            if area <= 0:
                continue

            areas.append(area)

            income_val = None
            if self._income_field:
                raw = sector.get(self._income_field)
                try:
                    v = float(raw)
                    income_val = v if v >= 0 else None
                except (TypeError, ValueError):
                    pass
            incomes.append(income_val)

            pop_val = None
            if self._pop_density_field:
                raw = sector.get(self._pop_density_field)
                try:
                    v = float(raw)
                    pop_val = v if v >= 0 else None
                except (TypeError, ValueError):
                    pass
            pop_densities.append(pop_val)

        if not areas:
            return dict(_NULL_CELL)

        return {
            "avg_income": _weighted_average(incomes, areas),
            "population_density": _weighted_average(pop_densities, areas),
        }
