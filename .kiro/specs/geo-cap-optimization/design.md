# Design Document — Geo Cap Optimization

## Visão Geral

Esta feature porta o conceito de otimização de capacidade (Fase 3.5) para o pipeline GeoIntelligence (`backend/geo_intelligence/`). O objetivo é identificar, para cada parceiro Active com `capacity < 80`, se existe demanda não coberta no heatmap GeoIntelligence que justifique aumentar o cap atual, e qual seria a melhor posição dentro de ~300 m do centroid atual para capturar essa demanda.

O módulo `geo_phase3_5_cap_optimizer.py` é inserido no modo `daily` do orquestrador **após** `run_daily()` (matching) e **antes** de `writer.update_supply_match` / `writer.update_territory_fit`. Falhas são capturadas com `try/except` para não abortar o pipeline.

As principais diferenças em relação ao pipeline vanilla (`phase3_5_cap_optimizer.py`) são:

| Aspecto | Vanilla | Geo |
|---|---|---|
| Sinal de demanda | `demand_residual` do `heatmap.geojson` | `delivery_density_r9` derivado de `geo_h3_cells` (Turso) |
| Resolução H3 | Resolução da base (`Config.get_h3_res`) | Sempre res 9 (~174 m de edge) |
| Persistência | `dados_mapa.json` (patch) | Turso — tabela `geo_partner_cap_opportunities` |
| Exposição | `dados_mapa.json` → frontend | `geo_api.py` endpoint REST |
| Ponto de entrada | `orchestrator.py` (vanilla) | `geo_orchestrator.py` (modo `daily`) |

**Por que res 9 para análise pontual de parceiro?** A resolução 8 tem edge ~461 m, adequada para análise de área (~1 km²). Para análise pontual de parceiro — onde o raio de busca é ~300 m — a res 9 (edge ~174 m) oferece granularidade suficiente para distinguir hexes dentro e fora do raio de entrega sem over-counting. O `grid_disk(k=3)` em res 9 cobre ~522 m de diâmetro, aproximando bem os 300 m de raio de busca.

---

## Arquitetura

```mermaid
flowchart TD
    subgraph geo_orchestrator.py — modo daily
        RD[run_daily\ngeo_daily.py] --> P35[run_geo_phase3_5\ngeo_phase3_5_cap_optimizer.py]
        P35 -->|try/except| USM[writer.update_supply_match]
        USM --> UTF[writer.update_territory_fit]
    end

    subgraph geo_phase3_5_cap_optimizer.py
        P35 --> LH[_load_h3_index\nTursoReader.get_h3_cells_for_station]
        LH --> DIS[_disaggregate_r8_to_r9\nh3.cell_to_children]
        DIS --> IDX[_build_coverage_index\nHaversine por parceiro Active]
        IDX --> SCAN[_scan_partner\ngrid_disk res9 k=3]
        SCAN --> CALC[_uncovered_demand\nexclui cobertura do próprio parceiro]
        CALC --> SEL[_select_best_candidate\nmax gain, min distance]
        SEL --> UPS[writer.upsert_cap_opportunities]
    end

    subgraph Turso
        GH3[(geo_h3_cells\nres 8 — delivery_density_r8)]
        GPC[(geo_partner_cap_opportunities\nres 9 — oportunidades)]
    end

    subgraph geo_api.py
        EP[GET /geo-intelligence\n/{station_code}/cap-opportunities]
        EP --> TR[TursoReader\n.get_cap_opportunities]
        TR --> GPC
    end

    LH --> GH3
    UPS --> GPC
```

### Decisões de Design

**`geo_phase3_5_cap_optimizer.py` como módulo standalone** — mantém responsabilidade única e facilita testes isolados. O orquestrador envolve a chamada em `try/except` para que falhas não abortem `update_supply_match` e `update_territory_fit`.

**Desagregação res 8 → res 9 em memória** — a tabela `geo_h3_cells` armazena `delivery_density_r8`. O módulo desagrega para res 9 via `h3.cell_to_children(h3_id_r8, 9)`, distribuindo `delivery_density_r8` proporcionalmente entre os 7 filhos res 9. O índice `{h3_id_r9: density}` é construído uma única vez por execução e reutilizado para todos os parceiros da base.

**Índice de cobertura Active com auto-exclusão** — ao avaliar o parceiro P, o índice de cobertura exclui a própria cobertura de P. Isso evita que hexes já cobertos por P sejam mascarados, revelando a demanda que P poderia absorver com um cap maior.

**`suggested_radius` via `Config.RADII`** — o menor raio de `Config.RADII` cujo círculo cobre `Demanda_Não_Coberta >= suggested_cap` a partir da posição candidata. Mantém consistência com a Fase 2 (CP-SAT).

**Persistência no Turso com `PRIMARY KEY (partner_id, run_id)`** — permite re-execuções idempotentes via `INSERT ... ON CONFLICT DO UPDATE`.

---

## Componentes e Interfaces

### `backend/geo_intelligence/geo_phase3_5_cap_optimizer.py` (novo)

```python
def run_geo_phase3_5(
    daily_result: GeoDailyResult,
    run_id: str,
    station_code: str,
    writer: TursoWriter,
    reader: TursoReader,
) -> int:
    """
    Fase 3.5 do pipeline GeoIntelligence.

    Avalia todos os parceiros Active do daily_result, identifica oportunidades
    de aumento de cap com base na demanda não coberta de geo_h3_cells (res 9),
    e persiste os resultados em geo_partner_cap_opportunities via TursoWriter.

    Retorna o número de oportunidades identificadas (adv_opportunity não nulo).
    Nunca propaga exceções ao chamador — erros são logados internamente.
    """
```

Funções auxiliares internas:

```python
def _load_h3_index(
    reader: TursoReader,
    station_code: str,
    run_id: str,
) -> Dict[str, float]:
    """
    Carrega geo_h3_cells para a base/run_id e constrói o índice
    {h3_id_r9: delivery_density_r9} via desagregação res 8 → res 9.

    Retorna dict vazio se não houver registros (log de aviso emitido).
    """

def _disaggregate_r8_to_r9(
    h3_id_r8: str,
    density_r8: float,
) -> Dict[str, float]:
    """
    Desagrega delivery_density_r8 de um hexágono res 8 para seus filhos res 9.

    Usa h3.cell_to_children(h3_id_r8, 9) — tipicamente 7 filhos.
    Distribui density_r8 proporcionalmente (density_r8 / n_children) por filho.

    Retorna {h3_id_r9: density_r9}.
    """

def _build_coverage_index(
    active_partners: List[GeoPartnerMatch],
    h3_index: Dict[str, float],
    exclude_partner_id: Optional[str] = None,
) -> Set[str]:
    """
    Constrói o conjunto de hexágonos res 9 cobertos por pelo menos um parceiro
    Active (exceto exclude_partner_id, se fornecido).

    Um hexágono é "coberto" se a distância geodésica (Haversine) entre seu
    centro (h3.cell_to_latlng) e o centroid do parceiro é <= raio do parceiro.

    Retorna set de h3_id_r9 cobertos.
    """

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distância geodésica em metros entre dois pontos (fórmula de Haversine).
    Usada para determinar cobertura de parceiros e distância de candidatos.
    """

def _scan_partner(
    partner: GeoPartnerMatch,
    h3_index: Dict[str, float],
    coverage_index: Set[str],
) -> Optional[Dict]:
    """
    Varre posições candidatas para um parceiro under-cap.

    1. Obtém candidatos via h3.grid_disk(origin_hex_r9, k=3) — res 9.
    2. Para cada candidato, calcula Demanda_Não_Coberta (excluindo coverage_index).
    3. Seleciona o candidato com maior estimated_adv_gain (desempate: menor distância).
    4. Calcula suggested_radius via _smallest_radius_for_cap.

    Retorna dict com campos da oportunidade, ou None se nenhum candidato for viável.
    """

def _uncovered_demand(
    candidate_hex: str,
    radius_m: int,
    h3_index: Dict[str, float],
    coverage_index: Set[str],
) -> float:
    """
    Soma delivery_density_r9 dos hexágonos res 9 dentro de radius_m do centro
    de candidate_hex que NÃO estão em coverage_index.

    Usa Haversine para determinar se cada hex está dentro do raio.
    Trata density None/ausente como 0.0.
    """

def _smallest_radius_for_cap(
    candidate_hex: str,
    target_cap: int,
    h3_index: Dict[str, float],
    coverage_index: Set[str],
) -> Optional[int]:
    """
    Retorna o menor valor de Config.RADII cujo raio cobre
    Demanda_Não_Coberta >= target_cap a partir de candidate_hex.

    Retorna None se nenhum raio de Config.RADII for suficiente
    (posição candidata descartada).
    """

def _select_best_candidate(
    candidates: List[Dict],
) -> Optional[Dict]:
    """
    Seleciona o melhor candidato da lista:
    - Critério primário: maior estimated_adv_gain
    - Critério de desempate: menor distance_from_current

    Retorna None se a lista estiver vazia.
    """
```

### `backend/geo_intelligence/geo_orchestrator.py` (modificação)

Na função `run_daily`, após `_run_daily(...)` e antes de `writer.update_supply_match`:

```python
# Fase 3.5 — Cap Optimization (GeoIntelligence)
try:
    from geo_intelligence.geo_phase3_5_cap_optimizer import run_geo_phase3_5
    n_opportunities = run_geo_phase3_5(
        daily_result=daily_result,
        run_id=run_id,
        station_code=station_code,
        writer=writer,
        reader=reader,
    )
    logger.info(
        "[%s] Fase 3.5 Geo: %d oportunidades identificadas em %d parceiros avaliados.",
        station_code,
        n_opportunities,
        len([m for m in daily_result.matched + daily_result.unmatched
             if m.status == "Active"]),
    )
except Exception as exc:
    logger.error("[%s] Fase 3.5 Geo falhou (pipeline continua): %s", station_code, exc)
```

### `backend/geo_intelligence/turso_writer.py` (modificação)

Novo método `upsert_cap_opportunities`:

```python
def upsert_cap_opportunities(
    self,
    run_id: str,
    opportunities: List[Dict],
) -> None:
    """
    Persiste ou atualiza registros em geo_partner_cap_opportunities.

    Cada dict em opportunities deve conter:
      partner_id, station_code, suggested_lat, suggested_lon,
      suggested_cap, suggested_radius, estimated_adv_gain,
      distance_from_current, created_at

    Usa INSERT ... ON CONFLICT(partner_id, run_id) DO UPDATE.
    """
```

### `backend/geo_intelligence/turso_reader.py` (modificação)

Novo método `get_cap_opportunities`:

```python
def get_cap_opportunities(
    self,
    station_code: str,
    run_id: Optional[str] = None,
    only_with_opportunity: bool = False,
) -> List[Dict]:
    """
    Retorna registros de geo_partner_cap_opportunities para a base/run_id.

    Se run_id não for fornecido, resolve automaticamente o run_id mais
    recente via get_latest_run_id(station_code).

    Se only_with_opportunity=True, filtra apenas registros com
    estimated_adv_gain IS NOT NULL.

    Cache TTL 5 min com chave 'cap_opportunities:{station_code}:{run_id}'.
    Retorna lista vazia (não lança exceção) se não houver registros.
    """
```

Novo método auxiliar `get_h3_cells_for_station`:

```python
def get_h3_cells_for_station(
    self,
    station_code: str,
    run_id: str,
) -> List[Dict]:
    """
    Retorna todos os registros de geo_h3_cells para a base/run_id.
    Cache TTL 5 min com chave 'h3_cells_station:{station_code}:{run_id}'.
    """
```

### `backend/geo_intelligence/geo_api.py` (modificação)

Novo endpoint:

```python
@app.get("/geo-intelligence/{station_code}/cap-opportunities")
def get_cap_opportunities(
    station_code: str,
    run_id: Optional[str] = Query(default=None),
    only_with_opportunity: bool = Query(default=False),
) -> List[Dict[str, Any]]:
    """
    Retorna oportunidades de cap para a base especificada.

    Query params:
      run_id               — run_id específico; se omitido, usa o mais recente
      only_with_opportunity — se true, retorna apenas registros com
                              estimated_adv_gain IS NOT NULL

    Ordenação: estimated_adv_gain DESC (nulls por último).

    HTTP 200 com lista vazia se não houver oportunidades.
    HTTP 404 se run_id mais recente não for encontrado para a base.
    """
```

---

## Modelos de Dados

### Schema DDL — `geo_partner_cap_opportunities`

```sql
CREATE TABLE IF NOT EXISTS geo_partner_cap_opportunities (
    partner_id              TEXT    NOT NULL,  -- salesforce_id do parceiro
    run_id                  TEXT    NOT NULL,  -- run_id do setup GeoIntelligence
    station_code            TEXT    NOT NULL,  -- código da base (ex: 'DSP2')
    suggested_lat           REAL,              -- latitude da posição sugerida (null = sem oportunidade)
    suggested_lon           REAL,              -- longitude da posição sugerida (null = sem oportunidade)
    suggested_cap           INTEGER,           -- cap sugerido (null = sem oportunidade)
    suggested_radius        INTEGER,           -- raio sugerido em metros (null = sem oportunidade)
    estimated_adv_gain      INTEGER,           -- suggested_cap - capacity_atual (null = sem oportunidade)
    distance_from_current   REAL,              -- distância geodésica em metros do centroid atual (null = sem oportunidade)
    created_at              TEXT    NOT NULL,  -- timestamp ISO 8601
    PRIMARY KEY (partner_id, run_id)
);
```

O DDL é adicionado à lista `_DDL_STATEMENTS` em `turso_writer.py` e criado via `ensure_schema()`.

### Objeto de oportunidade (resposta da API)

```json
{
  "partner_id": "0015g00000AbCdEfG",
  "run_id": "DSP2_20250715_143022_a1b2c3d4",
  "station_code": "DSP2",
  "suggested_lat": -23.5505,
  "suggested_lon": -46.6333,
  "suggested_cap": 72,
  "suggested_radius": 800,
  "estimated_adv_gain": 30,
  "distance_from_current": 187.4,
  "created_at": "2025-07-15T14:32:11.000Z"
}
```

Quando não há oportunidade para o parceiro:

```json
{
  "partner_id": "0015g00000XyZwVuT",
  "run_id": "DSP2_20250715_143022_a1b2c3d4",
  "station_code": "DSP2",
  "suggested_lat": null,
  "suggested_lon": null,
  "suggested_cap": null,
  "suggested_radius": null,
  "estimated_adv_gain": null,
  "distance_from_current": null,
  "created_at": "2025-07-15T14:32:11.000Z"
}
```

### Invariantes de dados

- `suggested_cap`: inteiro, `capacity_atual + 1 ≤ suggested_cap ≤ 80` quando não nulo
- `estimated_adv_gain`: inteiro, `= suggested_cap - capacity_atual` quando não nulo
- `distance_from_current`: float em metros, distância geodésica (Haversine) quando não nulo
- `suggested_radius`: inteiro de `Config.RADII` (valores: 200, 500, 800, 1100, 1500 m) quando não nulo

### Fluxo de dados detalhado

```
geo_h3_cells (Turso, res 8)
  └─ h3_id TEXT, delivery_density_r8 REAL
        │
        ▼  _disaggregate_r8_to_r9()
        │  h3.cell_to_children(h3_id_r8, 9) → 7 filhos
        │  density_r9 = density_r8 / 7
        ▼
  índice em memória: {h3_id_r9: density_r9}
        │
        ├─ _build_coverage_index(active_partners, h3_index, exclude=P)
        │    Haversine(hex_center, partner_centroid) <= partner.radius
        │    → Set[h3_id_r9] cobertos (excluindo P)
        │
        └─ para cada parceiro P com capacity < 80:
             h3.grid_disk(origin_hex_r9, k=3) → candidatos res 9
             para cada candidato C:
               _uncovered_demand(C, radius, h3_index, coverage_index)
               → soma density_r9 de hexes dentro do raio de C não cobertos
               se demanda > capacity:
                 suggested_cap = min(int(demanda), 80)
                 suggested_radius = _smallest_radius_for_cap(C, suggested_cap, ...)
                 estimated_adv_gain = suggested_cap - capacity
             _select_best_candidate(candidatos_viáveis)
             → melhor por gain, desempate por distância
                  │
                  ▼
  geo_partner_cap_opportunities (Turso)
    partner_id, run_id, station_code, suggested_*, estimated_adv_gain, ...
```

---

## Propriedades de Corretude

*Uma propriedade é uma característica ou comportamento que deve ser verdadeiro em todas as execuções válidas do sistema — essencialmente, uma declaração formal sobre o que o sistema deve fazer. Propriedades servem como ponte entre especificações legíveis por humanos e garantias de corretude verificáveis por máquina.*

### Propriedade 1: Cobertura total de parceiros Active

*Para qualquer* `GeoDailyResult` contendo N parceiros Active, após a execução de `run_geo_phase3_5`, a lista de oportunidades persistidas deve conter exatamente um registro para cada um dos N parceiros Active — sem omissões silenciosas, independentemente de haver ou não oportunidade.

**Valida: Requisitos 1.2, 10.6**

---

### Propriedade 2: Parceiros com cap >= 80 sempre resultam em oportunidade nula

*Para qualquer* parceiro Active com `capacity >= 80`, `run_geo_phase3_5` deve produzir `suggested_cap = null` e `estimated_adv_gain = null`, independentemente do conteúdo do índice `geo_h3_cells`.

**Valida: Requisitos 1.3, 10.1**

---

### Propriedade 3: Demanda não coberta exclui hexes cobertos por outros parceiros Active

*Para qualquer* posição candidata C, índice `h3_index` e conjunto de parceiros Active (excluindo o parceiro avaliado), a `Demanda_Não_Coberta` calculada por `_uncovered_demand` deve ser igual à soma de `delivery_density_r9` apenas dos hexes dentro do raio de C que **não** estão no `coverage_index`.

**Valida: Requisitos 1.5, 2.3**

---

### Propriedade 4: Auto-exclusão revela demanda do próprio parceiro

*Para qualquer* parceiro P com cobertura exclusiva sobre um conjunto de hexes H (hexes cobertos apenas por P e por nenhum outro parceiro Active), ao calcular a oportunidade de P, os hexes em H devem contribuir para a `Demanda_Não_Coberta` de P (pois a cobertura de P é excluída do índice ao avaliá-lo).

**Valida: Requisito 2.4**

---

### Propriedade 5: Invariante aritmético de suggested_cap e estimated_adv_gain

*Para qualquer* oportunidade não nula gerada por `run_geo_phase3_5`:
- `capacity_atual < suggested_cap ≤ 80`
- `estimated_adv_gain = suggested_cap - capacity_atual`

**Valida: Requisitos 1.6, 3.4, 3.5, 10.3, 10.4**

---

### Propriedade 6: Seleção do melhor candidato

*Para qualquer* conjunto de posições candidatas viáveis para um parceiro, a posição selecionada por `_select_best_candidate` deve ter o maior `estimated_adv_gain`; em caso de empate, a menor `distance_from_current`.

**Valida: Requisitos 1.7, 10.5**

---

### Propriedade 7: Conservação de densidade na desagregação res 8 → res 9

*Para qualquer* hexágono res 8 com `delivery_density_r8 = D`, a soma de `delivery_density_r9` de todos os seus filhos res 9 (via `h3.cell_to_children`) deve ser igual a `D` (dentro de tolerância de ponto flutuante).

**Valida: Requisito 7.2**

---

### Propriedade 8: Simetria e identidade da distância Haversine

*Para quaisquer* dois pontos geográficos A e B:
- `haversine(A, B) == haversine(B, A)` (simetria)
- `haversine(A, A) == 0` (identidade)
- `haversine(A, B) >= 0` (não-negatividade)

**Valida: Requisito 2.5**

---

### Propriedade 9: Determinismo

*Para qualquer* `GeoDailyResult` e índice `h3_index` fixos, executar `run_geo_phase3_5` duas vezes deve produzir resultados idênticos (mesmos `partner_id`, `suggested_cap`, `suggested_lat`, `suggested_lon`, `estimated_adv_gain`).

**Valida: Requisito 10.7**

---

## Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| `geo_h3_cells` vazio para o `run_id` | Log `WARNING`, encerra sem persistir registros em `geo_partner_cap_opportunities` |
| Leitura de `geo_h3_cells` falha com exceção | Log `ERROR`, encerra sem persistir, não propaga ao orquestrador |
| Parceiro sem `origin_hex` ou coordenadas válidas | Log `WARNING` para o parceiro, persiste registro com todos os campos de oportunidade `null`, continua para o próximo |
| `h3.grid_disk` falha para um parceiro | Log `WARNING`, persiste `null` para esse parceiro, continua |
| `h3.cell_to_latlng` falha para um hex candidato | Ignora o hex, continua avaliação dos demais candidatos |
| `upsert_cap_opportunities` falha no TursoWriter | Log `ERROR`, encerra sem propagar ao orquestrador |
| Exceção não tratada por parceiro individual | Capturada no loop por parceiro; log `WARNING`; persiste `null` para esse parceiro; continua |
| Fase 3.5 inteira falha com exceção não tratada | Orquestrador captura com `try/except`, loga `ERROR`, continua para `update_supply_match` |
| `run_id` mais recente não encontrado (endpoint) | HTTP 404 com mensagem descritiva |
| Nenhuma oportunidade para a base/run_id (endpoint) | HTTP 200 com lista vazia |

---

## Estratégia de Testes

### Testes Unitários

- `_disaggregate_r8_to_r9`: verificar que a soma dos filhos res 9 iguala a densidade do pai res 8
- `_haversine_m`: verificar simetria, identidade e valores conhecidos (ex: distância entre dois pontos com lat/lon fixos)
- `_build_coverage_index`: verificar que hexes dentro do raio estão no índice e hexes fora não estão; verificar auto-exclusão
- `_uncovered_demand`: verificar que hexes cobertos são excluídos da soma
- `_smallest_radius_for_cap`: verificar que retorna o menor raio suficiente de `Config.RADII`
- `_select_best_candidate`: verificar seleção por gain máximo e desempate por distância mínima
- `TursoReader.get_cap_opportunities`: verificar cache TTL, filtro `only_with_opportunity`, lista vazia
- Endpoint `GET /cap-opportunities`: verificar status codes, ordenação, filtros (via `TestClient` do FastAPI)

### Testes Baseados em Propriedades (Hypothesis)

Biblioteca: **Hypothesis** (Python). Mínimo de 100 iterações por propriedade.

Cada teste é anotado com o comentário:
```python
# Feature: geo-cap-optimization, Property N: <texto da propriedade>
```

- **Propriedade 1** — gerar `GeoDailyResult` com lista aleatória de parceiros Active (0–50 parceiros); verificar que todos estão representados na saída
- **Propriedade 2** — gerar parceiros Active com `capacity` em `[80, 200]` e índice `h3_index` aleatório; verificar que `suggested_cap` e `estimated_adv_gain` são `null`
- **Propriedade 3** — gerar índice `h3_index` aleatório, `coverage_index` aleatório e posição candidata; verificar que `_uncovered_demand` soma apenas hexes não cobertos
- **Propriedade 4** — gerar parceiro P com cobertura exclusiva sobre hexes H; verificar que `_uncovered_demand` inclui hexes de H ao calcular oportunidade de P
- **Propriedade 5** — gerar oportunidades válidas com `capacity` em `[1, 79]` e demanda suficiente; verificar invariantes aritméticos
- **Propriedade 6** — gerar conjuntos aleatórios de candidatos viáveis; verificar que `_select_best_candidate` retorna o ótimo
- **Propriedade 7** — gerar hexes res 8 com `density` aleatória em `[0.0, 1000.0]`; verificar conservação após desagregação
- **Propriedade 8** — gerar pares de coordenadas aleatórias; verificar simetria, identidade e não-negatividade de `_haversine_m`
- **Propriedade 9** — gerar `GeoDailyResult` e `h3_index` aleatórios; executar `run_geo_phase3_5` duas vezes com mocks determinísticos; verificar igualdade dos resultados

### Testes de Integração

- Ordem de chamadas no orquestrador: mock de `run_geo_phase3_5` e verificar que é chamado entre `_run_daily` e `writer.update_supply_match`
- Comportamento de falha: mock de `run_geo_phase3_5` lançando exceção; verificar que `update_supply_match` ainda é chamado
- End-to-end com fixture: executar `run_daily` do orquestrador com dados de fixture pequenos e verificar que `geo_partner_cap_opportunities` contém registros para todos os parceiros Active
