"""Inspecionar heatmap.geojson e territories_index.json para diagnosticar
demand_total nas áreas satélite."""
import json
from collections import Counter
from pathlib import Path

HEATMAP = Path("output_data/heatmap.geojson")
TERR_IDX = Path("output_data/territories_index.json")

SATELLITES = {
    "XBA1", "XCS1", "XGA2", "XPB1", "PUM2",
    "XRJ2", "XRJ4", "XSJ1", "XSP7", "XSP9", "XCP1",
}

with HEATMAP.open(encoding="utf-8") as f:
    hm = json.load(f)
feats = hm["features"]
print(f"Total features no heatmap: {len(feats):,}")

sat_feats = [f for f in feats if f["properties"].get("delivery_station") in SATELLITES]
print(f"Features com delivery_station = satelite: {len(sat_feats):,}\n")

with TERR_IDX.open(encoding="utf-8") as f:
    idx = json.load(f)

sat_terrs = {tid: m for tid, m in idx.items() if m.get("station_code") in SATELLITES}
print(f"Territorios de satelite no index: {len(sat_terrs)}")
for tid, meta in sat_terrs.items():
    hex_ids = meta.get("hex_ids") or []
    print(f"  {tid:<30} station={meta['station_code']:<6} "
          f"canonical={meta.get('canonical_base'):<6} "
          f"n_hex_meta={len(hex_ids):>4}  "
          f"daily_demand={meta.get('daily_demand')}")

# Cruzar territory_id das satelites com features do heatmap
hm_by_tid = Counter()
hm_demand_by_tid = {}
for f in feats:
    tid = f["properties"].get("territory_id", "")
    hm_by_tid[tid] += 1
    hm_demand_by_tid[tid] = hm_demand_by_tid.get(tid, 0) + f["properties"].get("demand_total", 0)

print("\nTerritorios satelite vs heatmap (cruzamento por territory_id):")
for tid in sat_terrs.keys():
    print(f"  {tid:<30} hex_no_heatmap={hm_by_tid.get(tid, 0):>4}  "
          f"sum_demand_total={hm_demand_by_tid.get(tid, 0):>8}")
