"""
main.py
=======
Stub simplificado do pipeline de dados do ATLAS.

O pipeline completo agora vive em load_partners.py:
  - Lê terra.xlsm via ExcelHandler
  - Consolida Active + Launches + WebLeads
  - Serializa dados_mapa.json com Schema_Limpo

Este módulo apenas orquestra load_partners() + ScorecardGenerator.
"""

import os
import time
import config
from load_partners import load_partners
from data_processing.excel_handler import ExcelHandler
from data_processing.generate_scorecard_json import ScorecardGenerator


def run_pipeline():
    """Executa o pipeline de dados: parceiros + scorecard."""
    print("--- INICIANDO PIPELINE DE PROCESSAMENTO DE DADOS ---")

    # Fase 1: parceiros — lê Excel, consolida, serializa dados_mapa.json
    load_partners()

    # Fase 2: scorecard — aba Lead (fluxo independente)
    with ExcelHandler(config.EXCEL_FILE_PATH) as excel:
        dataframes = excel.refresh_and_load_sheets(
            sheets_to_load=config.SHEETS_SCORECARD,
            macro_name=config.MACRO_NAME,
            timeout=config.MACRO_TIMEOUT_SECONDS,
        )

    import pandas as pd
    scorecard_df = dataframes.get("Lead", pd.DataFrame())
    output_path  = os.path.join(config.OUTPUT_JSON_DIR, f"{config.OUTPUT_JSON_SCORECARD_FILENAME_PREFIX}.json")
    ScorecardGenerator(scorecard_df, output_path, config.SCORECARD_CONFIG).generate_scorecard()

    print("--- PIPELINE CONCLUÍDO COM SUCESSO ---")


if __name__ == "__main__":
    start = time.time()
    run_pipeline()
    print(f"\nTempo total: {time.time() - start:.2f}s")
