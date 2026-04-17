"""
geo_config.py
=============
Configurações do módulo GeoIntelligence.
Carrega variáveis de ambiente do arquivo .env se existir (uso local).
"""

from __future__ import annotations

import os
from pathlib import Path

# Carrega .env automaticamente se existir (sem precisar instalar python-dotenv)
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

# ---------------------------------------------------------------------------
# Turso (libSQL)
# A variável pode ser TURSO_TOKEN (Vercel) ou TURSO_AUTH_TOKEN (local)
# ---------------------------------------------------------------------------

TURSO_URL: str = os.environ.get("TURSO_URL", "")
TURSO_AUTH_TOKEN: str = os.environ.get("TURSO_AUTH_TOKEN", "") or os.environ.get("TURSO_TOKEN", "")

# ---------------------------------------------------------------------------
# Potential Calculator — pesos das features
# ---------------------------------------------------------------------------

POTENTIAL_WEIGHTS: dict[str, float] = {
    "target_business_density": 0.25,
    "avg_income": 0.20,
    "population_density": 0.15,
    "region_type_weight": 0.20,
    "road_connectivity_index": 0.10,
    "commercial_activity_index": 0.10,
}

REGION_TYPE_WEIGHTS: dict[str, float] = {
    "comercial": 1.0,
    "residencial_alta_renda": 0.9,
    "alto_padrao": 0.85,
    "residencial_media_renda": 0.7,
    "residencial_baixa_renda": 0.5,
    "favela_comunidade": 0.4,
    "industrial": 0.3,
    "rural": 0.1,
}

# ---------------------------------------------------------------------------
# Thresholds e limites do solver
# ---------------------------------------------------------------------------

HIGH_OPPORTUNITY_THRESHOLD: float = 20.0
CP_SOLVER_TIME_LIMIT_S: int = 300
CP_CAPACITY_TOLERANCE: float = 0.10

# ---------------------------------------------------------------------------
# Resolução H3
# ---------------------------------------------------------------------------

H3_RES_ANALYSIS: int = 8   # análise de área (~1 km²)
H3_RES_SUPPLY: int = 9     # posicionamento de slots via CP-SAT (~0.1 km²)

# ---------------------------------------------------------------------------
# Thresholds de parceiros e perfis de referência
# ---------------------------------------------------------------------------

DELIVERY_DENSITY_THRESHOLD: int = 5        # pacotes/dia mínimos em res 8
MIN_TENURE_DAYS_FOR_PROFILE: int = 30      # tenure mínimo para entrar no perfil
FAST_EXIT_THRESHOLD_DAYS: int = 180        # saída rápida = penalidade extra
FAST_EXIT_PENALTY: float = 0.20            # penalidade no raw_score [0-1]
FAILURE_PENALTY_WEIGHT: float = 0.5        # peso da similaridade negativa
LOW_COVERAGE_WARNING_PCT: float = 10.0     # % mínimo de hexágonos com parceiro

# ---------------------------------------------------------------------------
# UMAP
# ---------------------------------------------------------------------------

UMAP_N_COMPONENTS: int = 2
UMAP_N_NEIGHBORS: int = 15
UMAP_MIN_DIST: float = 0.1
UMAP_RANDOM_STATE: int = 42

# ---------------------------------------------------------------------------
# Potential score weights
# ---------------------------------------------------------------------------

DELIVERY_DENSITY_WEIGHT: float = 0.10  # peso máximo do volume no score

# ---------------------------------------------------------------------------
# Exit reason classification
# ---------------------------------------------------------------------------

EXIT_REASON_MAP: dict[str, dict] = {
    "volume_insuficiente":    {"class": "area_signal",    "penalty": 1.0},
    "acesso_dificil":         {"class": "area_signal",    "penalty": 0.8},
    "sobreposicao":           {"class": "area_signal",    "penalty": 0.5},
    "falencia":               {"class": "partner_signal", "penalty": 0.0},
    "desistencia_voluntaria": {"class": "partner_signal", "penalty": 0.0},
    "compliance":             {"class": "partner_signal", "penalty": 0.0},
    "operacional":            {"class": "partner_signal", "penalty": 0.2},
}

# ---------------------------------------------------------------------------
# Semantic anchors (optional, per station)
# ---------------------------------------------------------------------------

SEMANTIC_ANCHORS: dict[str, dict[str, str]] = {}
