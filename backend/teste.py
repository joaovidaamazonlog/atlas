import config
import pandas as pd
import numpy as np

if __name__ == "__main__":
    df = pd.read_csv(config.BASE_PACKAGES)
    
    total_packages = len(df.tracking_id.unique())
    total_days = (pd.to_datetime(df['plan_date']).max() - pd.to_datetime(df['plan_date']).min()).days + 1
    median_packages_per_day = int(total_packages / total_days)
    print(f"Total de pacotes únicos: {total_packages}")
    print(f"Total de dias: {total_days}")
    print(f"Pacotes medianos por dia: {median_packages_per_day}")
