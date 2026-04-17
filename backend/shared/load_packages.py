"""
load_packages.py
================
Fase 1 — Carregamento do histórico de pacotes.

Responsabilidades
-----------------
- Ler o CSV de pacotes históricos.
- Converter lat/lon para hexágonos H3 (se necessário).
- Resolver conflitos de hexágonos presentes em múltiplas bases
  (winner-takes-all: base com maior volume absoluto vence).
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
from typing import Dict, Set

import h3
import pandas as pd

from shared.models import Config


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

def load_packages(path: str = None) -> PackageData:
    """
    Carrega o histórico de pacotes e retorna um PackageData.

    Parâmetros
    ----------
    path : str, opcional
        Caminho para o CSV. Se None, usa Config.BASE_PACKAGES.

    Fluxo
    -----
    1. Ler CSV e normalizar CEPs.
    2. Calcular hex H3 se não existir no CSV.
    3. Contar dias distintos no período.
    4. Agrupar por (station_code, hex) → quantidade total de linhas (entregas).
    5. Resolver duplicidades entre bases (winner-takes-all por volume).
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
            df["hex"] = [
                h3.latlng_to_cell(float(la), float(lo),
                                  Config.get_h3_res(str(sc)))
                for la, lo, sc in zip(df["latitude"], df["longitude"],
                                      df["station_code"])
            ]
        else:
            print(f"   Calculando hexagonos H3 (res={Config.H3_RES}) para "
                  f"{len(df):,} linhas ...")
            df["hex"] = [
                h3.latlng_to_cell(float(la), float(lo), Config.H3_RES)
                for la, lo in zip(df["latitude"], df["longitude"])
            ]

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

    # 5. Resolver duplicidades: hexes presentes em múltiplas bases
    #    → base com maior volume de entregas no hex vence ("winner takes all")
    #    → demanda do hex = soma de todas as bases (não perde volume)
    print("   Resolvendo duplicidades entre bases ...")

    # Demanda total do hex (soma de todas as bases onde aparece)
    hex_totals = (
        raw.groupby("hex")["total_packages"]
        .sum()
        .reset_index(name="demand_total")
    )

    # Base vencedora = a com maior volume no hex
    hex_winners = (
        raw.sort_values("total_packages", ascending=False)
        .drop_duplicates(subset=["hex"], keep="first")[["hex", "station_code"]]
    )

    # Unir: hex | station_vencedora | demanda_total_somada
    unified = pd.merge(hex_winners, hex_totals, on="hex")

    n_conflicts = len(raw["hex"].unique()) - len(raw.drop_duplicates("hex"))
    if n_conflicts > 0:
        print(f"   {n_conflicts} hexes conflitantes resolvidos.")
    print(f"   {len(unified):,} hexes únicos após unificação.")

    # 6. Construir demand_by_station
    demand_by_station: Dict[str, Dict[str, int]] = {}
    hex_to_base: Dict[str, str] = {}

    for _, row in unified.iterrows():
        station = row["station_code"]
        hex_id  = row["hex"]
        demand  = int(row["demand_total"])

        demand_by_station.setdefault(station, {})[hex_id] = demand
        hex_to_base[hex_id] = station

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
