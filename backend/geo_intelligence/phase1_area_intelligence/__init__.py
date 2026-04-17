"""
phase1_area_intelligence
========================
Orquestrador da Fase 1: Area Intelligence.

Fluxo:
  ingestor → enrichers (CNPJ, OSM, IBGE, Satélite) → feature_engineer
  → classifier → potential_calculator → area_selector
"""

from geo_intelligence.phase1_area_intelligence._orchestrator import run_area_intelligence

__all__ = ["run_area_intelligence"]
