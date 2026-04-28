"""
cleanup_orphan_heatmap_features.py
==================================
Remove do heatmap.geojson features 'fantasma':

A) Orfas por territory_id: tid nao existe mais em territories_index.json
   E demand_total == 0. Surgem quando um setup de satelite gera menos
   buckets que antes e o merge do heatmap nao limpa as features antigas.

B) Injetadas pelo patch com demanda zero: features com assinatura do
   patch_heatmap_add_satellite_hexes (covering_partners+demand_allocated
   +is_covered=False + demand_total=0 + ceps vazio) em territorios
   satelite validos. Elas existem apenas porque territory_index[tid]
   ["hex_ids"] continha hexes sem demanda historica, mas nao devem
   aparecer no heatmap (padrao das demais bases: hex sem demanda nao
   entra no heatmap).

C) Duplicatas canonica + satelite do mesmo hex: quando o setup satelite
   criou uma feature nova (ex: PUM2_bucket-01) mas o merge nao removeu
   a feature canonica antiga do mesmo hex (ex: DRJ3_bucket-09). Nesses
   casos a satelite vence — remove a canonica.

D) Duplicatas redundantes no mesmo tid: mesmo hex aparece duas vezes no
   mesmo territory_id, uma zerada (do patch, depois enriquecida com
   is_covered=True) e outra com demanda real. Remove a zerada.

Faz backup do heatmap antes de escrever.
"""
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

HEATMAP = Path("output_data/heatmap.geojson")
TERR_IDX = Path("output_data/territories_index.json")


def main() -> None:
    if not HEATMAP.exists() or not TERR_IDX.exists():
        print(f"ERRO: arquivos nao encontrados ({HEATMAP}, {TERR_IDX})")
        return

    with HEATMAP.open(encoding="utf-8") as f:
        hm = json.load(f)
    with TERR_IDX.open(encoding="utf-8") as f:
        idx = json.load(f)

    valid_tids = set(idx.keys())
    feats = hm.get("features", [])
    n_before = len(feats)

    # Conjunto de territorios satelite (tid comeca com codigo satelite).
    # Derivamos a partir de 'canonical_base' presente no territories_index.
    satellite_tids = {
        tid for tid, meta in idx.items()
        if meta.get("canonical_base")
    }

    # Classificar features:
    # (A) orfa zerada: territory_id nao esta em valid_tids E demand_total == 0
    # (B) fantasma do patch: assinatura do patch_heatmap_add_satellite_hexes
    #                        em territorio satelite valido
    # - orfa com demanda: territory_id nao esta em valid_tids mas demand_total > 0
    #                     (preservamos por seguranca)
    # - valida: demais casos
    kept = []
    n_removed_orphan = 0
    n_removed_ghost = 0
    n_orphan_with_demand = 0
    removed_by_tid: dict = {}

    def _is_patch_ghost(props: dict) -> bool:
        """Assinatura da feature injetada pelo patch_heatmap_add_satellite_hexes."""
        return (
            props.get("demand_total", 0) == 0
            and "covering_partners" in props
            and "demand_allocated" in props
            and "is_covered" in props
            and props.get("is_covered") is False
            and len(props.get("covering_partners", []) or []) == 0
            and len(props.get("ceps", []) or []) == 0
        )

    for ft in feats:
        props = ft.get("properties", {})
        tid = props.get("territory_id", "")
        dt = props.get("demand_total", 0) or 0

        # (A) Orfao zerado: tid nao-vazio, nao esta no index, demand=0
        if tid and tid not in valid_tids and dt == 0:
            removed_by_tid[tid] = removed_by_tid.get(tid, 0) + 1
            n_removed_orphan += 1
            continue

        # (B) Fantasma do patch em territorio satelite valido
        if tid in satellite_tids and _is_patch_ghost(props):
            removed_by_tid[tid] = removed_by_tid.get(tid, 0) + 1
            n_removed_ghost += 1
            continue

        if tid and tid not in valid_tids and dt > 0:
            n_orphan_with_demand += 1

        kept.append(ft)

    n_removed = n_removed_orphan + n_removed_ghost
    if n_removed == 0 and not any(c > 1 for c in Counter(
        ft["properties"].get("hex_id") for ft in kept
        if ft.get("properties", {}).get("hex_id")
    ).values()):
        print("Nenhuma feature orfa, fantasma ou duplicada para remover.")
        return

    # (C) Duplicatas canonica + satelite do mesmo hex_id
    # Agrupar features restantes por hex_id e detectar conflitos.
    satellite_tid_prefixes = tuple(f"{code}_" for code in {
        tid.split("_")[0] for tid, meta in idx.items()
        if meta.get("canonical_base")
    })

    def _is_satellite_feature(ft: dict) -> bool:
        tid = ft.get("properties", {}).get("territory_id", "")
        return bool(tid) and tid.startswith(satellite_tid_prefixes)

    hex_to_features: dict = {}
    for ft in kept:
        hid = ft.get("properties", {}).get("hex_id")
        if not hid:
            continue
        hex_to_features.setdefault(hid, []).append(ft)

    to_drop = set()
    n_removed_dup = 0
    dup_by_canonical_tid: dict = {}
    for hid, fts in hex_to_features.items():
        if len(fts) <= 1:
            continue
        has_sat = any(_is_satellite_feature(f) for f in fts)
        has_can = any(not _is_satellite_feature(f) for f in fts)
        if has_sat and has_can:
            # Manter apenas features satelite; remover canonicas
            for f in fts:
                if not _is_satellite_feature(f):
                    to_drop.add(id(f))
                    tid = f.get("properties", {}).get("territory_id", "")
                    dup_by_canonical_tid[tid] = dup_by_canonical_tid.get(tid, 0) + 1
                    n_removed_dup += 1

    if to_drop:
        kept = [ft for ft in kept if id(ft) not in to_drop]

    n_removed += n_removed_dup

    # (D) Duplicatas redundantes no mesmo territory_id:
    # mesmo hex + mesmo tid com uma feature zerada e outra com demanda.
    # Remove a zerada.
    n_removed_redundant = 0
    hex_tid_to_features: dict = {}
    for ft in kept:
        hid = ft.get("properties", {}).get("hex_id")
        tid = ft.get("properties", {}).get("territory_id", "")
        if not hid:
            continue
        key = (hid, tid)
        hex_tid_to_features.setdefault(key, []).append(ft)

    to_drop2 = set()
    for (hid, tid), fts in hex_tid_to_features.items():
        if len(fts) <= 1:
            continue
        demands = [ft.get("properties", {}).get("demand_total", 0) or 0 for ft in fts]
        has_nonzero = any(d > 0 for d in demands)
        has_zero = any(d == 0 for d in demands)
        if has_nonzero and has_zero:
            for ft in fts:
                if (ft.get("properties", {}).get("demand_total", 0) or 0) == 0:
                    to_drop2.add(id(ft))
                    n_removed_redundant += 1

    if to_drop2:
        kept = [ft for ft in kept if id(ft) not in to_drop2]

    n_removed += n_removed_redundant

    if n_removed == 0:
        print("Nenhuma feature para remover apos analise completa.")
        return

    # Backup
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = HEATMAP.with_name(f"heatmap.geojson.bak_{stamp}")
    shutil.copy2(HEATMAP, backup)
    print(f"Backup salvo em: {backup.name}")

    hm["features"] = kept
    if "metadata" in hm and isinstance(hm["metadata"], dict):
        hm["metadata"]["n_hexes"] = len(kept)
        hm["metadata"]["cleanup_at"] = datetime.now().isoformat(timespec="seconds")
        hm["metadata"]["cleanup_removed"] = n_removed

    with HEATMAP.open("w", encoding="utf-8") as f:
        json.dump(hm, f, ensure_ascii=False, indent=2)

    print(f"\nFeatures removidas: {n_removed:,} (de {n_before:,} -> {len(kept):,})")
    print(f"  orfaos zerados (tid nao existe mais): {n_removed_orphan:,}")
    print(f"  fantasmas do patch (tid satelite valido, sem demanda): {n_removed_ghost:,}")
    print(f"  duplicatas canonica+satelite (canonica removida): {n_removed_dup:,}")
    print(f"  duplicatas redundantes no mesmo tid (zerada removida): {n_removed_redundant:,}")
    print(f"Orfaos preservados por terem demanda > 0: {n_orphan_with_demand}")

    if removed_by_tid:
        print("\nRemovidos (orfaos e fantasmas) por territory_id:")
        for tid, n in sorted(removed_by_tid.items()):
            print(f"  {tid}: {n}")

    if dup_by_canonical_tid:
        print("\nDuplicatas canonicas removidas (substituidas por satelite):")
        for tid, n in sorted(dup_by_canonical_tid.items()):
            print(f"  {tid}: {n}")


if __name__ == "__main__":
    main()
