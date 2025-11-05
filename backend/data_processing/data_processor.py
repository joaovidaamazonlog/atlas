# /seu_projeto/data_processing/data_processor.py

import pandas as pd
import numpy as np
from sklearn.neighbors import BallTree
from typing import Dict

class DataProcessor:
    """
    Classe para consolidar, analisar e enriquecer os dados das lojas.
    """
    EARTH_RADIUS_KM = 6371.0

    @staticmethod
    def consolidate_stores(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Consolida os DataFrames 'Active' e 'Launches' e limpa os dados iniciais.
        """
        print("Consolidando bases 'Active' e 'Launches'...")
        
        mapeamento_ds = {
            'HSP2': 'DSP2',
            'HSP3': 'DSP3',
            'HSP5': 'DSP5',
            'HBH5': 'DBH5',
            'HFO3': 'DCE3',
            'HVI2': 'DES2',
            'HRJ3': 'DRJ3',
            'HGO2': 'DGO2',
            'HBS5': 'DBS5',
            'HPE4': 'DPE4',
            'HPR2': 'DPR2',
            'HRS5': 'DRS5',
            'HPB3': 'DPB3',
            'HSV8': 'DSA8'
        }
        
        active_df = dfs.get("Active", pd.DataFrame()).copy()
        launches_df = dfs.get("Launches", pd.DataFrame()).copy()
        stations_df = dfs.get("Delivery Stations", pd.DataFrame()).copy()

        if active_df.empty and launches_df.empty:
            raise ValueError("DataFrames 'Active' e 'Launches' estão vazios.")

        active_df["Source"] = "Active"
        launches_df["Source"] = "Launches"

        for df in [active_df, launches_df]:
            if "Radius" in df.columns:
                df["Radius"] = pd.to_numeric(df["Radius"], errors='coerce').fillna(1500)
            else:
                df["Radius"] = 1500

        if 'Id' in active_df.columns and 'Name' in active_df.columns and 'HCP Host Partner' in active_df.columns:
            map_host_partner = dict(zip(active_df['Id'].astype(str), active_df['Name']))
            active_df['HCP Host Partner'] = active_df['HCP Host Partner'].astype(str).map(map_host_partner)

        consolidated = pd.concat([active_df, launches_df], ignore_index=True, sort=False)

        if not stations_df.empty and 'Id' in stations_df.columns and 'Name' in stations_df.columns:
            station_map = dict(zip(stations_df['Id'].astype(str), stations_df['Name']))
            consolidated['Delivery Station'] = consolidated['Delivery Station'].astype(str).map(station_map)

        print("Limpando e convertendo colunas de coordenadas (Latitude, Longitude)...")
        for coord_col in ['Latitude', 'Longitude']:
            if coord_col in consolidated.columns:
                consolidated[coord_col] = consolidated[coord_col].astype(str).str.replace(',', '.', regex=False)
                consolidated[coord_col] = pd.to_numeric(consolidated[coord_col], errors='coerce')

        consolidated["Delivery Station"] = consolidated["Delivery Station"].replace(mapeamento_ds)
        print(f"Consolidação concluída: {consolidated.shape[0]} lojas no total.")
        return consolidated
    
    @staticmethod
    def calculate_perfect_mile_metrics(perfect_mile_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula as métricas de sucesso de entrega a partir do DataFrame Perfect Mile.
        """
        print("Calculando métricas de sucesso de entrega...")
        if perfect_mile_df.empty or 'Name' not in perfect_mile_df.columns:
            print("Aviso: DataFrame Perfect Mile está vazio ou sem 'Name'.")
            return pd.DataFrame()

        pm_df = perfect_mile_df.copy()
        pm_df['Name'] = pm_df['Name'].astype(str)
        pm_df["Dispatched Packages"] = pd.to_numeric(pm_df["Dispatched Packages"], errors='coerce').fillna(0)

        pm_filtered = pm_df[pm_df["Dispatched Packages"] > 0].copy()
        
        avg_columns = [col for col in ["DEA %", "EAD %", "FDDS %", "FTDS %", "DCR %"] if col in pm_filtered.columns]
        
        if not avg_columns:
            return pd.DataFrame()

        for col in avg_columns:
            pm_filtered[col] = pd.to_numeric(pm_filtered[col], errors='coerce')

        averages = pm_filtered.groupby("Name")[avg_columns].mean().round(2).reset_index()
        sums = pm_filtered.groupby("Name")[["Dispatched Packages", "Delivered Packages"]].sum().reset_index()
        
        metrics = pd.merge(averages, sums, on="Name")
        
        print(f"Métricas de sucesso de entrega calculadas para {metrics.shape[0]} lojas.")
        
        return metrics
    
    @staticmethod
    def calculate_historical_metrics(adv_raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula as métricas históricas e renomeia a coluna principal de ADV para clareza.
        """
        print("Calculando métricas históricas...")
        if adv_raw_df.empty or 'StoreID' not in adv_raw_df.columns:
            print("Aviso: DataFrame de ADV está vazio ou sem 'StoreID'.")
            return pd.DataFrame()

        historical = adv_raw_df.copy()
        historical['StoreID'] = historical['StoreID'].astype(str)
        historical["# Eligible Packages"] = pd.to_numeric(historical["# Eligible Packages"], errors='coerce').fillna(0)
        
        historical_filtered = historical[historical["# Eligible Packages"] > 0].copy()
        
        avg_columns = [col for col in ["Total Packages", "# Eligible Packages", "Partner Capacity", "Eligible and Allocated to CURRENT partner", "Eligible and Allocated to OTHER partners", "Eligible and could be allocated to CURRENT partner", "Allocated to VAN"] if col in historical.columns]
        
        if not avg_columns:
            return pd.DataFrame()

        for col in avg_columns:
            historical_filtered[col] = pd.to_numeric(historical_filtered[col], errors='coerce')

        averages = historical_filtered.groupby("StoreID")[avg_columns].mean().round(2).reset_index()     
        
        def calculate_additional_metrics(store_id, all_data, filtered_data):
            store_all = all_data[all_data["StoreID"] == store_id]
            store_filtered = filtered_data[filtered_data["StoreID"] == store_id]
            total_days, working_days, capping_days = store_all.shape[0], store_filtered.shape[0], 0
            if 'Partner Capacity' in store_filtered.columns and 'Eligible and Allocated to CURRENT partner' in store_filtered.columns:
                capping_days = store_filtered[pd.to_numeric(store_filtered["Partner Capacity"], errors='coerce') == pd.to_numeric(store_filtered["Eligible and Allocated to CURRENT partner"], errors='coerce')].shape[0]
                pct_capped = round(capping_days / working_days * 100, 2) if working_days > 0 else 0
                rostering = round(working_days / total_days * 100, 1) if total_days > 0 else 0
            return pd.Series({"Total days": total_days, "Qty Capping days": capping_days, "Qty working days": working_days, "% of capped days": pct_capped, "Rostering %": rostering})

        additional_metrics_df = averages["StoreID"].apply(lambda sid: calculate_additional_metrics(sid, historical, historical_filtered))
        final_metrics = pd.merge(averages, additional_metrics_df, left_index=True, right_index=True)
        final_metrics['TotalPackagesAllocated'] = historical_filtered.groupby("StoreID")["Eligible and Allocated to CURRENT partner"].sum().values

        if 'Eligible and Allocated to CURRENT partner' in final_metrics.columns:
            final_metrics.rename(columns={'Eligible and Allocated to CURRENT partner': 'ADV_calculated'}, inplace=True)
        
        print(f"Métricas históricas calculadas para {final_metrics.shape[0]} lojas.")
        
        return final_metrics

    @staticmethod
    def calculate_overlaps(stores_df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula a sobreposição entre lojas usando uma BallTree.
        """
        print("Calculando sobreposição de raios entre lojas...")
        df = stores_df.copy()
        
        for col in ["Latitude", "Longitude", "Radius"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        valid_stores = df.dropna(subset=["Latitude", "Longitude", "Radius", "StoreID"]).copy()
        valid_stores = valid_stores[valid_stores["Radius"] > 0].reset_index(drop=True)

        if valid_stores.empty:
            return pd.DataFrame()

        coords_rad = np.radians(valid_stores[["Latitude", "Longitude"]].values)
        tree = BallTree(coords_rad, metric="haversine")
        
        all_overlaps = []
        radii_m = valid_stores["Radius"].values
        store_ids = valid_stores["StoreID"].values
        max_radius_km = radii_m.max() / 1000.0
        search_radius_rad = (2 * max_radius_km) / DataProcessor.EARTH_RADIUS_KM
        
        store_overlaps_count = {}
        
        indices_list, distances_list_rad = tree.query_radius(coords_rad, r=search_radius_rad, return_distance=True)

        for i, (neighbor_indices, neighbor_dists_rad) in enumerate(zip(indices_list, distances_list_rad)):
            r1_m = radii_m[i]
            for j in neighbor_indices:
                if i == j: continue
                r2_m = radii_m[j]
                dist_m = neighbor_dists_rad[neighbor_indices.tolist().index(j)] * DataProcessor.EARTH_RADIUS_KM * 1000
                if dist_m < (r1_m + r2_m):
                    overlap_percent = 100 * (max(0, min(r1_m, r2_m, (r1_m + r2_m - dist_m)))) / max(r1_m, r2_m)
                    all_overlaps.append({"StoreID_1": store_ids[i], "StoreID_2": store_ids[j], "Distance_km": round(dist_m / 1000, 2), "overlap_percent": round(overlap_percent, 2)})
                    all_overlaps.append({"StoreID_1": store_ids[j], "StoreID_2": store_ids[i], "Distance_km": round(dist_m / 1000, 2), "overlap_percent": round(overlap_percent, 2)})

                    if store_ids[i] not in store_overlaps_count:
                        store_overlaps_count[store_ids[i]] = 0
                    if store_ids[j] not in store_overlaps_count:
                        store_overlaps_count[store_ids[j]] = 0
                    store_overlaps_count[store_ids[i]] += 1
                    store_overlaps_count[store_ids[j]] += 1

                    
        if not all_overlaps: return pd.DataFrame()
        
        overlaps_df = pd.DataFrame(all_overlaps)
        
        if not overlaps_df.empty:
            sorted_ids = np.sort(overlaps_df[['StoreID_1', 'StoreID_2']].values, axis=1)
            overlaps_df['StoreID_1'], overlaps_df['StoreID_2'] = sorted_ids[:, 0], sorted_ids[:, 1]
            overlaps_df = overlaps_df.drop_duplicates().reset_index(drop=True)
        
        overlaps_df['overlapping_count'] = overlaps_df['StoreID_1'].map(store_overlaps_count) + overlaps_df['StoreID_2'].map(store_overlaps_count)
        
        print(f"Cálculo de sobreposição concluído. {len(overlaps_df)} pares únicos encontrados.")
        return overlaps_df


    @staticmethod
    def enrich_with_overlaps(stores_df: pd.DataFrame, overlaps_df: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
        """
        Enriquece o DataFrame de lojas com os dados de sobreposição, limitado aos top_n vizinhos.
        """
        print(f"Enriquecendo dados com os TOP {top_n} overlaps mais próximos...")
        
        if overlaps_df.empty or overlaps_df is None:
            stores_df['overlap_data'] = None
            stores_df['overlapping_count'] = 0
            return stores_df

        stores_df['StoreID'] = stores_df['StoreID'].astype(str)
        overlaps_df['StoreID_1'] = overlaps_df['StoreID_1'].astype(str)
        overlaps_df['StoreID_2'] = overlaps_df['StoreID_2'].astype(str)

        overlaps_df = overlaps_df.sort_values(by='Distance_km', ascending=True)
        
        overlaps_enriched = pd.merge(overlaps_df, stores_df.add_suffix('_overlap'), left_on='StoreID_2', right_on='StoreID_overlap', how='left')

        def create_overlap_dict(row):
            metrics_to_get = {"store_id": "StoreID_2","status":"Status_overlap", "radius": "Radius_overlap", "distance": "Distance_km","overlapping_count": "overlapping_count", "overlap_percent":"overlap_percent", "total_packages": "Total Packages_overlap", "eligible_packages": "# Eligible Packages_overlap","total_packages_allocated":"TotalPackagesAllocated_overlap", "partner_capacity": "Partner Capacity_overlap", "ADV": "Actual ADV_overlap", "other_partners": "Eligible and Allocated to OTHER partners_overlap", "eligible_could_be_allocated": "Eligible and could be allocated to CURRENT partner_overlap", "allocated_van": "Allocated to VAN_overlap", "qty_capping_days": "Qty Capping days_overlap", "working_days": "Qty working days_overlap", "capped_days": "% of capped days_overlap", "rostering": "Rostering %_overlap"}
            overlap_item = {"overlap_id": row.name + 1}
            for key, col_name in metrics_to_get.items():
                overlap_item[key] = row.get(col_name)
            return overlap_item

        grouped_overlaps = overlaps_enriched.groupby('StoreID_1').apply(lambda g: g.head(top_n).reset_index(drop=True).apply(create_overlap_dict, axis=1).tolist())
        
        result_df = stores_df.merge(grouped_overlaps.rename('overlap_data'), left_on='StoreID', right_index=True, how='left')
        result_df['overlapping_count'] = result_df['overlap_data'].apply(lambda x: len(x) if isinstance(x, list) else 0)

        return result_df
    
    def _calculate_period(df: pd.DataFrame):
        if df.empty:
            return 0
        start = df.min()
        end = df.max()
        
        period = {
            "start": start.strftime("%Y-%m-%d"), 
            "end": end.strftime("%Y-%m-%d")
        }
        
        return period