"""
load_packages.py
================
Fase 1 — Carregamento do histórico de pacotes.

Responsabilidades
-----------------
- Ler o CSV de pacotes históricos.
- Converter lat/lon para hexágonos H3 (se necessário).
- Resolver conflitos de hexágonos presentes em múltiplas bases com a
  seguinte prioridade:
    1. Jurisdição: se o centróide do hex está dentro da jurisdição de
       exatamente uma base, essa base vence independentemente de volume.
    2. Volume (fallback): hexes fora de qualquer jurisdição, ou na
       fronteira de múltiplas jurisdições, são resolvidos pela base com
       maior volume absoluto (winner-takes-all original).
- Construir o mapa de demanda TOTAL BRUTA por hex (sem divisão por dias),
  eliminando zeros falsos que a média inteira produzia.
- Construir o índice CEP → hexágonos para uso nos reports.

Por que demanda total bruta em vez de média diária
---------------------------------------------------
Média diária com arredondamento inteiro produz zeros falsos:
    hex com 3 entregas em 30 dias → 3/30 = 0.1 → round → 0

Para a formação de territórios, o que importa é a PROPORÇÃO relativa
entre hexes, não o valor absoluto. Total bruto e média diária têm a
mesma proporção (ambos divididos pela mesma constante `days`), mas o
total bruto nunca produz zeros em hexes que tiveram ao menos 1 entrega.

O campo `days` é retornado separadamente para uso nos reports de
demanda diária média (total_demand / days).

Output principal
----------------
PackageData.demand_by_station : Dict[str, Dict[str, int]]
    { station_code: { hex_id: total_packages_no_periodo } }

PackageData.hex_to_ceps : Dict[str, Set[str]]
    { hex_id: {cep1, cep2, ...} }

PackageData.hex_to_base : Dict[str, str]
    { hex_id: station_code_vencedor }

PackageData.days : int
    Número de dias distintos no período histórico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set

import h3
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape
from shapely.validation import make_valid

from shared.models import Config


# ---------------------------------------------------------------------------
# HELPERS DE VETORIZAÇÃO (H3)
# ---------------------------------------------------------------------------

def _vectorized_latlng_to_cell(
    lat: pd.Series | np.ndarray,
    lon: pd.Series | np.ndarray,
    res: int,
) -> np.ndarray:
    """
    Aplicação vetorizada de `h3.latlng_to_cell` sobre Series/arrays.

    - NaN em `lat` ou `lon` resultam em `""` (string vazia) na posição
      correspondente, preservando o comportamento do laço anterior que
      operava APÓS o `dropna(subset=["lat", "lon"])` (zero NaN esperado
      em produção, mas defensivo para quando a função for chamada antes
      do drop — ex.: testes).
    - Usa `np.vectorize` sobre a função C-level `h3.latlng_to_cell`.
      Não é vetorização nativa em SIMD, mas elimina o overhead do
      `list-comprehension` e da criação de objetos Python intermediários.
    """
    lat_arr = np.asarray(lat, dtype=float)
    lon_arr = np.asarray(lon, dtype=float)
    n = len(lat_arr)
    if n == 0:
        return np.empty(0, dtype=object)

    mask = np.isfinite(lat_arr) & np.isfinite(lon_arr)
    out = np.full(n, "", dtype=object)
    if mask.any():
        _fn = np.vectorize(h3.latlng_to_cell, excluded={"res"}, otypes=[object])
        out[mask] = _fn(lat_arr[mask], lon_arr[mask], res=res)
    return out


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class PackageData:
    """Resultado do carregamento do histórico de pacotes."""

    # Demanda total (pacotes no período) por base → hex
    demand_by_station: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Índices auxiliares
    hex_to_base: Dict[str, str]        = field(default_factory=dict)
    hex_to_ceps: Dict[str, Set[str]]   = field(default_factory=dict)

    # Período
    days: int = 1

    def demand_map(self, station_code: str) -> Dict[str, int]:
        """Retorna o demand_map de uma base específica (total bruto)."""
        return self.demand_by_station.get(station_code, {})

    def daily_demand_map(self, station_code: str) -> Dict[str, float]:
        """Retorna demanda média diária (float) para uso em reports."""
        return {
            h: v / self.days
            for h, v in self.demand_by_station.get(station_code, {}).items()
        }

    @property
    def all_stations(self):
        return list(self.demand_by_station.keys())


# ---------------------------------------------------------------------------
# LOADER
# ---------------------------------------------------------------------------

def _build_jurisdiction_index(
    jur_geojson: Dict,
    satellite_setup_stations: Optional[Set[str]] = None,
) -> Dict[str, object]:
    """
    Constrói um índice { station_code → shapely polygon } a partir do
    GeoJSON de jurisdições.  Geometrias inválidas são corrigidas com
    make_valid antes de serem armazenadas.

    Bases satélite (ex: XBA1) são indexadas com o código da base canônica
    (ex: DSA8) via STATION_ALIASES, de forma que hexes dentro do polígono
    satélite sejam atribuídos diretamente à base canônica.

    Quando ``satellite_setup_stations`` é fornecido, os códigos satélite
    contidos neste conjunto são indexados com o **próprio código satélite**
    (não com a canônica), de modo que hexes dentro do polígono satélite
    sejam atribuídos diretamente ao código satélite. Isso é usado pelo
    setup pipeline quando rodando para a própria satélite.
    """
    from shared.config import STATION_ALIASES

    index: Dict[str, object] = {}
    for feature in jur_geojson.get("features", []):
        station = feature.get("properties", {}).get("delivery_station")
        if not station:
            continue
        # Se é satélite em modo setup, indexar com o próprio código satélite
        if satellite_setup_stations and station in satellite_setup_stations:
            canonical = station
        else:
            # Resolver satélite → canônica (comportamento padrão)
            canonical = STATION_ALIASES.get(station, station)
        try:
            poly = make_valid(shape(feature["geometry"]))
        except Exception:
            try:
                poly = shape(feature["geometry"])
            except Exception:
                continue

        if canonical not in index:
            index[canonical] = poly
        else:
            # Unir polígonos: canônica já existe, satélite é adicionada via union
            try:
                index[canonical] = index[canonical].union(poly)
            except Exception:
                pass  # mantém o polígono existente se union falhar

    return index


def _resolve_station_by_jurisdiction(
    hex_id: str,
    jur_index: Dict[str, object],
) -> Optional[str]:
    """
    Retorna o station_code cuja jurisdição contém o centróide do hex.

    - Se exatamente uma jurisdição contém o ponto → retorna essa base.
    - Se nenhuma ou mais de uma contém (fronteira) → retorna None
      (fallback por volume).
    """
    lat, lon = h3.cell_to_latlng(hex_id)
    pt = Point(lon, lat)
    matches = [
        station for station, poly in jur_index.items()
        if poly.contains(pt)
    ]
    return matches[0] if len(matches) == 1 else None


def load_packages(
    path: str = None,
    jurisdiction_geojson: Optional[Dict] = None,
    satellite_setup_stations: Optional[Set[str]] = None,
) -> "PackageData":
    """
    Carrega o histórico de pacotes e retorna um PackageData.

    Parâmetros
    ----------
    path : str, opcional
        Caminho para o CSV. Se None, usa Config.BASE_PACKAGES.
    jurisdiction_geojson : dict, opcional
        GeoJSON de jurisdições (FeatureCollection).  Quando fornecido,
        a atribuição de hexes a bases usa jurisdição como critério
        primário; volume é usado apenas como fallback para hexes fora
        de qualquer jurisdição ou na fronteira de múltiplas.
    satellite_setup_stations : set[str], opcional
        Conjunto de códigos satélite que estão sendo processados em modo
        setup. Para esses códigos, o remap via ``STATION_ALIASES`` é
        **suprimido** — seus pacotes permanecem com o código satélite
        original, e o índice de jurisdição indexa os polígonos satélite
        com o próprio código (não a canônica). Isso permite que o setup
        pipeline gere territórios dedicados para a satélite.

    Fluxo
    -----
    1. Ler CSV e normalizar CEPs.
    2. Calcular hex H3 se não existir no CSV.
    3. Contar dias distintos no período.
    4. Agrupar por (station_code, hex) → quantidade total de linhas (entregas).
    5. Resolver atribuição de hexes a bases:
       5a. Se jurisdiction_geojson fornecido: jurisdição primeiro, volume
           como fallback.
       5b. Caso contrário: winner-takes-all por volume (comportamento
           original).
    6. Construir demand_by_station com totais brutos.
    7. Construir hex_to_ceps.
    """
    csv_path = path or Config.BASE_PACKAGES
    print(f"[load_packages] Lendo {csv_path} ...")

    df = pd.read_csv(csv_path)

    # 1. Normalizar CEPs
    if "cep" in df.columns:
        df["cep"] = (
            df["cep"]
            .astype(str)
            .str.replace(r"\D", "", regex=True)
            .str.zfill(8)
        )

    # 1b. Remapear bases satélite → base canônica
    # Pacotes de XBA1, XCS1, etc. são tratados como se fossem da base canônica.
    # EXCETO quando a satélite está sendo processada em modo setup — nesse caso
    # os pacotes dessa satélite permanecem com o código satélite original.
    from shared.config import STATION_ALIASES as _aliases_cfg
    aliases = getattr(Config, "STATION_ALIASES", None) or _aliases_cfg
    if aliases and "station_code" in df.columns:
        # Filtrar: excluir códigos presentes em satellite_setup_stations
        if satellite_setup_stations:
            effective_aliases = {
                k: v for k, v in aliases.items()
                if k not in satellite_setup_stations
            }
        else:
            effective_aliases = dict(aliases)

        if effective_aliases:
            before_alias = df["station_code"].nunique()
            df["station_code"] = df["station_code"].replace(effective_aliases)
            after_alias = df["station_code"].nunique()
            remapped = (df["station_code"].isin(effective_aliases.values())).sum()
            if before_alias != after_alias:
                print(f"   STATION_ALIASES: {before_alias - after_alias} bases satélite "
                      f"consolidadas nas bases canônicas.")
            satellite_codes = set(effective_aliases.keys())
            n_remapped = len(df[df["station_code"].isin(
                [effective_aliases[k] for k in satellite_codes if k in effective_aliases]
            )])
            _ = n_remapped  # usado só para log acima
        if satellite_setup_stations:
            suppressed = satellite_setup_stations & set(aliases.keys())
            if suppressed:
                print(f"   STATION_ALIASES: remap suprimido para satélites em modo "
                      f"setup: {sorted(suppressed)}")

    # 2. Calcular hex H3 se ausente
    if "hex" not in df.columns:
        if "latitude" not in df.columns or "longitude" not in df.columns:
            raise ValueError(
                "[load_packages] CSV deve conter colunas 'hex' OU "
                "'latitude'+'longitude'."
            )
        # Verificar se ha resolucoes diferentes por base
        has_per_station = bool(Config.H3_RES_PER_STATION)

        if has_per_station and "station_code" in df.columns:
            print(f"   Resolucoes H3 por base: {Config.H3_RES_PER_STATION} "
                  f"(demais usam res {Config.H3_RES})")
            # Vetorização por grupo de resolução — cada grupo usa uma
            # única chamada vetorizada de h3.latlng_to_cell
            df["hex"] = ""
            resolutions = df["station_code"].map(
                lambda sc: Config.get_h3_res(str(sc))
            )
            for res, idx in resolutions.groupby(resolutions).indices.items():
                df.loc[df.index[idx], "hex"] = _vectorized_latlng_to_cell(
                    df.iloc[idx]["latitude"],
                    df.iloc[idx]["longitude"],
                    int(res),
                )
        else:
            print(f"   Calculando hexagonos H3 (res={Config.H3_RES}) para "
                  f"{len(df):,} linhas ...")
            df["hex"] = _vectorized_latlng_to_cell(
                df["latitude"], df["longitude"], Config.H3_RES
            )

    # 3. Dias distintos no período
    if "plan_date" in df.columns:
        days = max(pd.to_datetime(df["plan_date"]).nunique(), 1)
    else:
        days = 1
        print("   WARN: coluna 'plan_date' ausente — assumindo 1 dia.")

    print(f"   Período: {days} dia(s) | {len(df):,} entregas | "
          f"{df['hex'].nunique():,} hexes únicos")

    # 4. Agrupar por (station_code, hex) — cada linha = 1 entrega
    raw = (
        df.groupby(["station_code", "hex"])
        .size()
        .reset_index(name="total_packages")
    )

    # 5. Resolver atribuição de hexes a bases
    print("   Resolvendo atribuição de hexes a bases ...")

    # Demanda total do hex (soma de todas as bases onde aparece)
    hex_totals = (
        raw.groupby("hex")["total_packages"]
        .sum()
        .reset_index(name="demand_total")
    )

    # Base vencedora por volume (fallback original)
    hex_winners_by_volume = (
        raw.sort_values("total_packages", ascending=False)
        .drop_duplicates(subset=["hex"], keep="first")[["hex", "station_code"]]
        .rename(columns={"station_code": "station_volume"})
    )

    unified = pd.merge(hex_winners_by_volume, hex_totals, on="hex")

    if jurisdiction_geojson:
        # 5a. Jurisdição como critério primário
        jur_index = _build_jurisdiction_index(
            jurisdiction_geojson,
            satellite_setup_stations=satellite_setup_stations,
        )
        print(f"   Jurisdição: {len(jur_index)} bases indexadas. "
              f"Resolvendo {len(unified):,} hexes ...")

        n_by_jurisdiction = 0
        n_by_volume = 0
        n_outside = 0

        winner_stations: Dict[str, str] = {}
        for hex_id in unified["hex"]:
            station_jur = _resolve_station_by_jurisdiction(hex_id, jur_index)
            if station_jur is not None:
                winner_stations[hex_id] = station_jur
                n_by_jurisdiction += 1
            else:
                # Fallback: volume
                vol_row = hex_winners_by_volume[
                    hex_winners_by_volume["hex"] == hex_id
                ]
                if not vol_row.empty:
                    winner_stations[hex_id] = vol_row.iloc[0]["station_volume"]
                    n_by_volume += 1
                else:
                    n_outside += 1

        unified["station_code"] = unified["hex"].map(winner_stations)
        unified = unified.dropna(subset=["station_code"])

        print(f"   Atribuição: {n_by_jurisdiction} por jurisdição | "
              f"{n_by_volume} por volume (fallback) | "
              f"{n_outside} sem base (descartados).")
    else:
        # 5b. Comportamento original: winner-takes-all por volume
        unified = unified.rename(columns={"station_volume": "station_code"})

    n_conflicts = len(raw["hex"].unique()) - len(raw.drop_duplicates("hex"))
    if n_conflicts > 0:
        print(f"   {n_conflicts} hexes com múltiplas bases no histórico.")
    print(f"   {len(unified):,} hexes únicos após unificação.")

    # 6. Construir demand_by_station (vetorizado — substitui iterrows)
    demand_by_station: Dict[str, Dict[str, int]] = {
        st: dict(zip(grp["hex"], grp["demand_total"].astype(int)))
        for st, grp in unified.groupby("station_code")
    }
    hex_to_base: Dict[str, str] = dict(
        zip(unified["hex"], unified["station_code"])
    )

    # 7. Índice CEP → hex
    hex_to_ceps: Dict[str, Set[str]] = {}
    if "cep" in df.columns:
        hex_to_ceps = (
            df.groupby("hex")["cep"]
            .apply(set)
            .to_dict()
        )

    # Sumário por base
    for station, dmap in demand_by_station.items():
        total = sum(dmap.values())
        daily = total / days
        print(f"   [{station}] {len(dmap):,} hexes | "
              f"demanda total: {total:,} | média diária: {daily:,.1f}")

    print(f"[load_packages] Concluído: {len(demand_by_station)} bases carregadas.")

    return PackageData(
        demand_by_station=demand_by_station,
        hex_to_base=hex_to_base,
        hex_to_ceps=hex_to_ceps,
        days=days,
    )
