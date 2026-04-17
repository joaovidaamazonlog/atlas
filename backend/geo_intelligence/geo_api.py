"""
geo_api.py
==========
GeoIntelligence FastAPI — leitura dos resultados do pipeline para o frontend.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from geo_intelligence.geo_config import TURSO_AUTH_TOKEN, TURSO_URL
from geo_intelligence.turso_reader import TursoReader

logger = logging.getLogger(__name__)

app = FastAPI(title="GeoIntelligence API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # em produção, restringir para o domínio do Atlas
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

_reader: Optional[TursoReader] = None


def _get_reader() -> TursoReader:
    global _reader
    if _reader is None:
        _reader = TursoReader(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    return _reader


def _resolve_run_id(reader: TursoReader, station_code: str, run_id: Optional[str]) -> str:
    if run_id:
        return run_id
    latest = reader.get_latest_run_id(station_code)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma execução concluída encontrada para '{station_code}'. Execute o pipeline GeoIntelligence primeiro.",
        )
    return latest


class ExpansionTargetRequest(BaseModel):
    expansion_target_pct: float


@app.get("/geo-intelligence/runs/{run_id}")
def get_run_metadata(run_id: str) -> dict[str, Any]:
    reader = _get_reader()
    rows = reader._query("SELECT * FROM geo_run_metadata WHERE run_id = ?", [run_id])
    if not rows:
        raise HTTPException(status_code=404, detail=f"Execução '{run_id}' não encontrada.")
    return rows[0]


@app.get("/geo-intelligence/{station_code}/territories")
def list_territories(
    station_code: str,
    region_type: Optional[str] = Query(default=None),
    min_gap: Optional[float] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
) -> list[dict[str, Any]]:
    reader = _get_reader()
    resolved = _resolve_run_id(reader, station_code, run_id)
    return reader.get_territories(station_code, resolved, region_type=region_type, min_gap=min_gap)


@app.get("/geo-intelligence/{station_code}/territories/{territory_id}")
def get_territory_detail(
    station_code: str,
    territory_id: str,
    run_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    reader = _get_reader()
    resolved = _resolve_run_id(reader, station_code, run_id)
    territories = reader.get_territories(station_code, resolved)
    territory = next((t for t in territories if t.get("territory_id") == territory_id), None)
    if territory is None:
        raise HTTPException(status_code=404, detail=f"Território '{territory_id}' não encontrado.")
    return {**territory, "h3_cells": reader.get_h3_cells(territory_id, resolved)}


@app.get("/geo-intelligence/{station_code}/geojson")
def get_geojson(
    station_code: str,
    run_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    reader = _get_reader()
    resolved = _resolve_run_id(reader, station_code, run_id)
    territories = reader.get_territories(station_code, resolved)
    if not territories:
        raise HTTPException(status_code=404, detail=f"Nenhum dado GeoJSON para '{station_code}'.")

    features = []
    for t in territories:
        try:
            geometry = json.loads(t.get("geometry_geojson") or "{}")
        except Exception:
            geometry = None
        props = {k: v for k, v in t.items() if k != "geometry_geojson"}
        if isinstance(props.get("h3_ids_json"), str):
            try:
                props["h3_ids"] = json.loads(props.pop("h3_ids_json"))
            except Exception:
                props["h3_ids"] = []
        features.append({"type": "Feature", "geometry": geometry, "properties": props})

    return {"type": "FeatureCollection", "features": features}


@app.get("/geo-intelligence/{station_code}/scorecard")
def get_scorecard(
    station_code: str,
    run_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    reader = _get_reader()
    resolved = _resolve_run_id(reader, station_code, run_id)
    scorecard = reader.get_scorecard(station_code, resolved)
    if not scorecard.get("ds") and not scorecard.get("bdm"):
        raise HTTPException(status_code=404, detail=f"Nenhum scorecard para '{station_code}'.")
    return {"station_code": station_code, "run_id": resolved, **scorecard}


@app.get("/geo-intelligence/{station_code}/ideal-supply")
def get_ideal_supply(
    station_code: str,
    run_id: Optional[str] = Query(default=None),
) -> list[dict[str, Any]]:
    reader = _get_reader()
    resolved = _resolve_run_id(reader, station_code, run_id)
    supply = reader.get_ideal_supply(station_code, resolved)
    if not supply:
        raise HTTPException(status_code=404, detail=f"Nenhum supply para '{station_code}'.")
    return supply


@app.post("/geo-intelligence/{station_code}/expansion-targets")
def compute_expansion_targets(
    station_code: str,
    body: ExpansionTargetRequest,
    run_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    reader = _get_reader()
    resolved = _resolve_run_id(reader, station_code, run_id)
    territories = reader.get_territories(station_code, resolved)
    if not territories:
        raise HTTPException(status_code=404, detail=f"Nenhum território para '{station_code}'.")

    target_pct = body.expansion_target_pct
    sorted_t = sorted(territories, key=lambda t: float(t.get("gap") or 0.0), reverse=True)
    total_score = sum(float(t.get("potential_score") or 0.0) for t in territories)
    target_score = total_score * (target_pct / 100.0)

    selected, accumulated = [], 0.0
    for t in sorted_t:
        selected.append(t)
        accumulated += float(t.get("potential_score") or 0.0)
        if accumulated >= target_score:
            break

    return {
        "station_code": station_code,
        "run_id": resolved,
        "expansion_target_pct": target_pct,
        "selected_territories": selected,
        "total_potential_score": round(accumulated, 4),
        "n_territories": len(selected),
    }


@app.get("/geo-intelligence/{station_code}/runs")
def list_runs(station_code: str) -> list[dict[str, Any]]:
    reader = _get_reader()
    return reader._query(
        "SELECT * FROM geo_run_metadata WHERE station_code = ? ORDER BY timestamp_start DESC",
        [station_code],
    )
