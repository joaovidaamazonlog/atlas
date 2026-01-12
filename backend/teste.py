import config
import pandas as pd
import numpy as np
import optmization_ortools

if __name__ == "__main__":
    df = pd.read_csv(config.BASE_PACKAGES)
    
    total_packages = len(df.tracking_id.unique())
    total_days = (pd.to_datetime(df['plan_date']).max() - pd.to_datetime(df['plan_date']).min()).days + 1
    median_packages_per_day = int(total_packages / total_days)
    print(f"Total de pacotes únicos: {total_packages}")
    print(f"Total de dias: {total_days}")
    print(f"Pacotes medianos por dia: {median_packages_per_day}")
    
    hub = optmization_ortools.OptimizationHub(config.BASE_PACKAGES, config.BASE_PARTNERS)
    raw_results = hub.run()
    
    decisions = (
        raw_results["existing_partners"]
        + raw_results["new_partners"]
    )

    decisions = optmization_ortools.OptimizationHub.apply_snapshot(decisions, config.BASE_PREVIOUS_SNAPSHOT)
    
    optmization_ortools.OptimizationHub.export_hex_geojson(
        hub.hex_demand,
        hub.hex_demand,
        decisions,
        config.DEST_FOLDER + "\optmization_layer.geojson",
        scale=config.SCALING_FACTOR
    )
    
    optmization_ortools.OptimizationHub.save_snapshot(
        decisions,
        config.DEST_FOLDER + "\snapshot_current.json",
    )
    
    optmization_ortools.OptimizationHub.log_executed_actions(
        decisions,
        config.DEST_FOLDER + "\executed_actions.log",
    )