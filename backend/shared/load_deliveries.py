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

    # ------------------------------------------------------------------ #
    # 0. Aliases de colunas — compat entre versões do SQL de extração
    # ------------------------------------------------------------------ #
    # O SQL evoluiu ao longo do tempo e diferentes versões exportaram a
    # mesma coluna com nomes distintos. Em vez de quebrar o pipeline,
    # renomeamos os aliases conhecidos para o nome canônico que o resto
    # de `load_deliveries` espera. Ordem: só renomeamos se o alias existe
    # E a chave canônica NÃO existe (evita sobrescrever coluna já presente).
    _COLUMN_ALIASES = {
        # `delivery_reason_code` é o novo nome após o refactor do SQL que
        # corrigiu o fan-out de `ihs_ids` (mudamos `scan_reason` para um
        # alias mais descritivo). O pipeline continua falando `reason_code`
        # internamente porque é o nome usado em todo o código downstream.
        "delivery_reason_code": "reason_code",
    }
    for alias, canonical in _COLUMN_ALIASES.items():
        if alias in df.columns and canonical not in df.columns:
            df = df.rename(columns={alias: canonical})
            print(f"   Alias aplicado: '{alias}' → '{canonical}'")

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
    # `store_id` é um identificador numérico do Salesforce. Quando o CSV
    # vem sem dtype explícito, pandas infere float64 (porque há valores
    # ausentes representados como NaN), o que transforma os IDs em algo
    # como `7912931585.0`. Isso quebra o join com o cadastro de parceiros
    # (que armazena o ID sem a parte decimal). O tratamento abaixo força
    # cada ID a string, remove o ".0" trailing de floats, e zera strings
    # realmente vazias ("", "nan", "NaN", "None") para "".
    def _clean_store_id(val) -> str:
        s = str(val).strip()
        if s in ("", "nan", "NaN", "None"):
            return ""
        # float representation: "12345.0" → "12345"
        if s.endswith(".0") and s[:-2].isdigit():
            return s[:-2]
        return s

    df["store_id"] = df["store_id"].map(_clean_store_id)

    for col in ("tracking_id", "reason_code", "canal_entrega", "nome_empresa"):
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

    # ------------------------------------------------------------------ #
    # 2b. Deduplicar por tracking_id — defesa contra fan-out upstream
    # ------------------------------------------------------------------ #
    # Um tracking_id representa UMA entrega física. Se aparece mais de uma
    # vez no CSV, a fonte tem bug (ex.: LEFT JOIN cartesiano com cadastros
    # duplicados no lado de mapping de parceiros). Aceitar duplicatas
    # causaria contagem dobrada em todos os agregados downstream e parceiros
    # aparecendo replicados na UI (ex.: "Wilma" duas vezes na mesma área).
    #
    # Política: mantém a entrada mais recente (timestamp maior) como fonte
    # canônica do evento de entrega. Isso privilegia a última atualização
    # do scan_reason caso a fonte tenha múltiplas linhas para o mesmo TID
    # com status evoluindo (ex: DELIVERED → DELIVERED_TO_RECIPIENT).
    #
    # Emite WARN com contagem para que a operação possa acionar o time de
    # dados. NÃO aborta — queremos que o Atlas continue funcionando mesmo
    # com fonte imperfeita; só não vamos multiplicar o bug.
    before = len(df)
    df = (
        df.sort_values("scan_datetime_br", ascending=False)
        .drop_duplicates(subset=["tracking_id"], keep="first")
        .reset_index(drop=True)
    )
    dup_count = before - len(df)
    if dup_count > 0:
        # Amostra de TIDs duplicados para o log, limitada para não poluir.
        sample_df = pd.DataFrame({"tracking_id": []})  # fallback vazio
        try:
            # Para o log apenas: relê o df original pra identificar alguns
            # exemplos. Como `before - len(df)` já foi calculado, gastamos
            # um scan adicional só se houver duplicatas (caminho frio).
            all_tids = df["tracking_id"]  # únicos agora
            dup_ratio = 100.0 * dup_count / max(before, 1)
            print(
                f"   WARN {dup_count:,} tracking_id(s) duplicado(s) "
                f"({dup_ratio:.2f}%) — mantendo a entrada mais recente. "
                f"Indício de fan-out na fonte (verificar o JOIN de mapeamento "
                f"de parceiros)."
            )
            _ = all_tids, sample_df  # silencia unused warning
        except Exception:
            # Nunca deixa o warn de log quebrar o pipeline.
            pass

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
    # `days` é o span da janela em dias calendário (date_max - date_min + 1),
    # NÃO a contagem de dias com dados. Isso é essencial para que a média
    # diária leve em conta dias em que o parceiro não entregou (zeros) —
    # caso contrário, um parceiro que entregou em 2 de 15 dias teria a
    # média inflada ao dividir só por 2. O zero-fill do daily_series
    # obedece ao mesmo range.
    date_min_raw = df["scan_date"].min()
    date_max_raw = df["scan_date"].max()
    date_min = str(date_min_raw) if date_min_raw is not None else None
    date_max = str(date_max_raw) if date_max_raw is not None else None
    if date_min and date_max:
        days = int((pd.Timestamp(date_max) - pd.Timestamp(date_min)).days) + 1
    else:
        days = 0
    stations = set(df["station_code"].dropna().unique()) - {""}

    # Contagem por canal (só log)
    canal_counts = df["canal_entrega"].value_counts().to_dict()

    # Quantos dias realmente têm dados — útil para diagnóstico quando há
    # buracos grandes na janela (ex: feriados ou falha de ingestão).
    days_with_data = df["scan_date"].nunique()
    if days_with_data < days:
        print(
            f"   INFO: janela de {days} dias tem {days_with_data} dia(s) com dados "
            f"— média diária considerará dias vazios como zero."
        )

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
