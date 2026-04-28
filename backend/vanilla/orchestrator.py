"""
orchestrator.py
===============
Ponto de entrada do sistema de otimizacao de parceiros logisticos.

Dois modos de operacao
-----------------------
--mode setup    (roda uma vez / re-territorializacao)
    Fase 1: Formacao de territorios        -> territories.geojson
                                              territories_index.json
    Fase 2: Identificacao de vagas ideais  -> ideal_supply.json

--mode daily    (roda todo dia / base de pacotes atualizada)
    0. Lê Excel (Salesforce) via load_partners() → dados_mapa.json
    Fase 3: Matching parceiros x vagas     -> ideal_supply.json (atualizado)
    Fase 4: Qualificacao de webleads
    Fase 5: Relatorios + enriquece dados_mapa.json e heatmap.geojson
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from shared.load_packages import load_packages
from shared.load_partners import load_partners, load_partners_csv
from shared.models import Config
from shared.timing import PhaseTimer, TimingReport
from vanilla.phase_setup import run_setup as _run_setup_new, update_territories_geojson, rebuild_territory_polygons, patch_heatmap_satellite_stations, patch_heatmap_add_satellite_hexes
from shared.models import Config, TerritoriesResult, load_territories
from vanilla.phase2_ideal_supply import IdealSupplyResult, load_ideal_supply
from vanilla.phase3_partner_fit import FitResult, run_phase3
from vanilla.phase4_webleads import WebleadResult, run_phase4
from vanilla.phase5_reports import run_phase5
from vanilla.cnpj_lookup import run_cnpj_lookup, CnpjLookupResult


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _load_jurisdiction_geojson() -> Optional[dict]:
    """Carrega o GeoJSON de jurisdições. Retorna None em caso de falha."""
    import json
    try:
        with open(Config.BASE_JURISDICTION, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARN jurisdição não carregada ({e}) — atribuição de hexes usará apenas volume.")


# ---------------------------------------------------------------------------
# MODO SETUP
# ---------------------------------------------------------------------------

def run_setup(
    output_dir: str,
    stations: Optional[List[str]] = None,
    max_workers: int = 4,
) -> None:
    """
    Setup: solver por base → clustering de slots → territórios via BFS.

    Gera territories_index.json, territories.geojson e ideal_supply.json.
    Deve ser rodado manualmente ou ao expandir/reorganizar a rede.
    """
    print(f"\n{'#'*60}")
    print(f"  MODO SETUP (slots-first)")
    print(f"  Output: {output_dir}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    jur_geojson = _load_jurisdiction_geojson()

    # Identificar satélites em --stations para suprimir remap em load_packages
    from shared.config import STATION_ALIASES
    satellite_setup_stations = None
    if stations:
        sat_in_request = {s for s in stations if s in STATION_ALIASES}
        if sat_in_request:
            satellite_setup_stations = sat_in_request
            print(f"  Satélites em modo setup independente: {sorted(sat_in_request)}")

    pkg = load_packages(
        jurisdiction_geojson=jur_geojson,
        satellite_setup_stations=satellite_setup_stations,
    )

    territories, supply = _run_setup_new(
        pkg=pkg,
        output_dir=output_dir,
        stations=stations,
        max_workers=max_workers,
    )

    print(f"\n{'#'*60}")
    print(f"  SETUP CONCLUÍDO")
    print(f"  {len(territories.territory_index)} territórios")
    print(f"  {len(supply.all_slots)} slots ideais")
    print(f"  Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}\n")


# ---------------------------------------------------------------------------
# MODO DAILY
# ---------------------------------------------------------------------------

def run_daily(
    output_dir: str,
    stations: Optional[List[str]] = None,
    legacy_bucket_names: bool = False,
    partner_csv: Optional[str] = None,
    timing_report: Optional[TimingReport] = None,
    _disable_optimizations: bool = False,
) -> TimingReport:
    """
    Pipeline diário completo:
    1. Lê Excel (Salesforce) → serializa dados_mapa.json
       (ou CSV via --partnerCSV)
    2. Fases 3/4/5: matching, webleads, relatórios
    3. Enriquece dados_mapa.json com hex_coverage (Active/Onboarding)
    4. Enriquece heatmap.geojson com covering_partners e demand_residual

    Parâmetros
    ----------
    partner_csv : caminho para um CSV exportado do Salesforce.
                  Se fornecido, substitui a leitura do Excel (terra.xlsm).
                  Equivalente a passar ``--partnerCSV`` na CLI.
    timing_report : `TimingReport` opcional para coletar métricas de tempo
                  por fase. Se None, um novo `TimingReport(pipeline="daily")`
                  é criado internamente. O relatório é persistido em
                  ``<output_dir>/timing_report.json`` ao final da execução.
    _disable_optimizations : uso interno em testes de `Output_Equivalence`.
                  Quando True, as otimizações de performance (H3 cache,
                  vetorização, consolidação de replace) são contornadas
                  quando possível, para permitir comparação pareada com
                  a versão de referência no mesmo processo. Não exposta
                  via CLI.

    Retorna
    -------
    TimingReport : o relatório com tempos por fase, acessível programaticamente
                   por testes (ex.: ``report.phase("phase3_partner_fit").duration_s``).

    Deve ser rodado sempre que a base de pacotes ou os dados do Salesforce
    forem atualizados — garante que dados_mapa.json e heatmap.geojson
    estejam sempre em sincronia com as alocações do CP-SAT.
    """
    print(f"\n{'#'*60}")
    print(f"  MODO DAILY")
    print(f"  Output: {output_dir}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    report = timing_report or TimingReport(pipeline="daily")
    timer = PhaseTimer(report)
    timer.start_pipeline()

    # Carregar artefatos do setup (aborta se nao existirem)
    with timer.phase("load_territories_and_supply"):
        territories = load_territories(output_dir)
        supply      = load_ideal_supply(output_dir)

        # Filtrar bases se necessario
        if stations:
            from shared.config import STATION_ALIASES

            # Resolver canônicas solicitadas: --stations XBA1 equivale a solicitar
            # DSA8; --stations DSA8 inclui automaticamente XBA1_* (remapeado).
            canonical_requested = set()
            for s in stations:
                canonical_requested.add(STATION_ALIASES.get(s, s))

            # territories.territory_index já foi remapeado em memória para
            # canônica por load_territories; filtrar direto sobre station_code.
            all_tids = [
                tid for tid, meta in territories.territory_index.items()
                if meta["station_code"] in canonical_requested
            ]
            # Manter também territórios cujo canonical_base foi solicitado
            # (cobre casos de arquivos novos com canonical_base explícito).
            for tid, meta in territories.territory_index.items():
                canonical = meta.get("canonical_base")
                if canonical and canonical in canonical_requested and tid not in all_tids:
                    all_tids.append(tid)

            territories.hex_to_territory = {
                h: tid for h, tid in territories.hex_to_territory.items()
                if tid in all_tids
            }

    # Carregar parceiros e jurisdicoes (sempre frescos)
    jur_geojson = _load_jurisdiction_geojson()

    with timer.phase("load_packages"):
        pkg = load_packages(jurisdiction_geojson=jur_geojson)

    with timer.phase("load_partners"):
        if partner_csv:
            partner_data = load_partners_csv(partner_csv)
        else:
            partner_data = load_partners()

    # Fase 3: matching
    with timer.phase("phase3_partner_fit"):
        fit = run_phase3(
            territories=territories,
            supply=supply,
            partner_data=partner_data,
            pkg=pkg,
            output_dir=output_dir,
            stations=stations,
        )

        territory_stats = {
            tid: {
                "attainment": round(t_fit.attainment, 1),
                "accuracy": round(t_fit.accuracy, 1),
            } for tid, t_fit in fit.territories.items()
        }

        update_territories_geojson(output_dir=output_dir, territory_stats=territory_stats)

        # Reconstruir polígonos a partir dos hexágonos H3 reais (pós-matching)
        rebuild_territory_polygons(output_dir=output_dir, stations=stations)

        # Corrigir delivery_station de hexes satélite no heatmap (idempotente)
        patch_heatmap_satellite_stations(output_dir=output_dir)

        # Adicionar hexes satélite ausentes no heatmap (idempotente)
        patch_heatmap_add_satellite_hexes(output_dir=output_dir)

    # Fase 3.5: otimização de cap
    with timer.phase("phase3_5_cap_optimizer"):
        try:
            from vanilla.phase3_5_cap_optimizer import run_phase3_5
            run_phase3_5(fit=fit, output_dir=output_dir, stations=stations)
        except Exception as e:
            print(f"  WARN Phase 3.5 falhou: {e}")

    # Fase 4: webleads
    with timer.phase("phase4_webleads"):
        webleads = run_phase4(
            partner_data=partner_data,
            territories=territories,
            pkg=pkg,
            legacy_bucket_names=legacy_bucket_names,
        )

    # Fase 6: busca CNPJ para slots em aberto (roda antes da Fase 5 para enriquecer relatórios)
    with timer.phase("cnpj_lookup"):
        cnpj_result = None
        if Config.CNPJ_DB_PATH:
            try:
                cnpj_result = run_cnpj_lookup(
                    supply=supply,
                    pkg=pkg,
                    stations=stations,
                )
                if cnpj_result.total_candidates > 0:
                    print(f"\n  CNPJ LOOKUP: {cnpj_result.total_candidates} candidatos encontrados.")
            except FileNotFoundError as e:
                print(f"\n  WARN CNPJ LOOKUP: {e}")

    # Fase 5: relatorios
    with timer.phase("phase5_reports"):
        paths = run_phase5(
            territories=territories,
            supply=supply,
            fit=fit,
            webleads=webleads,
            pkg=pkg,
            output_dir=output_dir,
            stations=stations,
            cnpj_result=cnpj_result,
        )

    # Sumario de attainment por base
    summ = fit.summary()
    print(f"\n  RESUMO DE ATTAINMENT:")
    for station in sorted(summ):
        s = summ[station]
        pct = (s["active"] / s["slots"] * 100) if s["slots"] else 0
        print(f"  [{station}]  vagas={s['slots']}  "
              f"ativos={s['active']}  "
              f"em_aberto={s['open']}  "
              f"attainment={pct:.1f}%")

    # Fecha o pipeline e persiste o relatório de timing
    timer.end_pipeline()
    try:
        report.save(Path(output_dir) / "timing_report.json")
    except Exception as e:
        print(f"  WARN timing_report.json não persistido: {e}")
    report.log_summary()

    print(f"\n{'#'*60}")
    print(f"  DAILY CONCLUIDO")
    print(f"  Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}\n")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema de otimizacao de parceiros logisticos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python orchestrator.py --mode setup
  python orchestrator.py --mode daily
  python orchestrator.py --mode setup --stations DSP2 DSP4
  python orchestrator.py --mode daily --output output/2026-03-18/
  python orchestrator.py --mode daily --legacy-buckets
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["setup", "daily"],
        required=False,
        help="setup: Fases 1+2 (territorios e vagas ideais). "
             "daily: Fases 3+4+5 (matching e relatorios).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=f"Pasta de saida. Default: {Config.DEST_FOLDER}",
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
        help="Numero de workers paralelos para o solver (modo setup). Default: 4.",
    )
    parser.add_argument(
        "--legacy-buckets",
        action="store_true",
        default=False,
        help="Usar formato antigo de nomes de bucket no config de "
             "account managers (compatibilidade durante migracao).",
    )
    parser.add_argument(
        "--partnerCSV",
        default=None,
        metavar="PATH",
        help="Caminho para um CSV de parceiros exportado do Salesforce. "
             "Quando fornecido, substitui a leitura do Excel (terra.xlsm) "
             "no modo daily. Ex: --partnerCSV data/partners.csv",
    )
    return parser.parse_args()


def main() -> None:
    args    = _parse_args()
    out_dir = args.output or Config.DEST_FOLDER

    try:
        if args.mode == "setup":
            run_setup(
                output_dir=out_dir,
                stations=args.stations,
                max_workers=args.workers,
            )
        elif args.mode == "daily":
            run_daily(
                output_dir=out_dir,
                stations=args.stations,
                legacy_bucket_names=args.legacy_buckets,
                partner_csv=args.partnerCSV,
            )
        else:
            print("  Especifique --mode setup ou --mode daily.")
    except FileNotFoundError as e:
        print(f"\n  ERRO: {e}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Interrompido pelo usuario.", file=sys.stderr)
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

