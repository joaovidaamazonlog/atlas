# Design Document — GeoIntelligence v2

## Overview

Pipeline de expansão logística orientado a dados reais de operação. Aprende com o histórico de parceiros (ativos, exited e motivos de saída) para identificar áreas com perfil ideal para novos parceiros, usando UMAP + HDBSCAN para clustering morfológico e similaridade coseno com perfis de referência para scoring.

Arquitetura multi-resolução: H3 res 8 para análise de área (~1 km²), H3 res 9 para posicionamento preciso de slots via CP-SAT (~0.1 km²).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GEO-INTELLIGENCE v2 — SETUP                      │
│                                                                     │
│  load_packages() ──────────────────────────────────────────────┐   │
│  load_partners() ──────────────────────────────────────────────┤   │
│  Enrichers (CNPJ, OSM, IBGE, Satélite) ───────────────────────┤   │
│                                                                 ▼   │
│  Fase 1: Ingestão + Enriquecimento (res 8)                         │
│  Fase 2: Feature Engineering (build → impute → normalize)          │
│  Fase 3: Institutional Memory (Success/Failure Profiles)           │
│  Fase 4: UMAP + HDBSCAN (clustering morfológico)                   │
│  Fase 5: Similarity Score + Potential Score                        │
│  Fase 6: Area Selector (target_pct → SelectedTerritory[])          │
│  Fase 7: CP-SAT Ideal Supply (res 9 dentro dos territórios)        │
│          → TursoWriter (slots + run_metadata + profiles)           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    GEO-INTELLIGENCE v2 — DAILY                      │
│                                                                     │
│  load_partners() → parceiros reais                                  │
│  TursoReader → slots do setup mais recente                          │
│  territories.geojson → polígonos para point-in-polygon              │
│  territories_index.json → fallback centroide                        │
│          ↓                                                          │
│  geo_daily.run_daily() → matching hierárquico completo              │
│          ↓                                                          │
│  TursoWriter.update_supply_match()   → matched_partner_id           │
│  TursoWriter.update_territory_fit()  → attainment + accuracy        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
backend/
├── geo_intelligence/
│   ├── geo_orchestrator.py          # CLI: --mode setup / --mode daily
│   ├── geo_daily.py                 # Daily matching (hierarquia completa)
│   ├── geo_config.py                # Configurações: pesos, thresholds, exit_reason_map
│   ├── pipeline.py                  # Dataclasses: GeoSetupConfig, RunMetadata, etc.
│   ├── turso_writer.py              # Persistência no Turso
│   ├── turso_reader.py              # Leitura do Turso com cache TTL
│   ├── turso_http.py                # HTTP client para Turso
│   ├── phase2_ideal_supply.py       # CP-SAT (res 9)
│   ├── phase1_area_intelligence/
│   │   ├── _orchestrator.py         # Orquestra fases 1-6 do setup
│   │   ├── ingestor.py              # load_packages → H3 res 8 + filtro jurisdição
│   │   ├── partner_ingestor.py      # NEW: load_partners → Partner_Profiles res 8
│   │   ├── feature_engineer.py      # build → impute → normalize (res 8)
│   │   ├── profile_builder.py       # NEW: Success/Failure Profiles + tenure weighting
│   │   ├── classifier.py            # UMAP + HDBSCAN (+ KMeans fallback)
│   │   ├── potential_calculator.py  # Similarity score + gap + territory aggregation
│   │   ├── area_selector.py         # Seleciona territórios por target_pct
│   │   └── enrichers/
│   │       ├── cnpj_enricher.py
│   │       ├── osm_enricher.py
│   │       ├── ibge_enricher.py
│   │       └── satellite_enricher.py
```

---

## Data Models

### Partner_Profile (novo)

```python
@dataclass
class PartnerProfile:
    salesforce_id: str
    status: str                    # Active | Exited
    h3_id_r8: str                  # hex res 8
    lat: float
    lon: float
    tenure_days: int
    tenure_weight: float           # log(1 + tenure_days)
    exit_reason_class: str         # "area_signal" | "partner_signal" | None
    area_penalty: float            # 0.0 para Active, configurável para Exited
    features: dict[str, float]     # features normalizadas do hex res 8
    umap_embedding: list[float]    # preenchido após UMAP
```

### Reference Profiles

```python
@dataclass
class ReferenceProfiles:
    station_code: str
    success_vector: np.ndarray     # média ponderada por tenure_weight dos Active
    failure_vector: np.ndarray     # média ponderada por area_penalty * tenure dos Exited area_signal
    n_active: int
    n_exited_area: int
    avg_tenure_active: float
    profile_coverage: float        # % hexágonos com parceiro no raio grid_disk(1)
    low_coverage_warning: bool     # True se profile_coverage < 10%
    is_global_fallback: bool       # True se usou perfil global por falta de dados locais
```

### SelectedTerritory (atualizado)

```python
@dataclass
class SelectedTerritory:
    territory_id: str
    h3_ids_r8: list[str]           # res 8 para análise
    h3_ids_r9: list[str]           # res 9 para CP-SAT
    region_type: RegionType
    potential_score: float
    gap: float
    model_confidence: float
    high_opportunity: bool
    repeated_failure: bool         # True se 2+ Exited area_signal neste território
```

---

## Phase Design

### Fase 1 — Ingestão e Enriquecimento (res 8)

**Responsabilidade:** Mapear pacotes e parceiros para H3 res 8, enriquecer com dados externos.

**Inputs:**
- `packages_df` de `load_packages()`
- `partner_data` de `load_partners()` (inclui `decision_reason_code`, `exited_date`, `launch_date`)
- Enrichers: CNPJ/GMaps (Turso), OSM (osmnx), IBGE (setores censitários), Satélite

**Processing:**
1. `ingestor.ingest_packages()` → `{h3_id_r8: delivery_count}` filtrado pela jurisdição
2. `partner_ingestor.ingest_partners()` → `PartnerProfile[]` com `h3_id_r8` e `tenure_days`
3. Aplica `Delivery_Density_Threshold` (padrão: 5 pacotes/dia em res 8)
4. Enrichers rodam em paralelo com graceful degradation

**Output:** `{h3_id_r8: raw_features_dict}`, `PartnerProfile[]`

---

### Fase 2 — Feature Engineering

**Responsabilidade:** Consolidar, imputar e normalizar features por H3 res 8.

**Features por H3_Cell res 8:**

| Grupo | Features |
|---|---|
| Econômicas (CNPJ/GMaps) | `company_density`, `cnae_diversity_index`, `target_business_density`, `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density` |
| Urbanas (OSM) | `building_density`, `avg_building_size_m2`, `landuse_residential_ratio`, `landuse_commercial_ratio`, `poi_density`, `road_connectivity_index`, `landuse_entropy`, `road_centrality_index`, `local_clustering_coefficient` |
| Socioeconômicas (IBGE) | `avg_income`, `population_density` |
| Satélite | `ndvi_mean`, `urban_density_index`, `built_up_ratio` |
| Derivadas | `commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2` |
| Contexto (filtro) | `delivery_density_r8` (peso máx 0.10 no score) |

**Pipeline:** `build_features()` → `impute_missing(grid_disk=1, res=8)` → `normalize_features(min-max por DS)`

---

### Fase 3 — Institutional Memory (novo)

**Responsabilidade:** Construir Success_Profile e Failure_Profile a partir do histórico real de parceiros.

**`profile_builder.py`:**

```python
def build_reference_profiles(
    partner_profiles: list[PartnerProfile],
    cells_features: dict[str, np.ndarray],  # {h3_id_r8: feature_vector}
    exit_reason_map: dict[str, dict],        # de geo_config.py
    min_tenure_days: int = 30,
    global_fallback_profiles: ReferenceProfiles = None,
) -> ReferenceProfiles:
```

**Lógica de pesos:**

```python
# Active → Success Profile
tenure_weight = log(1 + tenure_days)  # parceiros mais antigos têm mais peso

# Exited area_signal → Failure Profile
area_penalty = exit_reason_map[exit_reason]["penalty"]  # configurável por motivo
failure_weight = area_penalty * log(1 + tenure_days)
# Saída rápida por volume = sinal mais forte de área ruim
```

**`exit_reason_map` em `geo_config.py`:**

```python
EXIT_REASON_MAP = {
    "volume_insuficiente":    {"class": "area_signal",    "penalty": 1.0},
    "acesso_dificil":         {"class": "area_signal",    "penalty": 0.8},
    "sobreposicao":           {"class": "area_signal",    "penalty": 0.5},
    "falencia":               {"class": "partner_signal", "penalty": 0.0},
    "desistencia_voluntaria": {"class": "partner_signal", "penalty": 0.0},
    "compliance":             {"class": "partner_signal", "penalty": 0.0},
    "operacional":            {"class": "partner_signal", "penalty": 0.2},
}
```

---

### Fase 4 — UMAP + HDBSCAN

**Responsabilidade:** Reduzir dimensionalidade e agrupar hexágonos por morfologia.

**UMAP:**
```python
umap.UMAP(
    n_components=2,
    n_neighbors=15,
    min_dist=0.1,
    random_state=42,
    metric="euclidean",
)
```

**HDBSCAN sobre embedding UMAP:**
```python
hdbscan.HDBSCAN(min_cluster_size=max(5, n_cells // 20))
```

**Fallback:** KMeans k=6 sobre embedding UMAP (não sobre features brutas).

**Âncoras semânticas** (opcional, configurável em `geo_config.py`):
```python
SEMANTIC_ANCHORS = {
    "DSP2": {
        "comercial": "8928308280fffff",  # hex do centro comercial
        "residencial_alta_renda": "...",
    }
}
```

**Artefatos persistidos:**
- Modelo UMAP: `models/{station_code}_umap_{timestamp}.joblib`
- Scatter plot 2D: `models/{station_code}_umap_scatter_{timestamp}.png`
- Máximo 3 modelos por base (purge automático)

---

### Fase 5 — Similarity Score + Potential Score

**Responsabilidade:** Calcular score de cada hexágono baseado em similaridade com perfis de referência.

**Fórmula:**

```python
# Projeta perfis de referência no espaço UMAP
success_umap = umap_model.transform([success_vector])[0]
failure_umap = umap_model.transform([failure_vector])[0]

# Similaridade coseno
sim_positive = cosine_similarity(cell_umap, success_umap)
sim_negative = cosine_similarity(cell_umap, failure_umap)

# Score bruto
raw_score = sim_positive - (FAILURE_PENALTY_WEIGHT * sim_negative)

# Penalidade por histórico de saída rápida (< 180 dias por area_signal)
if hex_has_fast_exit_history:
    raw_score -= FAST_EXIT_PENALTY  # padrão: 0.20

# Filtro de viabilidade (não é score, é gate)
if delivery_density_r8 < DELIVERY_DENSITY_THRESHOLD:
    raw_score = 0.0

# Normalização [0, 100] por DS
potential_score = normalize_to_100(raw_score)
```

**Agregação por território:**
```python
territory_score = weighted_average(
    [cell_scores[h] for h in territory_h3_ids_r8],
    weights=[delivery_density_r8[h] for h in territory_h3_ids_r8],
)
gap = territory_score - (current_partners / ideal_slots * 100)
```

---

### Fase 6 — Area Selector

**Responsabilidade:** Selecionar conjunto mínimo de territórios para atingir `target_pct` de volume.

```python
def select_areas(
    territory_scores: list[TerritoryScore],
    territory_h3_ids_r8: dict[str, list[str]],
    territory_h3_ids_r9: dict[str, list[str]],   # novo: res 9 para CP-SAT
    territory_region_types: dict[str, RegionType],
    territory_model_confidence: dict[str, float],
    territory_volumes: dict[str, int],
    partner_profiles: list[PartnerProfile],        # novo: para repeated_failure
    target_pct: float,
) -> list[SelectedTerritory]:
```

**`repeated_failure`:** território com 2+ parceiros Exited `area_signal` → flag visível no output.

---

### Fase 7 — CP-SAT Ideal Supply (res 9)

Sem mudanças na lógica do solver. Recebe `h3_ids_r9` dos `SelectedTerritory` e opera exatamente como hoje. Output: `GeoIdealSlot[]` com `matched_partner_id = None`.

---

### Daily — Territory Fit

Sem mudanças na lógica implementada em `geo_daily.py`. Hierarquia de fallback:
1. Hex exato em `hex_ids`
2. Point-in-polygon (Shapely + `territories.geojson`)
3. Centroide geométrico do polígono
4. Centroide dos slots (`territories_index.json`)

---

## Configuration (`geo_config.py`)

```python
# Resolução H3
H3_RES_ANALYSIS = 8    # análise de área
H3_RES_SUPPLY   = 9    # posicionamento de slots (CP-SAT)

# Thresholds
DELIVERY_DENSITY_THRESHOLD = 5      # pacotes/dia mínimos em res 8
MIN_TENURE_DAYS_FOR_PROFILE = 30    # tenure mínimo para entrar no perfil
FAST_EXIT_THRESHOLD_DAYS = 180      # saída rápida = penalidade extra
FAST_EXIT_PENALTY = 0.20            # penalidade no raw_score [0-1]
FAILURE_PENALTY_WEIGHT = 0.5        # peso da similaridade negativa
LOW_COVERAGE_WARNING_PCT = 10.0     # % mínimo de hexágonos com parceiro

# UMAP
UMAP_N_COMPONENTS = 2
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.1
UMAP_RANDOM_STATE = 42

# Potential score weights
POTENTIAL_WEIGHTS = {
    "target_business_density":  0.25,
    "avg_income":               0.20,
    "population_density":       0.15,
    "region_type_weight":       0.20,
    "road_connectivity_index":  0.10,
    "commercial_activity_index": 0.10,
}
DELIVERY_DENSITY_WEIGHT = 0.10  # peso máximo do volume no score

# Exit reason classification
EXIT_REASON_MAP = {
    "volume_insuficiente":    {"class": "area_signal",    "penalty": 1.0},
    "acesso_dificil":         {"class": "area_signal",    "penalty": 0.8},
    "sobreposicao":           {"class": "area_signal",    "penalty": 0.5},
    "falencia":               {"class": "partner_signal", "penalty": 0.0},
    "desistencia_voluntaria": {"class": "partner_signal", "penalty": 0.0},
    "compliance":             {"class": "partner_signal", "penalty": 0.0},
    "operacional":            {"class": "partner_signal", "penalty": 0.2},
}

# Semantic anchors (optional, per station)
SEMANTIC_ANCHORS: dict[str, dict[str, str]] = {}
```

---

## Turso Schema Changes

### Nova tabela: `geo_partner_profiles`

```sql
CREATE TABLE IF NOT EXISTS geo_partner_profiles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    station_code  TEXT NOT NULL,
    profile_type  TEXT NOT NULL,  -- 'success' | 'failure'
    vector_json   TEXT NOT NULL,  -- JSON array de floats
    n_partners    INTEGER,
    avg_tenure_days REAL,
    profile_coverage REAL,
    low_coverage_warning INTEGER,
    is_global_fallback   INTEGER,
    created_at    TEXT NOT NULL
)
```

### Nova tabela: `geo_partner_history`

```sql
CREATE TABLE IF NOT EXISTS geo_partner_history (
    salesforce_id        TEXT NOT NULL,
    station_code         TEXT NOT NULL,
    h3_id_r8             TEXT NOT NULL,
    status               TEXT NOT NULL,
    tenure_days          INTEGER,
    exit_reason_code     TEXT,
    exit_reason_class    TEXT,
    launch_date          TEXT,
    exited_date          TEXT,
    run_id               TEXT NOT NULL,
    PRIMARY KEY (salesforce_id, run_id)
)
```

### Alteração: `geo_ideal_supply`

Coluna `matched_partner_id TEXT` já adicionada na v1.

### Alteração: `geo_run_metadata`

Adicionar colunas:
```sql
ALTER TABLE geo_run_metadata ADD COLUMN umap_params TEXT;
ALTER TABLE geo_run_metadata ADD COLUMN n_clusters INTEGER;
ALTER TABLE geo_run_metadata ADD COLUMN low_quality_clustering INTEGER;
ALTER TABLE geo_run_metadata ADD COLUMN profile_coverage REAL;
```

---

## CLI

```bash
# Setup completo (fases 1-7)
python geo_intelligence/geo_orchestrator.py --mode setup --target 50
python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2 DSP4

# Daily matching
python geo_intelligence/geo_orchestrator.py --mode daily
python geo_intelligence/geo_orchestrator.py --mode daily --stations DSP2

# Atualizar heatmap sem refazer setup
python geo_intelligence/geo_orchestrator.py --update-heatmap --stations DSP2
```

---

## Correctness Properties (PBT)

1. `potential_score` ∈ [0, 100] para todo hexágono
2. `gap` = `potential_score - (current_partners / ideal_slots * 100)` para todo território com `ideal_slots > 0`
3. Hexágonos com `delivery_density_r8 < threshold` têm `potential_score = 0`
4. `sum(volume[t] for t in selected) >= target_pct * total_volume`
5. `tenure_weight = log(1 + tenure_days)` é monotonicamente crescente
6. Parceiros Exited com `partner_signal` não contribuem para `failure_vector`
7. `profile_coverage` = `|{h ∈ hexágonos : ∃ parceiro em grid_disk(h, 1)}| / |hexágonos|`
8. `repeated_failure = True` iff `count(exited_area_signal in territory) >= 2`
