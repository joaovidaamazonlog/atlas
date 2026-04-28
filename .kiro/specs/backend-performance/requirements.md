# Requirements Document

## Introduction

Esta spec define um conjunto de quatro otimizações de alto impacto e baixo esforço no backend Python, focadas em acelerar o modo `daily` do pipeline (`backend/vanilla/orchestrator.py`). A auditoria de performance identificou que o modo `daily` está lento, e esta feature cobre: (1) instrumentação de profiling/timing para obter baseline e medir o impacto real de cada melhoria, (2) memoização das chamadas H3 `grid_disk` e `grid_distance` na Fase 3, (3) vetorização de loops com `iterrows()` e de chamadas H3 não-vetorizadas em `load_packages.py` e `load_partners.py`, e (4) consolidação das múltiplas passagens de `.replace()` em `_consolidate_stores`.

Como o sistema toma decisões de negócio (matching estação↔parceiro), o critério inviolável é **preservação de output**: nenhuma otimização pode alterar os resultados produzidos pelo pipeline para os mesmos inputs. Todas as mudanças devem ser verificadas por testes baseados em propriedade (PBT) que comparam o DataFrame resultante de `run_daily` antes e depois da otimização. As melhorias de tempo devem ser mensuráveis pela instrumentação introduzida na Task 1.

## Glossary

- **Pipeline_Daily**: Sequência de execução do modo `daily` em `backend/vanilla/orchestrator.py`, composta por carregamento de pacotes/parceiros, Fase 3 (matching), Fase 4 (webleads), Fase 5 (relatórios) e etapas de consolidação.
- **Timing_Instrumentation**: Módulo/helper de medição de tempo por fase (Phase 1, Phase 2, Phase 3, consolidação, geração de relatórios) e tempo total, registrado via logs.
- **Baseline_Metrics**: Métricas de tempo coletadas ANTES de qualquer otimização, usadas como referência para validar as melhorias subsequentes.
- **H3_Cache**: Estrutura de memoização (ex.: `functools.lru_cache` ou dicionário) aplicada às funções `h3.grid_disk` e `h3.grid_distance` na Fase 3.
- **Phase3**: Fase 3 do pipeline, implementada em `backend/vanilla/phase3_partner_fit.py`, responsável pelo matching estação↔parceiro.
- **Vectorization**: Substituição de loops linha-a-linha (`df.iterrows()`, laços Python sobre DataFrames) por operações vetorizadas do pandas e chamadas vetorizadas de `h3` (ex.: `h3.latlng_to_cell` aplicado a arrays/Series).
- **Consolidate_Stores**: Função `_consolidate_stores` em `backend/shared/load_packages.py` (e afins em `backend/shared/load_partners.py`) que aplica múltiplas chamadas sequenciais de `.replace()` sobre um DataFrame.
- **Output_Equivalence**: Propriedade de que dois DataFrames resultantes de `run_daily` são iguais (mesmas linhas, mesmas colunas, mesmos valores, mesma ordem, considerando tolerância para floats) para o mesmo input.
- **Optimized_Pipeline**: Versão do `Pipeline_Daily` após aplicação de uma ou mais das otimizações descritas nesta spec.
- **Reference_Pipeline**: Versão do `Pipeline_Daily` imediatamente antes da aplicação da otimização em análise (baseline de correctness).

## Requirements

### Requirement 1: Instrumentação de profiling/timing no pipeline daily

**User Story:** Como engenheiro de plataforma, eu quero instrumentação de tempo por fase no modo `daily`, para que eu possa obter métricas de baseline e medir objetivamente o impacto de cada otimização subsequente.

#### Acceptance Criteria

1. WHEN o modo `daily` é executado, THE Timing_Instrumentation SHALL registrar o tempo decorrido (em segundos, com precisão mínima de milissegundos) de cada fase do `Pipeline_Daily`: Phase 1, Phase 2, Phase 3, consolidação e geração de relatórios.
2. WHEN o modo `daily` é executado, THE Timing_Instrumentation SHALL registrar o tempo total decorrido do início ao fim do pipeline.
3. WHEN cada fase termina, THE Timing_Instrumentation SHALL emitir um log contendo o nome da fase e o tempo decorrido dessa fase.
4. WHEN o pipeline termina, THE Timing_Instrumentation SHALL emitir um log contendo o tempo total e um sumário por fase (nome e tempo em segundos).
5. WHERE uma fase lança exceção, THE Timing_Instrumentation SHALL registrar o tempo decorrido até a exceção e propagar a exceção sem alterá-la.
6. THE Timing_Instrumentation SHALL expor os tempos medidos de forma programática (estrutura de dados retornada ou acessível por teste) para permitir asserções em testes de performance.
7. THE Timing_Instrumentation SHALL preservar o output funcional do `Pipeline_Daily`, isto é, o DataFrame resultante de `run_daily` com instrumentação ligada SHALL ser igual ao `Reference_Pipeline` sem instrumentação para o mesmo input (`Output_Equivalence`).
8. THE Timing_Instrumentation SHALL ser pré-requisito para validar as Requirements 2, 3 e 4 — as métricas coletadas aqui servem de baseline para as demais otimizações.

### Requirement 2: Cache de chamadas H3 `grid_disk` e `grid_distance` na Phase 3

**User Story:** Como engenheiro de plataforma, eu quero memoizar as chamadas repetidas de `h3.grid_disk` e `h3.grid_distance` na Fase 3, para que o matching estação↔parceiro não recalcule a mesma vizinhança H3 múltiplas vezes durante a execução.

#### Acceptance Criteria

1. WHEN `h3.grid_disk` é invocado com a mesma célula H3 e o mesmo parâmetro `k` durante a execução da Phase 3, THE H3_Cache SHALL retornar o resultado memoizado sem recomputar a vizinhança.
2. WHEN `h3.grid_distance` é invocado com o mesmo par ordenado de células H3 durante a execução da Phase 3, THE H3_Cache SHALL retornar o resultado memoizado sem recomputar a distância.
3. THE H3_Cache SHALL produzir, para qualquer par `(cell, k)` ou `(cell_a, cell_b)`, um resultado idêntico àquele retornado pela função original não memoizada.
4. WHEN a Phase 3 é executada com H3_Cache ativo e posteriormente sem H3_Cache para o mesmo input, THE pipeline SHALL produzir DataFrames resultantes iguais (`Output_Equivalence`).
5. THE H3_Cache SHALL estar escopado à execução do pipeline (não persistir entre execuções de processos distintos) para evitar consumo de memória ilimitado entre runs.
6. IF a célula H3 fornecida ao cache for inválida, THEN THE H3_Cache SHALL propagar a mesma exceção que a função `h3` original levantaria, sem mascarar o erro.
7. WHEN a Phase 3 é executada com H3_Cache ativo, THE Timing_Instrumentation SHALL registrar um tempo de Phase 3 igual ou menor que o baseline coletado na Requirement 1.

### Requirement 3: Vetorização de loops `iterrows()` e chamadas H3 não-vetorizadas

**User Story:** Como engenheiro de plataforma, eu quero substituir loops `df.iterrows()` e chamadas H3 linha-a-linha em `backend/shared/load_packages.py` e `backend/shared/load_partners.py` por operações vetorizadas do pandas e chamadas H3 vetorizadas, para que o carregamento de dados seja mais rápido sem alterar o output.

#### Acceptance Criteria

1. WHEN `load_packages` é executado, THE Vectorization SHALL substituir os usos de `df.iterrows()` identificados por operações vetorizadas do pandas (atribuição em coluna, `.apply` sobre Series quando justificado, `map`, merges, agregações).
2. WHEN `load_packages` calcula hexágonos H3 a partir de colunas `latitude` e `longitude`, THE Vectorization SHALL utilizar a variante vetorizada de `h3.latlng_to_cell` aplicada a arrays/Series ao invés de laços Python linha-a-linha.
3. WHEN `load_partners` é executado, THE Vectorization SHALL substituir os usos de `df.iterrows()` identificados por operações vetorizadas do pandas equivalentes.
4. WHEN `load_partners` calcula hexágonos H3 para os parceiros, THE Vectorization SHALL utilizar a variante vetorizada de `h3.latlng_to_cell` aplicada a arrays/Series quando as coordenadas estiverem disponíveis em coluna.
5. THE Vectorization SHALL preservar o output: `Optimized_Pipeline.load_packages(input)` SHALL produzir um `PackageData` cujos campos `demand_by_station`, `hex_to_base`, `hex_to_ceps` e `days` são iguais aos do `Reference_Pipeline.load_packages(input)` para o mesmo input.
6. THE Vectorization SHALL preservar o output: `Optimized_Pipeline.load_partners(input)` SHALL produzir um `PartnerData` cujos DataFrames (`partners_df`, `web_leads_df`, `no_coords_prospects_df`) são iguais aos do `Reference_Pipeline.load_partners(input)` (mesmas linhas, mesmas colunas, mesmos valores, mesma ordem após normalização determinística de ordenação).
7. WHEN `run_daily` é executado sobre o `Optimized_Pipeline` e sobre o `Reference_Pipeline` com o mesmo input, THE pipelines SHALL produzir DataFrames resultantes iguais (`Output_Equivalence`).
8. IF uma linha tiver valores inválidos de `latitude` ou `longitude` (NaN, fora de faixa), THEN THE Vectorization SHALL tratar essa linha de forma equivalente ao `Reference_Pipeline` (mesmo descarte, mesmo fallback, mesma mensagem de warning).
9. WHEN `load_packages` e `load_partners` são executados com Vectorization, THE Timing_Instrumentation SHALL registrar tempos iguais ou menores que o baseline coletado na Requirement 1 para as fases equivalentes.

### Requirement 4: Consolidação das passagens de `.replace()` em `_consolidate_stores`

**User Story:** Como engenheiro de plataforma, eu quero consolidar as múltiplas chamadas sequenciais de `.replace()` em `_consolidate_stores` numa única passagem, para que o DataFrame seja escaneado menos vezes sem mudar o resultado final.

#### Acceptance Criteria

1. WHEN `_consolidate_stores` é executado, THE Consolidate_Stores SHALL aplicar todas as substituições de valores que hoje são feitas por chamadas sequenciais de `.replace()` em uma única passagem, usando `.replace(dict)` consolidado ou uma única expressão regular equivalente.
2. THE Consolidate_Stores SHALL preservar o output: o DataFrame consolidado retornado pela versão otimizada SHALL ser igual ao DataFrame consolidado retornado pela versão original (`Reference_Pipeline`) para o mesmo input, comparando linhas, colunas, valores e ordem.
3. IF duas regras de substituição originais produziam resultados dependentes da ordem de aplicação (ex.: A→B e B→C aplicados em sequência resultavam em A→C), THEN THE Consolidate_Stores SHALL preservar exatamente o mesmo resultado final da aplicação sequencial original.
4. WHEN `run_daily` é executado sobre o `Optimized_Pipeline` e sobre o `Reference_Pipeline` com o mesmo input, THE pipelines SHALL produzir DataFrames resultantes iguais (`Output_Equivalence`).
5. WHEN `_consolidate_stores` é executado com a otimização aplicada, THE Timing_Instrumentation SHALL registrar um tempo de consolidação igual ou menor que o baseline coletado na Requirement 1.

### Requirement 5: Preservação de output end-to-end e testes baseados em propriedade

**User Story:** Como engenheiro de plataforma, eu quero garantir por meio de testes baseados em propriedade (PBT) que nenhuma das otimizações altera o resultado de `run_daily`, para que mudanças de performance não introduzam regressões nas decisões de negócio do sistema.

#### Acceptance Criteria

1. FOR ALL inputs válidos do `Pipeline_Daily`, executar `Reference_Pipeline.run_daily(input)` e `Optimized_Pipeline.run_daily(input)` SHALL produzir DataFrames resultantes iguais (mesmas linhas, mesmas colunas, mesmos valores, mesma ordem canônica) — propriedade de `Output_Equivalence`.
2. FOR ALL pares `(cell, k)` válidos de H3, THE H3_Cache SHALL retornar o mesmo resultado que `h3.grid_disk(cell, k)` sem cache (propriedade de equivalência funcional do cache).
3. FOR ALL pares `(cell_a, cell_b)` válidos de H3, THE H3_Cache SHALL retornar o mesmo resultado que `h3.grid_distance(cell_a, cell_b)` sem cache.
4. FOR ALL DataFrames de entrada válidos para `_consolidate_stores`, a aplicação da versão consolidada `.replace(dict)` SHALL produzir o mesmo DataFrame que a aplicação sequencial original das chamadas `.replace()` (propriedade de equivalência de substituição).
5. FOR ALL inputs válidos de `load_packages` e `load_partners`, a versão vetorizada SHALL produzir outputs iguais à versão `iterrows()` original (propriedade de equivalência de vetorização), comparando DataFrames por conteúdo após ordenação determinística.
6. WHEN um teste de propriedade falha, THE suite de testes SHALL reportar o contraexemplo reduzido pela biblioteca de PBT (ex.: Hypothesis) para permitir diagnóstico.
7. THE suite de testes SHALL cobrir cada uma das otimizações (Requirements 2, 3 e 4) com ao menos um teste de propriedade de `Output_Equivalence` end-to-end via `run_daily`.

### Requirement 6: Monotonicidade das métricas de tempo

**User Story:** Como engenheiro de plataforma, eu quero que cada otimização reduza (ou ao menos não aumente) o tempo da fase correspondente, para que o esforço aplicado se traduza em ganho mensurável e não em regressão de performance.

#### Acceptance Criteria

1. WHEN a otimização da Requirement 2 (H3_Cache) é aplicada, THE Timing_Instrumentation SHALL registrar, para o mesmo input, um tempo de Phase 3 menor ou igual ao baseline registrado antes da otimização.
2. WHEN a otimização da Requirement 3 (Vectorization) é aplicada, THE Timing_Instrumentation SHALL registrar, para o mesmo input, tempos de carregamento de `load_packages` e `load_partners` menores ou iguais aos respectivos baselines.
3. WHEN a otimização da Requirement 4 (Consolidate_Stores) é aplicada, THE Timing_Instrumentation SHALL registrar, para o mesmo input, um tempo de consolidação menor ou igual ao baseline.
4. WHEN todas as otimizações estão aplicadas, THE Timing_Instrumentation SHALL registrar, para o mesmo input, um tempo total de `run_daily` menor ou igual ao baseline do `Reference_Pipeline` sem nenhuma otimização.
5. IF qualquer medida registrada pela Timing_Instrumentation após uma otimização for maior que o baseline correspondente, THEN THE suite de testes SHALL sinalizar regressão de performance e falhar explicitamente.
