# Hub Delivery Optimization System

> Sistema de otimização de rede de parceiros logísticos last-mile baseado em hexágonos H3 e solver CP-SAT.
>
> Last-mile logistics partner network optimization system based on H3 hexagons and CP-SAT solver.

---

## Índice / Table of Contents

- [Português](#português)
  - [Objetivo](#objetivo)
  - [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
  - [Estrutura de Arquivos](#estrutura-de-arquivos)
  - [Fluxo de Execução](#fluxo-de-execução)
  - [Artefatos Gerados](#artefatos-gerados)
  - [Comportamento com --stations](#comportamento-com---stations)
  - [Como Usar](#como-usar)
  - [Configuração](#configuração)
  - [Dependências](#dependências)
  - [Notas de Implementação](#notas-de-implementação)
- [English](#english)
  - [Objective](#objective)
  - [Architecture Overview](#architecture-overview)
  - [File Structure](#file-structure)
  - [Execution Flow](#execution-flow)
  - [Generated Artifacts](#generated-artifacts)
  - [Behavior with --stations](#behavior-with---stations)
  - [How to Use](#how-to-use)
  - [Configuration](#configuration)
  - [Dependencies](#dependencies)
  - [Implementation Notes](#implementation-notes)

---

# Português

## Objetivo

O sistema identifica os pontos geográficos ideais para alocação de parceiros logísticos (hubs de entrega) em bases de distribuição last-mile, dividindo a área de cobertura de cada base em territórios equilibrados e acompanhando diariamente o atingimento de parceiros reais frente ao cenário ideal calculado.

**Problema resolvido:** dada uma base histórica de demanda de entregas (lat/lon, CEP, data), o sistema responde:
1. Onde deveriam estar os parceiros logísticos? (Modo Setup)
2. Quantos slots ideais cada território precisa? (Modo Setup)
3. Quais parceiros existentes cobrem quais vagas? (Modo Daily)
4. Qual o attainment atual e quais oportunidades estão em aberto? (Modo Daily)

---

## Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   MODO SETUP                        │
│  (executa uma vez / ao reorganizar a rede)          │
│                                                     │
│  load_packages → filtro jurisdição → solver CP-SAT  │
│  → dedup de slots → K-means UTM (cotas iguais)      │
│  → Voronoi por componente → clip jurisdição         │
│  → territories.geojson + ideal_supply.json          │
│    + heatmap.geojson + territories_index.json       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   MODO DAILY                        │
│  (executa todo dia com dados de parceiros frescos)  │
│                                                     │
│  load_partners → matching hierárquico (Fase 3)      │
│  → webleads (Fase 4) → relatórios (Fase 5)          │
│  → OPORTUNIDADES_ESTRATEGICAS.txt                   │
│  → RELATORIO_EXECUTIVO.txt                          │
│  → PARTNERS_PER_DS_BUCKET.csv                       │
│  → webleads_evaluated.csv                           │
│  → optimization_data.geojson                        │
└─────────────────────────────────────────────────────┘
```

---

## Estrutura de Arquivos

```
backend/
│
├── orchestrator.py          # Ponto de entrada CLI (--mode setup / --mode daily)
├── phase_setup.py           # Setup completo: solver + K-means + polígonos
├── phase3_partner_fit.py    # Matching hierárquico de parceiros com vagas
├── phase4_webleads.py       # Qualificação e roteamento de web leads
├── phase5_reports.py        # Geração de todos os artefatos de saída
│
├── load_packages.py         # Carregamento do histórico de pacotes
├── load_partners.py         # Carregamento de parceiros e jurisdições
├── models.py                # Dataclasses centrais, Config e load_territories
├── phase2_ideal_supply.py   # Persistência e carregamento de slots ideais
│
├── config.py                # Configurações da operação (não versionado)
│
└── data/
    └── jurisdiction.geojson # Polígonos de jurisdição por base (Polygon ou MultiPolygon)
```

> `models.py` contém `TerritoriesResult`, `load_territories` e todas as dataclasses do sistema.
> `phase2_ideal_supply.py` contém `IdealSupplyResult` e `load_ideal_supply`, usados pelo modo daily.

---

## Fluxo de Execução

### Modo Setup — "Onde deveriam estar os parceiros?"

```
1. load_packages()
   └─ Lê CSV histórico de pacotes (lat, lon, cep, station_code, plan_date)
   └─ Converte lat/lon → hexágonos H3 (resolução configurável por base)
   └─ Resolve conflitos de hexes em múltiplas bases (winner-takes-all)

2. Filtro de jurisdição + Solver CP-SAT por base (paralelo)
   └─ Remove hexes cujo centróide está fora do polígono de jurisdição
   └─ Para cada hex ativo: semente de maior demanda residual
   └─ CP-SAT escolhe raio mínimo que atinge MIN_CAP pacotes/dia
   └─ Maximiza pacotes alocados, penaliza raios maiores
   └─ Itera até não restar demanda ≥ MIN_CAP em nenhum hex

3. Deduplicação de slots (pós-processamento CP-SAT)
   └─ Mesmo origin_hex + mesmo radius_s → merge (soma capacity_s e allocations)
   └─ Mesmo origin_hex + radius_s diferentes → mantém apenas o de menor raio
   └─ Garante: um ponto geográfico = um parceiro

4. K-means geoespacial em UTM com cotas iguais
   └─ Converte lat/lon → UTM (metros) para evitar distorção geográfica
   └─ K-means++ com múltiplos restarts → melhores centroides
   └─ linear_sum_assignment garante exatamente ⌊N/K⌋ ou ⌈N/K⌉ slots por território

5. Construção de polígonos de território
   └─ Decompõe jurisdição em componentes (suporte a MultiPolygon)
   └─ Componentes sem slots → atribuídas diretamente ao cluster mais próximo
   └─ Voronoi de grafo por componente → células compactas
   └─ Expansão iterativa para cobrir bordas residuais
   └─ Suavização morfológica (buffer/erode)
   └─ Clip final pela jurisdição completa → MultiPolygon preservado

6. Heatmap
   └─ Spatial join: centróide do hex → polígono de território
   └─ Apenas hexes dentro da jurisdição (consistência com o solver)
```

### Modo Daily — "Como estamos hoje?"

```
3. Matching hierárquico (Fase 3)
   └─ Hierarquia: Active → Onboarding → BG Checks → Prospect → Inactive/Exited
   └─ Elegibilidade: parceiro em grid_disk(slot.origin_hex, 1) → ~900m
   └─ Vagas ordenadas por demanda decrescente (áreas críticas primeiro)
   └─ Greedy: para cada vaga, melhor parceiro disponível na vizinhança
   └─ Atualiza ideal_supply.json com matched_partner_id
   └─ Atualiza territories.geojson com attainment e accuracy por território

4. Web Leads (Fase 4)
   └─ Resolve CEP → hex (busca exata → maior demanda se múltiplos hexes)
   └─ Hex → territory_id via territories_index.json
   └─ Atribui Account Manager (ADE) responsável pelo território

5. Relatórios (Fase 5)
   └─ OPORTUNIDADES_ESTRATEGICAS.txt: slots em aberto por base/CTL/território
   └─ RELATORIO_EXECUTIVO.txt: resumo com cobertura, attainment, demanda
   └─ PARTNERS_PER_DS_BUCKET.csv: parceiros por território com matched_slot_id
   └─ webleads_evaluated.csv: leads com territory_id, CEP e OwnerId
   └─ optimization_data.geojson: 3 camadas (hexes + parceiros + slots abertos)
```

---

## Artefatos Gerados

### Setup

| Arquivo | Descrição |
|---|---|
| `territories.geojson` | Polígono (ou MultiPolygon) por território. Propriedades: `territory_id`, `delivery_station`, `bdm_cluster`, `n_slots`, `daily_demand`, `attainment`, `coverage`, `geom_type` |
| `ideal_supply.json` | Slots ideais por território. Cada slot: `slot_id`, `origin_hex`, `radius_s`, `capacity_s`, `lat`, `lon`, `allocations`, `matched_partner_id` |
| `heatmap.geojson` | Hexágonos H3 com `hex_id`, `demand_total`, `ceps`, `delivery_station`, `territory_id` |
| `territories_index.json` | Metadados dos territórios para lookup rápido nas fases daily |

> Territórios em jurisdições MultiPolygon podem ter geometria `MultiPolygon` — isso é esperado e correto.

### Daily

| Arquivo | Descrição |
|---|---|
| `OPORTUNIDADES_ESTRATEGICAS.txt` | Vagas em aberto por base → CTL → território, com localização, CEPs-alvo e link Google Maps |
| `RELATORIO_EXECUTIVO.txt` | Resumo por base e detalhamento por território: vagas, parceiros por status, cobertura, attainment, acuracidade |
| `PARTNERS_PER_DS_BUCKET.csv` | `station_code`, `territory_id`, `status`, `entity_type`, `salesforce_id`, `partner_name`, `store_id`, `decision`, `matched_slot_id` |
| `webleads_evaluated.csv` | `Id`, `Delivery Station`, `Cep`, `Jurisdiction`, `Name`, `OwnerId`, `decision` |
| `optimization_data.geojson` | 3 camadas: `TERRITORY_HEX` (hexes), `PARTNER_POINT` (parceiros), `IDEAL_SLOT` (vagas abertas) |

---

## Comportamento com --stations

Ao usar `--stations` em qualquer modo, o sistema faz **merge inteligente** dos arquivos de saída:

- Lê os arquivos existentes
- Remove apenas as entradas das stations especificadas
- Insere os dados recém-gerados
- Preserva intactos os dados de todas as outras stations

Isso vale para setup (`territories.geojson`, `heatmap.geojson`, `territories_index.json`, `ideal_supply.json`) e para daily (`PARTNERS_PER_DS_BUCKET.csv`, `webleads_evaluated.csv`, `optimization_data.geojson`).

Os relatórios `.txt` são sempre gerados apenas com as stations processadas na execução atual.

---

## Como Usar

### Pré-requisitos

```bash
pip install h3 pandas numpy scipy shapely ortools pyproj
```

> `pyproj` é necessário para a projeção UTM usada na construção dos polígonos. Sem ele, o sistema usa WGS84 como fallback (menos preciso).

### Primeira execução (Setup)

```bash
# Processar todas as bases
python orchestrator.py --mode setup

# Processar apenas bases específicas (merge com dados existentes)
python orchestrator.py --mode setup --stations DSP2 DSP4

# Definir pasta de saída e número de workers paralelos
python orchestrator.py --mode setup --output data/ --workers 8
```

O setup deve ser reexecutado ao:
- Alterar a área de cobertura de uma base (`jurisdiction.geojson`)
- Alterar o número de territórios por base (`CLUSTER_PER_STATION`)
- Após atualização significativa do histórico de demanda

### Execução diária (Daily)

```bash
# Execução padrão (lê artefatos do setup na pasta configurada)
python orchestrator.py --mode daily

# Filtrando bases (merge com dados existentes)
python orchestrator.py --mode daily --stations DSP2

# Com pasta de saída específica
python orchestrator.py --mode daily --output data/

# Compatibilidade com nomes antigos de bucket no config de Account Managers
python orchestrator.py --mode daily --legacy-buckets
```

> O modo daily falha com mensagem descritiva se `territories_index.json` ou `ideal_supply.json` não existirem.

---

## Configuração

Todas as configurações ficam em `config.py` (não versionado):

```python
# Caminhos dos dados de entrada
BASE_PACKAGES     = "data/packages.csv"
BASE_PARTNERS     = "data/partners.json"
BASE_JURISDICTION = "data/jurisdiction.geojson"

# Pasta de saída
DEST_FOLDER = "data/"

# H3 — resolução global e por base (bases grandes usam res 8, menores res 9)
H3_RESOLUTION = 9
H3_RES_PER_STATION = {"DSP2": 8, "DRJ3": 8}

# Capacidade de parceiros (pacotes/dia)
MIN_CAPACITY = 40
MAX_CAPACITY = 42

# Raios de atuação (metros) e penalidades no solver
RADII_M = [
    {"radius_s": 200,  "hex_distance": 1, "penalty": 0},
    {"radius_s": 500,  "hex_distance": 2, "penalty": 10},
    {"radius_s": 1000, "hex_distance": 3, "penalty": 20},
]

# Número de territórios por base
CLUSTER_PER_STATION = {
    "DSP2": 8,
    "DBH5": 4,
}

# Account Managers (ADEs) por território
ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "00XXXXX", "buckets": ["DSP2_bucket-01", "DSP2_bucket-02"]},
]

# BDM Clusters (definidos em models.py — Config.BDM_CLUSTERS)
```

---

## Dependências

| Biblioteca | Versão mínima | Uso |
|---|---|---|
| `h3` | 4.x | Indexação geoespacial em hexágonos |
| `pandas` | 1.5+ | Manipulação de dados tabulares |
| `numpy` | 1.23+ | Operações matriciais (K-means, UTM) |
| `scipy` | 1.9+ | Voronoi (`scipy.spatial`) e assignment (`scipy.optimize`) |
| `shapely` | 2.0+ | Operações em polígonos (union, clip, spatial join) |
| `ortools` | 9.x | Solver CP-SAT para encontrar slots ideais |
| `pyproj` | 3.x | Projeção UTM para cálculos métricos precisos |

---

## Notas de Implementação

### Deduplicação de Slots (CP-SAT)

Hexes com demanda > MAX_CAP geram múltiplos slots no mesmo ponto geográfico. O pós-processamento `_merge_duplicate_slots` resolve isso:

- **Mesmo `origin_hex` + mesmo `radius_s`** → merge: soma `capacity_s` e `allocations`
- **Mesmo `origin_hex` + `radius_s` diferentes** → mantém apenas o de menor raio, descarta os demais

### Polígonos com Jurisdição MultiPolygon

Quando a jurisdição de uma base é um `MultiPolygon` (áreas separadas geograficamente):

1. O Voronoi é calculado separadamente dentro de cada componente
2. Componentes sem slots são atribuídas diretamente ao cluster mais próximo (evita geometrias degeneradas)
3. O clip final pela jurisdição pode resultar em `MultiPolygon` por território — isso é correto e esperado
4. O GeoJSON serializa `MultiPolygon` nativamente

### K-means com Cotas Iguais em UTM

- Coordenadas convertidas para UTM (metros) antes de qualquer cálculo de distância
- `linear_sum_assignment` garante exatamente ⌊N/K⌋ ou ⌈N/K⌉ slots por território (diferença máxima de 1)
- 15 restarts com K-means++ para encontrar os melhores centroides

### Merge Inteligente com --stations

Ao rodar com `--stations`, nenhum dado de outras bases é perdido. O sistema lê os arquivos existentes, filtra as stations especificadas e reinsere os dados atualizados — comportamento idêntico nos modos setup e daily.

---

# English

## Objective

The system identifies ideal geographic locations for last-mile delivery partner (hub) allocation across distribution stations, dividing each station's coverage area into balanced territories and tracking daily how existing partners match the calculated ideal scenario.

**Problem solved:** given a historical delivery demand dataset (lat/lon, ZIP, date), the system answers:
1. Where should logistics partners be located? (Setup Mode)
2. How many ideal slots does each territory need? (Setup Mode)
3. Which existing partners cover which slots? (Daily Mode)
4. What is the current attainment and which opportunities are open? (Daily Mode)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   SETUP MODE                        │
│  (runs once / when reorganizing the network)        │
│                                                     │
│  load_packages → jurisdiction filter → CP-SAT solver│
│  → slot dedup → K-means UTM (equal quotas)          │
│  → Voronoi per component → jurisdiction clip        │
│  → territories.geojson + ideal_supply.json          │
│    + heatmap.geojson + territories_index.json       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   DAILY MODE                        │
│  (runs every day with fresh partner data)           │
│                                                     │
│  load_partners → hierarchical matching (Phase 3)    │
│  → webleads (Phase 4) → reports (Phase 5)           │
│  → OPORTUNIDADES_ESTRATEGICAS.txt                   │
│  → RELATORIO_EXECUTIVO.txt                          │
│  → PARTNERS_PER_DS_BUCKET.csv                       │
│  → webleads_evaluated.csv                           │
│  → optimization_data.geojson                        │
└─────────────────────────────────────────────────────┘
```

---

## File Structure

```
backend/
│
├── orchestrator.py          # CLI entry point (--mode setup / --mode daily)
├── phase_setup.py           # Full setup: solver + K-means + polygons
├── phase3_partner_fit.py    # Hierarchical partner-to-slot matching
├── phase4_webleads.py       # Web lead qualification and routing
├── phase5_reports.py        # All output artifact generation
│
├── load_packages.py         # Historical package data loader
├── load_partners.py         # Partner and jurisdiction loader
├── models.py                # Central dataclasses, Config and load_territories
├── phase2_ideal_supply.py   # Ideal slot persistence and loading
│
├── config.py                # Operational settings (not versioned)
│
└── data/
    └── jurisdiction.geojson # Jurisdiction polygons per station (Polygon or MultiPolygon)
```

> `models.py` owns `TerritoriesResult`, `load_territories` and all system dataclasses.
> `phase2_ideal_supply.py` owns `IdealSupplyResult` and `load_ideal_supply`, used by daily mode.

---

## Execution Flow

### Setup Mode — "Where should partners be?"

```
1. load_packages()
   └─ Reads historical package CSV (lat, lon, zip, station_code, plan_date)
   └─ Converts lat/lon → H3 hexagons (resolution configurable per station)
   └─ Resolves hex conflicts across stations (winner-takes-all by volume)

2. Jurisdiction filter + CP-SAT solver per station (parallel)
   └─ Removes hexes whose centroid falls outside the jurisdiction polygon
   └─ For each active hex: seed with highest residual demand
   └─ CP-SAT chooses minimum radius achieving MIN_CAP packages/day
   └─ Maximizes allocated packages, penalizes larger radii
   └─ Iterates until no hex has residual demand ≥ MIN_CAP

3. Slot deduplication (CP-SAT post-processing)
   └─ Same origin_hex + same radius_s → merge (sum capacity_s and allocations)
   └─ Same origin_hex + different radius_s → keep only the smallest radius
   └─ Guarantees: one geographic point = one partner

4. Geospatial K-means in UTM with equal quotas
   └─ Converts lat/lon → UTM (meters) to avoid geographic distortion
   └─ K-means++ with multiple restarts → best centroids
   └─ linear_sum_assignment guarantees exactly ⌊N/K⌋ or ⌈N/K⌉ slots per territory

5. Territory polygon construction
   └─ Decomposes jurisdiction into components (MultiPolygon support)
   └─ Components without slots → assigned directly to nearest cluster
   └─ Voronoi per component → compact cells
   └─ Iterative expansion to cover residual border gaps
   └─ Morphological smoothing (buffer/erode)
   └─ Final clip by full jurisdiction → MultiPolygon preserved

6. Heatmap
   └─ Spatial join: hex centroid → territory polygon
   └─ Only hexes inside jurisdiction (consistent with solver)
```

### Daily Mode — "How are we doing today?"

```
3. Hierarchical matching (Phase 3)
   └─ Priority: Active → Onboarding → BG Checks → Prospect → Inactive/Exited
   └─ Eligibility: partner within grid_disk(slot.origin_hex, 1) → ~900m
   └─ Slots ordered by demand descending (critical areas first)
   └─ Greedy: for each slot, best available partner in neighborhood
   └─ Updates ideal_supply.json with matched_partner_id
   └─ Updates territories.geojson with attainment and accuracy per territory

4. Web Leads (Phase 4)
   └─ Resolves ZIP → hex (exact match → highest demand if multiple hexes)
   └─ Hex → territory_id via territories_index.json
   └─ Assigns responsible Account Manager (ADE) per territory

5. Reports (Phase 5)
   └─ OPORTUNIDADES_ESTRATEGICAS.txt: open slots per station/CTL/territory
   └─ RELATORIO_EXECUTIVO.txt: coverage, attainment, demand summary
   └─ PARTNERS_PER_DS_BUCKET.csv: partners per territory with matched_slot_id
   └─ webleads_evaluated.csv: leads with territory_id, ZIP and OwnerId
   └─ optimization_data.geojson: 3 layers (hexes + partners + open slots)
```

---

## Generated Artifacts

### Setup

| File | Description |
|---|---|
| `territories.geojson` | Polygon (or MultiPolygon) per territory. Properties: `territory_id`, `delivery_station`, `bdm_cluster`, `n_slots`, `daily_demand`, `attainment`, `coverage`, `geom_type` |
| `ideal_supply.json` | Ideal slots per territory. Each slot: `slot_id`, `origin_hex`, `radius_s`, `capacity_s`, `lat`, `lon`, `allocations`, `matched_partner_id` |
| `heatmap.geojson` | H3 hexagons with `hex_id`, `demand_total`, `ceps`, `delivery_station`, `territory_id` |
| `territories_index.json` | Territory metadata for fast lookup in daily phases |

> Territories in MultiPolygon jurisdictions may have `MultiPolygon` geometry — this is expected and correct.

### Daily

| File | Description |
|---|---|
| `OPORTUNIDADES_ESTRATEGICAS.txt` | Open slots per station → CTL → territory, with location, target ZIPs and Google Maps link |
| `RELATORIO_EXECUTIVO.txt` | Station summary and per-territory breakdown: slots, partners by status, coverage, attainment, accuracy |
| `PARTNERS_PER_DS_BUCKET.csv` | `station_code`, `territory_id`, `status`, `entity_type`, `salesforce_id`, `partner_name`, `store_id`, `decision`, `matched_slot_id` |
| `webleads_evaluated.csv` | `Id`, `Delivery Station`, `Cep`, `Jurisdiction`, `Name`, `OwnerId`, `decision` |
| `optimization_data.geojson` | 3 layers: `TERRITORY_HEX` (hexes), `PARTNER_POINT` (partners), `IDEAL_SLOT` (open slots) |

---

## Behavior with --stations

When using `--stations` in any mode, the system performs **intelligent merge** of output files:

- Reads existing files
- Removes only entries for the specified stations
- Inserts newly generated data
- Preserves all other stations' data intact

This applies to setup (`territories.geojson`, `heatmap.geojson`, `territories_index.json`, `ideal_supply.json`) and daily (`PARTNERS_PER_DS_BUCKET.csv`, `webleads_evaluated.csv`, `optimization_data.geojson`).

The `.txt` reports are always generated only with the stations processed in the current run.

---

## How to Use

### Prerequisites

```bash
pip install h3 pandas numpy scipy shapely ortools pyproj
```

> `pyproj` is required for UTM projection used in polygon construction. Without it, the system falls back to WGS84 (less accurate).

### First Run (Setup)

```bash
# Process all stations
python orchestrator.py --mode setup

# Process specific stations only (merges with existing data)
python orchestrator.py --mode setup --stations DSP2 DSP4

# Custom output folder and parallel workers
python orchestrator.py --mode setup --output data/ --workers 8
```

Re-run setup when:
- A station's jurisdiction polygon changes (`jurisdiction.geojson`)
- The number of territories per station changes (`CLUSTER_PER_STATION`)
- After a significant update to the demand history

### Daily Run

```bash
# Standard run
python orchestrator.py --mode daily

# Filter specific stations (merges with existing data)
python orchestrator.py --mode daily --stations DSP2

# Custom output folder
python orchestrator.py --mode daily --output data/

# Legacy bucket name compatibility for Account Manager config
python orchestrator.py --mode daily --legacy-buckets
```

> Daily mode aborts with a descriptive message if `territories_index.json` or `ideal_supply.json` do not exist.

---

## Configuration

All settings are in `config.py` (not versioned):

```python
BASE_PACKAGES     = "data/packages.csv"
BASE_PARTNERS     = "data/partners.json"
BASE_JURISDICTION = "data/jurisdiction.geojson"
DEST_FOLDER       = "data/"

H3_RESOLUTION          = 9
H3_RES_PER_STATION     = {"DSP2": 8, "DRJ3": 8}

MIN_CAPACITY = 40
MAX_CAPACITY = 42

RADII_M = [
    {"radius_s": 200,  "hex_distance": 1, "penalty": 0},
    {"radius_s": 500,  "hex_distance": 2, "penalty": 10},
    {"radius_s": 1000, "hex_distance": 3, "penalty": 20},
]

CLUSTER_PER_STATION = {"DSP2": 8, "DBH5": 4}

ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "00XXXXX", "buckets": ["DSP2_bucket-01", "DSP2_bucket-02"]},
]
```

---

## Dependencies

| Library | Min Version | Usage |
|---|---|---|
| `h3` | 4.x | Geospatial hexagon indexing |
| `pandas` | 1.5+ | Tabular data manipulation |
| `numpy` | 1.23+ | Matrix operations (K-means, UTM) |
| `scipy` | 1.9+ | Voronoi (`scipy.spatial`) and assignment (`scipy.optimize`) |
| `shapely` | 2.0+ | Polygon operations (union, clip, spatial join) |
| `ortools` | 9.x | CP-SAT solver for ideal slot finding |
| `pyproj` | 3.x | UTM projection for accurate metric calculations |

---

## Implementation Notes

### Slot Deduplication (CP-SAT)

Hexes with demand > MAX_CAP generate multiple slots at the same geographic point. The `_merge_duplicate_slots` post-processing resolves this:

- **Same `origin_hex` + same `radius_s`** → merge: sum `capacity_s` and `allocations`
- **Same `origin_hex` + different `radius_s`** → keep only the smallest radius, discard the rest

### Polygons with MultiPolygon Jurisdiction

When a station's jurisdiction is a `MultiPolygon` (geographically separate areas):

1. Voronoi is computed separately within each component
2. Components without slots are assigned directly to the nearest cluster (avoids degenerate geometries)
3. The final clip by jurisdiction may result in `MultiPolygon` per territory — this is correct and expected
4. GeoJSON serializes `MultiPolygon` natively

### K-means with Equal Quotas in UTM

- Coordinates converted to UTM (meters) before any distance calculation
- `linear_sum_assignment` guarantees exactly ⌊N/K⌋ or ⌈N/K⌉ slots per territory (max difference of 1)
- 15 restarts with K-means++ to find the best centroids

### Intelligent Merge with --stations

When running with `--stations`, no data from other stations is lost. The system reads existing files, filters the specified stations, and reinserts updated data — identical behavior in both setup and daily modes.
