"""
main.py
=======
Stub do pipeline de dados do ATLAS.

Lê terra.xlsm, consolida parceiros e serializa output_data/dados_mapa.json.
"""

import time
from load_partners import load_partners


def run_pipeline():
    """Executa o pipeline de dados: lê Excel → serializa dados_mapa.json."""
    print("--- INICIANDO PIPELINE DE PROCESSAMENTO DE DADOS ---")
    load_partners()
    print("--- PIPELINE CONCLUÍDO COM SUCESSO ---")


if __name__ == "__main__":
    start = time.time()
    run_pipeline()
    print(f"\nTempo total: {time.time() - start:.2f}s")
