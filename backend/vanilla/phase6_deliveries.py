"""
phase6_deliveries.py
====================
Fase 6 — Geração de artefatos de análise de canal (IHS vs DSP) e
drill-down operacional de pacotes.

Por que essa fase existe (contexto do produto)
----------------------------------------------
O Dashboard Operacional precisa responder a perguntas que o pipeline
tradicional (fases 1-5) não cobre:

1. Qual o share real de cada parceiro hub em cada DS e território?
2. Qual a divisão IHS vs DSP por DS e por hex?
3. Onde prospectar — quais hexes têm alto volume sem hub presente?
4. Quais parceiros ativos estão entregando muito abaixo do cap?

Essas perguntas exigem granularidade de pacote individual (scan_datetime,
tracking_id, canal_entrega, reason_code). O `load_packages.py` original
agrega por (station, hex) e perde essa granularidade, portanto esta fase
faz um passe paralelo sobre o CSV enriquecido e produz artefatos
dedicados.

Artefatos gerados
-----------------
1. `deliveries_summary.json` (~0.5–2 MB)
   Carregado no boot do Dashboard. Contém:
   - Totais por canal por DS (para o card de %share IHS vs DSP).
   - Agregados por parceiro (store_id): total, daily_avg, by_day[],
     share no DS, share no território, cap_utilization_pct.
   - Série temporal diária por DS (para visão operacional).
   - Lista de parceiros "unknown" (store_id sem match no cadastro).

2. `deliveries_by_hex.json` (~3–15 MB — gzip opcional a cargo do servidor)
   Carregado sob demanda quando o usuário interage com análise manual
   ou ativa o layer de share DSP. Contém:
   - Por hex: total, ihs, dsp, top_partners[{store_id, count}].

3. `deliveries_detail/{DS}.jsonl.gz` (1 por DS canônica, 0.5–8 MB cada)
   Carregado sob demanda quando o usuário abre o drill-down de um
   parceiro. Linhas com: tracking_id, scan_datetime_br, store_id,
   reason_code, canal, lat, lon, hex.

Decisões de design
------------------
- Frontend calcula insights (parceiros subutilizados, queda súbita,
  hexes órfãos) em cima das métricas base, com sliders ajustáveis pelo
  usuário. Esta fase só entrega os ingredientes.
- "top_partners" por hex é truncado em 10 entradas — mantém o JSON
  leve sem prejudicar o caso de uso (raramente há mais de 3-4 parceiros
  competindo por um mesmo hex).
- Parceiros "unknown" (store_id no CSV de pacotes sem correspondência
  no `dados_mapa.json`) são mantidos e marcados com flag, para que o
  Dashboard sinalize "parceiro desconhecido" sem sumir o volume.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import h3
import pandas as pd

from shared.config import (
    CANAL_DSP,
    CANAL_IHS,
    DELIVERIES_DETAIL_SUBDIR,
)
from shared.load_deliveries import DeliveryData


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _safe_pct(numerator: float, denominator: float) -> float:
    """Retorna pct (0–100) com fallback seguro em caso de divisão por zero."""
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 2)


def _is_cap_misconfigured(meta: Optional[Dict[str, Any]], status: Optional[str]) -> bool:
    """
    Indica que o parceiro está cadastrado no Salesforce como Active/Onboarding
    mas com `capacity == 0` OU `radius == 0` — configuração incompleta que
    precisa de ação manual do time de ops. Isola esses parceiros das métricas
    de performance (cap_utilization, subutilizados) e alimenta o card de
    warning próprio no Dashboard.

    Retorna False para parceiros Exited/Inactive (cap=0 é esperado neles) e
    para parceiros "unknown" (sem meta do dados_mapa.json — não temos
    visibilidade do cadastro deles).
    """
    if meta is None:
        return False
    if status not in ("Active", "Onboarding"):
        return False
    capacity = meta.get("capacity") or 0
    radius = meta.get("radius") or 0
    return capacity == 0 or radius == 0


def _normalize_store_id(val) -> str:
    """
    Normaliza um store_id para a chave de join entre pacotes e parceiros.

    Pandas infere o store_id como float64 no CSV de pacotes (porque há
    NaN) — isso transforma `12345` em `"12345.0"` no `astype(str)`,
    quebrando o match com o cadastro de parceiros (que guarda `"12345"`).
    Aqui convertemos qualquer representação para a forma canônica (sem
    ".0" trailing) para garantir que ambos os lados falem a mesma língua.

    Entradas vazias (None, "", "nan", "NaN") viram string vazia.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if s in ("", "nan", "NaN", "None"):
        return ""
    if s.endswith(".0") and s[:-2].isdigit():
        return s[:-2]
    return s


def _build_partner_index(dados_mapa_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Lê o `dados_mapa.json` e constrói o índice `store_id → partner_meta`
    para resolver nome, status, cap, DS canônica, bucket_ade e
    salesforce_id de cada parceiro a partir do store_id do CSV de pacotes.

    Parceiros sem `store_id` preenchido são ignorados (não há como bater
    com os pacotes). O cadastro traz esse campo principalmente para hubs
    IHS; DSPs típicos ficam sem match e aparecerão como "unknown".

    Normalizamos o store_id via `_normalize_store_id` para garantir que
    a chave no índice seja idêntica à chave produzida pelo `load_deliveries`
    (ambos removem ".0" trailing se o ID tiver passado por um float).
    """
    if not dados_mapa_path.exists():
        print(f"  WARN phase6: {dados_mapa_path} não encontrado — partner_index vazio.")
        return {}

    with open(dados_mapa_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    index: Dict[str, Dict[str, Any]] = {}
    dupes = 0
    for p in payload.get("allMarkerData", []):
        sid_key = _normalize_store_id(p.get("store_id"))
        if not sid_key:
            continue
        if sid_key in index:
            # Mesmo store_id cadastrado em 2+ Salesforce IDs. Mantemos o
            # primeiro (ordem do JSON, tipicamente Active antes de Inactive)
            # e logamos para visibilidade. Caso raro — geralmente indica
            # cadastro duplicado no Salesforce.
            dupes += 1
            continue
        index[sid_key] = {
            "salesforce_id":   p.get("salesforce_id"),
            "name":            p.get("name"),
            "status":          p.get("status"),
            "capacity":        p.get("capacity") or 0,
            "radius":          p.get("radius") or 0,
            "delivery_station": p.get("delivery_station"),
            "bucket_ade":      p.get("bucket_ade"),
            "lat":             p.get("lat"),
            "lon":             p.get("lon"),
            "hub_initiatives": p.get("hub_delivey_initiatives"),
        }
    if dupes:
        print(f"  INFO phase6: {dupes} store_id duplicado(s) no cadastro — primeiro mantido.")
    return index


# ---------------------------------------------------------------------------
# AGREGAÇÕES
# ---------------------------------------------------------------------------

def _compute_station_totals(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
    """
    Totais por (station_code, canal_entrega).
    Saída: { DS: { total, ihs, dsp, other } }.
    """
    grouped = (
        df.groupby(["station_code", "canal_entrega"])
        .size()
        .unstack(fill_value=0)
    )
    result: Dict[str, Dict[str, int]] = {}
    for station, row in grouped.iterrows():
        if not station:
            continue
        ihs = int(row.get(CANAL_IHS, 0))
        dsp = int(row.get(CANAL_DSP, 0))
        total = int(row.sum())
        other = total - ihs - dsp
        result[str(station)] = {
            "total": total,
            "ihs":   ihs,
            "dsp":   dsp,
            "other": max(other, 0),
            "ihs_share_pct": _safe_pct(ihs, total),
            "dsp_share_pct": _safe_pct(dsp, total),
        }
    return result


def _compute_daily_by_station(
    df: pd.DataFrame,
    date_min: Optional[str] = None,
    date_max: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Série temporal diária por DS: { DS: [{date, ihs, dsp, total}, ...] }.
    Datas ordenadas ASC.

    Quando `date_min`/`date_max` são fornecidos, faz zero-fill para todos
    os dias da janela (inclusive os sem entrega) — essencial para o gráfico
    de média diária não mentir ao esconder dias vazios. Sem eles, usa só
    as datas presentes no df.
    """
    grouped = (
        df.groupby(["station_code", "scan_date", "canal_entrega"])
        .size()
        .unstack(fill_value=0)
    )

    # Datas completas da janela (para zero-fill)
    if date_min and date_max:
        full_dates = [
            d.strftime("%Y-%m-%d")
            for d in pd.date_range(start=date_min, end=date_max, freq="D")
        ]
    else:
        full_dates = None

    # Acumula por station: mapa date→{ihs,dsp,total}
    per_station: Dict[str, Dict[str, Dict[str, int]]] = {}
    for (station, date), row in grouped.iterrows():
        if not station:
            continue
        ihs = int(row.get(CANAL_IHS, 0))
        dsp = int(row.get(CANAL_DSP, 0))
        total = int(row.sum())
        per_station.setdefault(str(station), {})[str(date)] = {
            "ihs": ihs, "dsp": dsp, "total": total,
        }

    result: Dict[str, List[Dict[str, Any]]] = {}
    for station, date_map in per_station.items():
        dates_to_emit = full_dates if full_dates else sorted(date_map.keys())
        series = []
        for d in dates_to_emit:
            bucket = date_map.get(d, {"ihs": 0, "dsp": 0, "total": 0})
            series.append({"date": d, **bucket})
        result[station] = series

    return result


def _compute_partner_stats(
    df: pd.DataFrame,
    partner_index: Dict[str, Dict[str, Any]],
    station_totals: Dict[str, Dict[str, int]],
    territory_totals: Dict[str, int],
    days: int,
    date_min: Optional[str] = None,
    date_max: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Estatísticas por parceiro (store_id):
      - total, daily_avg, daily_series (zero-filled para o range da janela)
      - share_ds (% sobre o total do DS, considerando canal IHS e DSP)
      - share_ds_ihs (% sobre apenas o volume IHS do DS)
      - share_territory (% sobre o bucket_ade do parceiro; 0 se unknown)
      - cap_utilization_pct (daily_avg / capacity * 100)
      - trend_7d_pct (variação do volume últimos 7d vs 7d anteriores)
      - is_unknown (True se não bateu com partner_index)

    `daily_series` sempre cobre TODOS os dias entre date_min e date_max,
    inclusive os dias sem entrega (total=0). Isso permite que o chart do
    frontend mostre a média diária real sem enviesar para cima (do jeito
    errado, dias com 0 entregas seriam omitidos e o usuário enxergaria
    apenas os picos). É também essencial para comparar performance entre
    parceiros cujas janelas ativas diferem.

    Filtra para manter apenas store_ids não-vazios via `_normalize_store_id`.
    Parceiros IHS em geral terão store_id preenchido; entregas DSP típicas
    não — essas ficam nos agregados de DS mas não viram linhas aqui.
    """
    # Normalização defensiva: mesmo que load_deliveries já faça, aplicamos
    # de novo para tolerar callers que construam o df de outro modo.
    df = df.copy()
    df["store_id"] = df["store_id"].map(_normalize_store_id)
    df_valid = df[df["store_id"].astype(str).str.len() > 0]
    if df_valid.empty:
        return []

    # ------------------------------------------------------------------ #
    # Range completo de datas da janela — para zero-fill.
    # ------------------------------------------------------------------ #
    if date_min and date_max:
        full_dates = [
            d.strftime("%Y-%m-%d")
            for d in pd.date_range(start=date_min, end=date_max, freq="D")
        ]
    else:
        # Fallback: usa o range presente no df.
        full_dates = sorted(df_valid["scan_date"].unique().tolist())

    # ------------------------------------------------------------------ #
    # Agregação principal: total por (store_id, scan_date)
    # ------------------------------------------------------------------ #
    grouped = df_valid.groupby(["store_id", "scan_date"]).agg(
        total=("tracking_id", "count"),
    ).reset_index()

    # Station e canal dominantes por parceiro (em uma só passada)
    station_by_partner = (
        df_valid.groupby(["store_id", "station_code"])
        .size().reset_index(name="n")
        .sort_values(["store_id", "n"], ascending=[True, False])
        .drop_duplicates("store_id", keep="first")
        .set_index("store_id")["station_code"]
        .to_dict()
    )
    canal_by_partner = (
        df_valid.groupby(["store_id", "canal_entrega"])
        .size().reset_index(name="n")
        .sort_values(["store_id", "n"], ascending=[True, False])
        .drop_duplicates("store_id", keep="first")
        .set_index("store_id")["canal_entrega"]
        .to_dict()
    )
    # Nome da empresa (mais frequente) por store_id
    nome_by_partner = (
        df_valid[df_valid["nome_empresa"].astype(str).str.len() > 0]
        .groupby(["store_id", "nome_empresa"])
        .size().reset_index(name="n")
        .sort_values(["store_id", "n"], ascending=[True, False])
        .drop_duplicates("store_id", keep="first")
        .set_index("store_id")["nome_empresa"]
        .to_dict()
    )

    # Cutoffs para tendência (calculado uma vez)
    last_date = pd.to_datetime(full_dates[-1]) if full_dates else None
    cutoff_7 = (
        (last_date - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        if last_date is not None else None
    )
    cutoff_14 = (
        (last_date - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
        if last_date is not None else None
    )

    partners_out: List[Dict[str, Any]] = []

    for store_id, sub in grouped.groupby("store_id"):
        store_id = str(store_id)

        # Mapa date→total para o parceiro (rápido: dict lookup)
        partner_daily = dict(zip(sub["scan_date"].astype(str), sub["total"].astype(int)))
        total = int(sub["total"].sum())

        # Zero-fill: uma entrada por dia da janela, mesmo que volume=0.
        daily_series = [
            {"date": d, "total": int(partner_daily.get(d, 0))}
            for d in full_dates
        ]
        daily_avg = round(total / days, 2) if days > 0 else 0.0

        station_dom = str(station_by_partner.get(store_id, ""))
        canal_dom = str(canal_by_partner.get(store_id, ""))
        nome_empresa = str(nome_by_partner.get(store_id) or store_id)

        meta = partner_index.get(store_id)
        is_unknown = meta is None

        name = (meta or {}).get("name") or nome_empresa
        salesforce_id = (meta or {}).get("salesforce_id")
        capacity = int((meta or {}).get("capacity") or 0)
        bucket_ade = (meta or {}).get("bucket_ade")
        status = (meta or {}).get("status")

        # Shares
        ds_info = station_totals.get(station_dom, {})
        share_ds = _safe_pct(total, ds_info.get("total", 0))
        share_ds_ihs = _safe_pct(total, ds_info.get("ihs", 0))

        share_territory = 0.0
        if bucket_ade and bucket_ade in territory_totals:
            share_territory = _safe_pct(total, territory_totals[bucket_ade])

        cap_util = _safe_pct(daily_avg, capacity) if capacity else 0.0

        # Trend 7d vs 7d anteriores — usa o daily_series já zero-filled
        trend_pct = 0.0
        if cutoff_7 and cutoff_14:
            recent = sum(r["total"] for r in daily_series if r["date"] > cutoff_7)
            prior = sum(
                r["total"] for r in daily_series
                if cutoff_14 < r["date"] <= cutoff_7
            )
            if prior > 0:
                trend_pct = round(100.0 * (recent - prior) / prior, 2)
            elif recent > 0:
                trend_pct = 100.0

        partners_out.append({
            "store_id":              store_id,
            "salesforce_id":         salesforce_id,
            "name":                  name,
            "nome_empresa":          nome_empresa,
            "status":                status,
            "canal_dominante":       canal_dom,
            "delivery_station":      station_dom,
            "bucket_ade":            bucket_ade,
            "capacity":              capacity,
            "radius":                int((meta or {}).get("radius") or 0),
            "total":                 total,
            "daily_avg":             daily_avg,
            "cap_utilization_pct":   cap_util,
            "share_ds_pct":          share_ds,
            "share_ds_ihs_pct":      share_ds_ihs,
            "share_territory_pct":   share_territory,
            "trend_7d_pct":          trend_pct,
            "daily_series":          daily_series,
            "is_unknown":            is_unknown,
            # `cap_misconfigured` sinaliza hub ativo cadastrado no Salesforce
            # com capacity=0 OU radius=0 — configuração incompleta que vira
            # warning próprio no Dashboard. Não entra em cap_utilization_pct
            # (que fica 0.0 por definição de divisão) e não é considerado
            # "subutilizado" na aba Insights.
            "cap_misconfigured":     _is_cap_misconfigured(meta, status),
            "lat":                   (meta or {}).get("lat"),
            "lon":                   (meta or {}).get("lon"),
        })

    # Ordenação estável por total DESC para consumo direto no frontend.
    partners_out.sort(key=lambda p: p["total"], reverse=True)
    return partners_out


def _compute_territory_totals(
    df: pd.DataFrame,
    territories,
) -> Dict[str, int]:
    """
    Totais de pacotes por território (bucket_ade), a partir do hex do
    pacote e do mapa `hex_to_territory` já calculado pelo pipeline.

    Usado para share_territory de cada parceiro. Hexes fora de qualquer
    território são ignorados (ficam só no total do DS).
    """
    hex_to_territory = getattr(territories, "hex_to_territory", {}) or {}
    if not hex_to_territory or df.empty:
        return {}

    # Construir Series para mapear hex → tid sem chamar .map repetido.
    tid_series = df["hex"].map(hex_to_territory)
    valid = df[tid_series.notna()].copy()
    valid["territory_id"] = tid_series.dropna().values

    totals = valid.groupby("territory_id").size().to_dict()
    return {str(k): int(v) for k, v in totals.items()}


def _compute_hex_breakdown(
    df: pd.DataFrame,
    hex_to_territory: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Breakdown por hex: total, ihs, dsp, top_partners (10 maiores),
    station_code e territory_id (se disponíveis).

    station_code e territory_id são adicionados para permitir que o
    frontend recorte hexes órfãos pela hierarquia (BDM/DS/CTL/ADE).
    Sem eles, a aba Insights fica limitada a contagem global.

    top_partners é usado pela análise manual para identificar quem está
    competindo num raio específico. Limitado a 10 para manter o arquivo
    pequeno — em 99% dos hexes há bem menos que isso.
    """
    if df.empty or "hex" not in df.columns:
        return []

    df_hex = df[df["hex"].astype(str).str.len() > 0]
    if df_hex.empty:
        return []

    # Totais por canal
    by_canal = df_hex.groupby(["hex", "canal_entrega"]).size().unstack(fill_value=0)
    by_canal["total"] = by_canal.sum(axis=1)

    # Station vencedora por hex (a que mais entregou naquele hex dentro
    # da janela). Em fronteiras pode haver mais de uma — pegamos a
    # dominante por volume, igual ao load_packages.py.
    hex_to_station = (
        df_hex.groupby(["hex", "station_code"]).size()
        .reset_index(name="n")
        .sort_values(["hex", "n"], ascending=[True, False])
        .drop_duplicates("hex", keep="first")
        .set_index("hex")["station_code"]
        .to_dict()
    )

    # Top partners por hex
    by_partner = (
        df_hex[df_hex["store_id"].astype(str).str.len() > 0]
        .groupby(["hex", "store_id", "nome_empresa"])
        .size()
        .reset_index(name="count")
    )

    # Pré-ordenar para permitir head(10) por hex
    by_partner = by_partner.sort_values(["hex", "count"], ascending=[True, False])

    top_partners_map: Dict[str, List[Dict[str, Any]]] = {}
    for hex_id, grp in by_partner.groupby("hex"):
        top_partners_map[str(hex_id)] = [
            {
                "store_id":     str(row.store_id),
                "nome_empresa": str(row.nome_empresa) if row.nome_empresa else str(row.store_id),
                "count":        int(row.count),
            }
            for row in grp.head(10).itertuples()
        ]

    result: List[Dict[str, Any]] = []
    hex_to_territory = hex_to_territory or {}
    for hex_id, row in by_canal.iterrows():
        hex_id = str(hex_id)
        total = int(row["total"])
        ihs = int(row.get(CANAL_IHS, 0))
        dsp = int(row.get(CANAL_DSP, 0))
        entry: Dict[str, Any] = {
            "hex_id":        hex_id,
            "total":         total,
            "ihs":           ihs,
            "dsp":           dsp,
            "dsp_share_pct": _safe_pct(dsp, total),
            "top_partners":  top_partners_map.get(hex_id, []),
        }
        # Centróide do hex (lat, lon). Permite o frontend plotar um pin na
        # posição exata sem precisar de h3-js — o backend já tem o h3 em
        # memória e calcula por O(1) com a string do hex_id.
        try:
            lat, lon = h3.cell_to_latlng(hex_id)
            entry["lat"] = float(lat)
            entry["lon"] = float(lon)
        except Exception:
            # hex_id inválido (muito raro) — entrega sem coords, o frontend
            # esconde o botão "ver no mapa" nesse caso.
            pass
        station = hex_to_station.get(hex_id)
        if station:
            entry["station_code"] = str(station)
        territory = hex_to_territory.get(hex_id)
        if territory:
            entry["territory_id"] = str(territory)
        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# ESCRITA DOS ARTEFATOS
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def _write_details_per_ds(
    df: pd.DataFrame,
    out_dir: Path,
) -> Dict[str, int]:
    """
    Gera um `.jsonl.gz` por DS com os pacotes individuais, em formato
    line-delimited para permitir streaming no frontend.

    Cada linha: `{tid, sdt, rc, st, ch, lat, lon, hex}` — nomes curtos
    para reduzir o tamanho do payload. O Dashboard expande para nomes
    completos na leitura.

    Retorna o mapa { DS → nº de linhas escritas }, usado no manifesto.
    """
    detail_dir = out_dir / DELIVERIES_DETAIL_SUBDIR
    detail_dir.mkdir(parents=True, exist_ok=True)

    # Limpar arquivos antigos (a janela pode ter encolhido). Mantém só as DSs
    # que produzirão arquivo agora; o manifesto reflete o estado atual.
    for old in detail_dir.glob("*.jsonl.gz"):
        try:
            old.unlink()
        except OSError:
            pass

    counts: Dict[str, int] = {}
    if df.empty:
        return counts

    for station, sub in df.groupby("station_code"):
        if not station:
            continue
        file_path = detail_dir / f"{station}.jsonl.gz"
        lines_written = 0
        with gzip.open(file_path, "wt", encoding="utf-8") as gz:
            for row in sub.itertuples(index=False):
                record = {
                    "tid":  str(row.tracking_id),
                    "sdt":  str(row.scan_datetime_br),
                    "rc":   str(row.reason_code),
                    "st":   str(row.store_id),
                    "ne":   str(row.nome_empresa),
                    "ch":   str(row.canal_entrega),
                    "hex":  str(row.hex),
                }
                # Lat/Lon opcionais (para o pin no mapa)
                lat = getattr(row, "latitude", None)
                lon = getattr(row, "longitude", None)
                if lat is not None and pd.notna(lat):
                    record["lat"] = float(lat)
                if lon is not None and pd.notna(lon):
                    record["lon"] = float(lon)
                gz.write(json.dumps(record, ensure_ascii=False) + "\n")
                lines_written += 1
        counts[str(station)] = lines_written

    return counts


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------

@dataclass
class Phase6Result:
    """Caminhos dos arquivos gerados — para log/uso posterior."""
    summary: Optional[Path] = None
    by_hex: Optional[Path] = None
    detail_dir: Optional[Path] = None
    detail_files: Dict[str, int] = None

    def __post_init__(self):
        if self.detail_files is None:
            self.detail_files = {}


def run_phase6(
    deliveries: DeliveryData,
    dados_mapa_path: Path,
    territories,
    output_dir: str,
) -> Phase6Result:
    """
    Fase 6 — gera os artefatos de análise de canal.

    Parâmetros
    ----------
    deliveries : DeliveryData
        Resultado de `load_deliveries()`. Se vazio (CSV sem colunas
        novas), a fase é skippada com warning.

    dados_mapa_path : Path
        Caminho do `dados_mapa.json` recém-gerado pela Fase 5. Usado para
        casar `store_id` de pacotes com os metadados do parceiro.

    territories : TerritoriesResult
        Necessário para calcular share por território (bucket_ade).

    output_dir : str
        Pasta de destino dos artefatos.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if deliveries.empty:
        print("  Fase 6: DeliveryData vazio — pulando geração de artefatos.")
        return Phase6Result()

    print(f"\n{'='*60}")
    print(f"  FASE 6 — DELIVERIES (canal IHS vs DSP)")
    print(f"  Período: {deliveries.date_min} → {deliveries.date_max} "
          f"({deliveries.days}d)")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    df = deliveries.df

    # ------------------------------------------------------------------ #
    # 1. Índice de parceiros
    # ------------------------------------------------------------------ #
    partner_index = _build_partner_index(dados_mapa_path)
    print(f"  partner_index: {len(partner_index)} parceiros com store_id.")

    # ------------------------------------------------------------------ #
    # 2. Agregações
    # ------------------------------------------------------------------ #
    station_totals = _compute_station_totals(df)
    daily_by_station = _compute_daily_by_station(
        df,
        date_min=deliveries.date_min,
        date_max=deliveries.date_max,
    )
    territory_totals = _compute_territory_totals(df, territories)
    partner_stats = _compute_partner_stats(
        df=df,
        partner_index=partner_index,
        station_totals=station_totals,
        territory_totals=territory_totals,
        days=deliveries.days,
        date_min=deliveries.date_min,
        date_max=deliveries.date_max,
    )

    n_unknown = sum(1 for p in partner_stats if p["is_unknown"])
    print(f"  parceiros estatísticas: {len(partner_stats)} "
          f"(unknown: {n_unknown})")
    print(f"  territórios com volume: {len(territory_totals)}")

    # ------------------------------------------------------------------ #
    # 3. deliveries_summary.json
    # ------------------------------------------------------------------ #
    summary_path = out_dir / "deliveries_summary.json"
    summary_payload = {
        "period": {
            "date_min": deliveries.date_min,
            "date_max": deliveries.date_max,
            "days": deliveries.days,
        },
        "station_totals": station_totals,
        "territory_totals": territory_totals,
        "daily_by_station": daily_by_station,
        "partners": partner_stats,
    }
    _write_json(summary_path, summary_payload)
    size_kb = summary_path.stat().st_size / 1024
    print(f"  ✅ {summary_path.name}  ({size_kb:.1f} KB)")

    # ------------------------------------------------------------------ #
    # 4. deliveries_by_hex.json
    # ------------------------------------------------------------------ #
    hex_breakdown = _compute_hex_breakdown(
        df,
        hex_to_territory=getattr(territories, "hex_to_territory", None),
    )
    by_hex_path = out_dir / "deliveries_by_hex.json"
    by_hex_payload = {
        "period": {
            "date_min": deliveries.date_min,
            "date_max": deliveries.date_max,
            "days": deliveries.days,
        },
        "hexes": hex_breakdown,
    }
    _write_json(by_hex_path, by_hex_payload)
    size_mb = by_hex_path.stat().st_size / (1024 * 1024)
    print(f"  ✅ {by_hex_path.name}  "
          f"({len(hex_breakdown):,} hexes | {size_mb:.2f} MB)")

    # ------------------------------------------------------------------ #
    # 5. deliveries_detail/{DS}.jsonl.gz (um por DS)
    # ------------------------------------------------------------------ #
    detail_counts = _write_details_per_ds(df, out_dir)
    total_lines = sum(detail_counts.values())
    detail_dir = out_dir / DELIVERIES_DETAIL_SUBDIR
    print(f"  ✅ {DELIVERIES_DETAIL_SUBDIR}/  "
          f"({len(detail_counts)} DSs | {total_lines:,} linhas no total)")

    # ------------------------------------------------------------------ #
    # 6. Manifesto (liga os arquivos; consumido pelo frontend no load)
    # ------------------------------------------------------------------ #
    manifest_path = out_dir / "deliveries_manifest.json"
    manifest_payload = {
        "period": summary_payload["period"],
        "files": {
            "summary": "deliveries_summary.json",
            "by_hex": "deliveries_by_hex.json",
            "detail_dir": DELIVERIES_DETAIL_SUBDIR,
            "detail_per_ds": {
                ds: f"{DELIVERIES_DETAIL_SUBDIR}/{ds}.jsonl.gz"
                for ds in detail_counts
            },
        },
        "counts": {
            "partners": len(partner_stats),
            "unknown_partners": n_unknown,
            "hexes_with_volume": len(hex_breakdown),
            "stations": len(station_totals),
            "detail_lines_by_ds": detail_counts,
        },
    }
    _write_json(manifest_path, manifest_payload)
    print(f"  ✅ {manifest_path.name}")

    return Phase6Result(
        summary=summary_path,
        by_hex=by_hex_path,
        detail_dir=detail_dir,
        detail_files=detail_counts,
    )
