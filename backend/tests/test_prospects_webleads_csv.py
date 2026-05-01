"""
Valida o carregamento dos CSVs de prospects e webleads (formato
simplificado de 13 colunas: id, cep, cidade, estado, jurisdiction_name,
latitude, longitude, name, ownerid, phone, recruitment_representative,
status, origem) e o merge com o partners.csv em um único PartnerData.

Cobre:
- ``load_prospects_csv`` força status="Prospect" e preserva `origem` em
  `lead_source`.
- ``load_webleads_csv`` força status="New" e lead_source="Website Pardot Form".
- ``load_partners_sources`` consolida os 3 CSVs corretamente:
    * partners + prospects → partners_df
    * webleads             → web_leads_df
    * prospects sem coords → no_coords_prospects_df
- Deduplicação por salesforce_id (primeiro vence).
- FileNotFoundError quando nenhum CSV está disponível.
- Tolerância a arquivos ausentes (usa só os que existem).
- Hierarquia BDM/CTL/ADE NÃO é lida do CSV (jurisdiction_name ignorado).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_COLS = [
    "id", "cep", "cidade", "estado", "jurisdiction_name",
    "latitude", "longitude", "name", "ownerid", "phone",
    "recruitment_representative", "status", "origem",
]

_PARTNERS_COLS = [
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


def _write_simple_csv(tmp_path: Path, name: str, rows: list[dict]) -> Path:
    """CSV de 13 colunas (prospects/webleads format)."""
    normalized = [{c: r.get(c, "") for c in _SIMPLE_COLS} for r in rows]
    df = pd.DataFrame(normalized, columns=_SIMPLE_COLS)
    path = tmp_path / name
    df.to_csv(path, index=False)
    return path


def _write_partners_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """CSV de parceiros no formato real (40 colunas)."""
    normalized = [{c: r.get(c, "") for c in _PARTNERS_COLS} for r in rows]
    df = pd.DataFrame(normalized, columns=_PARTNERS_COLS)
    path = tmp_path / "partners.csv"
    df.to_csv(path, index=False)
    return path


def _write_empty_jurisdiction(tmp_path: Path) -> Path:
    path = tmp_path / "jur.geojson"
    path.write_text(
        '{"type": "FeatureCollection", "features": []}',
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def _isolated_dest_folder(tmp_path, monkeypatch):
    """
    Redireciona Config.DEST_FOLDER (e shared.config.DEST_FOLDER) para um
    diretório temporário, evitando que os testes sobrescrevam o
    dados_mapa.json de produção. Também redireciona BASE_JURISDICTION
    para um GeoJSON vazio.
    """
    import shared.config as cfg
    from shared.models import Config

    dest = tmp_path / "output_data"
    dest.mkdir(exist_ok=True)
    jur = _write_empty_jurisdiction(tmp_path)

    monkeypatch.setattr(cfg, "DEST_FOLDER", dest)
    monkeypatch.setattr(cfg, "BASE_JURISDICTION", jur)
    monkeypatch.setattr(Config, "DEST_FOLDER", dest, raising=False)
    monkeypatch.setattr(Config, "BASE_JURISDICTION", jur, raising=False)
    yield


# ---------------------------------------------------------------------------
# load_prospects_csv
# ---------------------------------------------------------------------------

class TestLoadProspectsCsv:

    def test_forces_status_prospect(self, tmp_path):
        """Independente do valor em `status` no CSV, o resultado deve ser 'Prospect'."""
        from shared.load_partners import load_prospects_csv

        # status vem incorretamente como "Active" — deve ser ignorado e forçado a Prospect
        csv = _write_simple_csv(tmp_path, "prospects.csv", [
            {
                "id": "00Q001", "name": "Fulano 1",
                "latitude": "-23.5", "longitude": "-46.6",
                "status": "Active",   # será ignorado
                "origem": "Cold Call",
                "ownerid": "005XYZ",
            },
        ])

        df = load_prospects_csv(str(csv))
        assert len(df) == 1
        assert df.iloc[0]["status"] == "Prospect"
        assert df.iloc[0]["lead_source"] == "Cold Call"

    def test_preserves_origem_in_lead_source(self, tmp_path):
        """`origem` é preservado como `lead_source`; vazio vira None."""
        from shared.load_partners import load_prospects_csv

        csv = _write_simple_csv(tmp_path, "prospects.csv", [
            {"id": "00Q01", "name": "A", "latitude": "-23", "longitude": "-46",
             "status": "Prospect", "origem": "Website Pardot Form"},
            {"id": "00Q02", "name": "B", "latitude": "-23.1", "longitude": "-46.1",
             "status": "Prospect", "origem": ""},  # vazio → None
            {"id": "00Q03", "name": "C", "latitude": "-23.2", "longitude": "-46.2",
             "status": "Prospect", "origem": "Cold Call"},
        ])

        df = load_prospects_csv(str(csv))
        assert len(df) == 3
        sources = {row["salesforce_id"]: row["lead_source"] for _, row in df.iterrows()}
        assert sources["00Q01"] == "Website Pardot Form"
        assert pd.isna(sources["00Q02"]) or sources["00Q02"] is None
        assert sources["00Q03"] == "Cold Call"

    def test_keeps_empty_ownerid_as_none(self, tmp_path):
        """ownerid vazio é preservado como None — não é um bug, é dado real."""
        from shared.load_partners import load_prospects_csv

        csv = _write_simple_csv(tmp_path, "prospects.csv", [
            {"id": "00Q01", "name": "A", "latitude": "-23", "longitude": "-46",
             "status": "Prospect", "ownerid": ""},
            {"id": "00Q02", "name": "B", "latitude": "-23.1", "longitude": "-46.1",
             "status": "Prospect", "ownerid": "005XYZ"},
        ])

        df = load_prospects_csv(str(csv))
        owners = {r["salesforce_id"]: r["owner_id"] for _, r in df.iterrows()}
        assert pd.isna(owners["00Q01"]) or owners["00Q01"] is None
        assert owners["00Q02"] == "005XYZ"

    def test_handles_missing_coordinates(self, tmp_path):
        """Prospects sem lat/lon são mantidos no DataFrame (serão separados depois)."""
        from shared.load_partners import load_prospects_csv

        csv = _write_simple_csv(tmp_path, "prospects.csv", [
            {"id": "00Q01", "name": "Com coords", "latitude": "-23.5",
             "longitude": "-46.6", "status": "Prospect"},
            {"id": "00Q02", "name": "Sem coords", "latitude": "",
             "longitude": "", "status": "Prospect"},
        ])

        df = load_prospects_csv(str(csv))
        assert len(df) == 2
        # Partner.from_row converte "" → None para lat/lon
        no_coords = df[df["salesforce_id"] == "00Q02"].iloc[0]
        assert pd.isna(no_coords["lat"]) or no_coords["lat"] is None
        assert pd.isna(no_coords["lon"]) or no_coords["lon"] is None

    def test_returns_empty_when_file_missing(self, tmp_path):
        """Arquivo inexistente → DataFrame vazio (não levanta exceção)."""
        from shared.load_partners import load_prospects_csv
        df = load_prospects_csv(str(tmp_path / "does_not_exist.csv"))
        assert df.empty


# ---------------------------------------------------------------------------
# load_webleads_csv
# ---------------------------------------------------------------------------

class TestLoadWebleadsCsv:

    def test_forces_status_new_and_lead_source(self, tmp_path):
        """Todos os webleads recebem status=New e lead_source=Website Pardot Form."""
        from shared.load_partners import load_webleads_csv

        # origem vem como "Other" — deve ser sobrescrito
        csv = _write_simple_csv(tmp_path, "webleads.csv", [
            {"id": "00Q01", "name": "A", "latitude": "-3.7", "longitude": "-38.5",
             "status": "Converted", "origem": "Other"},
            {"id": "00Q02", "name": "B", "latitude": "-3.8", "longitude": "-38.6",
             "status": "New", "origem": "Website Pardot Form"},
        ])

        df = load_webleads_csv(str(csv))
        assert len(df) == 2
        assert (df["status"] == "New").all()
        assert (df["lead_source"] == "Website Pardot Form").all()

    def test_keeps_generic_ownerid(self, tmp_path):
        """ownerid genérico (ex: 005at000002GuY9AAK) é preservado."""
        from shared.load_partners import load_webleads_csv

        csv = _write_simple_csv(tmp_path, "webleads.csv", [
            {"id": "00Q01", "name": "A", "latitude": "-3.7", "longitude": "-38.5",
             "status": "New", "ownerid": "005at000002GuY9AAK"},
        ])

        df = load_webleads_csv(str(csv))
        assert df.iloc[0]["owner_id"] == "005at000002GuY9AAK"

    def test_returns_empty_when_file_missing(self, tmp_path):
        from shared.load_partners import load_webleads_csv
        df = load_webleads_csv(str(tmp_path / "missing.csv"))
        assert df.empty


# ---------------------------------------------------------------------------
# load_partners_sources (merge)
# ---------------------------------------------------------------------------

class TestLoadPartnersSources:

    def test_merges_three_sources(self, tmp_path):
        """Partners + Prospects → partners_df; Webleads → web_leads_df."""
        from shared.load_partners import load_partners_sources

        partners = _write_partners_csv(tmp_path, [
            {"id": "001A", "name": "Active Partner", "status": "Active",
             "latitude": "-23.5", "longitude": "-46.6",
             "delivery_station": "DBR9", "volume cap": "42", "radius": "1500",
             "storeid": "STORE_A"},
            {"id": "001I", "name": "Inactive Partner", "status": "Inactive",
             "latitude": "-23.4", "longitude": "-46.5",
             "delivery_station": "DBR9", "volume cap": "0", "radius": "0",
             "storeid": "STORE_I"},
        ])
        prospects = _write_simple_csv(tmp_path, "prospects.csv", [
            {"id": "00P01", "name": "Prospect 1", "latitude": "-23.55",
             "longitude": "-46.65", "status": "Prospect", "origem": "Cold Call"},
        ])
        webleads = _write_simple_csv(tmp_path, "webleads.csv", [
            {"id": "00W01", "name": "Weblead 1", "latitude": "-3.7",
             "longitude": "-38.5", "status": "New", "origem": "Website Pardot Form"},
        ])

        data = load_partners_sources(
            partners_csv=str(partners),
            prospects_csv=str(prospects),
            webleads_csv=str(webleads),
        )

        # partners_df: active + inactive + prospect
        statuses = set(data.partners_df["status"])
        assert {"Active", "Inactive", "Prospect"}.issubset(statuses)
        # web_leads_df: só o weblead
        assert len(data.web_leads_df) == 1
        assert data.web_leads_df.iloc[0]["salesforce_id"] == "00W01"

    def test_works_with_only_partners(self, tmp_path):
        """Deve funcionar se só existir partners.csv."""
        from shared.load_partners import load_partners_sources

        partners = _write_partners_csv(tmp_path, [
            {"id": "001A", "name": "X", "status": "Active",
             "latitude": "-23.5", "longitude": "-46.6",
             "delivery_station": "DBR9"},
        ])

        data = load_partners_sources(partners_csv=str(partners))
        assert len(data.partners_df) == 1
        assert data.web_leads_df.empty

    def test_works_with_only_webleads(self, tmp_path):
        """Deve funcionar se só existir webleads.csv."""
        from shared.load_partners import load_partners_sources

        webleads = _write_simple_csv(tmp_path, "webleads.csv", [
            {"id": "00W01", "name": "X", "latitude": "-3.7",
             "longitude": "-38.5", "status": "New"},
        ])

        data = load_partners_sources(webleads_csv=str(webleads))
        assert data.partners_df.empty
        assert len(data.web_leads_df) == 1

    def test_skips_missing_sources(self, tmp_path):
        """Caminhos inexistentes são ignorados silenciosamente."""
        from shared.load_partners import load_partners_sources

        partners = _write_partners_csv(tmp_path, [
            {"id": "001A", "name": "X", "status": "Active",
             "latitude": "-23.5", "longitude": "-46.6",
             "delivery_station": "DBR9"},
        ])

        data = load_partners_sources(
            partners_csv=str(partners),
            prospects_csv=str(tmp_path / "nope1.csv"),
            webleads_csv=str(tmp_path / "nope2.csv"),
        )
        assert len(data.partners_df) == 1

    def test_raises_when_all_missing(self, tmp_path):
        """Sem nenhum CSV disponível, levanta FileNotFoundError."""
        from shared.load_partners import load_partners_sources

        with pytest.raises(FileNotFoundError):
            load_partners_sources(
                partners_csv=str(tmp_path / "a.csv"),
                prospects_csv=str(tmp_path / "b.csv"),
                webleads_csv=str(tmp_path / "c.csv"),
            )

    def test_deduplicates_by_salesforce_id(self, tmp_path):
        """Id que aparece em mais de um CSV → primeiro registro vence."""
        from shared.load_partners import load_partners_sources

        # Mesmo id em partners e prospects — deve prevalecer a versão "Active"
        partners = _write_partners_csv(tmp_path, [
            {"id": "DUP_ID", "name": "Active Version", "status": "Active",
             "latitude": "-23.5", "longitude": "-46.6",
             "delivery_station": "DBR9"},
        ])
        prospects = _write_simple_csv(tmp_path, "prospects.csv", [
            {"id": "DUP_ID", "name": "Prospect Version", "latitude": "-23.5",
             "longitude": "-46.6", "status": "Prospect"},
        ])

        data = load_partners_sources(
            partners_csv=str(partners),
            prospects_csv=str(prospects),
        )
        assert len(data.partners_df) == 1
        assert data.partners_df.iloc[0]["status"] == "Active"
        # _build_partner_data renames `name` → `partner_name`
        assert data.partners_df.iloc[0]["partner_name"] == "Active Version"

    def test_jurisdiction_name_from_csv_is_ignored(self, tmp_path):
        """
        Conforme correção explícita do usuário: a hierarquia de CTL/ADE/BDM
        e a jurisdição vêm do TEAM e do GeoJSON, NÃO do CSV.
        O campo `jurisdiction_name` do CSV de prospects/webleads não deve
        poluir o campo `bucket` do Partner — esse vem resolvido em fase
        posterior a partir do GeoJSON.
        """
        from shared.load_partners import load_prospects_csv

        csv = _write_simple_csv(tmp_path, "prospects.csv", [
            {"id": "00P01", "name": "X", "latitude": "-23.5",
             "longitude": "-46.6", "status": "Prospect",
             "jurisdiction_name": "DEVE_SER_IGNORADO"},
        ])

        df = load_prospects_csv(str(csv))
        # jurisdiction_name do CSV simplificado não é mapeado para "Bucket"
        # (o rename map não inclui essa chave). Portanto bucket fica None.
        val = df.iloc[0]["bucket"]
        assert pd.isna(val) or val is None
