"""
phase5_reports.py
=================
Fase 5 — Geracao de todos os artefatos de saida.

Arquivos gerados
----------------
OPORTUNIDADES_ESTRATEGICAS.txt
    Vagas ideais SEM parceiro vinculado, agrupadas por base → CTL → territorio.
    Inclui localizacao, CEPs-alvo, capacidade sugerida e raio.

RELATORIO_EXECUTIVO.txt
    Resumo por base: total de vagas, parceiros por status, attainment,
    demanda diaria total.
    Detalhamento por territorio: mesmos campos em granularidade menor.

PARTNERS_PER_DS_BUCKET.csv
    Um parceiro por linha. Mesmo formato do sistema anterior.
    Colunas: station_code, territory_id, status, salesforce_id,
             partner_name, store_id, decision, matched_slot_id

webleads_evaluated.csv
    Um lead por linha.
    Colunas: Id, Delivery Station, Jurisdiction, Name, OwnerId, decision

optimization_data.geojson
    FeatureCollection com dois tipos de features:
    - TERRITORY_HEX: poligono H3 com metadados do territorio
    - PARTNER_POINT: ponto do parceiro/vaga com metadados completos
    - IDEAL_SLOT: ponto da vaga ideal ainda em aberto (sem parceiro)

Entradas
--------
    territories : TerritoriesResult  (Fase 1)
    supply      : IdealSupplyResult  (Fase 2)
    fit         : FitResult          (Fase 3)
    webleads    : WebleadResult      (Fase 4)
    pkg         : PackageData        (load_packages)
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import h3

from load_packages import PackageData
from models import Config, IdealSlot, PartnerMetrics, TerritoriesResult
from phase2_ideal_supply import IdealSupplyResult
from phase3_partner_fit import FitResult, TerritoryFit
from phase4_webleads import WebleadResult


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

W = 90   # largura padrao das linhas de texto

def _line(char: str = "-", width: int = W) -> str:
    return char * width + "\n"

def _ceps_for_slot(slot: IdealSlot, hex_to_ceps: Dict[str, Set[str]]) -> List[str]:
    ceps: Set[str] = set()
    for a in slot.allocations:
        ceps.update(hex_to_ceps.get(a.hex_id, set()))
    return sorted(ceps)[:10]

def _ceps_for_partner(partner: PartnerMetrics, hex_to_ceps: Dict[str, Set[str]]) -> List[str]:
    ceps: Set[str] = set()
    for a in partner.allocations:
        ceps.update(hex_to_ceps.get(a.hex_id, set()))
    return sorted(ceps)[:5]

def _ctl_for_territory(territory_id: str) -> str:
    try:
        seq = int(territory_id.split("_T")[-1]) - 1
        return f"CTL-{chr(65 + (seq // 5))}"
    except (ValueError, IndexError):
        return "CTL-A"


# ---------------------------------------------------------------------------
# 1. OPORTUNIDADES ESTRATEGICAS
# ---------------------------------------------------------------------------

def _write_strategic(
    path: Path,
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    fit: FitResult,
    pkg: PackageData,
    cnpj_result=None,
) -> None:
    """
    Lista apenas as vagas ideais sem parceiro vinculado (is_open=True),
    agrupadas por base → CTL → territorio.
    Quando cnpj_result é fornecido, lista as empresas candidatas por slot.
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"RELATORIO ESTRATEGICO — OPORTUNIDADES EM ABERTO\n")
        f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(_line("="))

        for station in sorted(territories.stations):
            bdm = Config.get_bdm_cluster(station)
            f.write(f"\n📍 BASE: {station} | BDM: {bdm}\n")
            f.write(_line())

            t_metas = sorted(
                territories.territories_for(station),
                key=lambda m: (_ctl_for_territory(m["territory_id"]),
                               m["territory_id"]),
            )

            current_ctl = None
            for meta in t_metas:
                tid = meta["territory_id"]
                ctl = _ctl_for_territory(tid)

                if ctl != current_ctl:
                    current_ctl = ctl
                    f.write(f"\n   👮 {ctl} (Coordenador)\n")

                t_fit: Optional[TerritoryFit] = fit.territories.get(tid)
                slots_open = [s for s in supply.slots_for(tid) if s.is_open]
                slots_total = len(supply.slots_for(tid))

                f.write(_line())
                f.write(f"      📦 Territorio: {tid}\n")
                f.write(f"          - Demanda diaria:          {meta['daily_demand']:,.1f} pacotes/dia\n")
                f.write(f"          - Vagas ideais:             {slots_total}\n")
                f.write(f"          - Vagas em aberto:          {len(slots_open)}\n")

                if t_fit:
                    f.write(f"          - Parceiros Ativos:         {len(t_fit.partners_by_status('Active'))}\n")
                    f.write(f"          - Parceiros Onboarding:     {len(t_fit.partners_by_status('Onboarding'))}\n")
                    f.write(f"          - Parceiros Vetting:        {len(t_fit.partners_by_status('BG Checks'))}\n")
                    f.write(f"          - Attainment:               {t_fit.attainment:.1f}%\n")
                    f.write(f"          - Acuracidade:              {t_fit.accuracy:.1f}%\n")

                if not slots_open:
                    f.write(f"\n          ✅ Territorio Completo!\n")
                else:
                    f.write(f"\n          🚀 Oportunidades ({len(slots_open)}):\n")
                    for idx, slot in enumerate(
                        sorted(slots_open, key=lambda s: s.capacity_s, reverse=True), 1
                    ):
                        ceps = _ceps_for_slot(slot, pkg.hex_to_ceps)
                        f.write(f"          • Oportunidade {idx} [{slot.slot_id}]:\n")
                        f.write(f"              Capacidade sugerida: {slot.capacity_s:.1f} pacotes/dia"
                                f" | Raio: {slot.radius_s}m\n")
                        f.write(f"              CEPs-alvo (top 10): {', '.join(ceps) or 'N/D'}\n")
                        f.write(f"              Localizacao: https://maps.google.com/maps"
                                f"?q={slot.lat:.6f},{slot.lon:.6f}\n")

                        # Empresas candidatas (CNPJ lookup)
                        if cnpj_result:
                            candidates = cnpj_result.candidates_by_slot.get(slot.slot_id, [])
                            if candidates:
                                f.write(f"\n              🏢 Empresas candidatas ({len(candidates)}):\n")
                                for c in candidates:
                                    f.write(f"              ┌─ {c.razao_social} ({c.porte_descricao})\n")
                                    f.write(f"              │  CNPJ:       {c.cnpj}\n")
                                    f.write(f"              │  Endereço:   {c.endereco_completo}\n")
                                    if c.telefone_1:
                                        f.write(f"              │  Telefone 1: {c.telefone_1}\n")
                                    if c.telefone_2:
                                        f.write(f"              │  Telefone 2: {c.telefone_2}\n")
                                    if c.email:
                                        f.write(f"              │  Email:      {c.email}\n")
                                    if c.responsavel:
                                        f.write(f"              └─ Responsável: {c.responsavel}\n")
                                    else:
                                        f.write(f"              └─\n")
                            else:
                                f.write(f"\n              ℹ️  Nenhuma empresa candidata encontrada nos CEPs desta vaga.\n")

        f.write(_line("="))

    print(f"  ✅ {path.name}")


# ---------------------------------------------------------------------------
# 2. RELATORIO EXECUTIVO (TXT + JSON)
# ---------------------------------------------------------------------------

def _ceps_for_territory(
    territory_id: str,
    territories: TerritoriesResult,
    pkg: PackageData,
) -> List[str]:
    """Retorna lista de CEPs únicos associados a um território via hex_to_ceps."""
    ceps: Set[str] = set()
    for hex_id, tid in territories.hex_to_territory.items():
        if tid == territory_id:
            ceps.update(pkg.hex_to_ceps.get(hex_id, set()))
    return sorted(ceps)


def _write_executive_json(
    path: Path,
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    fit: FitResult,
    pkg: PackageData,
) -> None:
    """
    Gera relatorio_executivo.json com os dados estruturados do relatório executivo.
    Inclui CEPs por território (via hex_to_ceps).
    Consumido diretamente pelo Management Dashboard no frontend.
    """
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    bases = []

    for station in sorted(territories.stations):
        t_metas = territories.territories_for(station)
        bdm     = Config.get_bdm_cluster(station)

        total_daily_demand = sum(m["daily_demand"] for m in t_metas)
        total_slots        = sum(len(supply.slots_for(m["territory_id"])) for m in t_metas)
        total_open         = sum(
            len([s for s in supply.slots_for(m["territory_id"]) if s.is_open])
            for m in t_metas
        )

        base_partners = [
            p for tid in [m["territory_id"] for m in t_metas]
            for p in (fit.territories[tid].partners if tid in fit.territories else [])
        ]
        active     = sum(1 for p in base_partners if p.status == "Active")
        onboarding = sum(1 for p in base_partners if p.status == "Onboarding")
        bg         = sum(1 for p in base_partners if p.status == "BG Checks")
        prospects  = sum(1 for p in base_partners if p.entity_type == "PROSPECT")
        inactives  = sum(1 for p in base_partners if p.entity_type == "INACTIVE_EXITED")

        total_filled = total_slots - total_open
        coverage     = round(total_filled / total_slots, 4) if total_slots else 0.0
        attainment   = round(active / total_slots, 4) if total_slots else 0.0

        territory_list = []
        for meta in sorted(t_metas, key=lambda m: m["territory_id"]):
            tid          = meta["territory_id"]
            ctl          = _ctl_for_territory(tid)
            t_fit        = fit.territories.get(tid)
            t_slots      = supply.slots_for(tid)
            n_open       = len([s for s in t_slots if s.is_open])
            t_active     = len(t_fit.partners_by_status("Active"))     if t_fit else 0
            t_onboarding = len(t_fit.partners_by_status("Onboarding")) if t_fit else 0
            t_bg         = len(t_fit.partners_by_status("BG Checks"))  if t_fit else 0
            t_prospects  = len([p for p in (t_fit.partners if t_fit else []) if p.entity_type == "PROSPECT"])
            t_inactives  = len([p for p in (t_fit.partners if t_fit else []) if p.entity_type == "INACTIVE_EXITED"])
            t_attainment = round(t_fit.attainment / 100, 4) if t_fit else 0.0
            t_accuracy   = round(t_fit.accuracy / 100, 4)   if t_fit else 0.0
            ceps         = _ceps_for_territory(tid, territories, pkg)

            territory_list.append({
                "id":          tid,
                "ctl":         ctl,
                "dailyDemand": round(meta["daily_demand"], 1),
                "totalSlots":  len(t_slots),
                "openSlots":   n_open,
                "active":      t_active,
                "onboarding":  t_onboarding,
                "bg":          t_bg,
                "prospects":   t_prospects,
                "inactive":    t_inactives,
                "attainment":  t_attainment,
                "accuracy":    t_accuracy,
                "ceps":        ceps,
            })

        bases.append({
            "code":          station,
            "bdm":           bdm,
            "numTerritories": len(t_metas),
            "dailyDemand":   round(total_daily_demand, 1),
            "idealSlots":    total_slots,
            "matchedSlots":  total_filled,
            "openSlots":     total_open,
            "coverage":      coverage,
            "partners": {
                "active":     active,
                "onboarding": onboarding,
                "bgChecks":   bg,
                "prospects":  prospects,
                "inactive":   inactives,
            },
            "attainment":    attainment,
            "territories":   territory_list,
        })

    payload = {"generatedAt": generated_at, "bases": bases}

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {path.name}")


def _write_executive(
    path: Path,
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    fit: FitResult,
    pkg: PackageData,
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"RELATORIO EXECUTIVO DE OTIMIZACAO\n")
        f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write(_line("=", 80))

        for station in sorted(territories.stations):
            t_metas  = territories.territories_for(station)
            bdm      = Config.get_bdm_cluster(station)

            # Agregar metricas da base
            total_daily_demand = sum(m["daily_demand"] for m in t_metas)
            total_slots        = sum(len(supply.slots_for(m["territory_id"])) for m in t_metas)
            total_open         = sum(
                len([s for s in supply.slots_for(m["territory_id"]) if s.is_open])
                for m in t_metas
            )

            # Parceiros da base
            base_partners = [
                p for tid in [m["territory_id"] for m in t_metas]
                for p in (fit.territories[tid].partners if tid in fit.territories else [])
            ]
            active      = sum(1 for p in base_partners if p.status == "Active")
            onboarding  = sum(1 for p in base_partners if p.status == "Onboarding")
            bg          = sum(1 for p in base_partners if p.status == "BG Checks")
            prospects   = sum(1 for p in base_partners if p.entity_type == "PROSPECT")
            inactives   = sum(1 for p in base_partners
                              if p.entity_type == "INACTIVE_EXITED")
            total_exist   = active + onboarding + bg + prospects + inactives
            total_filled  = total_slots - total_open
            coverage      = (total_filled / total_slots * 100) if total_slots else 0.0
            attainment    = (active / total_slots * 100) if total_slots else 0.0

            f.write(f"\nBASE: {station} | BDM: {bdm}\n")
            f.write(_line("-", 80))
            f.write(f"  Territorios:                      {len(t_metas)}\n")
            f.write(f"  Demanda diaria total:             {total_daily_demand:,.1f} pacotes/dia\n")
            f.write(f"  Vagas ideais (total):             {total_slots}\n")
            f.write(f"  Vagas com match:                  {total_filled}\n")
            f.write(f"  Vagas em aberto:                  {total_open}\n")
            f.write(f"  Cobertura (match / total):        {total_filled}/{total_slots} = {coverage:.1f}%\n")
            f.write(f"  Parceiros existentes:             {total_exist}\n")
            f.write(f"    • Ativos:                       {active}\n")
            f.write(f"    • Onboarding:                   {onboarding}\n")
            f.write(f"    • BG Checks / Vetting:          {bg}\n")
            f.write(f"    • Prospects a aprovar:          {prospects}\n")
            f.write(f"    • Inativos a reativar:          {inactives}\n")
            f.write(f"  Attainment (Ativos / Vagas):      {attainment:.1f}%\n")
            f.write(_line("-", 80))
            f.write(f"  DETALHAMENTO POR TERRITORIO:\n\n")

            for meta in sorted(t_metas, key=lambda m: m["territory_id"]):
                tid     = meta["territory_id"]
                ctl     = _ctl_for_territory(tid)
                t_fit   = fit.territories.get(tid)
                t_slots = supply.slots_for(tid)
                n_open  = len([s for s in t_slots if s.is_open])

                t_active     = len(t_fit.partners_by_status("Active"))       if t_fit else 0
                t_onboarding = len(t_fit.partners_by_status("Onboarding"))   if t_fit else 0
                t_bg         = len(t_fit.partners_by_status("BG Checks"))    if t_fit else 0
                t_prospects  = len([p for p in (t_fit.partners if t_fit else [])
                                    if p.entity_type == "PROSPECT"])
                t_inactives  = len([p for p in (t_fit.partners if t_fit else [])
                                    if p.entity_type == "INACTIVE_EXITED"])
                t_attainment = t_fit.attainment if t_fit else 0.0
                t_accuracy   = t_fit.accuracy if t_fit else 0.0

                f.write(f"  {tid} ({ctl})\n")
                f.write(f"    Demanda diaria:     {meta['daily_demand']:>8,.1f} pacotes/dia\n")
                f.write(f"    Vagas / Em aberto:  {len(t_slots):>3} / {n_open}\n")
                f.write(f"    Ativos:             {t_active:>3}\n")
                f.write(f"    Onboarding:         {t_onboarding:>3}\n")
                f.write(f"    BG:                 {t_bg:>3}\n")
                f.write(f"    Prospects:          {t_prospects:>3}\n")
                f.write(f"    Inativos:           {t_inactives:>3}\n")
                f.write(f"    Attainment:         {t_attainment:>6.1f}%\n")
                f.write(f"    Acuracidade:        {t_accuracy:>6.1f}%\n\n")

        f.write(_line("=", 80))

    print(f"  ✅ {path.name}")


# ---------------------------------------------------------------------------
# 3. PARTNERS CSV
# ---------------------------------------------------------------------------

def _write_partners_csv(
    path: Path,
    fit: FitResult,
    stations: Optional[List[str]] = None,
) -> None:
    """
    Gera CSV com todos os parceiros dos tipos EXISTING, PROSPECT e INACTIVE_EXITED.
    Inclui parceiros com e sem slot matched.
    Quando stations é fornecido, faz merge com o arquivo existente preservando
    as demais stations.
    """
    INCLUDED_TYPES = {"EXISTING", "PROSPECT", "INACTIVE_EXITED"}

    fieldnames = [
        "station_code", "territory_id", "status", "entity_type",
        "salesforce_id", "partner_name", "store_id",
        "decision", "matched_slot_id",
    ]

    # Linhas existentes de outras stations (merge parcial)
    existing_rows: List[dict] = []
    if stations and path.exists():
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                existing_rows = [
                    row for row in reader
                    if row.get("station_code") not in stations
                ]
            print(f"  Merge {path.name}: mantendo {len(existing_rows)} linhas de outras stations.")
        except Exception as e:
            print(f"  WARN merge {path.name} falhou ({e}) — sobrescrevendo.")

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # Escrever linhas preservadas
        for row in existing_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        # Escrever novas linhas
        for t_fit in sorted(fit.territories.values(),
                            key=lambda t: (t.station_code, t.territory_id)):
            for p in t_fit.partners:
                if p.entity_type not in INCLUDED_TYPES:
                    continue
                writer.writerow({
                    "station_code":    p.station_code or "",
                    "territory_id":    t_fit.territory_id,
                    "status":          p.status,
                    "entity_type":     p.entity_type,
                    "salesforce_id":   p.salesforce_id,
                    "partner_name":    p.partner_name,
                    "store_id":        p.store_id or "",
                    "decision":        p.decision,
                    "matched_slot_id": p.matched_slot_id or "",
                })
    print(f"  ✅ {path.name}")


# ---------------------------------------------------------------------------
# 4. WEBLEADS CSV
# ---------------------------------------------------------------------------

def _write_webleads_csv(
    path: Path,
    webleads: WebleadResult,
    stations: Optional[List[str]] = None,
) -> None:
    fieldnames = ["Id", "Delivery Station", "Cep", "Jurisdiction", "Name", "OwnerId", "decision"]

    existing_rows: List[dict] = []
    if stations and path.exists():
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                existing_rows = [
                    row for row in reader
                    if row.get("Delivery Station") not in stations
                ]
            print(f"  Merge {path.name}: mantendo {len(existing_rows)} linhas de outras stations.")
        except Exception as e:
            print(f"  WARN merge {path.name} falhou ({e}) — sobrescrevendo.")

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in existing_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        for lead in webleads.leads:
            writer.writerow({
                "Id":               lead.salesforce_id,
                "Delivery Station": lead.station_code or "",
                "Cep":              lead.zip_code or "",
                "Jurisdiction":     lead.cluster_name or lead.bucket or "",
                "Name":             lead.partner_name,
                "OwnerId":          lead.owner_id or "",
                "decision":         lead.decision,
            })
    print(f"  ✅ {path.name}")


# ---------------------------------------------------------------------------
# 5. GEOJSON FINAL
# ---------------------------------------------------------------------------

def _write_geojson(
    path: Path,
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    fit: FitResult,
    pkg: PackageData,
    stations: Optional[List[str]] = None,
    cnpj_result=None,
) -> None:
    """
    FeatureCollection com duas camadas:

    TERRITORY_HEX  — polígono de cada hex com metadados do território
    IDEAL_SLOT     — ponto de cada vaga ideal ainda em aberto

    PARTNER_POINT foi removido — os dados de parceiros agora estão
    embutidos diretamente em dados_mapa.json.
    """
    existing_features: List[dict] = []
    if stations and path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_features = [
                ft for ft in existing.get("features", [])
                if ft.get("properties", {}).get("delivery_station") not in stations
                and ft.get("properties", {}).get("type") != "PARTNER_POINT"
            ]
            print(f"  Merge {path.name}: mantendo {len(existing_features)} features de outras stations.")
        except Exception as e:
            print(f"  WARN merge {path.name} falhou ({e}) — sobrescrevendo.")

    features: List[dict] = []

    # ── Camada 1: hexágonos por território ───────────────────────────────
    for h, tid in territories.hex_to_territory.items():
        meta   = territories.territory_index.get(tid, {})
        ctl    = _ctl_for_territory(tid)
        demand = pkg.demand_map(meta.get("station_code", "")).get(h, 0)

        boundary = h3.cell_to_boundary(h)
        coords   = [[c[1], c[0]] for c in boundary]
        coords.append(coords[0])

        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "type":             "TERRITORY_HEX",
                "hex_id":           h,
                "territory_id":     tid,
                "delivery_station": meta.get("station_code", ""),
                "bdm":              meta.get("bdm_cluster", ""),
                "ctl":              ctl,
                "demand_total":     demand,
                "demand_daily":     round(demand / pkg.days, 2) if pkg.days else 0,
                "ceps":             list(pkg.hex_to_ceps.get(h, set()))[:5],
            },
        })

    # ── Camada 2: vagas ideais em aberto ─────────────────────────────────
    for slot in supply.all_slots:
        if not slot.is_open:
            continue
        ceps = _ceps_for_slot(slot, pkg.hex_to_ceps)

        opportunities = []
        if cnpj_result:
            for c in cnpj_result.candidates_by_slot.get(slot.slot_id, []):
                opportunities.append({
                    "cnpj":           c.cnpj,
                    "razao_social":   c.razao_social,
                    "porte":          c.porte_descricao,
                    "endereco":       c.endereco_completo,
                    "cep":            c.cep,
                    "telefone_1":     c.telefone_1,
                    "telefone_2":     c.telefone_2,
                    "email":          c.email,
                    "responsavel":    c.responsavel,
                    "cnae_principal": c.cnae_principal,
                })

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [slot.lon, slot.lat]},
            "properties": {
                "type":            "IDEAL_SLOT",
                "slot_id":         slot.slot_id,
                "territory_id":    slot.bucket_id,
                "delivery_station": slot.station_code,
                "radius_s":        slot.radius_s,
                "capacity_day":    round(slot.capacity_s, 1),
                "ceps":            ceps,
                "opportunities":   opportunities,
                "n_opportunities": len(opportunities),
            },
        })

    geojson = {
        "type": "FeatureCollection",
        "features": existing_features + features,
        "metadata": {
            "generated_at":   datetime.now().isoformat(timespec="seconds"),
            "n_hex_features": sum(1 for ft in existing_features + features if ft["properties"]["type"] == "TERRITORY_HEX"),
            "n_open_slots":   sum(1 for ft in existing_features + features if ft["properties"]["type"] == "IDEAL_SLOT"),
            "n_opportunities": sum(ft["properties"].get("n_opportunities", 0) for ft in existing_features + features if ft["properties"]["type"] == "IDEAL_SLOT"),
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  ✅ {path.name}  "
          f"({geojson['metadata']['n_hex_features']:,} hexes | "
          f"{geojson['metadata']['n_open_slots']:,} vagas abertas | "
          f"{geojson['metadata']['n_opportunities']:,} candidatos CNPJ | "
          f"{size_mb:.1f} MB)")


def _write_dados_mapa(
    path: Path,
    fit: FitResult,
    partner_data_json_path: Path,
    stations: Optional[List[str]] = None,
) -> None:
    """
    Atualiza dados_mapa.json embutindo decision, reason, bucket_ade,
    radius_suggestion e cap_suggestion diretamente em cada parceiro.

    Faz merge parcial quando stations é fornecido — preserva parceiros
    de outras stations que já estavam no arquivo.
    """
    if not partner_data_json_path.exists():
        print(f"  WARN _write_dados_mapa: {partner_data_json_path} não encontrado — pulando.")
        return

    with open(partner_data_json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Índice rápido: salesforce_id → PartnerMetrics
    opt_index: Dict[str, PartnerMetrics] = {
        p.salesforce_id: p
        for p in fit.all_partners()
        if p.salesforce_id
    }

    updated = 0
    for record in payload.get("allMarkerData", []):
        sfid = record.get("salesforce_id")
        pm   = opt_index.get(sfid)
        if pm:
            record["decision"]          = pm.decision
            record["reason"]            = pm.reason
            record["bucket_ade"]        = pm.cluster_name or record.get("bucket")
            record["radius_suggestion"] = pm.radius_s
            record["cap_suggestion"]    = pm.capacity_s
            updated += 1

    with open(partner_data_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    size_mb = partner_data_json_path.stat().st_size / (1024 * 1024)
    print(f"  ✅ {partner_data_json_path.name}  "
          f"({updated} parceiros enriquecidos | {size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# FUNCAO PRINCIPAL
# ---------------------------------------------------------------------------

def run_phase5(
    territories: TerritoriesResult,
    supply: IdealSupplyResult,
    fit: FitResult,
    webleads: WebleadResult,
    pkg: PackageData,
    output_dir: str = None,
    stations: Optional[List[str]] = None,
    cnpj_result=None,
) -> Dict[str, Path]:
    """
    Executa a Fase 5: geracao de todos os artefatos de saida.

    Parametros
    ----------
    territories : TerritoriesResult   Fase 1
    supply      : IdealSupplyResult   Fase 2
    fit         : FitResult           Fase 3
    webleads    : WebleadResult       Fase 4
    pkg         : PackageData         load_packages()
    output_dir  : str, opcional       Default: Config.DEST_FOLDER

    Retorna
    -------
    Dict[str, Path] com os caminhos de cada arquivo gerado.
    Chaves: "strategic", "executive", "partners_csv",
            "webleads_csv", "geojson"
    """
    out_dir = Path(output_dir or Config.DEST_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  FASE 5 — GERACAO DE RELATORIOS")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}\n")

    paths: Dict[str, Path] = {}

    # 1. Oportunidades estrategicas
    p = out_dir / "OPORTUNIDADES_ESTRATEGICAS.txt"
    _write_strategic(p, territories, supply, fit, pkg, cnpj_result=cnpj_result)
    paths["strategic"] = p

    # 2. Relatorio executivo (TXT)
    p = out_dir / "RELATORIO_EXECUTIVO.txt"
    _write_executive(p, territories, supply, fit, pkg)
    paths["executive"] = p

    # 2b. Relatorio executivo (JSON — consumido pelo Management Dashboard)
    p = out_dir / "relatorio_executivo.json"
    _write_executive_json(p, territories, supply, fit, pkg)
    paths["executive_json"] = p

    # 3. Partners CSV
    p = out_dir / "PARTNERS_PER_DS_BUCKET.csv"
    _write_partners_csv(p, fit, stations=stations)
    paths["partners_csv"] = p

    # 4. Webleads CSV
    p = out_dir / "webleads_evaluated.csv"
    _write_webleads_csv(p, webleads, stations=stations)
    paths["webleads_csv"] = p

    # 5. GeoJSON final (TERRITORY_HEX + IDEAL_SLOT apenas)
    p = out_dir / "optimization_data.geojson"
    _write_geojson(p, territories, supply, fit, pkg, stations=stations, cnpj_result=cnpj_result)
    paths["geojson"] = p

    # 6. Enriquecer dados_mapa.json com campos de otimização
    dados_mapa_path = out_dir / "dados_mapa.json"
    _write_dados_mapa(dados_mapa_path, fit, dados_mapa_path, stations=stations)
    paths["dados_mapa"] = dados_mapa_path

    print(f"\n{'='*60}")
    print(f"  FASE 5 CONCLUIDA — {len(paths)} arquivos gerados")
    for name, fp in paths.items():
        size = fp.stat().st_size
        size_str = f"{size/1024:.1f} KB" if size < 1_048_576 else f"{size/1_048_576:.1f} MB"
        print(f"  {fp.name:<45} {size_str:>10}")
    print(f"{'='*60}\n")

    return paths
