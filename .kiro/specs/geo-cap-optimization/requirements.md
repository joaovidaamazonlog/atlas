# Requirements Document

## Introduction

A feature **Geo Cap Optimization** porta o conceito de otimização de capacidade (Fase 3.5) do pipeline vanilla para o pipeline GeoIntelligence (`backend/geo_intelligence/`). O objetivo é identificar, para cada parceiro Active com cap abaixo de 80, se existe demanda não coberta disponível no heatmap GeoIntelligence que justifique aumentar o cap atual, e qual seria a melhor posição dentro de 300 m do centroid atual para capturar essa demanda.

As principais diferenças em relação ao pipeline vanilla são:
- O sinal de demanda é `delivery_density_r9` derivado da tabela `geo_h3_cells` no Turso (volume de pacotes por hexágono H3 na **resolução 9**), em vez de `demand_residual` do `heatmap.geojson`. Análises pontuais de parceiro usam res 9 para maior precisão geográfica (~174 m de edge vs ~461 m em res 8).
- "Demanda não coberta" é definida como `delivery_density_r9` de hexágonos que **não** estão dentro do raio de nenhum parceiro Active.
- A persistência é feita no Turso (tabela `geo_partner_cap_opportunities`), não em arquivos JSON.
- A exposição ao frontend é feita via `geo_api.py` (FastAPI), não via `dados_mapa.json`.
- O ponto de entrada é `geo_daily.py` / `geo_orchestrator.py` (modo `daily`), executado após o matching e antes da persistência final.

---

## Glossary

- **Active**: status de parceiro operacional e ativo na rede.
- **ADV** (Average Daily Volume): volume médio diário de pacotes entregues por um parceiro.
- **adv_opportunity**: objeto persistido na tabela `geo_partner_cap_opportunities` descrevendo a oportunidade de otimização de cap para um parceiro Active; `null` quando não há oportunidade.
- **Cap**: capacidade máxima diária de pacotes de um parceiro (campo `capacity` nos dados do parceiro).
- **Cap_Max**: limite máximo de cap permitido pelo sistema — 80 pacotes/dia.
- **Centroid**: posição geográfica atual (lat/lon) de um parceiro.
- **Demanda_Não_Coberta**: soma de `delivery_density_r9` de hexágonos H3 (res 9) que não estão dentro do raio de nenhum parceiro Active. É o equivalente GeoIntelligence do `demand_residual` do pipeline vanilla. Usa res 9 para maior precisão na análise pontual de parceiro.
- **delivery_density_r9**: volume de pacotes por hexágono H3 na resolução 9 (pacotes/dia), derivado da tabela `geo_h3_cells` no Turso (que armazena dados em res 8) via desagregação proporcional, ou carregado diretamente se disponível em res 9.
- **estimated_adv_gain**: diferença entre `suggested_cap` e o cap atual do parceiro, representando o ganho estimado de ADV.
- **Fase_3_5_Geo**: nova fase do pipeline GeoIntelligence daily, executada após o matching (`run_daily`) e antes da persistência final dos resultados no Turso.
- **geo_h3_cells**: tabela no Turso com features por hexágono H3, incluindo `delivery_density_r8`, `potential_score`, `gap` e `territory_id`.
- **geo_partner_cap_opportunities**: nova tabela no Turso onde são persistidas as oportunidades de cap por parceiro Active.
- **GeoCapOptimizer**: módulo Python responsável pela Fase 3.5 do pipeline GeoIntelligence (`geo_intelligence/geo_phase3_5_cap_optimizer.py`).
- **GeoDailyResult**: dataclass de resultado do `run_daily` em `geo_daily.py`, contendo listas de parceiros matched/unmatched e métricas por território.
- **H3**: sistema de indexação geoespacial hexagonal usado pelo ATLAS.
- **load_partners()**: função de `shared/load_partners.py` que carrega os dados reais de parceiros (Excel ou JSON).
- **Parceiro_Under_Cap**: parceiro Active com `capacity` < 80.
- **Posição_Candidata**: hexágono H3 dentro de ~300 m do centroid atual de um parceiro, derivado via `h3.grid_disk`.
- **Raio_de_Busca**: distância máxima de 300 m do centroid atual para varredura de posições candidatas.
- **run_id**: identificador único de uma execução do pipeline GeoIntelligence, usado como chave de relacionamento entre tabelas no Turso.
- **TursoReader**: classe em `geo_intelligence/turso_reader.py` que lê dados do Turso via HTTP com cache TTL.
- **TursoWriter**: classe em `geo_intelligence/turso_writer.py` que persiste dados no Turso via HTTP com retry.

---

## Requirements

### Requirement 1: Fase 3.5 Geo — Avaliação de Oportunidades de Cap

**User Story:** Como analista de rede, quero que o pipeline GeoIntelligence daily avalie automaticamente todos os parceiros Active e identifique oportunidades de aumento de cap com base na demanda não coberta do heatmap GeoIntelligence, para que eu possa priorizar ações de otimização sem análise manual.

#### Acceptance Criteria

1. WHEN o orquestrador GeoIntelligence executa no modo `daily`, THE Fase_3_5_Geo SHALL ser executada após a conclusão do matching (`run_daily`) e antes da persistência final dos resultados no Turso.
2. THE Fase_3_5_Geo SHALL avaliar todos os parceiros com status `Active` presentes no `GeoDailyResult` retornado pelo `run_daily`.
3. WHEN um parceiro Active tem `capacity` >= 80, THE Fase_3_5_Geo SHALL registrar `adv_opportunity = null` para esse parceiro sem realizar varredura de posições candidatas.
4. WHEN um parceiro Active tem `capacity` < 80, THE Fase_3_5_Geo SHALL varrer posições candidatas dentro de ~300 m do centroid atual usando `h3.grid_disk` na **resolução 9** (`k=3`, cobrindo ~522 m de diâmetro), adequada para análise pontual de parceiro.
5. WHEN a varredura de posições candidatas é executada, THE Fase_3_5_Geo SHALL calcular a Demanda_Não_Coberta disponível para cada posição candidata usando `delivery_density_r9` (resolução 9) derivado da tabela `geo_h3_cells` no Turso, considerando apenas hexágonos que não estão cobertos por nenhum parceiro Active.
6. WHEN a Demanda_Não_Coberta disponível em uma posição candidata supera o cap atual do parceiro, THE Fase_3_5_Geo SHALL calcular `suggested_cap = min(int(demanda_nao_coberta), 80)` e `suggested_radius` como o menor raio (em metros) que cobre a demanda necessária para o `suggested_cap`.
7. WHEN múltiplas posições candidatas são viáveis, THE Fase_3_5_Geo SHALL selecionar a posição com maior `estimated_adv_gain` (desempate: menor `distance_from_current`).
8. WHEN uma oportunidade é identificada, THE Fase_3_5_Geo SHALL persistir na tabela `geo_partner_cap_opportunities` o registro com os campos: `partner_id`, `run_id`, `station_code`, `suggested_lat`, `suggested_lon`, `suggested_cap`, `suggested_radius`, `estimated_adv_gain`, `distance_from_current`, `created_at`.
9. WHEN nenhuma posição candidata supera o cap atual, THE Fase_3_5_Geo SHALL persistir um registro com `suggested_cap = null` e `estimated_adv_gain = null` para esse parceiro, indicando ausência de oportunidade.
10. IF a tabela `geo_h3_cells` não contiver registros para o `run_id` da base processada, THEN THE Fase_3_5_Geo SHALL registrar um aviso no log e encerrar sem persistir registros na tabela `geo_partner_cap_opportunities`.
11. IF o parceiro Active não possuir `origin_hex` ou coordenadas válidas, THEN THE Fase_3_5_Geo SHALL registrar um aviso no log e persistir `adv_opportunity = null` para esse parceiro.

---

### Requirement 2: Cálculo de Demanda Não Coberta

**User Story:** Como desenvolvedor, quero que o cálculo de demanda não coberta use corretamente o campo `delivery_density_r8` da tabela `geo_h3_cells`, excluindo hexágonos já cobertos por parceiros Active, para que a oportunidade estimada reflita apenas a demanda genuinamente disponível.

#### Acceptance Criteria

1. THE Fase_3_5_Geo SHALL construir um índice de cobertura Active mapeando cada hexágono H3 (res 9) para o conjunto de parceiros Active cujo raio de entrega o cobre, usando as coordenadas e raios dos parceiros Active do `GeoDailyResult`.
2. WHEN o índice de cobertura Active é construído, THE GeoCapOptimizer SHALL considerar um hexágono como "coberto" se o centro do hexágono está dentro do raio de entrega de pelo menos um parceiro Active.
3. WHEN a Demanda_Não_Coberta é calculada para uma posição candidata, THE GeoCapOptimizer SHALL somar `delivery_density_r9` apenas dos hexágonos (res 9) dentro do raio de entrega da posição candidata que **não** estão no índice de cobertura Active.
4. WHEN o parceiro avaliado é o próprio parceiro Active, THE GeoCapOptimizer SHALL excluir a cobertura desse parceiro do índice de cobertura ao calcular a Demanda_Não_Coberta para as posições candidatas desse parceiro (para evitar que a cobertura atual do próprio parceiro mascare a oportunidade).
5. THE GeoCapOptimizer SHALL usar distância geodésica (fórmula de Haversine) para determinar se um hexágono está dentro do raio de entrega de um parceiro ou posição candidata.
6. WHEN `delivery_density_r9` é `null` ou ausente para um hexágono, THE GeoCapOptimizer SHALL tratar o valor como 0.0 no cálculo da Demanda_Não_Coberta.

---

### Requirement 3: Estrutura de Dados da Tabela `geo_partner_cap_opportunities`

**User Story:** Como desenvolvedor, quero que a tabela `geo_partner_cap_opportunities` tenha uma estrutura bem definida e consistente no Turso, para que o `TursoReader` e a `geo_api.py` possam consumi-la de forma confiável.

#### Acceptance Criteria

1. THE TursoWriter SHALL criar a tabela `geo_partner_cap_opportunities` com o seguinte schema DDL:
   - `partner_id TEXT NOT NULL` — salesforce_id do parceiro
   - `run_id TEXT NOT NULL` — run_id do setup GeoIntelligence associado
   - `station_code TEXT NOT NULL` — código da base
   - `suggested_lat REAL` — latitude da posição sugerida (null quando sem oportunidade)
   - `suggested_lon REAL` — longitude da posição sugerida (null quando sem oportunidade)
   - `suggested_cap INTEGER` — cap sugerido (null quando sem oportunidade)
   - `suggested_radius INTEGER` — raio sugerido em metros (null quando sem oportunidade)
   - `estimated_adv_gain INTEGER` — ganho estimado de ADV (null quando sem oportunidade)
   - `distance_from_current REAL` — distância geodésica em metros do centroid atual (null quando sem oportunidade)
   - `created_at TEXT NOT NULL` — timestamp ISO 8601 da criação do registro
   - `PRIMARY KEY (partner_id, run_id)`
2. THE TursoWriter SHALL incluir o DDL da tabela `geo_partner_cap_opportunities` no método `ensure_schema()`.
3. THE TursoWriter SHALL implementar o método `upsert_cap_opportunities(run_id, opportunities)` que persiste ou atualiza registros na tabela `geo_partner_cap_opportunities` usando `INSERT ... ON CONFLICT DO UPDATE`.
4. THE TursoWriter SHALL garantir que `suggested_cap` seja sempre um inteiro entre `capacity_atual + 1` e `80` (inclusive) quando não for null.
5. THE TursoWriter SHALL garantir que `estimated_adv_gain = suggested_cap - capacity_atual` quando não for null.
6. THE TursoWriter SHALL garantir que `distance_from_current` seja a distância geodésica em metros entre o centroid atual e a posição sugerida quando não for null.

---

### Requirement 4: Leitura de Oportunidades via TursoReader

**User Story:** Como desenvolvedor, quero que o `TursoReader` exponha um método para ler as oportunidades de cap da tabela `geo_partner_cap_opportunities`, para que a `geo_api.py` possa servir esses dados ao frontend.

#### Acceptance Criteria

1. THE TursoReader SHALL implementar o método `get_cap_opportunities(station_code, run_id)` que retorna todos os registros da tabela `geo_partner_cap_opportunities` para a base e run_id especificados.
2. WHEN `run_id` não é fornecido ao método `get_cap_opportunities`, THE TursoReader SHALL resolver automaticamente o `run_id` mais recente para a `station_code` usando `get_latest_run_id`.
3. THE TursoReader SHALL aplicar cache TTL de 5 minutos nos resultados de `get_cap_opportunities`, usando a chave `cap_opportunities:{station_code}:{run_id}`.
4. WHEN a tabela `geo_partner_cap_opportunities` não contém registros para a base e run_id especificados, THE TursoReader SHALL retornar uma lista vazia sem lançar exceção.
5. THE TursoReader SHALL retornar apenas registros com `estimated_adv_gain IS NOT NULL` quando o parâmetro `only_with_opportunity=True` for passado ao método `get_cap_opportunities`.

---

### Requirement 5: Integração da Fase 3.5 Geo no Orquestrador

**User Story:** Como operador do pipeline, quero que a Fase 3.5 Geo seja integrada ao modo `daily` do orquestrador GeoIntelligence sem alterar os modos `setup` e `update-heatmap`, para que o pipeline continue funcionando de forma transparente.

#### Acceptance Criteria

1. WHEN o orquestrador GeoIntelligence executa no modo `daily`, THE Orchestrator SHALL chamar `run_geo_phase3_5` após `run_daily` e antes de `writer.update_supply_match` e `writer.update_territory_fit`.
2. THE Orchestrator SHALL passar ao `run_geo_phase3_5` os seguintes argumentos: `daily_result` (GeoDailyResult), `run_id` (run_id do setup mais recente), `station_code`, `writer` (instância de TursoWriter), `reader` (instância de TursoReader).
3. WHEN `stations` é fornecido ao orquestrador no modo `daily`, THE Fase_3_5_Geo SHALL processar apenas os parceiros Active das bases listadas.
4. IF a Fase 3.5 Geo falhar com exceção não tratada, THEN THE Orchestrator SHALL registrar o erro no log e continuar a execução das etapas seguintes (persistência de matches e territory fit) sem abortar o pipeline.
5. THE Orchestrator SHALL registrar no log o número de oportunidades identificadas e o número de parceiros avaliados ao final da Fase 3.5 Geo.

---

### Requirement 6: Endpoint REST para Oportunidades de Cap

**User Story:** Como desenvolvedor frontend, quero um endpoint REST na `geo_api.py` que retorne as oportunidades de cap por base, para que o frontend possa eventualmente consumir e exibir essas oportunidades.

#### Acceptance Criteria

1. THE Geo_API SHALL expor o endpoint `GET /geo-intelligence/{station_code}/cap-opportunities` que retorna a lista de oportunidades de cap para a base especificada.
2. WHEN o parâmetro `run_id` é fornecido como query string, THE Geo_API SHALL retornar as oportunidades do run_id especificado; caso contrário, SHALL usar o run_id mais recente.
3. WHEN o parâmetro `only_with_opportunity=true` é fornecido como query string, THE Geo_API SHALL retornar apenas registros com `estimated_adv_gain IS NOT NULL`.
4. WHEN não existem oportunidades para a base e run_id especificados, THE Geo_API SHALL retornar uma lista vazia com status HTTP 200 (não 404).
5. WHEN o run_id mais recente não é encontrado para a base especificada, THE Geo_API SHALL retornar HTTP 404 com mensagem descritiva.
6. THE Geo_API SHALL retornar cada oportunidade como um objeto JSON com os campos: `partner_id`, `run_id`, `station_code`, `suggested_lat`, `suggested_lon`, `suggested_cap`, `suggested_radius`, `estimated_adv_gain`, `distance_from_current`, `created_at`.
7. THE Geo_API SHALL ordenar os resultados por `estimated_adv_gain` decrescente (nulls por último).

---

### Requirement 7: Carregamento de `geo_h3_cells` para o Cálculo

**User Story:** Como desenvolvedor, quero que o GeoCapOptimizer carregue os dados de `geo_h3_cells` do Turso de forma eficiente, para que o cálculo de demanda não coberta seja preciso e performático.

#### Acceptance Criteria

1. THE GeoCapOptimizer SHALL carregar todos os registros de `geo_h3_cells` para o `run_id` e `station_code` da execução corrente usando o `TursoReader`.
2. THE GeoCapOptimizer SHALL construir um índice em memória `{h3_id_r9: delivery_density_r9}` a partir dos registros carregados para lookup O(1) durante o cálculo de Demanda_Não_Coberta. Os dados de res 8 da tabela `geo_h3_cells` são desagregados para res 9 via `h3.cell_to_children(h3_id_r8, 9)`, distribuindo `delivery_density_r8` proporcionalmente entre os filhos res 9.
3. WHEN `delivery_density_r8` é `null` ou ausente no registro de `geo_h3_cells`, THE GeoCapOptimizer SHALL usar 0.0 como valor padrão antes da desagregação para res 9.
4. THE GeoCapOptimizer SHALL carregar os dados de `geo_h3_cells` uma única vez por execução da Fase 3.5 Geo (não por parceiro), reutilizando o índice em memória para todos os parceiros da base.
5. WHEN o índice de `geo_h3_cells` está vazio após o carregamento, THE GeoCapOptimizer SHALL registrar um aviso no log e encerrar sem persistir registros na tabela `geo_partner_cap_opportunities`.

---

### Requirement 8: Raios Sugeridos e Compatibilidade com o Pipeline

**User Story:** Como desenvolvedor, quero que os raios sugeridos pela Fase 3.5 Geo sejam compatíveis com os raios usados pelo pipeline GeoIntelligence, para que as oportunidades sejam operacionalmente viáveis.

#### Acceptance Criteria

1. THE GeoCapOptimizer SHALL usar os raios definidos em `Config.RADII` (de `shared/models.py`) como conjunto de raios candidatos para `suggested_radius`.
2. THE GeoCapOptimizer SHALL selecionar como `suggested_radius` o menor valor de `Config.RADII` cujo raio cobre Demanda_Não_Coberta >= `suggested_cap` a partir da posição candidata.
3. WHEN nenhum raio de `Config.RADII` cobre Demanda_Não_Coberta >= `suggested_cap`, THE GeoCapOptimizer SHALL descartar essa posição candidata (não gerar oportunidade para ela).
4. THE GeoCapOptimizer SHALL usar a **resolução H3 res 9** para todos os cálculos de posições candidatas e demanda não coberta, garantindo precisão geográfica adequada para análise pontual de parceiro.
5. THE GeoCapOptimizer SHALL usar `k=3` no `h3.grid_disk` para cobrir ~300 m na resolução 9 (edge ~174 m, disk-3 ≈ 522 m de diâmetro).

---

### Requirement 9: Tratamento de Erros e Resiliência

**User Story:** Como operador do pipeline, quero que a Fase 3.5 Geo trate erros de forma resiliente, para que falhas pontuais em parceiros individuais ou na leitura do Turso não abortem o pipeline diário.

#### Acceptance Criteria

1. IF a leitura de `geo_h3_cells` do Turso falhar com exceção, THEN THE Fase_3_5_Geo SHALL registrar o erro no log e encerrar sem persistir registros, sem propagar a exceção ao orquestrador.
2. IF `h3.grid_disk` falhar para um parceiro específico, THEN THE Fase_3_5_Geo SHALL registrar um aviso no log, persistir `adv_opportunity = null` para esse parceiro e continuar para o próximo.
3. IF `h3.cell_to_latlng` falhar para um hexágono candidato, THEN THE Fase_3_5_Geo SHALL ignorar esse hexágono e continuar a avaliação dos demais candidatos.
4. IF `upsert_cap_opportunities` falhar no TursoWriter, THEN THE Fase_3_5_Geo SHALL registrar o erro no log e encerrar sem propagar a exceção ao orquestrador.
5. WHILE a Fase 3.5 Geo está em execução, THE Fase_3_5_Geo SHALL capturar exceções por parceiro individualmente, garantindo que a falha em um parceiro não interrompa a avaliação dos demais.

---

### Requirement 10: Testes e Propriedades de Corretude

**User Story:** Como desenvolvedor, quero que a Fase 3.5 Geo tenha propriedades de corretude verificáveis por testes baseados em propriedades, para que a implementação seja confiável e regressions sejam detectadas automaticamente.

#### Acceptance Criteria

1. THE GeoCapOptimizer SHALL garantir que, para qualquer conjunto de parceiros Active, todos os parceiros com `capacity` >= 80 resultem em `adv_opportunity = null` (sem exceção).
2. THE GeoCapOptimizer SHALL garantir que, para qualquer parceiro Active com `capacity` < 80 e índice de `geo_h3_cells` onde pelo menos um hexágono vizinho tem Demanda_Não_Coberta > `capacity`, o resultado seja um `adv_opportunity` não nulo.
3. THE GeoCapOptimizer SHALL garantir que `suggested_cap` satisfaça `capacity_atual < suggested_cap <= 80` para todo `adv_opportunity` não nulo.
4. THE GeoCapOptimizer SHALL garantir que `estimated_adv_gain = suggested_cap - capacity_atual` para todo `adv_opportunity` não nulo.
5. THE GeoCapOptimizer SHALL garantir que, dado um conjunto de posições candidatas viáveis, a posição selecionada tenha o maior `estimated_adv_gain`; em caso de empate, a menor `distance_from_current`.
6. THE GeoCapOptimizer SHALL garantir que todos os parceiros Active do `GeoDailyResult` estejam representados na tabela `geo_partner_cap_opportunities` após a execução (com ou sem oportunidade), sem omissões silenciosas.
7. FOR ALL execuções da Fase 3.5 Geo com o mesmo `GeoDailyResult` e o mesmo índice de `geo_h3_cells`, THE GeoCapOptimizer SHALL produzir resultados idênticos (determinismo).
