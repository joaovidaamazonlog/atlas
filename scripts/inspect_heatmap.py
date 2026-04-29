"""Ver se ha duplicatas hex_id entre features no heatmap final."""
import json
from collections import Counter
from pathlib import Path

HEATMAP = Path("output_data/heatmap.geojson")

with HEATMAP.open(encoding="utf-8") as f:
    hm = json.load(f)
feats = hm["features"]

hex_ids = [f["properties"].get("hex_id") for f in feats]
count = Counter(hex_ids)
dups = {h: n for h, n in count.items() if n > 1}
print(f"Total features: {len(feats):,}")
print(f"Hex_ids duplicados: {len(dups)}")

# Ver o hex proximo ao centro XBA1
target_hex = "89811018cd7ffff"
feats_for = [f for f in feats if f["properties"].get("hex_id") == target_hex]
print(f"\nFeatures para hex {target_hex}: {len(feats_for)}")
for f in feats_for:
    p = f["properties"]
    print(f"  ds={p.get('delivery_station'):<6} tid={p.get('territory_id'):<25} "
          f"canonical_base={p.get('canonical_base')!r:<10} in_jur={p.get('in_jurisdiction')}")

# Tambem ver o hex do centro satelite
target_hex2 = "8981101aa7bffff"
feats_for2 = [f for f in feats if f["properties"].get("hex_id") == target_hex2]
print(f"\nFeatures para hex {target_hex2} (centro XBA1): {len(feats_for2)}")
for f in feats_for2:
    p = f["properties"]
    print(f"  ds={p.get('delivery_station'):<6} tid={p.get('territory_id'):<25} "
          f"canonical_base={p.get('canonical_base')!r:<10} in_jur={p.get('in_jurisdiction')}")
