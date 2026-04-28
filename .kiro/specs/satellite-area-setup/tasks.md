# Plano de Implementação: satellite-area-setup

## Visão Geral

Implementar suporte a áreas satélite independentes no pipeline de setup, permitindo que códigos satélite (ex: `XBA1`, `XCS1`) gerem seus próprios territórios e slots ideais, enquanto continuam sendo agregados sob a base canônica no pipeline daily.

A implementação segue a separação de responsabilidades: **setup** produz artefatos com `station_code` original; **daily** faz o remap em memória para a base canônica.

## Tasks

- [x] 1. Modificar `load_packages` para suportar modo satélite
  - Adicionar parâmetro `satellite_setup_stations: Optional[Set[str]] = None` à assinatura de `load_packages` em `backend/shared/load_packages.py`
  - No passo 1b (remap via `STATION_ALIASES`), filtrar o dicionário de aliases para excluir os códigos presentes em `satellite_setup_stations` antes de aplicar o `df["station_code"].replace()`
  - Modificar `_build_jurisdiction_index` para aceitar `satellite_setup_stations: Optional[Set[str]] = None`; quando um código satélite estiver em `satellite_setup_stations`, indexá-lo com o próprio código satélite (não com a canônica), para que hexes dentro do polígono satélite sejam atribuídos ao código satélite
  - Propagar `satellite_setup_stations` para a chamada de `_build_jurisdiction_index` dentro de `load_packages`
  - _Requisitos: 2.1, 2.2, 2.3, 2.4_

  - [x]* 1.1 Escrever teste de propriedade para isolamento de demanda satélite (Property 1)
    - **Property 1: Isolamento de demanda satélite no setup**
    - Para qualquer código satélite em `STATION_ALIASES`, quando `load_packages` é chamado com `satellite_setup_stations={satellite_code}`, todos os hexes em `demand_by_station[satellite_code]` devem ter seus centróides dentro do polígono de jurisdição da própria satélite
    - Usar `@given(satellite_code=st.sampled_from(list(STATION_ALIASES.keys())))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 1: Isolamento de demanda satélite no setup`
    - **Validates: Requirements 2.1, 2.2**

  - [x]* 1.2 Escrever testes unitários para `load_packages` em modo satélite
    - `test_load_packages_satellite_mode`: verificar que `satellite_setup_stations={"XBA1"}` suprime o remap de `XBA1` mas mantém o remap de outras satélites
    - `test_build_jurisdiction_index_satellite_mode`: verificar que `_build_jurisdiction_index` indexa o código satélite com o próprio código quando em `satellite_setup_stations`
    - _Requisitos: 2.1, 2.2_

- [x] 2. Modificar `_load_jurisdiction_poly` para suportar modo satélite
  - Adicionar parâmetro `satellite_mode: bool = False` à assinatura de `_load_jurisdiction_poly` em `backend/vanilla/phase_setup.py`
  - Quando `satellite_mode=True`: usar `codes_to_include = {station_code}` (apenas o polígono da própria satélite, sem unir com a canônica)
  - Quando `satellite_mode=False` (padrão): manter comportamento atual — `codes_to_include = {station_code} | set(Config.get_satellites(station_code))`
  - _Requisitos: 1.1, 6.1_

  - [x]* 2.1 Escrever testes unitários para `_load_jurisdiction_poly`
    - `test_load_jurisdiction_poly_satellite_mode`: verificar que `satellite_mode=True` retorna apenas o polígono da satélite, sem unir com a canônica
    - `test_load_jurisdiction_poly_canonical_mode`: verificar que `satellite_mode=False` (padrão) une polígonos da canônica com suas satélites (retrocompatibilidade)
    - _Requisitos: 1.1, 6.1_

- [x] 3. Modificar `run_setup` em `phase_setup.py` para detectar satélites e adicionar `canonical_base`
  - No início de `run_setup`, importar `STATION_ALIASES` de `shared.config` e identificar quais estações em `target_sta` são satélites: `satellite_stations = {s for s in target_sta if s in STATION_ALIASES}`
  - Para cada estação no loop de solver (filtro de hexes por jurisdição), passar `satellite_mode=(station in satellite_stations)` para `_load_jurisdiction_poly`
  - Para cada estação no loop de K-means (construção de polígonos), passar `satellite_mode=(station in satellite_stations)` para `_load_jurisdiction_poly`
  - Ao construir `territory_index[tid]` no passo 4 (metadados por território), adicionar o campo `canonical_base`: `"canonical_base": STATION_ALIASES.get(station)` — será `None` para bases canônicas e o código canônico para satélites
  - Adicionar derivação proporcional de `n_clusters` para satélites sem configuração em `CLUSTER_PER_STATION`: calcular `ratio = satellite_demand / (canonical_demand + satellite_demand)` e `n_clusters = max(1, round(canonical_clusters * ratio))`
  - Logar warning quando código não reconhecido em `STATION_ALIASES` nem em bases conhecidas
  - _Requisitos: 1.1, 1.2, 1.3, 3.1, 3.2, 3.3, 7.2, 7.4_

  - [x]* 3.1 Escrever teste de propriedade para preservação do `station_code` no disco (Property 2)
    - **Property 2: Preservação do station_code no disco**
    - Para qualquer código satélite, após `run_setup` completar, todos os territórios em `territories_index.json` com prefixo `{satellite_code}_` devem ter `station_code` igual ao código satélite (não à base canônica)
    - Usar `@given(satellite_code=st.sampled_from(list(STATION_ALIASES.keys())))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 2: Preservação do station_code no disco`
    - **Validates: Requirements 1.2, 1.3, 3.1, 3.4**

  - [x]* 3.2 Escrever teste de propriedade para campo `canonical_base` (Property 3)
    - **Property 3: Campo canonical_base no territories_index**
    - Para qualquer código satélite em `STATION_ALIASES`, após `run_setup`, todos os territórios gerados para esse satélite devem ter o campo `canonical_base` igual a `STATION_ALIASES[satellite_code]`
    - Usar `@given(satellite_code=st.sampled_from(list(STATION_ALIASES.keys())))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 3: Campo canonical_base no territories_index`
    - **Validates: Requirements 3.2**

  - [x]* 3.3 Escrever testes unitários para `run_setup` com satélites
    - `test_run_setup_unknown_code_warning`: verificar que código desconhecido gera warning e é tratado como canônica
    - `test_cluster_count_derivation`: verificar derivação proporcional de cluster count para satélite sem configuração em `CLUSTER_PER_STATION`
    - _Requisitos: 3.2, 3.3, 7.2, 7.4_

- [x] 4. Checkpoint — Verificar artefatos do setup
  - Garantir que todos os testes das tasks 1–3 passam
  - Verificar manualmente que `territories_index.json` gerado para `XBA1` contém `station_code: "XBA1"` e `canonical_base: "DSA8"`
  - Garantir que o setup para bases canônicas sem satélites produz resultado idêntico ao comportamento anterior
  - Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 5. Modificar orquestrador vanilla `run_setup` em `orchestrator.py`
  - Em `backend/vanilla/orchestrator.py`, na função `run_setup`, identificar satélites no conjunto de estações: `satellite_setup_stations = {s for s in stations if s in STATION_ALIASES} or None` (apenas quando `stations` é fornecido)
  - Passar `satellite_setup_stations=satellite_setup_stations` ao chamar `load_packages`
  - _Requisitos: 1.1, 1.4, 7.1_

  - [x]* 5.1 Escrever testes de fumaça para a CLI
    - `test_cli_accepts_satellite_code`: verificar que a CLI não lança exceção ao receber `--stations XBA1`
    - `test_cli_accepts_mixed_codes`: verificar que a CLI não lança exceção ao receber `--stations DSA8 XBA1`
    - _Requisitos: 1.4, 7.1_

- [x] 6. Modificar `load_territories` em `models.py` para usar `canonical_base` como fonte primária
  - Em `backend/shared/models.py`, na função `load_territories`, no bloco de remap em memória, alterar a lógica para:
    1. Verificar campo `canonical_base` no `meta` como fonte primária: `canonical = meta.get("canonical_base")`
    2. Se `canonical` for `None` ou ausente, fazer fallback para `STATION_ALIASES`: `canonical = aliases.get(original)`
    3. Se encontrado em qualquer das duas fontes, aplicar o remap de `station_code` e `bdm_cluster` (comportamento atual)
  - Preservar o campo `canonical_base` no `meta` após o remap (não sobrescrever)
  - _Requisitos: 4.1, 6.2, 8.1, 8.3_

  - [x]* 6.1 Escrever teste de propriedade para round-trip de `territories_index` (Property 4)
    - **Property 4: Round-trip de territories_index — remap em memória**
    - Para qualquer `territories_index` contendo territórios satélite (com ou sem campo `canonical_base`), `load_territories` deve retornar um `TerritoriesResult` onde: (a) o conjunto de `territory_id` keys é idêntico ao do arquivo em disco, e (b) o `station_code` em memória de cada território satélite é a base canônica correspondente
    - Usar `@given(territory_index=st.dictionaries(...))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 4: Round-trip de territories_index — remap em memória`
    - **Validates: Requirements 4.1, 6.2, 8.1, 8.3**

  - [x]* 6.2 Escrever testes unitários para `load_territories`
    - `test_load_territories_canonical_base_field`: verificar remap usando campo `canonical_base` presente no JSON
    - `test_load_territories_fallback_aliases`: verificar remap via `STATION_ALIASES` quando `canonical_base` está ausente (retrocompatibilidade com arquivos antigos)
    - _Requisitos: 4.1, 6.2_

- [x] 7. Modificar orquestrador vanilla `run_daily` em `orchestrator.py` para expandir filtro de satélites
  - Em `backend/vanilla/orchestrator.py`, na função `run_daily`, no bloco de filtro por `stations`, substituir a lógica atual por:
    1. Importar `STATION_ALIASES` de `shared.config`
    2. Resolver canônicas solicitadas: para cada `s` em `stations`, calcular `canonical = STATION_ALIASES.get(s, s)` e acumular em `canonical_requested`
    3. Filtrar `all_tids` mantendo territórios cujo `meta["station_code"]` (já remapeado em memória por `load_territories`) está em `canonical_requested`
    4. Atualizar `territories.hex_to_territory` para incluir apenas os `tid` filtrados
  - Isso garante que `--stations DSA8` inclui territórios `XBA1_*` (remapeados para `DSA8`) e que `--stations XBA1` também funciona (resolvido para `DSA8`)
  - _Requisitos: 4.2, 4.3, 4.4, 7.1_

  - [x]* 7.1 Escrever teste de propriedade para filtro daily com satélites (Property 5)
    - **Property 5: Filtro daily inclui satélites da canônica solicitada**
    - Para qualquer base canônica `C` com satélites `{S1, S2, ...}`, quando `run_daily` é chamado com `--stations C`, o conjunto de territórios processados deve incluir todos os territórios cujo `station_code` original (no disco) é `C` ou qualquer `Si`
    - Usar `@given(canonical=st.sampled_from(list(set(STATION_ALIASES.values()))))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 5: Filtro daily inclui satélites da canônica solicitada`
    - **Validates: Requirements 4.2, 4.3**

  - [x]* 7.2 Escrever testes unitários para o filtro do `run_daily`
    - `test_daily_filter_expands_to_satellites`: verificar que `--stations DSA8` inclui territórios `XBA1_*`
    - `test_daily_filter_satellite_code`: verificar que `--stations XBA1` processa apenas territórios `XBA1_*`, remapeados para `DSA8`
    - _Requisitos: 4.2, 4.3, 4.4_

- [x] 8. Checkpoint — Verificar pipeline daily com satélites
  - Garantir que todos os testes das tasks 5–7 passam
  - Verificar que `run_daily` sem filtro processa todos os territórios (canônicos e satélites)
  - Verificar que `run_daily --stations DSA8` inclui territórios `XBA1_*` no processamento
  - Perguntar ao usuário se há dúvidas antes de prosseguir.

- [x] 9. Escrever testes de integração e smoke tests
  - Criar arquivo `backend/tests/test_satellite_area_setup.py` com os seguintes testes:

  - [x] 9.1 Implementar testes de integração
    - `test_setup_then_daily_satellite`: rodar setup para `XBA1` (com mock de dados), depois daily para `DSA8`, verificar que o `TerritoriesResult` em memória contém `XBA1_bucket-*` com `station_code="DSA8"`
    - `test_setup_canonical_unchanged`: rodar setup para `DSA8` (sem satélites), verificar que o resultado é idêntico ao comportamento atual — `_load_jurisdiction_poly` une polígonos da canônica com suas satélites
    - `test_mixed_setup`: rodar setup para `["DSA8", "XBA1"]`, verificar que cada um gera territórios independentes com `station_code` correto
    - _Requisitos: 1.5, 6.1, 6.3, 8.1_

  - [x]* 9.2 Escrever teste de propriedade para preservação do `territory_id` nos outputs (Property 6)
    - **Property 6: Preservação do territory_id nos outputs**
    - Para qualquer território satélite `XBA1_bucket-N`, após `run_daily`, o `territory_id` original deve ser preservado sem renomeação em todos os artefatos de saída
    - Usar `@given(satellite_code=st.sampled_from(list(STATION_ALIASES.keys())), n=st.integers(min_value=1, max_value=10))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 6: Preservação do territory_id nos outputs`
    - **Validates: Requirements 4.5, 5.4, 5.5**

  - [x]* 9.3 Escrever teste de propriedade para round-trip de `ideal_supply` (Property 9)
    - **Property 9: Round-trip de ideal_supply — station_code preservado**
    - Para qualquer `ideal_supply.json` contendo slots de territórios satélite, `load_ideal_supply` deve retornar um `IdealSupplyResult` onde o conjunto de `slot_id` keys é idêntico ao do arquivo em disco e o `station_code` de cada slot satélite é preservado como o código satélite (não remapeado)
    - Usar `@given(satellite_code=st.sampled_from(list(STATION_ALIASES.keys())))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 9: Round-trip de ideal_supply — station_code preservado`
    - **Validates: Requirements 8.2, 8.4**

  - [x]* 9.4 Escrever teste de propriedade para retrocompatibilidade do setup canônico (Property 8)
    - **Property 8: Retrocompatibilidade do setup canônico**
    - Para qualquer conjunto de estações contendo apenas bases canônicas (nenhuma em `STATION_ALIASES`), `run_setup` deve produzir exatamente o mesmo resultado que produziria sem esta feature — incluindo a união dos polígonos satélite na jurisdição da canônica em `_load_jurisdiction_poly`
    - Usar `@given(canonical_codes=st.lists(st.sampled_from(list(set(STATION_ALIASES.values()))), min_size=1, max_size=3, unique=True))` com `@settings(max_examples=50)`
    - Anotar: `# Feature: satellite-area-setup, Property 8: Retrocompatibilidade do setup canônico`
    - **Validates: Requirements 6.1, 6.3**

  - [x]* 9.5 Escrever teste de propriedade para agregação de métricas no relatório (Property 7)
    - **Property 7: Agregação de métricas satélite sob a canônica no relatório**
    - Para qualquer base canônica com territórios satélite, em `relatorio_executivo.json`: (a) os territórios satélite devem aparecer no array `territories` da base canônica, (b) cada território satélite deve ter `satelliteOrigin` igual ao código satélite, e (c) a soma das métricas de todos os territórios deve ser igual às métricas top-level da base
    - Usar `@given(canonical=st.sampled_from(list(set(STATION_ALIASES.values()))))` com `@settings(max_examples=100)`
    - Anotar: `# Feature: satellite-area-setup, Property 7: Agregação de métricas satélite sob a canônica no relatório`
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [x] 10. Checkpoint final — Garantir que todos os testes passam
  - Executar `pytest backend/tests/test_satellite_area_setup.py -v` e garantir que todos os testes passam
  - Executar `pytest backend/tests/ -v -k "satellite"` para verificar todos os testes relacionados
  - Garantir que os testes existentes não foram quebrados: `pytest backend/tests/ -v`
  - Perguntar ao usuário se há dúvidas antes de finalizar.

## Notas

- Tasks marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido
- Cada task referencia requisitos específicos para rastreabilidade
- Os testes de propriedade usam a biblioteca **Hypothesis** (já presente no projeto em `.hypothesis/`)
- O campo `canonical_base` é retrocompatível: arquivos antigos sem ele usam fallback via `STATION_ALIASES`
- O remap de `station_code` ocorre **apenas em memória** durante o daily — o disco nunca é alterado
- Checkpoints garantem validação incremental antes de avançar para a próxima fase
