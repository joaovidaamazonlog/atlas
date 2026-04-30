"""
Smoke test para a Fase 6 (deliveries / canal IHS vs DSP).

Valida:
- `load_deliveries` lê o CSV enriquecido e retorna DeliveryData coerente.
- `run_phase6` gera os 3 artefatos esperados (summary, by_hex, detail/*.jsonl.gz)
  e o manifesto consolidado.
- Agregações por canal batem com a contagem bruta.
- Parceiros sem match no dados_mapa.json são marcados como unknown.
- Entregas com store_id vazio aparecem nos totais por DS/hex mas não viram
  linhas de partner_stats (esse é o comportamento esperado para DSPs).

Não testa o pipeline completo — apenas o contrato da fase 6.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

# Permite rodar `pytest backend/tests/...` sem configurar PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.load_deliveries import load_deliveries, REQUIRED_DELIVERY_COLUMNS  # noqa: E402
from vanilla.phase6_deliveries import run_phase6  # noqa: E402


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

def _build_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Helper para gravar um CSV com as colunas do formato novo."""
    csv_path = tmp_path / "deliveries_test.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


def _build_dados_mapa(tmp_path: Path, partners: list[dict]) -> Path:
    path = tmp_path / "dados_mapa.json"
    payload = {"allMarkerData": partners}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return path


def _make_territories(hex_to_tid: dict) -> SimpleNamespace:
    """Stub mínimo compatível com `territories.hex_to_territory`."""
    return SimpleNamespace(
        hex_to_territory=hex_to_tid,
        territory_index={},
    )


@pytest.fixture
def sample_rows():
    """
    Cenário pequeno com:
    - 2 DSs: DSP2 e DBR9.
    - 1 hub IHS em DSP2 (store_id=HUB001 conhecido no dados_mapa).
    - 1 hub IHS em DBR9 (store_id=HUB002 NÃO presente no dados_mapa → unknown).
    - 2 entregas DSP em DSP2 sem store_id preenchido (comportamento típico).
    - Datas em 2 dias distintos para permitir série temporal.
    """
    return [
        # HUB001 em DSP2 (3 entregas IHS, hex_A, 2 datas)
        {
            "tracking_id": "T001", "scan_datetime_br": "2026-04-28 09:00:00",
            "reason_code": "OK_CUSTOMER", "canal_entrega": "IHS_STORE",
            "nome_empresa": "Hub Alpha LTDA", "store_id": "HUB001",
            "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
            "hex": "hex_A", "cep": "01310100",
        },
        {
            "tracking_id": "T002", "scan_datetime_br": "2026-04-28 10:00:00",
            "reason_code": "OK_RECEPTIONIST", "canal_entrega": "IHS_STORE",
            "nome_empresa": "Hub Alpha LTDA", "store_id": "HUB001",
            "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
            "hex": "hex_A", "cep": "01310100",
        },
        {
            "tracking_id": "T003", "scan_datetime_br": "2026-04-29 11:00:00",
            "reason_code": "OK_CUSTOMER", "canal_entrega": "IHS_STORE",
            "nome_empresa": "Hub Alpha LTDA", "store_id": "HUB001",
            "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
            "hex": "hex_A", "cep": "01310100",
        },
        # HUB002 em DBR9 (1 entrega IHS, hex_B, unknown partner)
        {
            "tracking_id": "T004", "scan_datetime_br": "2026-04-29 12:00:00",
            "reason_code": "OK_CUSTOMER", "canal_entrega": "IHS_STORE",
            "nome_empresa": "Hub Beta ME", "store_id": "HUB002",
            "station_code": "DBR9", "latitude": -23.53, "longitude": -46.77,
            "hex": "hex_B", "cep": "05000000",
        },
        # 2 entregas DSP em DSP2 (hex_A) — sem store_id
        {
            "tracking_id": "T005", "scan_datetime_br": "2026-04-28 13:00:00",
            "reason_code": "OK_CUSTOMER", "canal_entrega": "DSP",
            "nome_empresa": "DSP Rival SA", "store_id": "",
            "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
            "hex": "hex_A", "cep": "01310100",
        },
        {
            "tracking_id": "T006", "scan_datetime_br": "2026-04-29 14:00:00",
            "reason_code": "OK_CUSTOMER", "canal_entrega": "DSP",
            "nome_empresa": "DSP Rival SA", "store_id": "",
            "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
            "hex": "hex_A", "cep": "01310100",
        },
    ]


# ---------------------------------------------------------------------------
# TESTES: load_deliveries
# ---------------------------------------------------------------------------

def test_load_deliveries_reads_required_columns(tmp_path, sample_rows):
    csv_path = _build_csv(tmp_path, sample_rows)
    dd = load_deliveries(path=str(csv_path), days_window=0)

    assert not dd.empty
    assert len(dd.df) == 6
    for col in REQUIRED_DELIVERY_COLUMNS:
        assert col in dd.df.columns
    assert dd.days == 2
    assert dd.stations == {"DSP2", "DBR9"}


def test_load_deliveries_missing_column_returns_empty(tmp_path):
    # CSV sem coluna `canal_entrega` — fase deve ficar no-op
    rows = [{
        "tracking_id": "T001", "scan_datetime_br": "2026-04-28 09:00:00",
        "reason_code": "OK_CUSTOMER", "nome_empresa": "X", "store_id": "S1",
        "station_code": "DSP2", "latitude": -23.5, "longitude": -46.6,
        "hex": "hex_A",
    }]
    csv_path = _build_csv(tmp_path, rows)
    dd = load_deliveries(path=str(csv_path), days_window=0)
    assert dd.empty


def test_load_deliveries_window_filter(tmp_path):
    # 3 registros; janela=1 dia deve manter só o mais recente.
    rows = [
        {
            "tracking_id": "T001", "scan_datetime_br": "2026-04-20 09:00:00",
            "reason_code": "OK", "canal_entrega": "IHS_STORE",
            "nome_empresa": "A", "store_id": "S1", "station_code": "DSP2",
            "latitude": -23.5, "longitude": -46.6, "hex": "hex_A",
        },
        {
            "tracking_id": "T002", "scan_datetime_br": "2026-04-28 09:00:00",
            "reason_code": "OK", "canal_entrega": "IHS_STORE",
            "nome_empresa": "A", "store_id": "S1", "station_code": "DSP2",
            "latitude": -23.5, "longitude": -46.6, "hex": "hex_A",
        },
        {
            "tracking_id": "T003", "scan_datetime_br": "2026-04-29 09:00:00",
            "reason_code": "OK", "canal_entrega": "IHS_STORE",
            "nome_empresa": "A", "store_id": "S1", "station_code": "DSP2",
            "latitude": -23.5, "longitude": -46.6, "hex": "hex_A",
        },
    ]
    csv_path = _build_csv(tmp_path, rows)
    dd = load_deliveries(path=str(csv_path), days_window=1)

    # Janela de 1d a partir de 2026-04-29 deve preservar só T003
    # (corte estrito: > max - 1d)
    assert len(dd.df) == 1
    assert dd.df.iloc[0]["tracking_id"] == "T003"


# ---------------------------------------------------------------------------
# TESTES: run_phase6
# ---------------------------------------------------------------------------

def test_run_phase6_generates_all_artifacts(tmp_path, sample_rows):
    csv_path = _build_csv(tmp_path, sample_rows)
    dd = load_deliveries(path=str(csv_path), days_window=0)

    dados_mapa = _build_dados_mapa(tmp_path, [
        {
            "salesforce_id": "SF_001", "store_id": "HUB001", "name": "Hub Alpha",
            "status": "Active", "capacity": 50, "radius": 1500,
            "delivery_station": "DSP2",
            "bucket_ade": "DSP2_bucket-01", "lat": -23.55, "lon": -46.63,
        },
        # HUB002 propositalmente omitido para virar "unknown"
    ])

    territories = _make_territories({
        "hex_A": "DSP2_bucket-01",
        "hex_B": "DBR9_bucket-01",
    })

    result = run_phase6(
        deliveries=dd,
        dados_mapa_path=dados_mapa,
        territories=territories,
        output_dir=str(tmp_path),
    )

    # Arquivos gerados
    assert result.summary and result.summary.exists()
    assert result.by_hex and result.by_hex.exists()
    assert (tmp_path / "deliveries_manifest.json").exists()

    # Detalhe por DS
    detail_dir = result.detail_dir
    assert detail_dir.exists()
    assert (detail_dir / "DSP2.jsonl.gz").exists()
    assert (detail_dir / "DBR9.jsonl.gz").exists()

    # Ler e validar summary
    summary = json.loads(result.summary.read_text(encoding="utf-8"))
    st = summary["station_totals"]
    assert st["DSP2"]["total"] == 5       # 3 IHS + 2 DSP
    assert st["DSP2"]["ihs"] == 3
    assert st["DSP2"]["dsp"] == 2
    assert st["DSP2"]["ihs_share_pct"] == 60.0
    assert st["DBR9"]["total"] == 1

    # Parceiro conhecido (HUB001) e unknown (HUB002)
    partners_by_id = {p["store_id"]: p for p in summary["partners"]}
    assert "HUB001" in partners_by_id
    assert partners_by_id["HUB001"]["is_unknown"] is False
    assert partners_by_id["HUB001"]["name"] == "Hub Alpha"
    assert partners_by_id["HUB001"]["total"] == 3
    assert partners_by_id["HUB001"]["capacity"] == 50
    # daily_avg = 3 / 2 dias = 1.5; cap_util = 1.5/50*100 = 3.0%
    assert partners_by_id["HUB001"]["daily_avg"] == 1.5
    assert partners_by_id["HUB001"]["cap_utilization_pct"] == 3.0
    # HUB001 tem capacity=50 e o fixture traz lat/lon — portanto NÃO está
    # misconfigured.
    assert partners_by_id["HUB001"]["cap_misconfigured"] is False

    assert "HUB002" in partners_by_id
    assert partners_by_id["HUB002"]["is_unknown"] is True
    assert partners_by_id["HUB002"]["name"] == "Hub Beta ME"
    # Parceiros unknown (sem meta no dados_mapa.json) não são marcados como
    # misconfigured — não temos visibilidade do cadastro Salesforce deles.
    assert partners_by_id["HUB002"]["cap_misconfigured"] is False

    # Validar by_hex
    by_hex = json.loads(result.by_hex.read_text(encoding="utf-8"))
    hex_entries = {h["hex_id"]: h for h in by_hex["hexes"]}
    assert hex_entries["hex_A"]["total"] == 5
    assert hex_entries["hex_A"]["ihs"] == 3
    assert hex_entries["hex_A"]["dsp"] == 2
    assert hex_entries["hex_A"]["dsp_share_pct"] == 40.0
    # station_code (DS dominante) e territory_id devem aparecer quando
    # a agregação tem dados e o stub de territories fornece hex_to_territory
    assert hex_entries["hex_A"]["station_code"] == "DSP2"
    assert hex_entries["hex_A"]["territory_id"] == "DSP2_bucket-01"
    assert hex_entries["hex_B"]["station_code"] == "DBR9"
    # top_partners de hex_A deve conter HUB001 (único com store_id no hex)
    top_ids = [p["store_id"] for p in hex_entries["hex_A"]["top_partners"]]
    assert "HUB001" in top_ids

    # Validar detalhe DSP2 (5 linhas)
    with gzip.open(detail_dir / "DSP2.jsonl.gz", "rt", encoding="utf-8") as gz:
        lines = gz.readlines()
    assert len(lines) == 5
    rec = json.loads(lines[0])
    assert set(rec.keys()) >= {"tid", "sdt", "rc", "st", "ne", "ch", "hex"}


def test_run_phase6_empty_deliveries_is_noop(tmp_path):
    from shared.load_deliveries import DeliveryData
    dd = DeliveryData()  # empty
    dados_mapa = _build_dados_mapa(tmp_path, [])
    result = run_phase6(
        deliveries=dd,
        dados_mapa_path=dados_mapa,
        territories=_make_territories({}),
        output_dir=str(tmp_path),
    )
    assert result.summary is None
    assert result.by_hex is None
    assert not (tmp_path / "deliveries_summary.json").exists()


# ---------------------------------------------------------------------------
# TESTES: cap_misconfigured
# ---------------------------------------------------------------------------

def test_cap_misconfigured_flags_active_hub_with_zero_cap(tmp_path):
    """
    Hub Active com capacity=0 (dado real do Salesforce — configuração
    incompleta) deve ser marcado com cap_misconfigured=True. Não deve
    entrar em métricas de performance nem no card de subutilizados.
    """
    rows = [{
        "tracking_id": "T001", "scan_datetime_br": "2026-04-28 09:00:00",
        "reason_code": "OK", "canal_entrega": "IHS_STORE",
        "nome_empresa": "Hub Sem Cap", "store_id": "HUB_ZEROCAP",
        "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
        "hex": "hex_A", "cep": "01310100",
    }]
    csv_path = _build_csv(tmp_path, rows)
    dd = load_deliveries(path=str(csv_path), days_window=0)

    dados_mapa = _build_dados_mapa(tmp_path, [{
        "salesforce_id": "SF_ZEROCAP", "store_id": "HUB_ZEROCAP",
        "name": "Hub Sem Cap", "status": "Active",
        "capacity": 0, "radius": 1500,  # capacity=0 explícito
        "delivery_station": "DSP2", "bucket_ade": "DSP2_bucket-01",
        "lat": -23.55, "lon": -46.63,
    }])

    result = run_phase6(
        deliveries=dd,
        dados_mapa_path=dados_mapa,
        territories=_make_territories({"hex_A": "DSP2_bucket-01"}),
        output_dir=str(tmp_path),
    )

    summary = json.loads(result.summary.read_text(encoding="utf-8"))
    by_id = {p["store_id"]: p for p in summary["partners"]}
    p = by_id["HUB_ZEROCAP"]
    assert p["cap_misconfigured"] is True
    assert p["capacity"] == 0
    # cap_utilization_pct cai para 0 naturalmente (divisão por zero
    # protegida), mas a UI vai mostrar badge de warning em vez de alerta
    # de performance.
    assert p["cap_utilization_pct"] == 0.0


def test_cap_misconfigured_flags_zero_radius(tmp_path):
    """Radius=0 também vira cap_misconfigured (mesma regra)."""
    rows = [{
        "tracking_id": "T001", "scan_datetime_br": "2026-04-28 09:00:00",
        "reason_code": "OK", "canal_entrega": "IHS_STORE",
        "nome_empresa": "Hub Sem Raio", "store_id": "HUB_ZERORADIUS",
        "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
        "hex": "hex_A",
    }]
    csv_path = _build_csv(tmp_path, rows)
    dd = load_deliveries(path=str(csv_path), days_window=0)

    dados_mapa = _build_dados_mapa(tmp_path, [{
        "salesforce_id": "SF_ZR", "store_id": "HUB_ZERORADIUS",
        "name": "Hub Sem Raio", "status": "Active",
        "capacity": 50, "radius": 0,  # radius=0
        "delivery_station": "DSP2", "bucket_ade": "DSP2_bucket-01",
    }])

    result = run_phase6(
        deliveries=dd, dados_mapa_path=dados_mapa,
        territories=_make_territories({"hex_A": "DSP2_bucket-01"}),
        output_dir=str(tmp_path),
    )
    summary = json.loads(result.summary.read_text(encoding="utf-8"))
    by_id = {p["store_id"]: p for p in summary["partners"]}
    assert by_id["HUB_ZERORADIUS"]["cap_misconfigured"] is True


def test_cap_misconfigured_false_for_exited_partner(tmp_path):
    """
    Parceiro Exited com capacity=0 NÃO é misconfigured — é esperado que
    parceiros que saíram tenham o cap zerado. A flag é um warning
    operacional aplicável só a Active/Onboarding.
    """
    rows = [{
        "tracking_id": "T001", "scan_datetime_br": "2026-04-28 09:00:00",
        "reason_code": "OK", "canal_entrega": "IHS_STORE",
        "nome_empresa": "Hub Exited", "store_id": "HUB_EXITED",
        "station_code": "DSP2", "latitude": -23.55, "longitude": -46.63,
        "hex": "hex_A",
    }]
    csv_path = _build_csv(tmp_path, rows)
    dd = load_deliveries(path=str(csv_path), days_window=0)

    dados_mapa = _build_dados_mapa(tmp_path, [{
        "salesforce_id": "SF_EX", "store_id": "HUB_EXITED",
        "name": "Hub Exited", "status": "Exited",
        "capacity": 0, "radius": 0,
        "delivery_station": "DSP2",
    }])

    result = run_phase6(
        deliveries=dd, dados_mapa_path=dados_mapa,
        territories=_make_territories({"hex_A": "DSP2_bucket-01"}),
        output_dir=str(tmp_path),
    )
    summary = json.loads(result.summary.read_text(encoding="utf-8"))
    by_id = {p["store_id"]: p for p in summary["partners"]}
    assert by_id["HUB_EXITED"]["cap_misconfigured"] is False
