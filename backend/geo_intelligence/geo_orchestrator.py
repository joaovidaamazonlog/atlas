"""
geo_orchestrator.py
===================
Ponto de entrada do pipeline GeoIntelligence.

Modos de operação
-----------------
--mode setup --target <pct>
    Executa as fases 1+2 do pipeline GeoIntelligence:
      Fase 1: Area Intelligence (enriquecimento H3 + classificação + potential score)
      Fase 2: Ideal Supply (CP-SAT)
    Persiste resultados no SQLite local.

--mode daily
    Executa o pipeline diário completo:
      Fase 3: Matching parceiros × vagas (vanilla)
      Fase 4: Qualificação de webleads (vanilla)
      Fase 5: Relatórios + heatmap.geojson + dados_mapa.json (vanilla)
    Lê territories e ideal supply do SQLite local.
    Para atualizar o heatmap, basta rodar --mode daily.

--sync-empresas
    Sincroniza a tabela empresas_alvo do Turso para o SQLite local.

Exemplos:
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2 DSP4
  python geo_intelligence/geo_orchestrator.py --mode daily
  python geo_intelligence/geo_orchestrator.py --mode daily --stations DSP2
  python geo_intelligence/geo_orchestrator.py --sync-empresas
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
import uuid
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _selected_territories_to_territories_result(
    selected_territories: list,
    station_code: str,
    territories_geojson_path: str | None = None,
    demand_map: dict | None = None,
    pkg_days: int = 30,
) -> "TerritoriesResult":
    """
    Converts Phase 1 SelectedTerritory list to TerritoriesResult for vanilla Phase 3.
    """
    import h3
    from pathlib import Path
    from shared.models import Config, TerritoriesResult

    territory_index: dict = {}
    hex_to_territory: dict = {}

    for territory in selected_territories:
        territory_id = territory.territory_id
        h3_ids = territory.h3_ids_r8

        # Compute centroid from h3 cells
        if h3_ids:
            latlngs = [h3.cell_to_latlng(h) for h in h3_ids]
            centroid_lat = sum(ll[0] for ll in latlngs) / len(latlngs)
            centroid_lon = sum(ll[1] for ll in latlngs) / len(latlngs)
        else:
            centroid_lat = 0.0
            centroid_lon = 0.0

        # Compute daily demand from demand_map
        dm = demand_map or {}
        daily_demand = sum(dm.get(h, 0) for h in h3_ids) / pkg_days

        territory_index[territory_id] = {
            "station_code": station_code,
            "hex_ids": h3_ids,
            "potential_score": territory.potential_score,
            "gap": territory.gap,
            "region_type": (
                territory.region_type.value
                if hasattr(territory.region_type, "value")
                else territory.region_type
            ),
            "model_confidence": getattr(territory, "model_confidence", None),
            "high_opportunity": getattr(territory, "high_opportunity", False),
            "bdm_cluster": Config.get_bdm_cluster(station_code),
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "daily_demand": daily_demand,
        }

        for h3_id in h3_ids:
            hex_to_territory[h3_id] = territory_id

    result = TerritoriesResult(
        territory_index=territory_index,
        hex_to_territory=hex_to_territory,
    )

    if territories_geojson_path:
        from pathlib import Path as _Path
        p = _Path(territories_geojson_path)
        if p.exists():
            result.geojson_path = p

    return result


def _sqlite_rows_to_ideal_supply_result(supply_rows: list) -> "IdealSupplyResult":
    """
    Converts geo_ideal_supply SQLite rows to IdealSupplyResult for vanilla Phase 3.
    """
    import h3
    from vanilla.phase2_ideal_supply import IdealSupplyResult
    from shared.models import IdealSlot

    slots_by_territory: dict = {}

    for row in supply_rows:
        slot_id = row["supply_id"]
        bucket_id = row["territory_id"]
        station_code = row["station_code"]
        lat = row["lat"]
        lon = row["lon"]

        radius_km = row.get("radius_km")
        if radius_km is None:
            logger.warning(
                "[_sqlite_rows_to_ideal_supply_result] radius_km ausente para slot %s — usando 1.5",
                slot_id,
            )
            radius_km = 1.5
        radius_s = int(radius_km * 1000)

        capacity_s = row.get("capacity_day")
        if capacity_s is None:
            logger.warning(
                "[_sqlite_rows_to_ideal_supply_result] capacity_day ausente para slot %s — usando 42",
                slot_id,
            )
            capacity_s = 42

        origin_hex = row.get("origin_hex")
        if origin_hex is None:
            logger.warning(
                "[_sqlite_rows_to_ideal_supply_result] origin_hex ausente para slot %s — calculando via h3",
                slot_id,
            )
            origin_hex = h3.latlng_to_cell(lat, lon, 9)

        slot = IdealSlot(
            slot_id=slot_id,
            bucket_id=bucket_id,
            station_code=station_code,
            lat=lat,
            lon=lon,
            radius_s=radius_s,
            capacity_s=capacity_s,
            origin_hex=origin_hex,
            allocations=[],
        )

        if bucket_id not in slots_by_territory:
            slots_by_territory[bucket_id] = []
        slots_by_territory[bucket_id].append(slot)

    return IdealSupplyResult(slots_by_territory=slots_by_territory)


# ---------------------------------------------------------------------------
# Helper: convert SQLite geo_territories rows to SelectedTerritory-like objects
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass, field as _field
import json as _json


@_dataclass
class _TerritoryRow:
    """Lightweight SelectedTerritory-like object built from SQLite geo_territories rows."""
    territory_id: str
    h3_ids_r8: list
    potential_score: float
    gap: float
    region_type: str
    model_confidence: Optional[float]
    high_opportunity: bool


def _territory_rows_to_selected(rows: list) -> list:
    """
    Converts SQLite geo_territories rows into _TerritoryRow objects
    compatible with _selected_territories_to_territories_result.
    """
    result = []
    for row in rows:
        h3_ids_raw = row.get("h3_ids_json", "[]")
        if isinstance(h3_ids_raw, str):
            try:
                h3_ids = _json.loads(h3_ids_raw)
            except Exception:
                h3_ids = []
        else:
            h3_ids = list(h3_ids_raw) if h3_ids_raw else []

        result.append(_TerritoryRow(
            territory_id=row["territory_id"],
            h3_ids_r8=h3_ids,
            potential_score=row.get("potential_score", 0.0),
            gap=row.get("gap", 0.0),
            region_type=row.get("region_type", ""),
            model_confidence=row.get("model_confidence"),
            high_opportunity=bool(row.get("high_opportunity", 0)),
        ))
    return result


# ---------------------------------------------------------------------------
# Modo setup
# ---------------------------------------------------------------------------

def run_setup(
    target_pct: float,
    output_dir: str,
    stations: Optional[List[str]] = None,
    max_workers: int = 4,
) -> None:
    """Executa as 2 fases do pipeline GeoIntelligence para cada base listada.

    Fase 1: Area Intelligence (H3 + enrichers + classifier)
    Fase 2: Ideal Supply (CP-SAT) → persiste no Turso

    O matching com parceiros reais é feito pelo modo daily (--mode daily).
    """
    import json
    import os
    from pathlib import Path
    import pandas as pd
    from geo_intelligence.geo_config import TURSO_URL, TURSO_AUTH_TOKEN
    from geo_intelligence.phase1_area_intelligence import run_area_intelligence
    from geo_intelligence.phase2_ideal_supply import run_phase2
    from geo_intelligence.local_writer import LocalWriter
    from geo_intelligence.pipeline import build_run_metadata, territories_to_geojson

    print(f"\n{'#'*60}")
    print(f"  GEO-INTELLIGENCE — MODO SETUP")
    print(f"  Target: {target_pct}%  |  Output: {output_dir}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"  Workers: {max_workers}")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    station_list = stations or _discover_stations(output_dir)
    writer = LocalWriter()

    # Load shared data — importa diretamente do módulo shared
    _backend_dir = Path(__file__).parent.parent
    from shared.config import BASE_PACKAGES as _BASE_PACKAGES, DEST_FOLDER as _DEST_FOLDER
    packages_path = str(_BASE_PACKAGES)
    territories_geojson_path = str(_DEST_FOLDER / "territories.geojson")
    territories_index_path = str(_DEST_FOLDER / "territories_index.json")

    print(f"  Pacotes: {packages_path} (existe: {os.path.exists(packages_path)})")
    print(f"  Territórios: {territories_geojson_path} (existe: {os.path.exists(territories_geojson_path)})")

    packages_df = pd.read_csv(packages_path) if os.path.exists(packages_path) else pd.DataFrame()

    # Normaliza nomes de colunas para lat/lng (o ingestor espera lat e lng)
    if not packages_df.empty:
        col_map = {}
        for col in packages_df.columns:
            if col.lower() == "latitude":
                col_map[col] = "lat"
            elif col.lower() == "longitude":
                col_map[col] = "lng"
        if col_map:
            packages_df = packages_df.rename(columns=col_map)
        print(f"  Pacotes carregados: {len(packages_df):,} linhas | colunas: {list(packages_df.columns)}")
    territories_index = {}
    if os.path.exists(territories_index_path):
        with open(territories_index_path) as f:
            territories_index = json.load(f)

    for station_code in station_list:
        run_id = f"{station_code}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        from geo_intelligence.pipeline import GeoSetupConfig
        from geo_intelligence.geo_config import POTENTIAL_WEIGHTS
        config = GeoSetupConfig(station_code=station_code, expansion_target_pct=target_pct, potential_weights=POTENTIAL_WEIGHTS)
        writer.upsert_run(run_id, config)

        print(f"\n  [{station_code}] Iniciando pipeline GeoIntelligence (run_id={run_id})...")
        ts_start = datetime.now(timezone.utc).isoformat()

        try:
            # Fase 1
            station_territories = {k: v for k, v in territories_index.items() if v.get("station_code") == station_code}
            selected_territories, phase1_metrics = run_area_intelligence(
                station_code=station_code,
                target_pct=target_pct,
                packages_df=packages_df,
                territories_geojson_path=territories_geojson_path,
                territories_index=station_territories,
                turso_url=TURSO_URL,
                turso_auth_token=TURSO_AUTH_TOKEN,
            )

            # Fase 2
            demand_map = {}
            if not packages_df.empty and "lat" in packages_df.columns:
                import h3 as _h3
                for _, row in packages_df.iterrows():
                    try:
                        h3_id = _h3.latlng_to_cell(float(row["lat"]), float(row["lng"]), 9)
                        demand_map[h3_id] = demand_map.get(h3_id, 0) + 1
                    except Exception:
                        pass

            ideal_supply = run_phase2(
                geo_territories=selected_territories,
                demand_map=demand_map,
                station_code=station_code,
                max_workers=max_workers,
            )

            # Persiste slots no Turso (sem matching — daily faz isso)
            supply_points = [
                {"supply_id": slot.slot_id, "territory_id": slot.territory_id,
                 "station_code": station_code, "lat": slot.lat, "lon": slot.lon,
                 "radius_km": slot.radius_s / 1000.0, "capacity_day": slot.capacity_s,
                 "origin_hex": slot.origin_hex}
                for slots in ideal_supply.values() for slot in slots
            ]
            writer.upsert_ideal_supply(run_id, supply_points)

            clf_metrics = phase1_metrics.get("classifier", {})
            metadata = build_run_metadata(
                run_id=run_id,
                station_code=station_code,
                expansion_target_pct=target_pct,
                timestamp_start=ts_start,
                n_h3_cells=phase1_metrics.get("n_h3_cells"),
                n_territories=len(selected_territories),
                clustering_algorithm=clf_metrics.get("algorithm"),
                silhouette_score=clf_metrics.get("silhouette_score"),
                status="setup_complete",
            )
            writer.finalize_run(run_id, metadata)
            print(f"  [{station_code}] Pipeline concluído. {len(selected_territories)} territórios selecionados.")

        except Exception as exc:
            logger.error("[%s] Pipeline falhou: %s", station_code, exc)
            traceback.print_exc()
            from geo_intelligence.pipeline import RunMetadata
            from datetime import timezone as _tz
            writer.finalize_run(run_id, RunMetadata(
                run_id=run_id, station_code=station_code, expansion_target_pct=target_pct,
                timestamp_start=ts_start, timestamp_end=datetime.now(_tz.utc).isoformat(),
                n_h3_cells=None, n_territories=None, clustering_algorithm=None,
                silhouette_score=None, supervised_model=None, supervised_f1_macro=None,
                is_optimal=None, solver_status=None, status="failed",
            ))

    print(f"\n{'#'*60}")
    print(f"  SETUP CONCLUÍDO — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}\n")


def _discover_stations(output_dir: str) -> List[str]:
    """Descobre bases disponíveis no diretório de output (stub)."""
    # Será implementado quando o ingestor estiver disponível.
    return []


# ---------------------------------------------------------------------------
# Modo daily
# ---------------------------------------------------------------------------

def run_daily(
    output_dir: str,
    stations: Optional[List[str]] = None,
) -> None:
    """
    Executa o pipeline diário GeoIntelligence:
    - Lê territories e ideal supply do SQLite local (via LocalReader)
    - Converte para TerritoriesResult e IdealSupplyResult
    - Chama run_phase3 → run_phase4 → run_phase5 (vanilla, sem modificação)
    - Persiste matched_partner_id e attainment/accuracy no SQLite local
    """
    import json
    import os
    from pathlib import Path
    from geo_intelligence.local_reader import LocalReader
    from geo_intelligence.local_writer import LocalWriter
    from shared.config import DEST_FOLDER as _DEST_FOLDER
    from shared.load_partners import load_partners
    from shared.load_packages import load_packages
    from vanilla.phase3_partner_fit import run_phase3
    from vanilla.phase4_webleads import run_phase4
    from vanilla.phase5_reports import run_phase5

    dest = _DEST_FOLDER
    territories_geojson_path = str(dest / "territories.geojson")
    territories_index_path = str(dest / "territories_index.json")

    print(f"\n{'#'*60}")
    print(f"  GEO-INTELLIGENCE — MODO DAILY")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    reader = LocalReader()
    writer = LocalWriter()

    # Discover stations from territories_index if not provided
    territories_index: dict = {}
    if os.path.exists(territories_index_path):
        with open(territories_index_path, encoding="utf-8") as f:
            territories_index = json.load(f)

    station_list = stations or list({
        meta.get("station_code") for meta in territories_index.values()
        if meta.get("station_code")
    })

    # Load shared data once
    partner_data = load_partners()
    pkg = load_packages()

    for station_code in sorted(station_list):
        run_id = reader.get_latest_run_id(station_code)
        if not run_id:
            print(f"  [{station_code}] Nenhum run de setup encontrado — execute --mode setup primeiro.")
            continue

        supply_rows = reader.get_ideal_supply(station_code, run_id)
        if not supply_rows:
            print(f"  [{station_code}] Nenhum slot encontrado para run_id={run_id}.")
            continue

        territory_rows = reader.get_territories(station_code, run_id)
        print(f"\n  [{station_code}] run_id={run_id} | slots={len(supply_rows)} | territórios={len(territory_rows)}")

        # Convert to vanilla types
        # For territories, build SelectedTerritory-like objects from SQLite rows
        selected_territories = _territory_rows_to_selected(territory_rows)
        territories = _selected_territories_to_territories_result(
            selected_territories,
            station_code,
            territories_geojson_path=territories_geojson_path,
            demand_map=None,
            pkg_days=pkg.days if pkg else 30,
        )
        supply = _sqlite_rows_to_ideal_supply_result(supply_rows)

        # Phase 3: matching
        fit = run_phase3(
            territories=territories,
            supply=supply,
            partner_data=partner_data,
            pkg=pkg,
            output_dir=output_dir,
            stations=[station_code],
        )

        # Persist matched_partner_id and territory fit to SQLite
        matches = [
            {"supply_id": p.matched_slot_id, "partner_id": p.salesforce_id}
            for p in fit.all_partners()
            if p.matched_slot_id and p.salesforce_id
        ]
        if matches:
            writer.update_supply_match(run_id, matches)

        fits = [
            {"territory_id": tid, "attainment": round(t.attainment, 1), "accuracy": round(t.accuracy, 1)}
            for tid, t in fit.territories.items()
        ]
        if fits:
            writer.update_territory_fit(run_id, fits)

        # Phase 4: webleads
        webleads = run_phase4(
            partner_data=partner_data,
            territories=territories,
            pkg=pkg,
        )

        # Phase 5: reports + heatmap enrichment
        run_phase5(
            territories=territories,
            supply=supply,
            fit=fit,
            webleads=webleads,
            pkg=pkg,
            output_dir=output_dir,
            stations=[station_code],
        )

        print(f"  [{station_code}] Daily concluído.")

    print(f"\n{'#'*60}")
    print(f"  DAILY CONCLUÍDO — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline GeoIntelligence — expansão logística baseada em dados territoriais",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2 DSP4
  python geo_intelligence/geo_orchestrator.py --mode daily
  python geo_intelligence/geo_orchestrator.py --mode daily --stations DSP2
  python geo_intelligence/geo_orchestrator.py --sync-empresas
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "daily"],
        required=False,
        default="setup",
        help="setup: fases 1+2 (territórios e slots ideais). daily: matching com parceiros reais. Default: setup.",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=None,
        help="Percentual de share alvo para expansão (ex: 50 para 50%%). Obrigatório com --mode setup.",
    )
    parser.add_argument(
        "--stations",
        nargs="+",
        default=None,
        help="Processar apenas as bases listadas (ex: DSP2 DSP4).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Número de workers paralelos para o solver CP-SAT. Default: 4.",
    )
    parser.add_argument(
        "--sync-empresas",
        action="store_true",
        default=False,
        help="Sincroniza a tabela empresas_alvo do Turso para o SQLite local. "
             "Não requer --mode. Exemplo: python geo_intelligence/geo_orchestrator.py --sync-empresas",
    )
    parser.add_argument(
        "--output",
        default="output/geo_intelligence",
        help="Pasta de saída. Default: output/geo_intelligence",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        if args.sync_empresas:
            from geo_intelligence.geo_config import TURSO_URL, TURSO_AUTH_TOKEN
            from geo_intelligence.local_writer import LocalWriter
            from geo_intelligence.turso_http import TursoHTTP
            from geo_intelligence.etl_geocode_empresas import sync_empresas_alvo

            if not TURSO_URL or not TURSO_AUTH_TOKEN:
                print(
                    "  ERRO: TURSO_URL e TURSO_AUTH_TOKEN devem estar configurados para --sync-empresas.",
                    file=sys.stderr,
                )
                sys.exit(1)

            try:
                turso_client = TursoHTTP(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
            except Exception as exc:
                print(f"  ERRO: Falha ao conectar ao Turso: {exc}", file=sys.stderr)
                sys.exit(1)

            writer = LocalWriter()
            try:
                summary = sync_empresas_alvo(writer, turso_client)
            except Exception as exc:
                print(f"  ERRO: Falha ao sincronizar empresas_alvo: {exc}", file=sys.stderr)
                sys.exit(1)

            print(
                f"  sync-empresas concluído: "
                f"inserted={summary['inserted']} "
                f"updated={summary['updated']} "
                f"total={summary['total']}"
            )

        elif args.mode == "setup":
            if args.target is None:
                print("  ERRO: --target é obrigatório com --mode setup.", file=sys.stderr)
                sys.exit(1)
            run_setup(
                target_pct=args.target,
                output_dir=args.output,
                stations=args.stations,
                max_workers=args.workers,
            )
        elif args.mode == "daily":
            run_daily(
                output_dir=args.output,
                stations=args.stations,
            )
        else:
            print(
                "  Especifique --mode setup --target <pct>, --mode daily ou --sync-empresas.",
                file=sys.stderr,
            )
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"\n  ERRO: {e}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Interrompido pelo usuário.", file=sys.stderr)
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
