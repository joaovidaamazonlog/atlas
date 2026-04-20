"""
geo_orchestrator.py
===================
Ponto de entrada do pipeline GeoIntelligence.

Modos de operação
-----------------
--mode setup --target <pct>
    Executa as 3 fases do pipeline GeoIntelligence:
      Fase 1: Area Intelligence (enriquecimento H3 + classificação + potential score)
      Fase 2: Ideal Supply (CP-SAT)
      Fase 3: Territory Fit (matching)

--update-heatmap
    Regenera o heatmap GeoIntelligence com a base de pacotes atual
    sem refazer o setup completo (sem re-rodar enrichers, classifier ou CP-SAT).

Exemplos:
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2
  python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2 DSP4
  python geo_intelligence/geo_orchestrator.py --update-heatmap
  python geo_intelligence/geo_orchestrator.py --update-heatmap --stations DSP2
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


def run_update_geo_heatmap(
    output_dir: str,
    stations: Optional[List[str]] = None,
) -> None:
    """Regenera o heatmap GeoIntelligence sem refazer o setup completo."""
    from geo_intelligence.geo_heatmap import run_update_geo_heatmap as _run
    _run(output_dir=output_dir, stations=stations)


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
    from geo_intelligence.turso_writer import TursoWriter
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
    writer = TursoWriter(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    writer.ensure_schema()

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
                status="completed",
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
    """Executa o matching diário GeoIntelligence para cada base.

    Carrega parceiros reais via load_partners(), busca os slots do setup
    mais recente no Turso e executa o matching com hierarquia completa de
    fallback (hex exato → point-in-polygon → centroide polígono → centroide slots).
    Persiste attainment/accuracy e matched_partner_id no Turso.
    """
    import json
    import os
    from pathlib import Path
    from geo_intelligence.geo_config import TURSO_URL, TURSO_AUTH_TOKEN
    from geo_intelligence.turso_reader import TursoReader
    from geo_intelligence.turso_writer import TursoWriter
    from geo_intelligence.geo_daily import run_daily as _run_daily

    # Resolve caminhos via shared.config
    _backend_dir = Path(__file__).parent.parent
    from shared.config import DEST_FOLDER as _DEST_FOLDER
    from shared.load_partners import load_partners
    dest = _DEST_FOLDER
    territories_geojson_path = str(dest / "territories.geojson")
    territories_index_path   = str(dest / "territories_index.json")

    print(f"\n{'#'*60}")
    print(f"  GEO-INTELLIGENCE — MODO DAILY")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    # Carrega parceiros reais
    partner_data = load_partners()

    # Carrega territories_index para fallback de centroide
    territories_index: dict = {}
    if os.path.exists(territories_index_path):
        with open(territories_index_path, encoding="utf-8") as f:
            territories_index = json.load(f)

    reader = TursoReader(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    writer = TursoWriter(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)

    # Descobre bases a processar
    station_list = stations or list({
        meta.get("station_code") for meta in territories_index.values()
        if meta.get("station_code")
    })

    for station_code in sorted(station_list):
        run_id = reader.get_latest_run_id(station_code)
        if not run_id:
            print(f"  [{station_code}] Nenhum run de setup encontrado — execute --mode setup primeiro.")
            continue

        slots = reader.get_ideal_supply(station_code, run_id)
        if not slots:
            print(f"  [{station_code}] Nenhum slot encontrado para run_id={run_id}.")
            continue

        print(f"\n  [{station_code}] run_id={run_id} | slots={len(slots)}")

        daily_result = _run_daily(
            station_code=station_code,
            run_id=run_id,
            partner_data=partner_data,
            slots=slots,
            territories_geojson_path=territories_geojson_path,
            territories_index=territories_index,
        )

        # Fase 3.5 — Cap Optimization (GeoIntelligence)
        try:
            from geo_intelligence.geo_phase3_5_cap_optimizer import run_geo_phase3_5
            n_opportunities = run_geo_phase3_5(
                daily_result=daily_result,
                run_id=run_id,
                station_code=station_code,
                writer=writer,
                reader=reader,
            )
            logger.info(
                "[%s] Fase 3.5 Geo: %d oportunidades identificadas em %d parceiros avaliados.",
                station_code,
                n_opportunities,
                len([m for m in daily_result.matched + daily_result.unmatched
                     if m.status == "Active"]),
            )
        except Exception as exc:
            logger.error("[%s] Fase 3.5 Geo falhou (pipeline continua): %s", station_code, exc)

        # Persiste matched_partner_id
        matches = [
            {"supply_id": m.matched_slot_id, "partner_id": m.partner_id}
            for m in daily_result.matched
            if m.matched_slot_id
        ]
        if matches:
            writer.update_supply_match(run_id, matches)

        # Persiste attainment/accuracy por território
        fits = [
            {"territory_id": t.territory_id, "attainment": round(t.attainment, 1), "accuracy": round(t.accuracy, 1)}
            for t in daily_result.territories.values()
        ]
        if fits:
            writer.update_territory_fit(run_id, fits)

        print(
            f"  [{station_code}] matched={len(daily_result.matched)} "
            f"unmatched={len(daily_result.unmatched)} "
            f"territórios={len(daily_result.territories)}"
        )

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
  python geo_intelligence/geo_orchestrator.py --update-heatmap
  python geo_intelligence/geo_orchestrator.py --update-heatmap --stations DSP2
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
        "--update-heatmap",
        action="store_true",
        default=False,
        help="Regenera o heatmap GeoIntelligence com a base de pacotes atual "
             "sem refazer o setup completo.",
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
        if args.update_heatmap:
            run_update_geo_heatmap(
                output_dir=args.output,
                stations=args.stations,
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
                "  Especifique --mode setup --target <pct>, --mode daily ou --update-heatmap.",
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
