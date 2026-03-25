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

--mode daily    (roda todo dia)
    Fase 3: Matching parceiros x vagas     -> ideal_supply.json (atualizado)
    Fase 4: Qualificacao de webleads
    Fase 5: Geracao de relatorios          -> *.txt, *.csv, *.geojson

Uso
---
    python orchestrator.py --mode setup
    python orchestrator.py --mode daily
    python orchestrator.py --mode setup --stations DSP2 DSP4
    python orchestrator.py --mode daily --output output/2026-03-18/

Dependencias entre artefatos
------------------------------
    setup  ->  territories_index.json
               ideal_supply.json
    daily  ->  le territories_index.json  (Fase 1 ja rodada)
               le ideal_supply.json       (Fase 2 ja rodada)
               escreve ideal_supply.json  (matched_partner_id atualizado)
               escreve relatorios finais

Se territories_index.json ou ideal_supply.json nao existirem no modo daily,
o orchestrador aborta com mensagem descritiva indicando para rodar --mode setup.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from main import run_pipeline
from load_packages import load_packages
from load_partners import load_partners
from models import Config
from phase_setup import run_setup as _run_setup_new, update_territories_geojson
from phase1_territories import TerritoriesResult, load_territories
from phase2_ideal_supply import IdealSupplyResult, load_ideal_supply
from phase3_partner_fit import FitResult, run_phase3
from phase4_webleads import WebleadResult, run_phase4
from phase5_reports import run_phase5


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

    pkg = load_packages()

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
) -> None:
    """
    Fases 3, 4 e 5: matching diario de parceiros e geracao de relatorios.
    Le os artefatos de setup sem re-rodar territorializacao ou solver.
    """
    print(f"\n{'#'*60}")
    print(f"  MODO DAILY")
    print(f"  Output: {output_dir}")
    if stations:
        print(f"  Bases filtradas: {stations}")
    print(f"  Inicio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}")

    # Carregar artefatos do setup (aborta se nao existirem)
    territories = load_territories(output_dir)
    supply      = load_ideal_supply(output_dir)

    # Filtrar bases se necessario
    if stations:
        all_tids = [
            tid for tid, meta in territories.territory_index.items()
            if meta["station_code"] in stations
        ]
        territories.hex_to_territory = {
            h: tid for h, tid in territories.hex_to_territory.items()
            if tid in all_tids
        }

    # Carregar parceiros e jurisdicoes (sempre frescos)
    pkg          = load_packages()
    partner_data = load_partners()

    # Fase 3: matching
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

    # Fase 4: webleads
    webleads = run_phase4(
        partner_data=partner_data,
        territories=territories,
        pkg=pkg,
        legacy_bucket_names=legacy_bucket_names,
    )

    # Fase 5: relatorios
    paths = run_phase5(
        territories=territories,
        supply=supply,
        fit=fit,
        webleads=webleads,
        pkg=pkg,
        output_dir=output_dir,
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

    print(f"\n{'#'*60}")
    print(f"  DAILY CONCLUIDO")
    print(f"  Fim: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'#'*60}\n")


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
        required=True,
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
        else:
            run_daily(
                output_dir=out_dir,
                stations=args.stations,
                legacy_bucket_names=args.legacy_buckets,
            )
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
