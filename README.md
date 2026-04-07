# ATLAS — Analytical Tracking for Location and Store performance

> Sistema completo de gestão e otimização de rede de parceiros logísticos last-mile.
>
> Complete management and optimization system for last-mile logistics partner networks.

---

## Índice / Table of Contents

- [Português](#português)
  - [O que é o ATLAS](#o-que-é-o-atlas)
  - [Funcionalidades](#funcionalidades)
  - [Arquitetura Geral](#arquitetura-geral)
  - [Backend — Pipeline de Otimização](#backend--pipeline-de-otimização)
  - [Frontend — Interface Interativa](#frontend--interface-interativa)
  - [Google Maps Scraper](#google-maps-scraper)
  - [Estrutura de Arquivos](#estrutura-de-arquivos)
  - [Como Usar](#como-usar)
  - [Configuração](#configuração)
  - [Dependências](#dependências)
- [English](#english)
  - [What is ATLAS](#what-is-atlas)
  - [Features](#features)
  - [General Architecture](#general-architecture)
  - [Backend — Optimization Pipeline](#backend--optimization-pipeline)
  - [Frontend — Interactive Interface](#frontend--interactive-interface)
  - [Google Maps Scraper](#google-maps-scraper-1)
  - [File Structure](#file-structure)
  - [How to Use](#how-to-use)
  - [Configuration](#configuration)
  - [Dependencies](#dependencies)

---

# Português

## O que é o ATLAS

O ATLAS é um sistema completo de gestão e otimização de rede de parceiros logísticos para operações de entrega last-mile (hub delivery). Ele resolve o problema de **onde, quantos e quais parceiros** uma rede de distribuição precisa, automatizando desde a identificação de oportunidades geográficas até o gerenciamento operacional diário.

**Problemas resolvidos:**

- Onde deveriam estar os parceiros logísticos? *(planejamento geográfico)*
- Quantos slots ideais cada território precisa? *(dimensionamento)*
- Quais parceiros existentes cobrem quais vagas? *(matching diário)*
- Qual o attainment atual e quais oportunidades estão em aberto? *(acompanhamento)*
- Quais empresas locais podem se tornar novos parceiros? *(geração de leads)*
- Como otimizar a rede HCP (Host/Pickup) existente? *(otimização de network)*
- Como gerenciar riscos operacionais no dia a dia? *(resgate de parceiros)*

---

## Funcionalidades

### Criação de Oportunidades e Territórios
- Processa histórico de pacotes entregues (lat/lon, CEP, data) para identificar pontos geográficos ideais de parceiros
- Divide a área de cobertura de cada base em territórios equilibrados via solver CP-SAT + K-means geoespacial em UTM
- Suporte a jurisdições MultiPolygon (áreas descontínuas)
- Polígonos de território reconstruídos após o daily para refletir a rede real

### Indicadores de Expansão por Território
- Attainment (parceiros ativos / vagas ideais) por território e base
- Acuracidade (vagas preenchidas / vagas totais)
- Priorização automática de territórios por menor cobertura
- Painel de stats com Performance, Expansion e Routes

### Qualificação Automática de Leads
- Web leads vindos do website são avaliados automaticamente por CEP
- Verifica se o lead está dentro de uma área de atuação ativa
- Qualifica a volumetria disponível na região para decidir se vale seguir com o cadastro
- Atribui o Account Developer Executive (ADE) responsável pelo território

### Geração de Leads — Receita Federal

O sistema consulta o banco de dados público da Receita Federal brasileira (SQLite local) para encontrar empresas que possam se tornar parceiros logísticos.

**Critérios de busca:**
- CNPJ ativo (situação cadastral = 02)
- CNAE principal ou secundário iniciado com `5320` (atividades de entrega/correio)
- Data de início de atividade anterior a 01/01/2024 (empresa com histórico mínimo)
- CEP presente na lista de CEPs dos slots em aberto

**Dados retornados por empresa:**
- CNPJ, razão social, porte (ME/EPP)
- Endereço completo (logradouro, número, bairro, CEP, UF, município)
- Telefone 1 e Telefone 2
- E-mail
- Responsável (primeiro sócio cadastrado)
- CNAE principal

**Validação geográfica (H3 grid_disk):**
O frontend valida a proximidade do lead ao slot usando a grade H3. O CEP da empresa é convertido em hex H3 via o `heatmap.geojson` (índice CEP → hex_id). A distância é calculada como `h3.gridDistance(empresa_hex, slot_origin_hex)`:
- `grid_disk = 0` → empresa no mesmo hexágono do slot ✅
- `grid_disk = 1` → empresa no hexágono vizinho (~900m) ✅
- `grid_disk > 1` → empresa fora do raio ⚠️

**Integração:**
- Backend: `cnpj_lookup.py` — roda na Fase 6 do modo daily
- Frontend: `js/modules/gmaps-scraper.js` — exibe no popup do slot com badge de validação

---

### Geração de Leads — Google Maps

O sistema faz scraping automatizado do Google Maps para encontrar estabelecimentos comerciais próximos aos slots em aberto que possam se tornar parceiros.

**Tipos de negócio buscados:**
- Lanchonete
- Açaí e sorveteria
- Chaveiro
- Assistência técnica

**Pipeline de scraping:**
1. GitHub Actions roda `run_batch.js` diariamente às 6h (horário de Brasília)
2. Para cada território com slots em aberto, busca os 4 tipos de negócio
3. Coleta até 20 links de resultados por busca via scroll automático
4. Visita cada página de detalhes com **3 abas em paralelo** (concorrência controlada)
5. Extrai: nome, endereço, CEP, telefone, site, link do Maps e **coordenadas geográficas**
6. **Filtro de qualidade**: só salva empresas com endereço completo (logradouro + número) E CEP de 8 dígitos
7. Merge incremental: evita duplicatas por nome + endereço
8. Salva resultado em `data/gmaps_results.json` e faz commit automático

**Extração de coordenadas:**
As coordenadas lat/lon são extraídas diretamente do link do Google Maps via regex `!3d<lat>!4d<lon>`, que é mais estável que a URL da página. Isso garante coordenadas precisas sem chamadas extras de API.

**Validação geográfica (distância métrica):**
No frontend, a distância entre a empresa e o slot é calculada via Turf.js em metros:
- Distância ≤ raio do slot → ✅ Dentro do raio (exibe distância em metros)
- Distância > raio do slot → ⚠️ Fora do raio

**Filtro de exibição:**
Apenas empresas a **≤1000m** do slot são exibidas no popup. Empresas mais distantes são descartadas na exibição, mesmo que estejam no território.

**Resultado no popup do slot:**
```
🏪 Empresas Candidatas — DBH5_bucket-02

📂 lanchonete (2)
  ✅ Bar do João (180m)
     📍 Rua das Flores, 123 - Bela Vista, 30130-000
     📞 31 99999-9999
     Ver no Google Maps ↗

  ✅ Lanchonete Central (420m)
     📍 Av. Principal, 456 - Centro, 30140-000
     📞 31 98888-8888

📂 Receita Federal (3)
  ✅ TRANSPORTES RAPIDOS LTDA (grid_disk=0)
     📍 Rua X, 100 - Bairro Y, 30130-000
     📞 31 3299-1234
```

### Otimização de Network — HCP Suggestion
- Sistema em 3 fases para sugestão de clusters HCP (Host/Pickup):
  - **Fase 1**: Otimiza a alocação de pickups existentes aos hosts mais próximos
  - **Fase 2**: Aloca Hub Heroes a hosts existentes com capacidade disponível
  - **Fase 3**: Identifica novos hosts potenciais via clusterização K-means
- Visualização no mapa com destaque por cor (roxo = host, rosa = pickup)

### Gerenciamento de Risco Operacional — Solicitação de Resgate
- Quando um parceiro não pode entregar os pacotes do dia, o sistema identifica os parceiros ativos mais próximos
- Calcula distância real via OSRM (roteamento por vias)
- Sugere bônus por distância e gera link direto para WhatsApp

---

## Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND (Python)                     │
│                                                             │
│  MODO SETUP (uma vez / ao reorganizar a rede)               │
│  packages.csv → CP-SAT solver → K-means UTM                 │
│  → Voronoi + clip jurisdição → territories.geojson          │
│                              → ideal_supply.json            │
│                              → heatmap.geojson              │
│                                                             │
│  MODO DAILY (todo dia)                                      │
│  partners.json → matching hierárquico → webleads            │
│  → CNPJ lookup → relatórios + optimization_data.geojson     │
│                                                             │
│  --update-heatmap  (atualiza só o heatmap)                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (JS puro + Leaflet)             │
│                                                             │
│  ATLAS.html + js/main.js (ES Modules nativos)               │
│                                                             │
│  Mapa interativo com:                                       │
│  - Marcadores de parceiros por status                       │
│  - Polígonos de território e jurisdição                     │
│  - Heatmap de demanda por hexágono H3                       │
│  - Painel de stats (Performance / Expansion / Routes)       │
│  - HCP Suggestion, Resgate, Rotas, Empresas Candidatas      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              GOOGLE MAPS SCRAPER (Node.js)                  │
│                                                             │
│  GitHub Actions (cron diário)                               │
│  → run_batch.js → Puppeteer → gmaps_results.json            │
└─────────────────────────────────────────────────────────────┘
```

---

## Backend — Pipeline de Otimização

### Modo Setup — "Onde deveriam estar os parceiros?"

```
1. load_packages()
   └─ Lê CSV histórico de pacotes (lat, lon, cep, station_code, plan_date)
   └─ Converte lat/lon → hexágonos H3 (resolução configurável por base)
   └─ Resolve conflitos de hexes entre bases (winner-takes-all por volume)

2. Filtro de jurisdição + Solver CP-SAT por base (paralelo)
   └─ Remove hexes fora do polígono de jurisdição
   └─ CP-SAT encontra pontos ideais com raio mínimo que atinge MIN_CAP pacotes/dia
   └─ Deduplicação: mesmo origin_hex + mesmo radius_s → merge

3. K-means geoespacial em UTM com cotas iguais
   └─ Converte lat/lon → UTM (metros) para evitar distorção geográfica
   └─ linear_sum_assignment garante ⌊N/K⌋ ou ⌈N/K⌉ slots por território

4. Construção de polígonos de território
   └─ Voronoi por componente da jurisdição (suporte a MultiPolygon)
   └─ Componentes sem slots → atribuídas ao cluster mais próximo
   └─ Expansão iterativa + suavização + clip final pela jurisdição

5. Heatmap
   └─ Spatial join: centróide do hex → polígono de território
   └─ Salva demand_total e demand_daily por hexágono
```

### Modo Daily — "Como estamos hoje?"

```
3. Matching hierárquico (Fase 3)
   └─ Pré-computa território de cada parceiro (hex_ids → point-in-polygon → centroide)
   └─ Hierarquia: Active → Onboarding → BG Checks → Prospect → Inactive/Exited
   └─ Parceiro só pode cobrir vaga do seu próprio território
   └─ Reconstrói polígonos a partir dos hex_ids H3 reais

4. Web Leads (Fase 4)
   └─ Resolve CEP → hex → territory_id
   └─ Atribui Account Manager (ADE) responsável

5. CNPJ Lookup (Fase 6)
   └─ Busca empresas com CNAE 5320 nos CEPs dos slots em aberto
   └─ Filtra: situação ativa, início de atividade < 01/01/2024

6. Relatórios (Fase 5)
   └─ OPORTUNIDADES_ESTRATEGICAS.txt — slots em aberto + empresas candidatas
   └─ RELATORIO_EXECUTIVO.txt — cobertura, attainment, demanda
   └─ PARTNERS_PER_DS_BUCKET.csv — parceiros por território
   └─ webleads_evaluated.csv — leads qualificados
   └─ optimization_data.geojson — 3 camadas: hexes + parceiros + slots abertos
```

### Comportamento com --stations

Ao usar `--stations` em qualquer modo, o sistema faz **merge inteligente** dos arquivos de saída — preserva dados de todas as outras bases e atualiza apenas as especificadas.

### Artefatos Gerados

| Arquivo | Descrição |
|---|---|
| `territories.geojson` | Polígono (ou MultiPolygon) por território |
| `ideal_supply.json` | Slots ideais por território com matched_partner_id |
| `heatmap.geojson` | Hexágonos H3 com demand_total e demand_daily |
| `territories_index.json` | Metadados dos territórios para lookup rápido |
| `OPORTUNIDADES_ESTRATEGICAS.txt` | Vagas em aberto + empresas candidatas |
| `RELATORIO_EXECUTIVO.txt` | Resumo por base e território |
| `PARTNERS_PER_DS_BUCKET.csv` | Parceiros por território |
| `webleads_evaluated.csv` | Leads qualificados com territory_id e OwnerId |
| `optimization_data.geojson` | 3 camadas: TERRITORY_HEX, PARTNER_POINT, IDEAL_SLOT |

---

## Frontend — Interface Interativa

### Módulos (ES Modules nativos)

| Arquivo | Responsabilidade |
|---|---|
| `js/config.js` | Constantes e URLs centralizadas |
| `js/models.js` | Classes tipadas: `Partner`, `ProspectCompany`, `RouteStop`, etc. |
| `js/state.js` | Estado global reativo via Proxy com `subscribe()` |
| `js/modules/data-manager.js` | Carregamento, enriquecimento e filtros via Web Worker |
| `js/modules/map-manager.js` | Mapa Leaflet, marcadores, estilos, legenda |
| `js/modules/polygon-manager.js` | Territórios, jurisdições, heatmap, seleção interativa |
| `js/modules/ui-manager.js` | Filtros, autocomplete, popups, painel de stats |
| `js/modules/route-manager.js` | Rotas OSRM, paradas, HCP clustering (3 fases) |
| `js/modules/gmaps-scraper.js` | Busca gmaps_results.json + API Receita Federal |
| `js/main.js` | Bootstrap: subscribers reativos + event listeners |

### Artefatos consumidos pelo frontend

| Arquivo | Descrição |
|---|---|
| `data/dados_mapa.json` | Parceiros, delivery stations, período |
| `data/territories.geojson` | Polígonos de território |
| `data/jurisdiction.geojson` | Polígonos de jurisdição por base |
| `data/optimization_data.geojson` | 3 camadas: TERRITORY_HEX, PARTNER_POINT, IDEAL_SLOT |
| `data/heatmap.geojson` | Hexágonos H3 com demand_total e demand_daily |
| `data/gmaps_results.json` | Empresas candidatas por território |

---

## Google Maps Scraper

Serviço Node.js que roda via GitHub Actions para gerar o banco de dados de empresas candidatas.

### Tipos de negócio buscados
- Lanchonete
- Açaí e sorveteria
- Chaveiro
- Assistência técnica

### Instalação

```bash
cd gmaps-scraper
npm install
node run_batch.js                          # todas as bases
node run_batch.js --stations DSP2 DBH5    # bases específicas
```

---

## Estrutura de Arquivos

```
atlas/
│
├── ATLAS.html                    # Frontend principal (PWA)
├── js/                           # Frontend modular (ES Modules)
│   ├── config.js
│   ├── models.js
│   ├── state.js
│   ├── main.js
│   └── modules/
│       ├── data-manager.js
│       ├── map-manager.js
│       ├── polygon-manager.js
│       ├── ui-manager.js
│       ├── route-manager.js
│       └── gmaps-scraper.js
│
├── backend/                      # Pipeline de otimização (Python)
│   ├── orchestrator.py
│   ├── phase_setup.py
│   ├── phase3_partner_fit.py
│   ├── phase4_webleads.py
│   ├── phase5_reports.py
│   ├── cnpj_lookup.py
│   ├── load_packages.py
│   ├── load_partners.py
│   ├── models.py
│   ├── phase2_ideal_supply.py
│   └── config.py
│
├── gmaps-scraper/                # Scraper Google Maps (Node.js)
│   ├── run_batch.js
│   ├── scraper.js
│   ├── index.js
│   └── package.json
│
├── data/                         # Artefatos gerados e consumidos
│   ├── territories.geojson
│   ├── territories_index.json
│   ├── ideal_supply.json
│   ├── heatmap.geojson
│   ├── optimization_data.geojson
│   ├── jurisdiction.geojson
│   └── gmaps_results.json
│
└── .github/
    └── workflows/
        └── scrape-gmaps.yml      # GitHub Actions: scraping diário
```

---

## Como Usar

### Backend

```bash
pip install h3 pandas numpy scipy shapely ortools pyproj

# Setup
python orchestrator.py --mode setup
python orchestrator.py --mode setup --stations DSP2 DSP4 --workers 8

# Daily
python orchestrator.py --mode daily
python orchestrator.py --mode daily --stations DSP2

# Atualizar heatmap
python orchestrator.py --update-heatmap
```

### Frontend

```bash
# Servidor local simples
python -m http.server 8080
# Acesse: http://localhost:8080/ATLAS.html
```

### Google Maps Scraper

```bash
cd gmaps-scraper
npm install
node run_batch.js
```

---

## Configuração

### backend/config.py

```python
BASE_PACKAGES     = "data/packages.csv"
BASE_PARTNERS     = "data/partners.json"
BASE_JURISDICTION = "data/jurisdiction.geojson"
DEST_FOLDER       = "data/"
H3_RESOLUTION     = 9
H3_RES_PER_STATION = {"DSP2": 8, "DRJ3": 8}
MIN_CAPACITY      = 40
MAX_CAPACITY      = 42
CLUSTER_PER_STATION = {"DSP2": 8, "DBH5": 4}
DB_EMPRESAS       = "path/to/cnpj_2025_06.db"
ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "00XXXXX", "buckets": ["DSP2_bucket-01"]},
]
```

### js/config.js

```js
export const DATA_URLS = { partners: "...", territories: "...", ... };
export const HCP_CONFIG = { maxPickupsPerHost: 5, maxDistanceM: 6000, ... };
export const CNPJ_API_URL = "https://api-cnpj-br.vercel.app/api/buscar";
```

---

## Dependências

### Backend (Python)

| Biblioteca | Versão mínima | Uso |
|---|---|---|
| `h3` | 4.x | Indexação geoespacial em hexágonos |
| `pandas` | 1.5+ | Manipulação de dados tabulares |
| `numpy` | 1.23+ | Operações matriciais |
| `scipy` | 1.9+ | Voronoi e assignment |
| `shapely` | 2.0+ | Operações em polígonos |
| `ortools` | 9.x | Solver CP-SAT |
| `pyproj` | 3.x | Projeção UTM |

### Frontend (JavaScript)

| Biblioteca | Uso |
|---|---|
| Leaflet.js | Mapa interativo |
| Leaflet Routing Machine | Rotas OSRM |
| Turf.js | Operações geoespaciais no browser |
| Tabulator | Tabelas de dados |

### Google Maps Scraper (Node.js)

| Pacote | Uso |
|---|---|
| `puppeteer` | Scraping headless do Google Maps |
| `express` | API REST local (opcional) |
| `cors` | Controle de CORS |

---

# English

## What is ATLAS

ATLAS is a complete management and optimization system for last-mile logistics partner networks (hub delivery). It solves the problem of **where, how many, and which partners** a distribution network needs, automating everything from geographic opportunity identification to daily operational management.

**Problems solved:**

- Where should logistics partners be located? *(geographic planning)*
- How many ideal slots does each territory need? *(sizing)*
- Which existing partners cover which slots? *(daily matching)*
- What is the current attainment and which opportunities are open? *(tracking)*
- Which local businesses can become new partners? *(lead generation)*
- How to optimize the existing HCP (Host/Pickup) network? *(network optimization)*
- How to manage operational risks day-to-day? *(partner rescue)*

---

## Features

### Opportunity and Territory Creation
- Processes historical package delivery data (lat/lon, ZIP, date) to identify ideal partner locations
- Divides each station coverage area into balanced territories via CP-SAT solver + geospatial K-means in UTM
- MultiPolygon jurisdiction support (discontinuous areas)
- Territory polygons rebuilt after daily run to reflect the real network

### Expansion Indicators by Territory
- Attainment (active partners / ideal slots) per territory and station
- Accuracy (filled slots / total slots)
- Automatic territory prioritization by lowest coverage
- Stats panel with Performance, Expansion and Routes tabs

### Automatic Lead Qualification
- Website leads are automatically evaluated by ZIP code
- Checks if the lead is within an active coverage area
- Qualifies available volume in the region to decide whether to proceed with registration
- Assigns the responsible Account Manager (ADE) for the territory

### Lead Generation — Brazilian Tax Authority (Receita Federal)

The system queries the public Brazilian Tax Authority (Receita Federal) database (local SQLite) to find companies that could become logistics partners.

**Search criteria:**
- Active CNPJ (registration status = 02)
- Primary or secondary CNAE starting with `5320` (delivery/courier activities)
- Business start date before 01/01/2024 (minimum track record)
- ZIP code present in the open slot's ZIP code list

**Data returned per company:**
- CNPJ, company name, size (ME/EPP)
- Full address (street, number, neighborhood, ZIP, state, city)
- Phone 1 and Phone 2
- Email
- Responsible person (first registered partner)
- Primary CNAE

**Geographic validation (H3 grid_disk):**
The frontend validates proximity to the slot using the H3 grid. The company's ZIP code is converted to an H3 hex via `heatmap.geojson` (ZIP → hex_id index). Distance is calculated as `h3.gridDistance(company_hex, slot_origin_hex)`:
- `grid_disk = 0` → company in the same hexagon as the slot ✅
- `grid_disk = 1` → company in a neighboring hexagon (~900m) ✅
- `grid_disk > 1` → company outside the radius ⚠️

**Integration:**
- Backend: `cnpj_lookup.py` — runs in Phase 6 of daily mode
- Frontend: `js/modules/gmaps-scraper.js` — displayed in slot popup with validation badge

---

### Lead Generation — Google Maps

The system performs automated Google Maps scraping to find commercial establishments near open slots that could become partners.

**Business types searched:**
- Snack bar (lanchonete)
- Acai and ice cream shop
- Locksmith (chaveiro)
- Tech support (assistência técnica)

**Scraping pipeline:**
1. GitHub Actions runs `run_batch.js` daily at 6am (Brasília time)
2. For each territory with open slots, searches all 4 business types
3. Collects up to 20 result links per search via automatic scroll
4. Visits each detail page with **3 parallel tabs** (controlled concurrency)
5. Extracts: name, address, ZIP, phone, website, Maps link and **geographic coordinates**
6. **Quality filter**: only saves companies with complete address (street + number) AND 8-digit ZIP code
7. Incremental merge: avoids duplicates by name + address
8. Saves result to `data/gmaps_results.json` and auto-commits

**Coordinate extraction:**
Lat/lon coordinates are extracted directly from the Google Maps link via regex `!3d<lat>!4d<lon>`, which is more stable than the page URL. This ensures precise coordinates without extra API calls.

**Geographic validation (metric distance):**
In the frontend, the distance between the company and the slot is calculated via Turf.js in meters:
- Distance ≤ slot radius → ✅ Within radius (shows distance in meters)
- Distance > slot radius → ⚠️ Outside radius

**Display filter:**
Only companies within **≤1000m** of the slot are shown in the popup. More distant companies are discarded from display even if they are in the territory.

**Result in slot popup:**
```
🏪 Candidate Companies — DBH5_bucket-02

📂 snack bar (2)
  ✅ Bar do João (180m)
     📍 Rua das Flores, 123 - Bela Vista, 30130-000
     📞 31 99999-9999
     View on Google Maps ↗

📂 Receita Federal (3)
  ✅ TRANSPORTES RAPIDOS LTDA (grid_disk=0)
     📍 Rua X, 100 - Bairro Y, 30130-000
     📞 31 3299-1234
```

### Network Optimization — HCP Suggestion
- 3-phase system for HCP (Host/Pickup) cluster suggestions:
  - **Phase 1**: Optimizes allocation of existing pickups to nearest hosts
  - **Phase 2**: Allocates Hub Heroes to existing hosts with available capacity
  - **Phase 3**: Identifies potential new hosts via K-means clustering
- Map visualization with color highlights (purple = host, pink = pickup)

### Operational Risk Management — Partner Rescue
- When a partner cannot deliver packages for the day, the system identifies the nearest active partners
- Calculates real driving distance via OSRM
- Suggests bonus by distance and generates direct WhatsApp link

---

## General Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        BACKEND (Python)                     │
│                                                             │
│  SETUP MODE (once / when reorganizing the network)          │
│  packages.csv → CP-SAT solver → UTM K-means                 │
│  → Voronoi + jurisdiction clip → territories.geojson        │
│                               → ideal_supply.json           │
│                               → heatmap.geojson             │
│                                                             │
│  DAILY MODE (every day)                                     │
│  partners.json → hierarchical matching → webleads           │
│  → CNPJ lookup → reports + optimization_data.geojson        │
│                                                             │
│  --update-heatmap  (updates only the heatmap)               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Vanilla JS + Leaflet)          │
│                                                             │
│  ATLAS.html + js/main.js (Native ES Modules)                │
│                                                             │
│  Interactive map with:                                      │
│  - Partner markers by status                                │
│  - Territory and jurisdiction polygons                      │
│  - H3 hexagon demand heatmap                                │
│  - Stats panel (Performance / Expansion / Routes)           │
│  - HCP Suggestion, Rescue, Routes, Candidate Companies      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              GOOGLE MAPS SCRAPER (Node.js)                  │
│                                                             │
│  GitHub Actions (daily cron)                                │
│  → run_batch.js → Puppeteer → gmaps_results.json            │
└─────────────────────────────────────────────────────────────┘
```

---

## Backend — Optimization Pipeline

### Setup Mode

```
1. load_packages()
   Reads historical package CSV (lat, lon, zip, station_code, plan_date)
   Converts lat/lon → H3 hexagons (resolution configurable per station)
   Resolves hex conflicts between stations (winner-takes-all by volume)

2. Jurisdiction filter + CP-SAT solver per station (parallel)
   Removes hexes outside jurisdiction polygon
   CP-SAT finds ideal points with minimum radius achieving MIN_CAP packages/day
   Deduplication: same origin_hex + same radius_s → merge

3. Geospatial K-means in UTM with equal quotas
   Converts lat/lon → UTM (meters) to avoid geographic distortion
   linear_sum_assignment guarantees floor(N/K) or ceil(N/K) slots per territory

4. Territory polygon construction
   Voronoi per jurisdiction component (MultiPolygon support)
   Components without slots → assigned to nearest cluster
   Iterative expansion + smoothing + final clip by jurisdiction

5. Heatmap
   Spatial join: hex centroid → territory polygon
   Saves demand_total and demand_daily per hexagon
```

### Daily Mode

```
3. Hierarchical matching (Phase 3)
   Pre-computes territory for each partner (hex_ids → point-in-polygon → centroid)
   Priority: Active → Onboarding → BG Checks → Prospect → Inactive/Exited
   Partner can only cover slots in their own territory
   Rebuilds polygons from real H3 hex_ids

4. Web Leads (Phase 4)
   Resolves ZIP → hex → territory_id
   Assigns responsible Account Manager (ADE)

5. CNPJ Lookup (Phase 6)
   Searches companies with CNAE 5320 in ZIP codes of open slots
   Filters: active status, start date < 01/01/2024

6. Reports (Phase 5)
   OPORTUNIDADES_ESTRATEGICAS.txt — open slots + candidate companies
   RELATORIO_EXECUTIVO.txt — coverage, attainment, demand
   PARTNERS_PER_DS_BUCKET.csv — partners per territory
   webleads_evaluated.csv — qualified leads
   optimization_data.geojson — 3 layers: hexes + partners + open slots
```

### Generated Artifacts

| File | Description |
|---|---|
| `territories.geojson` | Polygon (or MultiPolygon) per territory |
| `ideal_supply.json` | Ideal slots per territory with matched_partner_id |
| `heatmap.geojson` | H3 hexagons with demand_total and demand_daily |
| `territories_index.json` | Territory metadata for fast lookup |
| `OPORTUNIDADES_ESTRATEGICAS.txt` | Open slots + candidate companies |
| `RELATORIO_EXECUTIVO.txt` | Summary per station and territory |
| `PARTNERS_PER_DS_BUCKET.csv` | Partners per territory |
| `webleads_evaluated.csv` | Qualified leads with territory_id and OwnerId |
| `optimization_data.geojson` | 3 layers: TERRITORY_HEX, PARTNER_POINT, IDEAL_SLOT |

---

## Frontend — Interactive Interface

### Modules (Native ES Modules)

| File | Responsibility |
|---|---|
| `js/config.js` | Centralized constants and URLs |
| `js/models.js` | Typed classes: `Partner`, `ProspectCompany`, `RouteStop`, etc. |
| `js/state.js` | Reactive global state via Proxy with `subscribe()` |
| `js/modules/data-manager.js` | Loading, enrichment and filters via Web Worker |
| `js/modules/map-manager.js` | Leaflet map, markers, styles, legend |
| `js/modules/polygon-manager.js` | Territories, jurisdictions, heatmap, interactive selection |
| `js/modules/ui-manager.js` | Filters, autocomplete, popups, stats panel |
| `js/modules/route-manager.js` | OSRM routes, stops, HCP clustering (3 phases) |
| `js/modules/gmaps-scraper.js` | Fetches gmaps_results.json + Receita Federal API |
| `js/main.js` | Bootstrap: reactive subscribers + event listeners |

---

## Google Maps Scraper

Node.js service running via GitHub Actions to generate the candidate company database.

### Business types searched
- Snack bar (lanchonete)
- Acai and ice cream shop
- Locksmith (chaveiro)
- Tech support (assistência técnica)

### Installation

```bash
cd gmaps-scraper
npm install
node run_batch.js
node run_batch.js --stations DSP2 DBH5
```

---

## File Structure

```
atlas/
│
├── ATLAS.html                    # Main frontend (PWA)
├── js/                           # Modular frontend (ES Modules)
│   ├── config.js
│   ├── models.js
│   ├── state.js
│   ├── main.js
│   └── modules/
│       ├── data-manager.js
│       ├── map-manager.js
│       ├── polygon-manager.js
│       ├── ui-manager.js
│       ├── route-manager.js
│       └── gmaps-scraper.js
│
├── backend/                      # Optimization pipeline (Python)
│   ├── orchestrator.py
│   ├── phase_setup.py
│   ├── phase3_partner_fit.py
│   ├── phase4_webleads.py
│   ├── phase5_reports.py
│   ├── cnpj_lookup.py
│   ├── load_packages.py
│   ├── load_partners.py
│   ├── models.py
│   ├── phase2_ideal_supply.py
│   └── config.py
│
├── gmaps-scraper/                # Google Maps scraper (Node.js)
│   ├── run_batch.js
│   ├── scraper.js
│   ├── index.js
│   └── package.json
│
├── data/                         # Generated and consumed artifacts
│   ├── territories.geojson
│   ├── territories_index.json
│   ├── ideal_supply.json
│   ├── heatmap.geojson
│   ├── optimization_data.geojson
│   ├── jurisdiction.geojson
│   └── gmaps_results.json
│
└── .github/
    └── workflows/
        └── scrape-gmaps.yml      # GitHub Actions: daily scraping
```

---

## How to Use

### Backend

```bash
pip install h3 pandas numpy scipy shapely ortools pyproj

# Setup
python orchestrator.py --mode setup
python orchestrator.py --mode setup --stations DSP2 DSP4 --workers 8

# Daily
python orchestrator.py --mode daily
python orchestrator.py --mode daily --stations DSP2

# Update heatmap only
python orchestrator.py --update-heatmap
```

### Frontend

```bash
python -m http.server 8080
# Open: http://localhost:8080/ATLAS.html
```

### Google Maps Scraper

```bash
cd gmaps-scraper
npm install
node run_batch.js
```

---

## Configuration

### backend/config.py

```python
BASE_PACKAGES     = "data/packages.csv"
BASE_PARTNERS     = "data/partners.json"
BASE_JURISDICTION = "data/jurisdiction.geojson"
DEST_FOLDER       = "data/"
H3_RESOLUTION     = 9
H3_RES_PER_STATION = {"DSP2": 8, "DRJ3": 8}
MIN_CAPACITY      = 40
MAX_CAPACITY      = 42
CLUSTER_PER_STATION = {"DSP2": 8, "DBH5": 4}
DB_EMPRESAS       = "path/to/cnpj_2025_06.db"
ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "00XXXXX", "buckets": ["DSP2_bucket-01"]},
]
```

### js/config.js

```js
export const DATA_URLS = { partners: "...", territories: "...", ... };
export const HCP_CONFIG = { maxPickupsPerHost: 5, maxDistanceM: 6000, ... };
export const CNPJ_API_URL = "https://api-cnpj-br.vercel.app/api/buscar";
```

---

## Dependencies

### Backend (Python)

| Library | Min Version | Usage |
|---|---|---|
| `h3` | 4.x | Geospatial hexagon indexing |
| `pandas` | 1.5+ | Tabular data manipulation |
| `numpy` | 1.23+ | Matrix operations |
| `scipy` | 1.9+ | Voronoi and assignment |
| `shapely` | 2.0+ | Polygon operations |
| `ortools` | 9.x | CP-SAT solver |
| `pyproj` | 3.x | UTM projection |

### Frontend (JavaScript)

| Library | Usage |
|---|---|
| Leaflet.js | Interactive map |
| Leaflet Routing Machine | OSRM routes |
| Turf.js | Geospatial operations in browser |
| Tabulator | Data tables |

### Google Maps Scraper (Node.js)

| Package | Usage |
|---|---|
| `puppeteer` | Headless Google Maps scraping |
| `express` | Local REST API (optional) |
| `cors` | CORS control |
