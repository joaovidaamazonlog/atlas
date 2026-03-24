# Hub Delivery Optimization System

> Sistema de otimização de rede de parceiros logísticos last-mile baseado em hexágonos H3 e solver CP-SAT.
>
> Last-mile logistics partner network optimization system based on H3 hexagons and CP-SAT solver.

---

## Índice / Table of Contents

- [Hub Delivery Optimization System](#hub-delivery-optimization-system)
  - [Índice / Table of Contents](#índice--table-of-contents)
- [Português](#português)
  - [Objetivo](#objetivo)
  - [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
  - [Estrutura de Arquivos](#estrutura-de-arquivos)
  - [Fluxo de Execução](#fluxo-de-execução)
    - [Modo Setup — "Onde deveriam estar os parceiros?"](#modo-setup--onde-deveriam-estar-os-parceiros)
    - [Modo Daily — "Como estamos hoje?"](#modo-daily--como-estamos-hoje)
  - [Artefatos Gerados](#artefatos-gerados)
    - [Setup](#setup)
    - [Daily](#daily)
  - [Como Usar](#como-usar)
    - [Pré-requisitos](#pré-requisitos)
    - [Primeira execução (Setup)](#primeira-execução-setup)
    - [Execução diária (Daily)](#execução-diária-daily)
  - [Configuração](#configuração)
  - [Dependências](#dependências)
  - [Notas de Implementação](#notas-de-implementação)
    - [Consistência de Dados no Setup](#consistência-de-dados-no-setup)
    - [K-means com Cotas Iguais](#k-means-com-cotas-iguais)
- [English](#english)
  - [Objective](#objective)
  - [Architecture Overview](#architecture-overview)
  - [File Structure](#file-structure)
  - [Execution Flow](#execution-flow)
    - [Setup Mode — "Where should partners be?"](#setup-mode--where-should-partners-be)
    - [Daily Mode — "How are we doing today?"](#daily-mode--how-are-we-doing-today)
  - [Generated Artifacts](#generated-artifacts)
    - [Setup](#setup-1)
    - [Daily](#daily-1)
  - [How to Use](#how-to-use)
    - [Prerequisites](#prerequisites)
    - [First Run (Setup)](#first-run-setup)
    - [Daily Run](#daily-run)
  - [Configuration](#configuration)
  - [Dependencies](#dependencies)

---

# Português

## Objetivo

O sistema tem como objetivo identificar os pontos geográficos ideais para alocação de parceiros logísticos (hubs de entrega) em bases de distribuição last-mile, dividindo a área de cobertura de cada base em territórios equilibrados e acompanhando diariamente o atingimento de parceiros reais frente ao cenário ideal calculado.

**Problema resolvido:** dada uma base histórica de demanda de entregas (lat/lon, CEP, data), o sistema responde:
1. Onde deveriam estar os parceiros logísticos? (Modo Setup)
2. Quantos slots ideais cada território precisa? (Modo Setup)
3. Quais parceiros existentes cobrem quais vagas? (Modo Daily)
4. Qual o attainment atual e quais oportunidades estão em aberto? (Modo Daily)

---

## Visão Geral da Arquitetura

O sistema opera em dois modos independentes:

```
┌─────────────────────────────────────────────────────┐
│                   MODO SETUP                        │
│  (executa uma vez / ao reorganizar a rede)          │
│                                                     │
│  load_packages → solver CP-SAT → K-means constrained│
│  → polígonos Voronoi → territories.geojson          │
│                      → ideal_supply.json            │
│                      → heatmap.geojson              │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   MODO DAILY                        │
│  (executa todo dia com dados de parceiros frescos)  │
│                                                     │
│  load_partners → matching hierárquico → webleads    │
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
projeto/
│
├── orchestrator.py          # Ponto de entrada (CLI)
│
├── phase_setup.py           # Setup: solver + clustering + polígonos
├── phase3_partner_fit.py    # Matching de parceiros com vagas ideais
├── phase4_webleads.py       # Qualificação de web leads
├── phase5_reports.py        # Geração de todos os relatórios
│
├── load_packages.py         # Carregamento do histórico de pacotes
├── load_partners.py         # Carregamento de parceiros e jurisdições
├── models.py                # Dataclasses e Config central
│
├── phase1_territories.py    # Persistência e carregamento de territórios
├── phase2_ideal_supply.py   # Persistência e carregamento de slots
│
├── config.py                # Configurações da operação (não versionado)
│
└── data/
    └── jurisdiction.geojson # Polígonos de jurisdição por base
```

> `phase1_territories.py` e `phase2_ideal_supply.py` são utilizados no modo daily para carregar os artefatos persistidos pelo setup. A formação de territórios e slots é feita inteiramente pelo `phase_setup.py`.

---

## Fluxo de Execução

### Modo Setup — "Onde deveriam estar os parceiros?"

```
1. load_packages()
   └─ Lê CSV histórico de pacotes (lat, lon, cep, station_code, plan_date)
   └─ Converte lat/lon → hexágonos H3 (resolução 9, configurável por base)
   └─ Resolve conflitos de hexes em múltiplas bases (winner-takes-all)
   └─ Retorna demanda total bruta por hex

2. Solver CP-SAT por base (paralelo)
   └─ **IMPORTANTE:** Filtra demand_map por jurisdição antes do processamento
   └─ Apenas hexes com centroide DENTRO do polígono de jurisdição são processados
   └─ Para cada hex ativo: encontra semente de maior demanda residual
   └─ CP-SAT escolhe raio mínimo que atinge MIN_CAP pacotes/dia
   └─ Maximiza pacotes alocados, penaliza raios maiores
   └─ Itera até não restar demanda ≥ MIN_CAP em nenhum hex
   └─ Resultado: N slots ideais por base com lat/lon, raio e capacidade
   └─ demand_map filtrado é reutilizado para construir heatmap.geojson (garantia de consistência)

3. K-means constrained (cotas iguais)
   └─ K-means++ geográfico encontra K centroides ótimos
   └─ linear_sum_assignment atribui slots com cotas exatas floor(N/K) ou ceil(N/K)
   └─ Garantia: diferença máxima de 1 slot entre qualquer par de territórios

4. Polígonos de território (Voronoi + clip)
   └─ Diagrama de Voronoi de todos os slots da base
   └─ União das regiões por cluster → polígono bruto
   └─ force_single_polygon: elimina MultiPolygon, mantém maior componente
   └─ fill_jurisdiction: preenche gaps com o território mais próximo
   └─ Clip pelo polígono de jurisdição da base
   └─ Resultado: polígonos simples, sem gaps, dentro da jurisdição

5. Construção de heatmap.geojson
   └─ Utiliza o demand_map filtrado pela jurisdição (salvo na etapa 2)
   └─ **CONSISTÊNCIA GARANTIDA:** apenas hexes processados pelo solver aparecem no heatmap
   └─ Cada hex recebe: hex_id, demand_total, ceps, delivery_station, territory_id
   └─ Spatial join via Point-in-Polygon: centroide → polígono de território
   └─ Fallback para centroide mais próximo se fora de qualquer polígono
```

### Modo Daily — "Como estamos hoje?"

```
3. Matching hierárquico (Fase 3)
   └─ Hierarquia: Active → Onboarding → BG Checks → Prospect → Inactive
   └─ Elegibilidade: parceiro em grid_disk(slot.origin_hex, 1) → ~900m
   └─ Vagas ordenadas por demanda decrescente (áreas críticas primeiro)
   └─ Greedy: para cada vaga, melhor parceiro disponível na vizinhança
   └─ Atualiza ideal_supply.json com matched_partner_id

4. Web Leads (Fase 4)
   └─ Resolve CEP → hex (busca exata → prefixo de 5 dígitos)
   └─ Hex → territory_id via territories_index.json
   └─ Atribui Account Manager (ADE) responsável pelo território

5. Relatórios (Fase 5)
   └─ OPORTUNIDADES_ESTRATEGICAS.txt: slots em aberto por base/CTL/território
   └─ RELATORIO_EXECUTIVO.txt: resumo com cobertura, attainment, demanda
   └─ PARTNERS_PER_DS_BUCKET.csv: parceiros por território com matched_slot_id
   └─ webleads_evaluated.csv: leads com territory_id e OwnerId
   └─ optimization_data.geojson: hexes + parceiros + slots abertos (3 camadas)
```

---

## Artefatos Gerados

### Setup

| Arquivo | Descrição |
|---|---|
| `territories.geojson` | Polígono único por território. Propriedades: `territory_id`, `delivery_station`, `bdm_cluster`, `n_slots`, `daily_demand`, `attainment` (atualizado pelo daily), `coverage` (atualizado pelo daily) |
| `ideal_supply.json` | Slots ideais por território. Cada slot tem `slot_id`, `origin_hex`, `radius_s`, `capacity_s`, `lat`, `lon`, `allocations`, `matched_partner_id` |
| `heatmap.geojson` | Hexágonos H3 com `hex_id`, `demand_total`, `ceps`, `delivery_station`, `territory_id`. **Contém APENAS hexes com centroide dentro da jurisdição** (mesmo conjunto processado pelo solver CP-SAT) |
| `territories_index.json` | Metadados dos territórios para consumo interno das fases daily |

> **Nota Técnica:** A consistência entre solver, ideal_supply.json e heatmap.geojson é garantida reutilizando o demand_map filtrado pela jurisdição em todas as etapas. Dessa forma, nenhum hex "órfão" (fora da jurisdição) aparece no heatmap sem ter passado pelo solver.

### Daily

| Arquivo | Descrição |
|---|---|
| `OPORTUNIDADES_ESTRATEGICAS.txt` | Vagas em aberto por base → CTL → território, com localização e CEPs-alvo |
| `RELATORIO_EXECUTIVO.txt` | Resumo por base e detalhamento por território: vagas, parceiros por status, cobertura (match/total), attainment (ativos/vagas) |
| `PARTNERS_PER_DS_BUCKET.csv` | `station_code`, `territory_id`, `status`, `salesforce_id`, `partner_name`, `store_id`, `decision`, `matched_slot_id` |
| `webleads_evaluated.csv` | `Id`, `Delivery Station`, `Jurisdiction`, `Name`, `OwnerId`, `decision` |
| `optimization_data.geojson` | 3 camadas: `TERRITORY_HEX` (hexes por território), `PARTNER_POINT` (pontos dos parceiros), `IDEAL_SLOT` (vagas em aberto) |

---

## Como Usar

### Pré-requisitos

```bash
pip install h3 pandas numpy scipy shapely ortools
```

### Primeira execução (Setup)

```bash
# Processar todas as bases
python orchestrator.py --mode setup

# Processar apenas bases específicas
python orchestrator.py --mode setup --stations DSP2 DSP4

# Definir pasta de saída e número de workers paralelos
python orchestrator.py --mode setup --output output/2026-03/ --workers 8
```

O setup deve ser reexecutado ao:
- Alterar a área de cobertura de uma base
- Alterar o número de territórios por base (`CLUSTER_PER_STATION`)
- Após atualização significativa do histórico de demanda

### Execução diária (Daily)

```bash
# Execução padrão (lê artefatos do setup na pasta configurada)
python orchestrator.py --mode daily

# Com pasta de saída específica
python orchestrator.py --mode daily --output output/2026-03-19/

# Filtrando bases
python orchestrator.py --mode daily --stations DSP2

# Compatibilidade com nomes antigos de bucket no config de Account Managers
python orchestrator.py --mode daily --legacy-buckets
```

> O modo daily falha com mensagem descritiva se os artefatos do setup não existirem na pasta de saída.

---

## Configuração

Todas as configurações ficam em `config.py`:

```python
# Caminhos dos dados de entrada
BASE_PACKAGES     = "data/packages.csv"       # histórico de pacotes
BASE_PARTNERS     = "data/partners.json"      # parceiros (formato allMarkerData)
BASE_JURISDICTION = "data/jurisdiction.geojson"

# Pasta de saída
DEST_FOLDER = "output/"

# H3
H3_RESOLUTION = 9                             # resolução global
H3_RES_PER_STATION = {"DSP2": 8, "DRJ3": 8}  # opcional: por base

# Capacidade de parceiros (pacotes/dia)
MIN_CAPACITY = 40
MAX_CAPACITY = 42

# Raios de atuação configurados
RADII_M = [
    {"radius_s": 500,  "hex_distance": 1, "penalty": 0},
    {"radius_s": 1000, "hex_distance": 2, "penalty": 10},
    {"radius_s": 1500, "hex_distance": 3, "penalty": 20},
]

# Número de territórios por base
CLUSTER_PER_STATION = {
    "DSP2": 8,
    "DRJ3": 6,
    # ...
}

# Account Managers por território
ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "00XXXXX", "buckets": ["DSP2_T01", "DSP2_T02"]},
    # ...
]
```

---

## Dependências

| Biblioteca | Versão mínima | Uso |
|---|---|---|
| `h3` | 4.x | Indexação geoespacial em hexágonos |
| `pandas` | 1.5+ | Manipulação de dados tabulares |
| `numpy` | 1.23+ | Operações matriciais (K-means, Voronoi) |
| `scipy` | 1.9+ | Voronoi (`scipy.spatial`) e assignment (`scipy.optimize`) |
| `shapely` | 2.0+ | Operações em polígonos (union, clip, spatial join) |
| `ortools` | 9.x | Solver CP-SAT para encontrar slots ideais |
| `networkx` | 2.8+ | (presente no código legado) |
| `scikit-learn` | 1.1+ | K-means para inicialização de centroides |

---

## Notas de Implementação

### Consistência de Dados no Setup

**Problema**: O heatmap.geojson deveria conter apenas os hexes que foram efetivamente processados pelo solver (dentro da jurisdição), para garantir consistência com ideal_supply.json.

**Solução implementada** (2026-03-24):
- O demand_map é filtrado pela jurisdição **antes** de ser enviado ao solver
- O demand_map filtrado é armazenado em cache (`dm_filtered_by_station`)
- O heatmap.geojson é construído usando esse demand_map filtrado, em vez de chamada nova a `pkg.demand_map(station)`
- **Resultado**: Sincronismo garantido entre solver → ideal_supply.json → heatmap.geojson

**Impacto**: Elimina hexes "órfãos" (fora da jurisdição) que poderiam aparecer no heatmap sem terem sido considerados no planejamento de slots.

### K-means com Cotas Iguais

O algoritmo de `_kmeans_constrained()` garante que:
- Cada território de uma base terá ⌊N/K⌋ ou ⌈N/K⌉ slots (diferença máxima de 1)
- A distribuição geográfica é otimizada via linear_sum_assignment
- Nenhum slot fica isolado em um micro-cluster por razões numéricas

---

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

The system operates in two independent modes:

```
┌─────────────────────────────────────────────────────┐
│                   SETUP MODE                        │
│  (runs once / when reorganizing the network)        │
│                                                     │
│  load_packages → CP-SAT solver → constrained K-means│
│  → Voronoi polygons → territories.geojson           │
│                     → ideal_supply.json             │
│                     → heatmap.geojson               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                   DAILY MODE                        │
│  (runs every day with fresh partner data)           │
│                                                     │
│  load_partners → hierarchical matching → webleads   │
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
project/
│
├── orchestrator.py          # Entry point (CLI)
│
├── phase_setup.py           # Setup: solver + clustering + polygons
├── phase3_partner_fit.py    # Partner-to-slot matching
├── phase4_webleads.py       # Web lead qualification
├── phase5_reports.py        # Report generation
│
├── load_packages.py         # Historical package data loader
├── load_partners.py         # Partner and jurisdiction loader
├── models.py                # Dataclasses and central Config
│
├── phase1_territories.py    # Territory persistence and loading
├── phase2_ideal_supply.py   # Slot persistence and loading
│
├── config.py                # Operational settings (not versioned)
│
└── data/
    └── jurisdiction.geojson # Jurisdiction polygons per station
```

---

## Execution Flow

### Setup Mode — "Where should partners be?"

```
1. load_packages()
   └─ Reads historical package CSV (lat, lon, zip, station_code, plan_date)
   └─ Converts lat/lon → H3 hexagons (resolution 9, configurable per station)
   └─ Resolves hex conflicts across stations (winner-takes-all by volume)
   └─ Returns raw total demand per hex

2. CP-SAT solver per station (parallel)
   └─ For each active hex: finds seed with highest residual demand
   └─ CP-SAT chooses minimum radius achieving MIN_CAP packages/day
   └─ Maximizes allocated packages, penalizes larger radii
   └─ Iterates until no hex has residual demand ≥ MIN_CAP
   └─ Output: N ideal slots per station with lat/lon, radius and capacity

3. Constrained K-means (equal quotas)
   └─ K-means++ finds K optimal geographic centroids
   └─ linear_sum_assignment assigns slots with exact quotas floor(N/K) or ceil(N/K)
   └─ Guarantee: max difference of 1 slot between any two territories

4. Territory polygons (Voronoi + clip)
   └─ Voronoi diagram of all slots in the station
   └─ Union regions by cluster → raw polygon per territory
   └─ force_single_polygon: eliminates MultiPolygon, keeps largest component
   └─ fill_jurisdiction: fills gaps by assigning to nearest territory
   └─ Clip to station jurisdiction polygon
   └─ Output: simple polygons, no gaps, within jurisdiction boundary
```

### Daily Mode — "How are we doing today?"

```
3. Hierarchical matching (Phase 3)
   └─ Priority: Active → Onboarding → BG Checks → Prospect → Inactive
   └─ Eligibility: partner within grid_disk(slot.origin_hex, 1) → ~900m
   └─ Slots ordered by demand descending (critical areas first)
   └─ Greedy: for each slot, best available partner in neighborhood
   └─ Updates ideal_supply.json with matched_partner_id

4. Web Leads (Phase 4)
   └─ Resolves ZIP → hex (exact match → 5-digit prefix fallback)
   └─ Hex → territory_id via territories_index.json
   └─ Assigns responsible Account Manager (ADE) per territory

5. Reports (Phase 5)
   └─ OPORTUNIDADES_ESTRATEGICAS.txt: open slots per station/CTL/territory
   └─ RELATORIO_EXECUTIVO.txt: coverage, attainment, demand summary
   └─ PARTNERS_PER_DS_BUCKET.csv: partners per territory with matched_slot_id
   └─ webleads_evaluated.csv: leads with territory_id and OwnerId
   └─ optimization_data.geojson: hexes + partners + open slots (3 layers)
```

---

## Generated Artifacts

### Setup

| File | Description |
|---|---|
| `territories.geojson` | Single polygon per territory. Properties: `territory_id`, `delivery_station`, `bdm_cluster`, `n_slots`, `daily_demand`, `attainment` (updated by daily), `coverage` (updated by daily) |
| `ideal_supply.json` | Ideal slots per territory. Each slot has `slot_id`, `origin_hex`, `radius_s`, `capacity_s`, `lat`, `lon`, `allocations`, `matched_partner_id` |
| `heatmap.geojson` | H3 hexagons with `hex_id`, `demand_total`, `ceps`, `delivery_station`, `territory_id` |
| `territories_index.json` | Territory metadata for internal consumption by daily phases |

### Daily

| File | Description |
|---|---|
| `OPORTUNIDADES_ESTRATEGICAS.txt` | Open slots per station → CTL → territory, with location and target ZIP codes |
| `RELATORIO_EXECUTIVO.txt` | Station summary and per-territory breakdown: slots, partners by status, coverage (matched/total), attainment (active/slots) |
| `PARTNERS_PER_DS_BUCKET.csv` | `station_code`, `territory_id`, `status`, `salesforce_id`, `partner_name`, `store_id`, `decision`, `matched_slot_id` |
| `webleads_evaluated.csv` | `Id`, `Delivery Station`, `Jurisdiction`, `Name`, `OwnerId`, `decision` |
| `optimization_data.geojson` | 3 layers: `TERRITORY_HEX` (hexes per territory), `PARTNER_POINT` (partner locations), `IDEAL_SLOT` (open slots) |

---

## How to Use

### Prerequisites

```bash
pip install h3 pandas numpy scipy shapely ortools
```

### First Run (Setup)

```bash
# Process all stations
python orchestrator.py --mode setup

# Process specific stations only
python orchestrator.py --mode setup --stations DSP2 DSP4

# Custom output folder and parallel workers
python orchestrator.py --mode setup --output output/2026-03/ --workers 8
```

Re-run setup when:
- A station's coverage area changes
- The number of territories per station changes (`CLUSTER_PER_STATION`)
- After a significant update to the demand history

### Daily Run

```bash
# Standard run (reads setup artifacts from configured folder)
python orchestrator.py --mode daily

# Custom output folder
python orchestrator.py --mode daily --output output/2026-03-19/

# Filter specific stations
python orchestrator.py --mode daily --stations DSP2

# Legacy bucket name compatibility for Account Manager config
python orchestrator.py --mode daily --legacy-buckets
```

> Daily mode aborts with a descriptive message if setup artifacts do not exist in the output folder.

---

## Configuration

All settings are in `config.py`:

```python
# Input data paths
BASE_PACKAGES     = "data/packages.csv"       # historical packages
BASE_PARTNERS     = "data/partners.json"      # partners (allMarkerData format)
BASE_JURISDICTION = "data/jurisdiction.geojson"

# Output folder
DEST_FOLDER = "output/"

# H3
H3_RESOLUTION = 9                             # global resolution
H3_RES_PER_STATION = {"DSP2": 8, "DRJ3": 8}  # optional: per station

# Partner capacity (packages/day)
MIN_CAPACITY = 40
MAX_CAPACITY = 42

# Operating radii
RADII_M = [
    {"radius_s": 500,  "hex_distance": 1, "penalty": 0},
    {"radius_s": 1000, "hex_distance": 2, "penalty": 10},
    {"radius_s": 1500, "hex_distance": 3, "penalty": 20},
]

# Territories per station
CLUSTER_PER_STATION = {
    "DSP2": 8,
    "DRJ3": 6,
    # ...
}

# Account Managers per territory
ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "00XXXXX", "buckets": ["DSP2_T01", "DSP2_T02"]},
    # ...
]
```

---

## Dependencies

| Library | Min Version | Usage |
|---|---|---|
| `h3` | 4.x | Geospatial hexagon indexing |
| `pandas` | 1.5+ | Tabular data manipulation |
| `numpy` | 1.23+ | Matrix operations (K-means, Voronoi) |
| `scipy` | 1.9+ | Voronoi (`scipy.spatial`) and assignment (`scipy.optimize`) |
| `shapely` | 2.0+ | Polygon operations (union, clip, spatial join) |
| `ortools` | 9.x | CP-SAT solver for ideal slot finding |
| `networkx` | 2.8+ | (present in legacy code) |
| `scikit-learn` | 1.1+ | K-means centroid initialization |
