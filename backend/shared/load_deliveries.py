"""
load_deliveries.py
==================
Carregamento enriquecido do histórico de pacotes para as análises de
canal (IHS vs DSP), parceiro e drill-down operacional.

Responsabilidades
-----------------
- Ler o CSV de pacotes considerando as novas colunas:
  `tracking_id`, `scan_datetime_br`, `reason_code`, `canal_entrega`,
  `nome_empresa`, `store_id`.
- Normalizar tipos (datetime BR, strings, station_code remapeado para base
  canônica conforme `STATION_ALIASES`).
- Consolidar em um único DataFrame de pacotes, preservando granularidade
  linha-a-linha para alimentar as análises do frontend.
- Calcular o hex H3 quando não presente, respeitando a resolução por base.

O que NÃO é responsabilidade deste módulo
------------------------------------------
- Gerar artefatos JSON (feito pela Fase 6 — `phase6_deliveries.py`).
- Alocar demanda a parceiros (continua em `load_packages.py`).
- Resolver conflitos de hex entre bases por jurisdição (continua em
  `load_packages.py`; aqui usamos o `station_code` original remapeado).

Por que um módulo separado
--------------------------
`load_packages.py` já é crítico para as fases 1-5 (setup e daily). Para
evitar regressões em contratos existentes (shape de `PackageData`,
sumário por base, resolução de jurisdição), as análises de canal vivem
em um caminho paralelo. Um segundo passe sobre o CSV custa poucos
segundos e mantém o código novo isolado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set

import h3
import numpy as np
import pandas as pd

from shared.models import Config


# Colunas mínimas que o CSV precisa ter para as análises de canal
# funcionarem. Faltando uma delas, a Fase 6 é abortada com warning claro
# (o pipeline tradicional segue funcionando normalmente).
REQUIRED_DELIVERY_COLUMNS = [
    "tracking_id",
    "scan_datetime_br",
    "reason_code",
    "canal_entrega",
    "nome_empresa",
    "store_id",
]


# ---------------------------------------------------------------------------
# OUTPUT DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class DeliveryData:
    """
    Resultado do carregamento enriquecido de pacotes.

    Atributos
    ---------
    df : pd.DataFrame
        Uma linha por pacote, com as colunas:
        `tracking_id, scan_datetime_br, scan_date, reason_code, canal_entrega,
         nome_empresa, store_id, station_code, hex, latitude, longitude, cep`.
        `station_code` já está remapeado para a base canônica.

    days : int
        Número de dias distintos cobertos pela base (após o filtro de
        janela de `PACKAGE_HISTORY_DAYS`, se aplicado).

    date_min, date_max : str | None
        Datas ISO (YYYY-MM-DD) do início e fim do período. Úteis para o
        frontend exibir o range coberto pelas análises.

    stations : set[str]
        Conjunto de bases canônicas presentes na base.
    """

    df: pd.DataFrame = field(default_factory=pd.DataFrame)
    days: int = 0
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    stations: Set[str] = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return self.df is None or len(self.df) == 0


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _vectorized_latlng_to_cell(
    lat: pd.Series | np.ndarray,
    lon: pd.Series | np.ndarray,
    res: int,
) -> np.ndarray:
    """Vetorização do `h3.latlng_to_cell` com proteção a NaN."""
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


def _check_required_columns(df: pd.DataFrame) -> Optional[str]:
    """Retorna a primeira coluna faltante, ou None se todas estão presentes."""
    for col in REQUIRED_DELIVERY_COLUMNS:
        if col not in df.columns:
            return col
    return None


# ---------------------------------------------------------------------------
# LOADER PRINCIPAL
# ---------------------------------------------------------------------------

def load_deliveries(
    path: str = None,
    days_window: Optional[int] = None,
) -> DeliveryData:
    """
    Lê o CSV de pacotes e retorna um DataFrame enriquecido para análises
    de canal e drill-down.

    Parâmetros
    ----------
    path : str, opcional
        Caminho do CSV. Se None, usa ``Config.BASE_PACKAGES``.

    days_window : int, opcional
        Se fornecido, filtra o DataFrame mantendo apenas entregas dos
        últimos `days_window` dias (inclusive a data mais recente).
        Se None, usa ``Config.PACKAGE_HISTORY_DAYS``. Passe `0` para
        desabilitar o filtro e manter o CSV inteiro.

    Retorno
    -------
    DeliveryData. Se o CSV não tiver as colunas novas obrigatórias, o
    DataFrame vem vazio e um warning é impresso (o pipeline legado
    continua funcional).
    """
    csv_path = path or Config.BASE_PACKAGES
    window = Config.PACKAGE_HISTORY_DAYS if days_window is None else days_window

    print(f"[load_deliveries] Lendo {csv_path} (janela={window}d)...")

    df = pd.read_csv(csv_path)

    missing = _check_required_columns(df)
    if missing:
        print(
            f"   WARN coluna obrigatória ausente: '{missing}'. "
            f"Análises de canal (IHS vs DSP) serão puladas nesta execução."
        )
        return DeliveryData()

    # ------------------------------------------------------------------ #
    # 1. Normalização de strings
    # ------------------------------------------------------------------ #
    for col in ("tracking_id", "reason_code", "canal_entrega", "nome_empresa", "store_id"):
        df[col] = df[col].astype(str).str.strip()
        # Strings vazias ficam como "" (não NaN) para simplificar groupby.
        df.loc[df[col].isin(("nan", "NaN", "None")), col] = ""

    # Canal normalizado em uppercase; mantém os valores canônicos do config.
    df["canal_entrega"] = df["canal_entrega"].str.upper()

    # CEP normalizado (8 dígitos com leading zeros).
    if "cep" in df.columns:
        df["cep"] = (
            df["cep"]
            .astype(str)
            .str.replace(r"\D", "", regex=True)
            .str.zfill(8)
        )
    else:
        df["cep"] = ""

    # ------------------------------------------------------------------ #
    # 2. Datetime e recorte por janela
    # ------------------------------------------------------------------ #
    df["scan_datetime_br"] = pd.to_datetime(
        df["scan_datetime_br"], errors="coerce"
    )
    df = df.dropna(subset=["scan_datetime_br"])
    if df.empty:
        print("   WARN nenhum registro com scan_datetime_br válido.")
        return DeliveryData()

    df["scan_date"] = df["scan_datetime_br"].dt.date.astype(str)

    if window and window > 0:
        cutoff = df["scan_datetime_br"].max() - pd.Timedelta(days=window)
        before = len(df)
        df = df[df["scan_datetime_br"] > cutoff].copy()
        print(
            f"   Janela aplicada: {before:,} → {len(df):,} registros "
            f"(últimos {window} dias)."
        )

    if df.empty:
        print("   WARN DataFrame vazio após filtro de janela.")
        return DeliveryData()

    # ------------------------------------------------------------------ #
    # 3. Remap de bases satélite → canônica
    # ------------------------------------------------------------------ #
    if "station_code" in df.columns:
        aliases = getattr(Config, "STATION_ALIASES", None) or {}
        if aliases:
            df["station_code"] = df["station_code"].replace(aliases)
    else:
        print("   WARN coluna 'station_code' ausente — análises por DS serão afetadas.")
        df["station_code"] = ""

    # ------------------------------------------------------------------ #
    # 4. Hex H3 (se ausente)
    # ------------------------------------------------------------------ #
    if "hex" not in df.columns:
        if "latitude" not in df.columns or "longitude" not in df.columns:
            print(
                "   WARN CSV sem colunas 'hex' nem 'latitude'/'longitude'. "
                "Análises por hex ficarão vazias."
            )
            df["hex"] = ""
        else:
            has_per_station = bool(getattr(Config, "H3_RES_PER_STATION", None))
            default_res = getattr(Config, "H3_RES", 9) or 9

            if has_per_station and "station_code" in df.columns:
                df["hex"] = ""
                resolutions = df["station_code"].map(
                    lambda sc: Config.get_h3_res(str(sc))
                    if hasattr(Config, "get_h3_res") else default_res
                )
                for res, idx in resolutions.groupby(resolutions).indices.items():
                    df.loc[df.index[idx], "hex"] = _vectorized_latlng_to_cell(
                        df.iloc[idx]["latitude"],
                        df.iloc[idx]["longitude"],
                        int(res),
                    )
            else:
                df["hex"] = _vectorized_latlng_to_cell(
                    df["latitude"], df["longitude"], default_res
                )

    # ------------------------------------------------------------------ #
    # 5. Serialização do datetime para ISO (string) para simplificar I/O
    # ------------------------------------------------------------------ #
    df["scan_datetime_br"] = df["scan_datetime_br"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Manter apenas as colunas relevantes; demais custam memória sem uso.
    keep = [
        "tracking_id", "scan_datetime_br", "scan_date",
        "reason_code", "canal_entrega", "nome_empresa", "store_id",
        "station_code", "hex",
    ]
    if "latitude" in df.columns:
        keep.append("latitude")
    if "longitude" in df.columns:
        keep.append("longitude")
    if "cep" in df.columns:
        keep.append("cep")
    df = df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # 6. Sumário
    # ------------------------------------------------------------------ #
    days = df["scan_date"].nunique()
    date_min = df["scan_date"].min()
    date_max = df["scan_date"].max()
    stations = set(df["station_code"].dropna().unique()) - {""}

    # Contagem por canal (só log)
    canal_counts = df["canal_entrega"].value_counts().to_dict()

    print(
        f"   Período: {date_min} → {date_max} ({days}d) | "
        f"{len(df):,} entregas | {len(stations)} bases | "
        f"canais: {canal_counts}"
    )

    return DeliveryData(
        df=df,
        days=days,
        date_min=date_min,
        date_max=date_max,
        stations=stations,
    )
