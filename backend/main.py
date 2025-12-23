import os
import time
from datetime import datetime
import pandas as pd
import config
from data_processing.excel_handler import ExcelHandler
from data_processing.data_processor import DataProcessor
from data_processing.json_generator import JsonGenerator
from data_processing.generate_scorecard_json import ScorecardGenerator

def run_pipeline():
    """
    Executa o pipeline completo de processamento de dados.
    """
    print("--- INICIANDO PIPELINE DE PROCESSAMENTO DE DADOS ---")
    
    try:
        #Ler dados do Excel
        with ExcelHandler(config.EXCEL_FILE_PATH) as excel:
            dataframes = excel.refresh_and_load_sheets(
                sheets_to_load=config.SHEETS_TO_LOAD,
                macro_name=config.MACRO_NAME,
                timeout=config.MACRO_TIMEOUT_SECONDS
            )

        #Consolidar lojas
        consolidated_stores = DataProcessor.consolidate_stores(dataframes)
        
        #Calcular métricas sobreposições e scorecard
        adv_raw_df = dataframes.get("ADV - Coverage raw data", pd.DataFrame())
        perfect_mile_df = dataframes.get("PerfectMile", pd.DataFrame())
        historical_metrics = DataProcessor.calculate_historical_metrics(adv_raw_df)
        overlaps = DataProcessor.calculate_overlaps(consolidated_stores)
        scorecard_df = dataframes.get("Lead", pd.DataFrame())
        
        #Mesclar e enriquecer os dados
        if 'StoreID' in consolidated_stores.columns:
            consolidated_stores['StoreID'] = consolidated_stores['StoreID'].astype(str)
        if not historical_metrics.empty and 'StoreID' in historical_metrics.columns:
            historical_metrics['StoreID'] = historical_metrics['StoreID'].astype(str)
        if 'StoreID' in historical_metrics.columns and historical_metrics['StoreID'].str.endswith('.0').any():
            historical_metrics['StoreID'] = historical_metrics['StoreID'].str[:-2]
        
        final_df = pd.merge(consolidated_stores, historical_metrics, on="StoreID", how="left")
        
        if 'ADV_calculated' in final_df.columns:
            final_df['Actual ADV'] = final_df['ADV_calculated'].combine_first(final_df['Actual ADV'])
            final_df.drop(columns=['ADV_calculated'], inplace=True)
            
        pm_metrics = DataProcessor.calculate_perfect_mile_metrics(perfect_mile_df)
        final_df = DataProcessor.enrich_with_overlaps(final_df, overlaps, top_n=5)

        final_df = final_df.merge(pm_metrics, on="Name", how="left")
        
        print("Dados consolidados e enriquecidos com sucesso.")

        #Filtrar lojas sem coordenadas válidas
        initial_rows = len(final_df)
        final_df.dropna(subset=['Latitude', 'Longitude'], inplace=True)
        filtered_rows = len(final_df)
        
        if initial_rows > filtered_rows:
            print(f"AVISO: {initial_rows - filtered_rows} lojas foram removidas por não terem coordenadas válidas.")

        #Gerar os arquivos JSON para mapa e Scorecard
    
        period_data = adv_raw_df["Start Period"]
        period = datetime.today().strftime("%Y-%m-%d : %Hh:%Mm")

        json_filename = f"{config.OUTPUT_JSON_FILENAME_PREFIX}.json"
        json_scorecard_filename = f"{config.OUTPUT_JSON_SCORECARD_FILENAME_PREFIX}.json"
        output_path = os.path.join(config.OUTPUT_JSON_DIR, json_filename)
        output_path_scorecard = os.path.join(config.OUTPUT_JSON_DIR, json_scorecard_filename)
        JsonGenerator.generate_json(period, final_df, output_path)
        ScorecardGenerator(scorecard_df, output_path_scorecard, config.SCORECARD_CONFIG).generate_scorecard()

    except Exception as e:
        print(f"\nERRO CRÍTICO DURANTE A EXECUÇÃO DO PIPELINE: {e}")
        import traceback
        traceback.print_exc()
        print("--- PIPELINE INTERROMPIDO ---")


if __name__ == "__main__":
    start_time = time.time()
    run_pipeline()
    end_time = time.time()
    print("--- PIPELINE CONCLUÍDO COM SUCESSO ---")
    print(f"\nTempo total de execução: {end_time - start_time:.2f} segundos.")