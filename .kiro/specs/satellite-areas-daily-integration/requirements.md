# Requirements Document

## Introduction

As áreas satélite (ex: XBA1, XCS1, XGA2, XPB1, PUM2, XRJ2, XRJ4, XSJ1, XSP7, XSP9, XCP1) são bases de entrega anexadas logicamente a uma base canônica (ex: DSA8, DRS5, DGO2, DPB3, DRJ3, DSP4, DSP5). Atualmente o pipeline diário (`run_daily`) remapeia todos os pacotes das satélites para suas canônicas, fazendo com que volume, cobertura, carteira de parceiros e recomendações do evaluator fiquem misturados com os da canônica. Isso confunde o analista, que ao clicar numa área satélite no frontend recebe a recomendação da canônica.

Este feature faz com que as áreas satélite sejam tratadas como anexos reais no modo daily: volume de pacotes, hexes do heatmap, carteira de parceiros, residual e cobertura são calculados separadamente, enquanto a relação hierárquica com a canônica é preservada na UI e nos reports. O daily passa a atualizar semanalmente os territórios satélite existentes sem exigir um novo setup, com a mesma cadência que já ocorre para as canônicas. Reports executivos e o dashboard operacional passam a exibir as satélites como linhas filhas indentadas sob sua canônica.

## Glossary

- **Canonical_Station**: Base de entrega canônica, identificada por código de 4 caracteres começando com `D` (ex: `DSA8`, `DRJ3`, `DSP5`). Base âncora no sistema.
- **Satellite_Station**: Base satélite anexada a uma canônica, identificada por código de 4 caracteres começando com `X` ou `P` (ex: `XBA1`, `PUM2`). Listada em `STATION_ALIASES` em `backend/shared/config.py` com sua canônica correspondente.
- **Canonical_Base**: Para uma satélite, a canônica à qual ela está ancorada (ex: `XBA1` → canonical_base `DSA8`). Armazenada no campo `canonical_base` de cada território satélite em `territories_index.json`.
- **Territories_Index**: Arquivo `output_data/territories_index.json` contendo a definição de cada território (canônico ou satélite), seus hexes e metadados.
- **Heatmap**: Arquivo GeoJSON de features por hex (H3) contendo campos `delivery_station`, `demand`, `residual`, `is_covered`, consumido pelo frontend.
- **Daily_Pipeline**: Pipeline `run_daily` em `backend/vanilla/orchestrator.py` que atualiza semanalmente demanda, cobertura e partner fit sem recriar territórios.
- **Setup_Pipeline**: Pipeline `run_setup` que cria territórios a partir do zero.
- **Partner_Fit**: Fase do pipeline que atribui parceiros a territórios com base em cobertura de hexes.
- **Recruitable_Area_Evaluator**: Módulo frontend `atlas-react/src/lib/recruitableAreaEvaluator.ts` que decide qual base recomendar ao analista ao clicar em um hex.
- **Package**: Pacote de entrega com atributos `station_code` (canônica ou satélite) e localização; fonte de volume.
- **Anchored_Satellite_Report**: Visualização parent-child em relatórios executivos e dashboard operacional, exibindo satélites indentadas sob sua canônica com colunas próprias.

## Requirements

### Requirement 1: Preservação de identidade satélite no daily

**User Story:** Como engenheiro de pipeline, quero que o daily preserve a identidade das bases satélite ao carregar pacotes, para que o volume de cada satélite seja contabilizado separadamente do volume da sua canônica.

#### Acceptance Criteria

1. WHEN o `Daily_Pipeline` carrega pacotes via `load_packages`, THE `Daily_Pipeline` SHALL detectar automaticamente os códigos de `Satellite_Station` presentes no `Territories_Index` e passá-los como `satellite_setup_stations` para `load_packages`.
2. WHEN `load_packages` recebe uma lista não vazia de `satellite_setup_stations`, THE `Load_Packages` SHALL manter `station_code` original dos pacotes dessas satélites em vez de remapeá-lo para a canônica via `STATION_ALIASES`.
3. THE `Daily_Pipeline` SHALL computar o volume semanal de cada `Satellite_Station` exclusivamente a partir dos pacotes cujo `station_code` corresponde ao código da satélite.
4. THE `Daily_Pipeline` SHALL computar o volume semanal de cada `Canonical_Station` exclusivamente a partir dos pacotes cujo `station_code` corresponde ao código da canônica, excluindo pacotes de suas satélites.
5. WHEN o `Daily_Pipeline` executa com pacotes que somam volume total `V` antes da mudança (tudo ia para canônica), THE soma dos volumes de cada `Canonical_Station` com seus `Satellite_Station` anexados SHALL ser igual a `V` (conservação de volume).

### Requirement 2: Hexes satélite no heatmap com delivery_station próprio

**User Story:** Como analista operacional, quero que os hexes pertencentes a territórios satélite apareçam no heatmap com `delivery_station` igual ao código da satélite, para que o frontend possa distinguir visualmente e funcionalmente as áreas satélite das canônicas.

#### Acceptance Criteria

1. THE `Daily_Pipeline` SHALL atribuir `delivery_station` igual ao código da `Satellite_Station` em cada feature do `Heatmap` cujo hex pertence a um território satélite, conforme o `Territories_Index`.
2. THE `Daily_Pipeline` SHALL atribuir `delivery_station` igual ao código da `Canonical_Station` em cada feature do `Heatmap` cujo hex pertence a um território canônico.
3. THE `Heatmap` resultante do `Daily_Pipeline` SHALL conter exatamente uma feature por hex (nenhuma duplicata com `delivery_station` canônica E satélite para o mesmo hex).
4. THE `Heatmap` resultante do `Daily_Pipeline` SHALL conter zero features órfãs, definidas como features cujo hex não pertence a nenhum território no `Territories_Index`.
5. WHEN o `Daily_Pipeline` executa, THE `Daily_Pipeline` SHALL remover as rotinas `patch_heatmap_satellite_stations` e `patch_heatmap_add_satellite_hexes` de `backend/vanilla/phase_setup.py`, consolidando a atribuição de `delivery_station` diretamente na geração do heatmap.

### Requirement 3: Cálculo independente de demanda, residual e cobertura por satélite

**User Story:** Como analista, quero que cada hex satélite tenha demanda, residual e status de cobertura calculados com base apenas na satélite, para que a análise de cobertura da satélite não seja distorcida por parceiros ou demanda da canônica.

#### Acceptance Criteria

1. THE `Daily_Pipeline` SHALL calcular o campo `demand` de cada feature de hex satélite a partir dos pacotes da `Satellite_Station` correspondente.
2. THE `Daily_Pipeline` SHALL calcular o campo `residual` de cada feature de hex satélite como `demand` menos a demanda absorvida por parceiros atribuídos à mesma `Satellite_Station`.
3. THE `Daily_Pipeline` SHALL calcular o campo `is_covered` de cada feature de hex satélite considerando exclusivamente parceiros atribuídos à mesma `Satellite_Station`.
4. THE `Daily_Pipeline` SHALL calcular `demand`, `residual` e `is_covered` de hexes canônicos excluindo qualquer demanda ou parceiro vinculado às `Satellite_Station` anexadas à canônica.

### Requirement 4: Carteira de parceiros independente por satélite

**User Story:** Como gestor de parceiros, quero ver a carteira de parceiros de cada satélite separada da canônica, para que eu possa avaliar capacidade e gap de recrutamento de forma independente por base.

#### Acceptance Criteria

1. THE `Partner_Fit` SHALL atribuir parceiros que cobrem exclusivamente hexes de uma `Satellite_Station` à carteira dessa satélite.
2. THE `Partner_Fit` SHALL atribuir parceiros que cobrem exclusivamente hexes de uma `Canonical_Station` à carteira dessa canônica.
3. THE `Territories_Index` atualizado pelo `Daily_Pipeline` SHALL expor a lista de parceiros atribuídos em cada território satélite e canônico de forma desagregada.
4. IF um parceiro cobre hexes de uma `Canonical_Station` e de uma `Satellite_Station` anexada a ela, THEN THE `Partner_Fit` SHALL registrar esse caso em log de aviso e atribuir o parceiro conforme a regra definida no design (caso tratado como exceção por premissa geográfica de que satélites estão geograficamente distantes das canônicas).

### Requirement 5: Atualização incremental sem rerun de setup

**User Story:** Como operador do pipeline, quero que o daily atualize semanalmente os territórios satélite existentes sem exigir rerun de `run_setup`, para que a cadência de atualização das satélites seja equivalente à das canônicas.

#### Acceptance Criteria

1. WHEN o `Daily_Pipeline` executa e o `Territories_Index` já contém territórios `Satellite_Station`, THE `Daily_Pipeline` SHALL atualizar os campos `demand`, `residual`, `is_covered` e lista de parceiros desses territórios sem recriar nem remover os territórios satélite.
2. THE `Daily_Pipeline` SHALL preservar a estrutura de hexes de cada território satélite existente (hexes do território não mudam entre execuções do daily).
3. THE `Daily_Pipeline` SHALL preservar o campo `canonical_base` de cada território satélite.
4. WHEN o `Daily_Pipeline` é executado duas vezes consecutivas com o mesmo conjunto de pacotes de entrada, THE `Territories_Index` e THE `Heatmap` resultantes da segunda execução SHALL ser equivalentes aos da primeira execução (idempotência: mesmas features, mesmos valores de `demand`, `residual`, `is_covered`, mesma carteira de parceiros).

### Requirement 6: Evaluator frontend resolve para a base satélite

**User Story:** Como analista no frontend, quando clico em um hex de área satélite, quero ver a recomendação apontando para a satélite com a indicação de que é anexo da canônica, para que eu siga o fluxo correto de recrutamento sem confundir satélite com canônica.

#### Acceptance Criteria

1. WHEN o `Recruitable_Area_Evaluator` processa um clique em um hex cujo `delivery_station` é uma `Satellite_Station`, THE `Recruitable_Area_Evaluator` SHALL resolver a base recomendada para o código da `Satellite_Station` (não para a canônica).
2. WHEN o `Recruitable_Area_Evaluator` resolve uma recomendação para uma `Satellite_Station`, THE frontend SHALL exibir um badge textual indicando "Anexo de [código_canonical_base]" junto ao nome da satélite.
3. WHEN o `Recruitable_Area_Evaluator` agrupa hexes por base para cálculo de balde dominante, THE `Recruitable_Area_Evaluator` SHALL agrupar hexes de `Satellite_Station` separadamente dos hexes da sua canônica.
4. WHEN o `Recruitable_Area_Evaluator` computa demanda, residual e parceiros para exibição, THE `Recruitable_Area_Evaluator` SHALL usar os valores da `Satellite_Station` para hexes satélite e os valores da `Canonical_Station` para hexes canônicos.

### Requirement 7: Visualização hierárquica em reports e dashboard operacional

**User Story:** Como gestor executivo, quero ver as satélites como linhas filhas indentadas sob sua canônica nos reports e no dashboard operacional, para que eu entenda a relação de anexo e compare volume e carteira sem confundir com bases independentes.

#### Acceptance Criteria

1. THE dashboard operacional SHALL exibir cada `Satellite_Station` como uma linha filha indentada sob sua `Canonical_Station`.
2. THE dashboard operacional SHALL exibir colunas próprias de volume, carteira de parceiros e cobertura para cada `Satellite_Station`, independentes da linha da canônica.
3. THE dashboard operacional SHALL exibir, na linha da `Canonical_Station`, métricas calculadas exclusivamente a partir dos hexes e pacotes da canônica (não somando satélites).
4. WHERE o report executivo tem visualização agregada por região, THE report SHALL apresentar uma linha de total por `Canonical_Station` que inclui a canônica e suas satélites anexadas, rotulada de forma que distinga do total da canônica isolada.
5. THE dashboard operacional SHALL permitir expandir e colapsar o conjunto de satélites de cada canônica.

### Requirement 8: Detecção automática de satélites no daily

**User Story:** Como operador do pipeline, quero que o daily detecte automaticamente quais satélites devem ser preservadas sem precisar passar parâmetros manuais, para que a execução semanal não dependa de configuração adicional.

#### Acceptance Criteria

1. WHEN o `Daily_Pipeline` inicia, THE `Daily_Pipeline` SHALL ler o `Territories_Index` e extrair a lista de todas `Satellite_Station` presentes, identificadas por possuírem o campo `canonical_base` preenchido.
2. THE `Daily_Pipeline` SHALL usar essa lista automaticamente como `satellite_setup_stations` ao invocar `load_packages`, sem requerer flag de CLI adicional.
3. IF o `Territories_Index` não contém nenhuma `Satellite_Station`, THEN THE `Daily_Pipeline` SHALL executar com comportamento equivalente ao anterior à feature (sem satélites a preservar).
