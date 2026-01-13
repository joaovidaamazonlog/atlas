import config
import pandas as pd
import numpy as np
import optmization_ortools
from pathlib import Path

if __name__ == "__main__": 
    hub = optmization_ortools.OptimizationHub(config.BASE_PACKAGES, config.BASE_PARTNERS)
    raw_results = hub.run()
    
    decisions = (
        raw_results["existing_partners"]
        + raw_results["new_partners"]
    )

    decisions = optmization_ortools.OptimizationHub.apply_snapshot(decisions, config.BASE_PREVIOUS_SNAPSHOT)
    
    optmization_ortools.OptimizationHub.export_hex_geojson(
        decisions,
        config.DEST_FOLDER / "optmization_layer.geojson",
        scale=config.SCALING_FACTOR
    )
    
    optmization_ortools.OptimizationHub.save_snapshot(
        decisions,
        config.BASE_PREVIOUS_SNAPSHOT
    )
    
    optmization_ortools.OptimizationHub.log_executed_actions(
        decisions,
        config.DEST_FOLDER / "executed_actions.log",
    )