# /seu_projeto/data_processing/data_processor.py

import pandas as pd
from typing import Dict


class DataProcessor:
    """
    Consolidação de dados das lojas a partir do Excel.

    Métodos removidos (pipeline refatorado):
    - calculate_historical_metrics  → não utilizado
    - calculate_perfect_mile_metrics → não utilizado
    - calculate_overlaps             → não utilizado
    - enrich_with_overlaps           → não utilizado

    A lógica de consolidate_stores foi migrada para load_partners._consolidate_stores,
    mas é mantida aqui para compatibilidade com qualquer chamada legada durante transição.
    """

    @staticmethod
    def consolidate_stores(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Consolida os DataFrames 'Active' e 'Launches' e limpa os dados iniciais.
        Mantido por compatibilidade — a lógica canônica está em load_partners._consolidate_stores.
        """
        print("Consolidando bases 'Active' e 'Launches'...")

        mapeamento_ds = {
            'HSP2': 'DSP2', 'HSP3': 'DSP3', 'HSP5': 'DSP5', 'HBH5': 'DBH5',
            'HFO3': 'DCE3', 'HVI2': 'DES2', 'HRJ3': 'DRJ3', 'HGO2': 'DGO2',
            'HBS5': 'DBS5', 'HPE4': 'DPE4', 'HPR2': 'DPR2', 'HRS5': 'DRS5',
            'HPB3': 'DPB3', 'HSV8': 'DSA8',
        }

        active_df      = dfs.get("Active",            pd.DataFrame()).copy()
        launches_df    = dfs.get("Launches",           pd.DataFrame()).copy()
        stations_df    = dfs.get("Delivery Stations",  pd.DataFrame()).copy()
        jurisdictions_df = dfs.get("Jurisdictions",    pd.DataFrame()).copy()
        webleads_df    = dfs.get("WebLeads",           pd.DataFrame()).copy()

        if active_df.empty and launches_df.empty:
            raise ValueError("DataFrames 'Active' e 'Launches' estão vazios.")

        active_df["Source"]   = "Active"
        launches_df["Source"] = "Launches"

        for df in [active_df, launches_df]:
            if "Radius" in df.columns:
                df["Radius"] = pd.to_numeric(df["Radius"], errors='coerce').fillna(1500)
            else:
                df["Radius"] = 1500

            if "Volume Cap" in df.columns:
                df["Volume Cap"] = pd.to_numeric(df["Volume Cap"], errors='coerce').fillna(45)
            else:
                df["Volume Cap"] = 45

        if {'Id', 'Name', 'HCP Host Partner'}.issubset(active_df.columns):
            map_host_partner = dict(zip(active_df['Id'].astype(str), active_df['Name']))
            active_df['HCP Host Partner'] = active_df['HCP Host Partner'].astype(str).map(map_host_partner)

        consolidated = pd.concat([active_df, launches_df, webleads_df], ignore_index=True, sort=False)

        if not stations_df.empty and {'Id', 'Name'}.issubset(stations_df.columns):
            station_map = dict(zip(stations_df['Id'].astype(str), stations_df['Name']))
            consolidated['Delivery Station'] = consolidated['Delivery Station'].astype(str).map(station_map)

        if not jurisdictions_df.empty and {'Id', 'Name'}.issubset(jurisdictions_df.columns):
            jurisdictions_map = dict(zip(jurisdictions_df['Id'].astype(str), jurisdictions_df['Name'].str[5:]))
            consolidated['Bucket'] = consolidated['Jurisdiction'].astype(str).map(jurisdictions_map)

        for coord_col in ['Latitude', 'Longitude']:
            if coord_col in consolidated.columns:
                consolidated[coord_col] = consolidated[coord_col].astype(str).str.replace(',', '.', regex=False)
                consolidated[coord_col] = pd.to_numeric(consolidated[coord_col], errors='coerce')

        consolidated["Delivery Station"] = consolidated["Delivery Station"].replace(mapeamento_ds)
        print(f"Consolidação concluída: {consolidated.shape[0]} lojas no total.")
        return consolidated
