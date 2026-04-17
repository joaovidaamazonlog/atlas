﻿# ATLAS — Analytical Tracking for Location and Store performance

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
  - [Pipeline GeoIntelligence v2](#pipeline-geointelligence-v2)
  - [Frontend — Interface Interativa](#frontend--interface-interativa)
  - [Frontend React (atlas-react)](#frontend-react-atlas-react)
  - [Google Maps Scraper e API de Prospecção](#google-maps-scraper-e-api-de-prospecção)
  - [Estrutura de Arquivos](#estrutura-de-arquivos)
  - [Como Usar](#como-usar)
  - [Configuração](#configuração)
  - [Dependências](#dependências)
- [English](#english)
  - [What is ATLAS](#what-is-atlas)
  - [Features](#features)
  - [General Architecture](#general-architecture)
  - [Backend — Optimization Pipeline](#backend--optimization-pipeline)
  - [GeoIntelligence Pipeline v2](#geointelligence-pipeline-v2)
  - [Frontend — Interactive Interface](#frontend--interactive-interface)
  - [React Frontend (atlas-react)](#react-frontend-atlas-react)
  - [Google Maps Scraper and Prospecting API](#google-maps-scraper-and-prospecting-api)
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


┌─────────────────────────────────────────────────────────────┐
│           GEOINTELLIGENCE V2 PIPELINE (Python + ML)        │
│                                                             │
│  Fase 1: Area Intelligence (H3 + enrichers + classifier)    │
│  Fase 2: Ideal Supply (CP-SAT solver)                       │
│  Fase 3: Territory Fit (matching)                           │
│  → Resultados persistidos no Turso (libSQL)                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│           FRONTEND REACT — atlas-react (React 18)           │
│                                                             │
│  Vite + TypeScript + Leaflet + Zustand + Tailwind CSS       │
│  Mapa interativo, dashboard KPIs, prospecção de leads       │
│  PWA com Web Worker para processamento assíncrono           │
└─────────────────────────────────────────────────────────────┘
```\n\n---\n\n## Backend — Pipeline de Otimização

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


## Pipeline GeoIntelligence v2

Pipeline baseado em H3 + ML para expansão territorial orientada a dados. Roda independente do pipeline principal e responde à pergunta: **"Quais territórios têm maior potencial para novos parceiros?"**

```bash
cd backend
python geo_intelligence/geo_orchestrator.py --mode setup --target 50
python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2
python geo_intelligence/geo_orchestrator.py --update-heatmap
```

### Visão Geral das Fases

```
packages.csv + partners.json
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  FASE 1 — Area Intelligence                                 │
│                                                             │
│  Ingestor → Enrichers (CNPJ, OSM, IBGE, Satélite)          │
│  → Feature Engineering (24 features, imputação, min-max)   │
│  → Profile Builder (Success/Failure vectors)                │
│  → Classifier (UMAP → HDBSCAN / KMeans / Random Forest)    │
│  → Potential Calculator (score [0-100] por hex e território)│
│  → Area Selector (top N% por gap)                           │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  FASE 2 — Ideal Supply (CP-SAT)                             │
│  Posiciona vagas ideais nos territórios selecionados        │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  FASE 3 — Territory Fit                                     │
│  Matching de parceiros existentes com territórios           │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
   Turso (libSQL) — resultados persistidos
   Camada showGeoIntelligence no mapa
```

---

### Fase 1 — Area Intelligence (ML detalhado)

#### 1.1 Ingestor

Mapeia entregas históricas para hexágonos H3 resolução 8 (~1 km²) dentro da jurisdição da base.

- Lê `packages.csv` (lat, lon, station_code)
- Converte cada entrega para `h3.latlng_to_cell(lat, lon, res=8)`
- Filtra hexes fora do polígono de jurisdição via `shapely.contains(centroide)`
- Aplica `DELIVERY_DENSITY_THRESHOLD = 5` entregas/dia — hexes abaixo são descartados (sem demanda viável)
- Resultado: `{h3_id: delivery_count}` — apenas hexes com demanda real

#### 1.2 Enrichers — Fontes de Dados

Cada enricher é independente e tem degradação graciosa (falha → features `None`, pipeline continua).

**CnpjEnricher** (Turso/libSQL):
- Consulta tabela `empresas_geo` com `h3_id` pré-computado
- Calcula por hex (~0.1 km²):
  - `company_density` — total de empresas / área
  - `cnae_diversity_index` — entropia de Shannon normalizada sobre CNAEs (diversidade econômica)
  - `target_business_density` — empresas com CNAE 5320/5310/5229/5212/5211 (logística/entrega) / área
  - `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density` — densidades por tipo de estabelecimento (proxy de fluxo de pessoas)

**OsmEnricher** (OpenStreetMap via osmnx):
- Extrai features urbanas por bounding box do hex:
  - `building_density` — edifícios / km²
  - `avg_building_size_m2` — área média das footprints (m²)
  - `landuse_residential_ratio` / `landuse_commercial_ratio` — fração da área por tipo de uso
  - `poi_density` — pontos de interesse / km²
  - `road_connectivity_index` — grau médio dos nós na rede viária (acessibilidade)
  - `landuse_entropy` — entropia de Shannon sobre categorias de landuse (diversidade urbana)
  - `road_centrality_index` — betweenness centralidade média da rede viária (normalizado)
  - `local_clustering_coefficient` — coeficiente de clustering médio da rede viária

**IbgeEnricher** (Censo 2022):
- Interseção geométrica entre o hex H3 e setores censitários IBGE
- Média ponderada pela área de interseção:
  - `avg_income` — renda média do setor
  - `population_density` — densidade demográfica
- Download automático do shapefile por UF via API IBGE se não existir localmente

**SatelliteEnricher** (Google Earth Engine):
- `ndvi_mean` — índice de vegetação NDVI médio (Landsat 8, últimos 12 meses, cloud < 20%)
- `urban_density_index` — proporção de superfície construída (GHSL GHS_BUILT_S, normalizado para [0,1])
- `built_up_ratio` — fração de pixels construídos (GHSL GHS_BUILT_C)
- `morphology_class` — classificação da morfologia urbana por thresholds:
  - `ndvi > 0.4` → `green_area`
  - `urban_density > 0.8` → `high_density_urban`
  - `urban_density > 0.4` → `low_density_urban`
  - `built_up > 0.6 AND ndvi < 0.1` → `commercial_industrial`
  - `built_up > 0.3 AND urban_density < 0.3` → `informal_settlement`
  - else → `rural`

#### 1.3 Feature Engineering

Pipeline: **build → impute → normalize**

**24 features numéricas** consolidadas de todos os enrichers:

| Grupo | Features |
|---|---|
| Econômicas (CNPJ) | `company_density`, `cnae_diversity_index`, `target_business_density`, `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density` |
| Urbanas (OSM) | `building_density`, `avg_building_size_m2`, `landuse_residential_ratio`, `landuse_commercial_ratio`, `poi_density`, `road_connectivity_index`, `landuse_entropy`, `road_centrality_index`, `local_clustering_coefficient` |
| Socioeconômicas (IBGE) | `avg_income`, `population_density` |
| Satélite (GEE) | `ndvi_mean`, `urban_density_index`, `built_up_ratio` |
| Derivadas (v2) | `commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2` |
| Contexto (v2) | `delivery_density_r8` — volume normalizado de entregas no hex (peso máx `DELIVERY_DENSITY_WEIGHT = 0.10`) |

**Imputação por vizinhança H3:**
Valores `None` são imputados pela mediana dos hexes no `grid_disk(h, 1)` (anel de 6 vizinhos). Isso preserva a continuidade espacial sem introduzir viés global.

**Normalização min-max por DS:**
Cada feature é normalizada para `[0, 1]` dentro da base (`(x - min) / (max - min)`). Os parâmetros são persistidos em `models/{station_code}_norm_params_{timestamp}.json` (mantém os 3 mais recentes).

#### 1.4 Profile Builder — Memória Institucional

Constrói dois vetores de referência a partir do histórico de parceiros:

**Success Vector** — média ponderada por `log(1 + tenure_days)` dos parceiros `Active` com tenure ≥ 30 dias. Representa o perfil geográfico de onde parceiros prosperam.

**Failure Vector** — média ponderada por `area_penalty × log(1 + tenure_days)` dos parceiros `Exited` com `exit_reason_class = "area_signal"`. Representa onde a área em si causou a saída (não o parceiro).

Classificação de motivos de saída:

| Motivo | Classe | Penalidade |
|---|---|---|
| `volume_insuficiente` | `area_signal` | 1.0 |
| `acesso_dificil` | `area_signal` | 0.8 |
| `sobreposicao` | `area_signal` | 0.5 |
| `operacional` | `partner_signal` | 0.2 |
| `falencia`, `desistencia_voluntaria`, `compliance` | `partner_signal` | 0.0 |

Fallback global: se `n_active < 3`, usa perfil global pré-construído para evitar overfitting em bases novas.

`profile_coverage` mede a fração de hexes com pelo menos um parceiro no `grid_disk(h, 1)`. Alerta se < 10%.

Vetores persistidos em `models/{station_code}_success_{timestamp}.npy` e `_failure_{timestamp}.npy`.

#### 1.5 Classifier — UMAP → HDBSCAN

**Objetivo:** classificar cada hex em um `RegionType` (tipo de região) para ponderar o potential score.

**Pipeline de classificação:**

```
Feature Matrix (n_cells × 24)
        │
        ▼
   UMAP (n_components=2, n_neighbors=15, min_dist=0.1)
   Redução dimensional não-linear — preserva estrutura local
        │
        ▼
   HDBSCAN (min_cluster_size = max(5, n//20))
   Clustering hierárquico baseado em densidade
   Detecta clusters de forma arbitrária + ruído (label=-1)
        │
        ├─ < 3 clusters → fallback KMeans (k=6)
        │
        ▼
   Silhouette Score — alerta se < 0.2 (clustering de baixa qualidade)
        │
        ▼
   Semantic Anchors (opcional)
   Mapeia cluster_id → RegionType via hex de referência configurado
        │
        ▼
   CellClassification {h3_id, region_type, model_confidence, low_confidence}
```

**RegionTypes disponíveis:**

| Tipo | Peso no potential score |
|---|---|
| `comercial` | 1.0 |
| `residencial_alta_renda` | 0.9 |
| `alto_padrao` | 0.85 |
| `residencial_media_renda` | 0.7 |
| `residencial_baixa_renda` | 0.5 |
| `favela_comunidade` | 0.4 |
| `industrial` | 0.3 |
| `rural` | 0.1 |

**Confiança do modelo:** calculada como `1 - (distância ao centroide / distância máxima)` no espaço UMAP. Hexes com confiança < 0.5 são marcados como `low_confidence`.

**Modo supervisionado (quando há dados rotulados suficientes):**
Se `labeled_data` for fornecido com ≥ 50 amostras por classe, treina um **Random Forest** (ou XGBoost se disponível) sobre as features brutas (não UMAP). Métricas por classe (precision, recall, F1) são logadas. O modelo é persistido em `models/{station_code}_{timestamp}.joblib`.

O modelo UMAP é salvo em `models/{station_code}_umap_{timestamp}.joblib` e um scatter plot em `models/{station_code}_umap_scatter_{timestamp}.png` para inspeção visual.

#### 1.6 Potential Calculator

**Score por hex (cell-level):**

```
potential = Σ(weight_i × feature_i) / Σ(weight_i)
```

Onde as features e pesos são:

| Feature | Peso |
|---|---|
| `target_business_density` | 0.25 |
| `avg_income` | 0.20 |
| `region_type_weight` | 0.20 |
| `population_density` | 0.15 |
| `road_connectivity_index` | 0.10 |
| `commercial_activity_index` | 0.10 |

**Agregação por território:**
Média ponderada pelo volume de entregas (`delivery_count`) dos hexes do território. Normalizada para `[0, 100]` dentro da DS (max = 100).

**Gap:**
```
gap = potential_score - (current_partners / ideal_slots × 100)
```
Territórios com `gap > 20` são marcados como `high_opportunity`.

**Modo similarity (v2):**
Quando há perfis de referência, usa similaridade de cosseno no espaço UMAP:
```
raw_score = cosine_sim(cell_umap, success_umap)
           - FAILURE_PENALTY_WEIGHT × cosine_sim(cell_umap, failure_umap)
```
Penalidades adicionais:
- Fast-exit penalty (`-0.20`) se o hex tem histórico de 2+ saídas rápidas (< 180 dias) por `area_signal`
- Delivery density gate: `raw_score = 0` se `delivery_density < DELIVERY_DENSITY_THRESHOLD`

Resultados persistidos no Turso. Camada `showGeoIntelligence` disponível no mapa.

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


## Frontend React (atlas-react)

Versão moderna do ATLAS em React 18 + TypeScript + Leaflet + Zustand. Substitui progressivamente o frontend legado.

```bash
cd atlas-react
npm install
npm run dev    # desenvolvimento
npm run build  # produção
npm test       # testes (vitest --run)
```

- Mapa interativo: marcadores, polígonos, heatmap, rotas, camada GeoIntelligence v2
- Painel de controles: Filtros, Rotas, Prospecção, Análise de Área, Estilo
- Dashboard com KPIs, gráficos (Chart.js) e tabela de estações
- Prospecção de leads com clustering visual e integração com a API
- PWA com service worker, Web Worker para processamento assíncrono
- Tema claro/escuro, layout responsivo (Tailwind CSS)

| Biblioteca | Uso |
|---|---|
| React 18 + TypeScript | UI e tipagem |
| Vite | Build e dev server |
| Leaflet + react-leaflet | Mapa interativo |
| @turf/turf | Operações geoespaciais |
| Zustand | Estado global |
| Chart.js | Gráficos |
| Tailwind CSS | Estilização |
| Vitest + fast-check | Testes + PBT |

---

## Google Maps Scraper e API de Prospecção

Ecossistema de prospecção de leads composto por dois serviços complementares.

### Google Maps Scraper (Node.js)

Serviço Node.js que roda via GitHub Actions para gerar o banco de dados de empresas candidatas.

#### Tipos de negócio buscados
- Lanchonete
- Açaí e sorveteria
- Chaveiro
- Assistência técnica

#### Instalação

```bash
cd _api_backend/gmaps_scraper
npm install
node run_batch.js                          # todas as bases
node run_batch.js --stations DSP2 DBH5    # bases específicas
```

### API de Prospecção (FastAPI + Vercel)

FastAPI deployada no Vercel. Conecta ao Turso via HTTP API para busca de leads e rastreamento de contatos.

#### Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api` | Status da API |
| POST | `/api/empresas` | Busca empresas por CEPs e/ou territory_id |
| POST | `/api/empresas/contactada` | Marca/desmarca lead como contactado |

#### Deploy local

```bash
cd _api_backend
pip install -r requirements.txt
uvicorn api.main:app --reload
```

Variáveis de ambiente: `TURSO_URL`, `TURSO_TOKEN`.

#### ETL CNPJ

```bash
python _api_backend/etl_cnpj.py           # versão padrão
python _api_backend/etl_cnpj_low_mem.py   # versão low-memory
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


┌─────────────────────────────────────────────────────────────┐
│           GEOINTELLIGENCE V2 PIPELINE (Python + ML)        │
│                                                             │
│  Phase 1: Area Intelligence (H3 + enrichers + classifier)   │
│  Phase 2: Ideal Supply (CP-SAT solver)                      │
│  Phase 3: Territory Fit (matching)                          │
│  → Results persisted in Turso (libSQL)                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│           REACT FRONTEND — atlas-react (React 18)           │
│                                                             │
│  Vite + TypeScript + Leaflet + Zustand + Tailwind CSS       │
│  Interactive map, KPI dashboard, lead prospecting           │
│  PWA with Web Worker for async data processing              │
└─────────────────────────────────────────────────────────────┘
```\n\n---\n\n## Backend — Optimization Pipeline

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


## GeoIntelligence Pipeline v2

H3 + ML-based pipeline for data-driven territorial expansion. Runs independently from the main pipeline and answers: **"Which territories have the highest potential for new partners?"**

```bash
cd backend
python geo_intelligence/geo_orchestrator.py --mode setup --target 50
python geo_intelligence/geo_orchestrator.py --mode setup --target 50 --stations DSP2
python geo_intelligence/geo_orchestrator.py --update-heatmap
```

### Phase Overview

```
packages.csv + partners.json
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1 — Area Intelligence                                │
│                                                             │
│  Ingestor → Enrichers (CNPJ, OSM, IBGE, Satellite)         │
│  → Feature Engineering (24 features, imputation, min-max)  │
│  → Profile Builder (Success/Failure vectors)                │
│  → Classifier (UMAP → HDBSCAN / KMeans / Random Forest)    │
│  → Potential Calculator (score [0-100] per hex/territory)   │
│  → Area Selector (top N% by gap)                            │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2 — Ideal Supply (CP-SAT)                            │
│  Positions ideal slots in selected territories              │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3 — Territory Fit                                    │
│  Matches existing partners to territories                   │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
   Turso (libSQL) — persisted results
   showGeoIntelligence layer on the map
```

---

### Phase 1 — Area Intelligence (ML detail)

#### 1.1 Ingestor

Maps historical deliveries to H3 hexagons at resolution 8 (~1 km²) within the station's jurisdiction.

- Reads `packages.csv` (lat, lon, station_code)
- Converts each delivery to `h3.latlng_to_cell(lat, lon, res=8)`
- Filters hexes outside the jurisdiction polygon via `shapely.contains(centroid)`
- Applies `DELIVERY_DENSITY_THRESHOLD = 5` deliveries/day — hexes below are discarded (no viable demand)
- Output: `{h3_id: delivery_count}` — only hexes with real demand

#### 1.2 Enrichers — Data Sources

Each enricher is independent with graceful degradation (failure → features `None`, pipeline continues).

**CnpjEnricher** (Turso/libSQL):
- Queries `empresas_geo` table with pre-computed `h3_id`
- Computes per hex (~0.1 km²):
  - `company_density` — total companies / area
  - `cnae_diversity_index` — normalized Shannon entropy over CNAEs (economic diversity)
  - `target_business_density` — companies with CNAE 5320/5310/5229/5212/5211 (logistics/delivery) / area
  - `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density` — densities by establishment type (foot traffic proxy)

**OsmEnricher** (OpenStreetMap via osmnx):
- Extracts urban features per hex bounding box:
  - `building_density` — buildings / km²
  - `avg_building_size_m2` — average building footprint area (m²)
  - `landuse_residential_ratio` / `landuse_commercial_ratio` — area fraction by land use type
  - `poi_density` — points of interest / km²
  - `road_connectivity_index` — average node degree in road network (accessibility)
  - `landuse_entropy` — Shannon entropy over land use categories (urban diversity)
  - `road_centrality_index` — average betweenness centrality of road network (normalized)
  - `local_clustering_coefficient` — average clustering coefficient of road network

**IbgeEnricher** (Census 2022):
- Geometric intersection between H3 hex and IBGE census sectors
- Area-weighted average:
  - `avg_income` — sector average income
  - `population_density` — demographic density
- Auto-downloads state shapefile from IBGE API if not found locally

**SatelliteEnricher** (Google Earth Engine):
- `ndvi_mean` — average NDVI vegetation index (Landsat 8, last 12 months, cloud < 20%)
- `urban_density_index` — built surface proportion (GHSL GHS_BUILT_S, normalized to [0,1])
- `built_up_ratio` — fraction of built pixels (GHSL GHS_BUILT_C)
- `morphology_class` — urban morphology classification by thresholds:
  - `ndvi > 0.4` → `green_area`
  - `urban_density > 0.8` → `high_density_urban`
  - `urban_density > 0.4` → `low_density_urban`
  - `built_up > 0.6 AND ndvi < 0.1` → `commercial_industrial`
  - `built_up > 0.3 AND urban_density < 0.3` → `informal_settlement`
  - else → `rural`

#### 1.3 Feature Engineering

Pipeline: **build → impute → normalize**

**24 numeric features** consolidated from all enrichers:

| Group | Features |
|---|---|
| Economic (CNPJ) | `company_density`, `cnae_diversity_index`, `target_business_density`, `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density` |
| Urban (OSM) | `building_density`, `avg_building_size_m2`, `landuse_residential_ratio`, `landuse_commercial_ratio`, `poi_density`, `road_connectivity_index`, `landuse_entropy`, `road_centrality_index`, `local_clustering_coefficient` |
| Socioeconomic (IBGE) | `avg_income`, `population_density` |
| Satellite (GEE) | `ndvi_mean`, `urban_density_index`, `built_up_ratio` |
| Derived (v2) | `commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2` |
| Context (v2) | `delivery_density_r8` — normalized delivery volume in hex (max weight `DELIVERY_DENSITY_WEIGHT = 0.10`) |

**H3 neighborhood imputation:**
`None` values are imputed by the median of hexes in `grid_disk(h, 1)` (ring of 6 neighbors). This preserves spatial continuity without introducing global bias.

**Min-max normalization per DS:**
Each feature is normalized to `[0, 1]` within the station (`(x - min) / (max - min)`). Parameters are persisted in `models/{station_code}_norm_params_{timestamp}.json` (keeps 3 most recent).

#### 1.4 Profile Builder — Institutional Memory

Builds two reference vectors from partner history:

**Success Vector** — tenure-weighted average (`log(1 + tenure_days)`) of `Active` partners with tenure ≥ 30 days. Represents the geographic profile of where partners thrive.

**Failure Vector** — weighted average (`area_penalty × log(1 + tenure_days)`) of `Exited` partners with `exit_reason_class = "area_signal"`. Represents where the area itself caused the exit (not the partner).

Exit reason classification:

| Reason | Class | Penalty |
|---|---|---|
| `volume_insuficiente` | `area_signal` | 1.0 |
| `acesso_dificil` | `area_signal` | 0.8 |
| `sobreposicao` | `area_signal` | 0.5 |
| `operacional` | `partner_signal` | 0.2 |
| `falencia`, `desistencia_voluntaria`, `compliance` | `partner_signal` | 0.0 |

Global fallback: if `n_active < 3`, uses a pre-built global profile to avoid overfitting on new stations.

`profile_coverage` measures the fraction of hexes with at least one partner in `grid_disk(h, 1)`. Warns if < 10%.

Vectors persisted in `models/{station_code}_success_{timestamp}.npy` and `_failure_{timestamp}.npy`.

#### 1.5 Classifier — UMAP → HDBSCAN

**Goal:** classify each hex into a `RegionType` to weight the potential score.

**Classification pipeline:**

```
Feature Matrix (n_cells × 24)
        │
        ▼
   UMAP (n_components=2, n_neighbors=15, min_dist=0.1)
   Non-linear dimensionality reduction — preserves local structure
        │
        ▼
   HDBSCAN (min_cluster_size = max(5, n//20))
   Hierarchical density-based clustering
   Detects arbitrary-shape clusters + noise (label=-1)
        │
        ├─ < 3 clusters → fallback KMeans (k=6)
        │
        ▼
   Silhouette Score — warns if < 0.2 (low quality clustering)
        │
        ▼
   Semantic Anchors (optional)
   Maps cluster_id → RegionType via configured reference hex
        │
        ▼
   CellClassification {h3_id, region_type, model_confidence, low_confidence}
```

**Available RegionTypes:**

| Type | Weight in potential score |
|---|---|
| `comercial` | 1.0 |
| `residencial_alta_renda` | 0.9 |
| `alto_padrao` | 0.85 |
| `residencial_media_renda` | 0.7 |
| `residencial_baixa_renda` | 0.5 |
| `favela_comunidade` | 0.4 |
| `industrial` | 0.3 |
| `rural` | 0.1 |

**Model confidence:** calculated as `1 - (distance to centroid / max distance)` in UMAP space. Hexes with confidence < 0.5 are flagged as `low_confidence`.

**Supervised mode (when enough labeled data is available):**
If `labeled_data` is provided with ≥ 50 samples per class, trains a **Random Forest** (or XGBoost if available) on raw features (not UMAP). Per-class metrics (precision, recall, F1) are logged. Model persisted in `models/{station_code}_{timestamp}.joblib`.

The UMAP model is saved in `models/{station_code}_umap_{timestamp}.joblib` and a scatter plot in `models/{station_code}_umap_scatter_{timestamp}.png` for visual inspection.

#### 1.6 Potential Calculator

**Per-hex score (cell-level):**

```
potential = Σ(weight_i × feature_i) / Σ(weight_i)
```

Features and weights:

| Feature | Weight |
|---|---|
| `target_business_density` | 0.25 |
| `avg_income` | 0.20 |
| `region_type_weight` | 0.20 |
| `population_density` | 0.15 |
| `road_connectivity_index` | 0.10 |
| `commercial_activity_index` | 0.10 |

**Territory aggregation:**
Delivery-volume-weighted average of hex scores within the territory. Normalized to `[0, 100]` within the DS (max = 100).

**Gap:**
```
gap = potential_score - (current_partners / ideal_slots × 100)
```
Territories with `gap > 20` are flagged as `high_opportunity`.

**Similarity mode (v2):**
When reference profiles are available, uses cosine similarity in UMAP space:
```
raw_score = cosine_sim(cell_umap, success_umap)
           - FAILURE_PENALTY_WEIGHT × cosine_sim(cell_umap, failure_umap)
```
Additional penalties:
- Fast-exit penalty (`-0.20`) if the hex has a history of 2+ fast exits (< 180 days) due to `area_signal`
- Delivery density gate: `raw_score = 0` if `delivery_density < DELIVERY_DENSITY_THRESHOLD`

Results persisted in Turso. `showGeoIntelligence` layer available on the map.

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


## React Frontend (atlas-react)

Modern ATLAS version in React 18 + TypeScript + Leaflet + Zustand. Progressively replacing the legacy frontend.

```bash
cd atlas-react
npm install
npm run dev    # development
npm run build  # production
npm test       # tests (vitest --run)
```

- Interactive Leaflet map: markers, polygons, heatmap, routes, GeoIntelligence v2 layer
- Control panel: Filters, Routes, Prospecting, Area Analysis, Style
- Dashboard with KPIs, charts (Chart.js) and stations table
- Lead prospecting with visual clustering and API integration
- PWA with service worker, Web Worker for async data processing
- Light/dark theme, responsive layout (Tailwind CSS)

| Library | Usage |
|---|---|
| React 18 + TypeScript | UI and typing |
| Vite | Build and dev server |
| Leaflet + react-leaflet | Interactive map |
| @turf/turf | Geospatial operations |
| Zustand | Global state |
| Chart.js | Charts |
| Tailwind CSS | Styling |
| Vitest + fast-check | Tests + PBT |

---

## Google Maps Scraper and Prospecting API

Lead prospecting ecosystem composed of two complementary services.

### Google Maps Scraper (Node.js)

Node.js service running via GitHub Actions to generate the candidate company database.

#### Business types searched
- Snack bar (lanchonete)
- Acai and ice cream shop
- Locksmith (chaveiro)
- Tech support (assistência técnica)

#### Installation

```bash
cd _api_backend/gmaps_scraper
npm install
node run_batch.js
node run_batch.js --stations DSP2 DBH5
```

### Prospecting API (FastAPI + Vercel)

FastAPI deployed on Vercel. Connects to Turso via HTTP API for lead search and contact tracking.

#### Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/api` | API status |
| POST | `/api/empresas` | Search companies by ZIP codes and/or territory_id |
| POST | `/api/empresas/contactada` | Mark/unmark lead as contacted |

#### Local deploy

```bash
cd _api_backend
pip install -r requirements.txt
uvicorn api.main:app --reload
```

Environment variables: `TURSO_URL`, `TURSO_TOKEN`.

#### CNPJ ETL

```bash
python _api_backend/etl_cnpj.py           # standard version
python _api_backend/etl_cnpj_low_mem.py   # low-memory version
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