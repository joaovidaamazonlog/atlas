"""
Valida o mapeamento de colunas do partners.csv real (export Salesforce
com snake_case minúsculo e espaços: "volume cap", "supply run",
"launch date"). Cobre os aliases H* (HSP2/HSP5/HRJ3/HSV8/HPE4/HFO3/HPB3/HBH5)
adicionados ao STATION_ALIASES para garantir que parceiros com DS virtual
sejam remapeados corretamente para as canônicas.

O teste constrói um CSV mínimo diretamente dos cabeçalhos reais do export
e valida que `load_partners_csv` produz objetos Partner com:
- salesforce_id, name, store_id, status populados.
- delivery_station remapeado (HSP5 → DSP5, HSV8 → DSA8, etc).
- capacity e radius lidos de 'volume cap' e 'radius'.
- lat/lon numéricos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# Permite rodar `pytest backend/tests/...` sem configurar PYTHONPATH.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_partners_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Gera um CSV no formato real do export (snake_case + espaços)."""
    # Cabeçalho exato do partners.csv de produção.
    columns = [
        "id", "account_manager", "cep", "cidade", "converted_date",
        "createdbyid", "createddate", "decision_reason_code",
        "decision_reason_detail", "decision_status", "delivery_mode",
        "delivery_station", "diff_b_w_vetting_and_converted_date",
        "diff_b_w_vetting_and_prospect", "diff_converted_and_original_launch",
        "estado", "exit_date", "field_acquisition_manager", "hcp_host_partner",
        "hcp_rate_card", "hub_delivery_initiatives", "jurisdiction_name",
        "jurisdiction_type", "latitude", "longitude", "name", "launch date",
        "onboarding_support", "ownerid", "phone", "ready_to_launch_date",
        "recruitment_representative", "status", "storeid", "supply run",
        "territory_manager_owner", "tm_owner", "vetting_date",
        "volume cap", "radius",
    ]
    # Preenche colunas faltantes com string vazia.
    normalized = [
        {col: row.get(col, "") for col in columns}
        for row in rows
    ]
    df = pd.DataFrame(normalized, columns=columns)
    csv_path = tmp_path / "partners_real.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


def _make_empty_jurisdiction_geojson(tmp_path: Path) -> Path:
    path = tmp_path / "jur.geojson"
    path.write_text('{"type": "FeatureCollection", "features": []}', encoding="utf-8")
    return path


def test_partners_csv_real_format_basic_fields(tmp_path, monkeypatch):
    """
    Sanity check: três parceiros com DS canônico, DS virtual H*, e satélite X*.
    Valida que delivery_station é remapeado, campos principais populados e
    capacity/radius vêm das colunas 'volume cap' e 'radius' do CSV.
    """
    from shared.load_partners import load_partners_csv
    import shared.config as cfg

    # Direciona a escrita de dados_mapa.json para tmp_path para não poluir
    # o output_data de produção.
    monkeypatch.setattr(cfg, "DEST_FOLDER", tmp_path)

    rows = [
        # 1. Parceiro com DS canônica + store_id preenchido
        {
            "id": "001A00000aaaa",
            "name": "Hub Alpha LTDA",
            "storeid": "STORE_A",
            "status": "Active",
            "delivery_station": "DSP2",
            "latitude": "-23.55",
            "longitude": "-46.63",
            "cep": "01310100",
            "cidade": "São Paulo",
            "estado": "SP",
            "volume cap": "80",
            "radius": "1500",
            "hub_delivery_initiatives": "Hub Hero",
            "hcp_rate_card": "Tier 1",
            "launch date": "2025-10-15",
            "jurisdiction_name": "DSP2_bucket-01",  # ignorado pelo pipeline — fase 5 recalcula
            "account_manager": "Deve ser ignorado",  # TEAM manda
            "territory_manager_owner": "DSP2_MRA",  # idem
        },
        # 2. Parceiro com DS virtual H* → deve ser remapeado para DSP5
        {
            "id": "001A00000bbbb",
            "name": "Hub Beta ME",
            "storeid": "STORE_B",
            "status": "Active",
            "delivery_station": "HSP5",
            "latitude": "-22.91",
            "longitude": "-47.08",
            "cep": "13083000",
            "cidade": "Campinas",
            "estado": "SP",
            "volume cap": "50",
            "radius": "2000",
        },
        # 3. Parceiro com DS satélite X* existente — continua funcionando
        {
            "id": "001A00000cccc",
            "name": "Hub Gamma",
            "storeid": "STORE_C",
            "status": "Onboarding",
            "delivery_station": "XCP1",
            "latitude": "-22.99",
            "longitude": "-47.05",
            "cep": "13100000",
            "cidade": "Campinas",
            "estado": "SP",
            "volume cap": "42",
            "radius": "1500",
        },
    ]
    csv_path = _make_partners_csv(tmp_path, rows)
    j_path = _make_empty_jurisdiction_geojson(tmp_path)

    data = load_partners_csv(str(csv_path), jurisdiction_path=str(j_path))
    df = data.partners_df

    assert len(df) == 3, f"Esperado 3 parceiros, vieram {len(df)}."

    # Índice por salesforce_id
    by_sid = {r["salesforce_id"]: r for _, r in df.iterrows()}

    # 1. Canônica pura
    a = by_sid["001A00000aaaa"]
    # Dentro do partners_df, name → partner_name e delivery_station → station_code
    # (renomeação feita por _build_partner_data para alinhar com Fases 3-5).
    assert a["partner_name"] == "Hub Alpha LTDA"
    assert a["store_id"] == "STORE_A"
    assert a["status"] == "Active"
    assert a["station_code"] == "DSP2"
    assert a["capacity"] == 80, f"capacity esperado 80, veio {a['capacity']}"
    assert a["radius"] == 1500, f"radius esperado 1500, veio {a['radius']}"
    assert float(a["lat"]) == pytest.approx(-23.55, abs=1e-4)
    assert a["hub_delivey_initiatives"] == "Hub Hero"

    # 2. Virtual H* remapeado para canônica
    b = by_sid["001A00000bbbb"]
    assert b["station_code"] == "DSP5", (
        f"HSP5 deveria virar DSP5, veio {b['station_code']}"
    )
    assert b["store_id"] == "STORE_B"
    assert b["capacity"] == 50

    # 3. Satélite X*: o parceiro MANTÉM o código X* em `station_code` porque
    # _DS_REMAP (em Partner.from_row) só contém os aliases virtuais H*. O
    # remap satélite → canônica para X* acontece no nível da demanda de
    # pacotes (`load_packages.py` usa STATION_ALIASES) e via jurisdição no
    # pipeline. Isso é comportamento esperado e não muda com os ajustes.
    c = by_sid["001A00000cccc"]
    assert c["station_code"] == "XCP1", (
        f"XCP1 deve manter o código original no parceiro, veio {c['station_code']}"
    )
    assert c["status"] == "Onboarding"


def test_partners_csv_all_H_aliases_mapped(tmp_path, monkeypatch):
    """
    Valida especificamente os 8 aliases virtuais H* adicionados ao
    STATION_ALIASES. Cada DS virtual deve ser remapeado para sua canônica.
    """
    from shared.load_partners import load_partners_csv
    import shared.config as cfg

    monkeypatch.setattr(cfg, "DEST_FOLDER", tmp_path)

    expected = {
        "HSP2": "DSP2",
        "HSP5": "DSP5",
        "HRJ3": "DRJ3",
        "HSV8": "DSA8",
        "HPE4": "DPE4",
        "HFO3": "DCE3",
        "HPB3": "DPB3",
        "HBH5": "DBH5",
    }

    rows = [
        {
            "id": f"001H{i:08x}",
            "name": f"Virtual Hub {virtual}",
            "storeid": f"VH_{virtual}",
            "status": "Active",
            "delivery_station": virtual,
            "latitude": "-23.0",
            "longitude": "-46.0",
            "cep": "01000000",
            "cidade": "City",
            "estado": "SP",
            "volume cap": "42",
            "radius": "1500",
        }
        for i, virtual in enumerate(expected.keys())
    ]
    csv_path = _make_partners_csv(tmp_path, rows)
    j_path = _make_empty_jurisdiction_geojson(tmp_path)

    data = load_partners_csv(str(csv_path), jurisdiction_path=str(j_path))
    df = data.partners_df

    remapped = {
        r["partner_name"].replace("Virtual Hub ", ""): r["station_code"]
        for _, r in df.iterrows()
    }

    for virtual, canonical in expected.items():
        assert remapped.get(virtual) == canonical, (
            f"Alias H* falhou: {virtual} → {remapped.get(virtual)} "
            f"(esperado {canonical})"
        )


def test_partners_csv_ignores_team_and_jurisdiction_columns(tmp_path, monkeypatch):
    """
    Confirma que account_manager, territory_manager_owner, tm_owner e
    jurisdiction_name (quando usadas para atribuir CTL/ADE/bucket) são
    ignoradas pelo parser — a hierarquia vem da config TEAM e o bucket_ade
    é recalculado na Fase 5 pelo hex do parceiro.

    Testa apenas que esses campos não criam inconsistências no Partner
    resultante (não alteram delivery_station nem quebram from_row).
    """
    from shared.load_partners import load_partners_csv
    import shared.config as cfg

    monkeypatch.setattr(cfg, "DEST_FOLDER", tmp_path)

    rows = [{
        "id": "001TESTE1",
        "name": "Parceiro Teste",
        "storeid": "T1",
        "status": "Active",
        "delivery_station": "DPR2",
        "latitude": "-25.43",
        "longitude": "-49.27",
        "volume cap": "60",
        "radius": "1500",
        # Campos que devem ser IGNORADOS pelo parser:
        "account_manager": "NÃO DEVE AFETAR",
        "territory_manager_owner": "DPR2_MRA",
        "tm_owner": "005at000",
        "jurisdiction_name": "DPR2_bucket-99",  # fase 5 recalcula
    }]
    csv_path = _make_partners_csv(tmp_path, rows)
    j_path = _make_empty_jurisdiction_geojson(tmp_path)

    data = load_partners_csv(str(csv_path), jurisdiction_path=str(j_path))
    df = data.partners_df

    assert len(df) == 1
    p = df.iloc[0]
    # Campos operacionais carregados corretamente.
    # (delivery_station é renomeado internamente para station_code.)
    assert p["station_code"] == "DPR2"
    assert p["capacity"] == 60
    # bucket vem do CSV aqui (jurisdiction_name → Bucket), mas na Fase 5
    # o pipeline real resolve bucket_ade via hex_to_territory e sobrescreve.
    # Isto é esperado: o CSV serve apenas como seed; a hierarquia
    # operacional vem do TEAM.


def test_partners_csv_preserves_explicit_zero_cap_and_radius(tmp_path, monkeypatch):
    """
    Regra de ouro: ``volume cap = 0`` e ``radius = 0`` vindos do CSV são
    dados operacionais reais (parceiro ativo sem configuração de cap/raio
    no Salesforce). O parser deve preservar como 0, NÃO aplicar o default
    42/1500. Apenas valores vazios/NaN devem cair no default.

    Essa regra é a base para o warning "hubs ativos com cap/raio zerados"
    na aba Pacotes & Canais do Dashboard: confiamos que 0 no cadastro
    significa "sem cap", não "sem dado".
    """
    from shared.load_partners import load_partners_csv
    import shared.config as cfg

    monkeypatch.setattr(cfg, "DEST_FOLDER", tmp_path)

    rows = [
        # (a) Hub ativo com cap=0 e radius=0 EXPLÍCITOS no CSV.
        #     Deve preservar 0 (não cair no default 42/1500).
        {
            "id": "001ZEROCAP",
            "name": "Hub Com Cap Zero",
            "storeid": "Z1",
            "status": "Active",
            "delivery_station": "DSP2",
            "latitude": "-23.55",
            "longitude": "-46.63",
            "volume cap": "0",
            "radius": "0",
        },
        # (b) Hub ativo com campos VAZIOS no CSV.
        #     Aí sim deve cair no default 42/1500.
        {
            "id": "001VAZIO",
            "name": "Hub Sem Dado",
            "storeid": "V1",
            "status": "Active",
            "delivery_station": "DSP2",
            "latitude": "-23.55",
            "longitude": "-46.63",
            "volume cap": "",
            "radius": "",
        },
    ]
    csv_path = _make_partners_csv(tmp_path, rows)
    j_path = _make_empty_jurisdiction_geojson(tmp_path)

    data = load_partners_csv(str(csv_path), jurisdiction_path=str(j_path))
    df = data.partners_df
    by_sid = {r["salesforce_id"]: r for _, r in df.iterrows()}

    # (a) Zero explícito preservado.
    zero = by_sid["001ZEROCAP"]
    assert zero["capacity"] == 0, (
        f"capacity=0 no CSV deveria ser preservado, veio {zero['capacity']}"
    )
    assert zero["radius"] == 0, (
        f"radius=0 no CSV deveria ser preservado, veio {zero['radius']}"
    )

    # (b) Vazio cai no default.
    vazio = by_sid["001VAZIO"]
    assert vazio["capacity"] == 42
    assert vazio["radius"] == 1500
