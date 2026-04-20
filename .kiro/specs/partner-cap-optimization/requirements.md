# Requirements Document

## Introduction

A feature **Partner Cap Optimization** adiciona ao ATLAS uma nova fase de otimização de capacidade (Fase 3.5) no pipeline diário do backend e uma nova seção de interface no frontend para explorar e simular oportunidades de aumento de cap para parceiros Active.

O objetivo central é identificar, para cada parceiro Active, se existe demanda residual disponível no heatmap enriquecido que justifique aumentar o cap atual (até o máximo de 80 pacotes/dia) e, quando possível, reduzir o raio de entrega. O resultado é persistido no `dados_mapa.json` e exposto no frontend como uma lista de oportunidades ordenada por ganho estimado de ADV, com suporte a simulação what-if via arrasto de marcadores no mapa.

O escopo também inclui uma revisão da apresentação de attainment e acuracidade no Dashboard para uma visão mais consolidada de saúde da rede, sem alterações estruturais.

---

## Glossary

- **Active**: status de parceiro operacional e ativo na rede.
- **ADV** (Average Daily Volume): volume médio diário de pacotes entregues por um parceiro.
- **adv_opportunity**: objeto persistido no `dados_mapa.json` descrevendo a oportunidade de otimização de cap para um parceiro Active; `null` quando não há oportunidade.
- **Cap**: capacidade máxima diária de pacotes de um parceiro (campo `capacity` no `dados_mapa.json`).
- **Cap_Max**: limite máximo de cap permitido pelo sistema — 80 pacotes/dia.
- **Centroid**: posição geográfica atual (lat/lon) de um parceiro.
- **Demanda Residual**: campo `demand_residual` de cada hexágono H3 no `heatmap.geojson`, representando demanda não coberta por nenhum parceiro Active/Onboarding.
- **estimated_adv_gain**: diferença entre `suggested_cap` e o cap atual do parceiro, representando o ganho estimado de ADV.
- **Fase 3.5**: nova fase do pipeline diário, executada após a Fase 3 (matching) e antes da Fase 5 (reports).
- **H3**: sistema de indexação geoespacial hexagonal usado pelo ATLAS.
- **heatmap.geojson**: arquivo GeoJSON com hexágonos H3 enriquecidos com campos `demand_daily`, `demand_residual`, `is_covered`, `covering_partner_id`.
- **dados_mapa.json**: arquivo JSON com todos os parceiros, incluindo campos de otimização.
- **Oportunidade de Cap**: condição em que um parceiro Active tem cap atual < 80 E há demanda residual disponível além do cap atual dentro do raio de busca.
- **Posição Candidata**: posição geográfica alternativa dentro de 300m do centroid atual de um parceiro, derivada de hexágonos H3 vizinhos.
- **Raio de Busca**: distância máxima de 300m do centroid atual para varredura de posições candidatas na Fase 3.5.
- **ResultPanel**: painel lateral direito do frontend onde resultados de análises são exibidos.
- **AreaAnalysisTab**: aba do painel de controles do frontend que contém as seções de análise de área.
- **What-If Manual**: modo interativo no mapa em que parceiros Active ficam arrastáveis para simulação de cap em tempo real.
- **Guardrail Visual**: círculo de 300m exibido no mapa durante o what-if para delimitar o limite de arrasto permitido.
- **Hex Selection**: conjunto de hexágonos H3 selecionados pelo usuário via clique no heatmap quando a aba "Área" está ativa.
- **Soma Acumulada**: soma de `demand_daily` e `demand_residual` de todos os hexágonos da Hex Selection.

---

## Requirements

### Requirement 1: Fase 3.5 — Avaliação de Oportunidades de Cap

**User Story:** Como analista de rede, quero que o pipeline diário avalie automaticamente todos os parceiros Active e identifique oportunidades de aumento de cap, para que eu possa priorizar ações de otimização sem análise manual.

#### Acceptance Criteria

1. WHEN o pipeline diário executa, THE Fase_3_5 SHALL ser executada após a conclusão da Fase 3 (matching) e antes da Fase 5 (reports).
2. THE Fase_3_5 SHALL avaliar todos os parceiros com status `Active` presentes no `FitResult` gerado pela Fase 3.
3. WHEN um parceiro Active tem `capacity` >= 80, THE Fase_3_5 SHALL registrar `adv_opportunity = null` para esse parceiro sem realizar varredura de posições candidatas.
4. WHEN um parceiro Active tem `capacity` < 80, THE Fase_3_5 SHALL varrer posições candidatas dentro de 300m do centroid atual usando hexágonos H3 vizinhos (grid_disk com raio equivalente a 300m na resolução H3 do parceiro).
5. WHEN a varredura de posições candidatas é executada, THE Fase_3_5 SHALL calcular a demanda residual disponível no raio de entrega atual do parceiro para cada posição candidata usando os campos `demand_residual` do `heatmap.geojson` enriquecido.
6. WHEN a demanda residual disponível em uma posição candidata supera o cap atual do parceiro, THE Fase_3_5 SHALL calcular `suggested_cap = min(demanda_residual_disponivel, 80)` e `suggested_radius` como o menor raio que cobre a demanda necessária para o `suggested_cap`.
7. WHEN múltiplas posições candidatas são viáveis, THE Fase_3_5 SHALL selecionar a posição com maior `estimated_adv_gain` (desempate: menor `distance_from_current`).
8. WHEN uma oportunidade é identificada, THE Fase_3_5 SHALL persistir no parceiro dentro do `dados_mapa.json` o objeto `adv_opportunity` com os campos: `suggested_lat`, `suggested_lon`, `suggested_cap`, `suggested_radius`, `estimated_adv_gain`, `distance_from_current`.
9. WHEN nenhuma posição candidata supera o cap atual, THE Fase_3_5 SHALL persistir `adv_opportunity = null` para esse parceiro.
10. THE Fase_3_5 SHALL preservar todos os demais campos existentes de cada parceiro no `dados_mapa.json` sem modificação.
11. IF o `heatmap.geojson` não estiver disponível no diretório de output, THEN THE Fase_3_5 SHALL registrar um aviso no log e encerrar sem modificar o `dados_mapa.json`.

---

### Requirement 2: Estrutura de Dados de Oportunidade

**User Story:** Como desenvolvedor, quero que o campo `adv_opportunity` tenha uma estrutura de dados bem definida e consistente, para que o frontend possa consumi-lo de forma confiável.

#### Acceptance Criteria

1. THE Fase_3_5 SHALL serializar `adv_opportunity` como um objeto JSON com os campos: `suggested_lat` (float), `suggested_lon` (float), `suggested_cap` (int), `suggested_radius` (int, em metros), `estimated_adv_gain` (int), `distance_from_current` (float, em metros).
2. WHEN `adv_opportunity` não existe para um parceiro, THE Fase_3_5 SHALL serializar o campo como `null` (não omitir o campo).
3. THE Fase_3_5 SHALL garantir que `suggested_cap` seja sempre um inteiro entre `capacity_atual + 1` e `80` (inclusive).
4. THE Fase_3_5 SHALL garantir que `estimated_adv_gain = suggested_cap - capacity_atual`.
5. THE Fase_3_5 SHALL garantir que `distance_from_current` seja a distância geodésica em metros entre o centroid atual e a posição sugerida.
6. THE Partner_Model SHALL incluir o campo `adv_opportunity` como campo opcional no modelo `Partner` do `shared/models.py`, com valor padrão `None`.

---

### Requirement 3: Integração da Fase 3.5 no Orquestrador

**User Story:** Como operador do pipeline, quero que a Fase 3.5 seja integrada ao modo `daily` do orquestrador sem alterar os demais modos, para que o pipeline continue funcionando de forma transparente.

#### Acceptance Criteria

1. WHEN o orquestrador executa no modo `daily`, THE Orchestrator SHALL chamar `run_phase3_5` após `run_phase3` e antes de `run_phase4`.
2. THE Orchestrator SHALL passar ao `run_phase3_5` os seguintes argumentos: `fit` (FitResult da Fase 3), `output_dir` (diretório de saída), `stations` (lista de bases filtradas, opcional).
3. WHEN `stations` é fornecido ao orquestrador, THE Fase_3_5 SHALL processar apenas os parceiros Active das bases listadas.
4. IF a Fase 3.5 falhar com exceção não tratada, THEN THE Orchestrator SHALL registrar o erro no log e continuar a execução das fases seguintes sem abortar o pipeline.

---

### Requirement 4: Tipo TypeScript para `adv_opportunity`

**User Story:** Como desenvolvedor frontend, quero que o tipo `Partner` no TypeScript inclua o campo `adv_opportunity` com tipagem estrita, para que o compilador detecte erros de acesso ao campo.

#### Acceptance Criteria

1. THE Partner_Type SHALL incluir o campo `adv_opportunity` com o tipo `AdvOpportunity | null`.
2. THE AdvOpportunity_Interface SHALL definir os campos: `suggested_lat: number`, `suggested_lon: number`, `suggested_cap: number`, `suggested_radius: number`, `estimated_adv_gain: number`, `distance_from_current: number`.
3. THE Partner_Model_Class SHALL mapear o campo `adv_opportunity` do JSON de entrada para o tipo `AdvOpportunity | null` durante a construção do objeto `Partner`.
4. WHEN o campo `adv_opportunity` está ausente ou é `null` no JSON de entrada, THE Partner_Model_Class SHALL atribuir `null` ao campo `adv_opportunity` do objeto `Partner`.

---

### Requirement 5: Seção "Oportunidades de Cap" na AreaAnalysisTab

**User Story:** Como analista de rede, quero ver uma lista de parceiros Active com oportunidades de aumento de cap no painel de análise de área, para que eu possa identificar rapidamente onde há potencial de crescimento de ADV.

#### Acceptance Criteria

1. THE AreaAnalysisTab SHALL exibir uma seção "Oportunidades de Cap" separada das seções "Área Recrutável" e de análise de prospects existentes.
2. WHEN o usuário aciona a análise de oportunidades de cap, THE Cap_Opportunity_Section SHALL exibir no ResultPanel todos os parceiros Active com `adv_opportunity != null`, ordenados por `estimated_adv_gain` decrescente.
3. WHEN a lista de oportunidades é exibida, THE Cap_Opportunity_Section SHALL mostrar para cada item: nome do parceiro, cap atual → cap sugerido, raio atual → raio sugerido, ganho estimado de ADV.
4. WHEN a lista de oportunidades está vazia (nenhum parceiro Active tem `adv_opportunity != null`), THE Cap_Opportunity_Section SHALL exibir uma mensagem informando que não há oportunidades identificadas.
5. WHEN o usuário clica em um item da lista, THE Cap_Opportunity_Section SHALL exibir no mapa: marcador na posição atual do parceiro (estilo normal) e marcador na posição sugerida (estilo destacado), círculo de raio atual e círculo de raio sugerido.
6. WHEN o usuário clica novamente no mesmo item da lista, THE Cap_Opportunity_Section SHALL remover os marcadores e círculos de comparação do mapa (toggle).
7. WHEN a análise de oportunidades de cap está ativa, THE AreaAnalysisTab SHALL aplicar o filtro de status `Active` nos marcadores do mapa.

---

### Requirement 6: What-If Manual — Arrasto de Parceiros dentro da Análise Manual

**User Story:** Como analista de rede, quero ativar o modo what-if de parceiros dentro do painel "Análise Manual" existente, para que eu possa arrastar parceiros Active no mapa e simular o impacto no cap e raio sugeridos em tempo real, de forma integrada ao fluxo de análise manual já existente.

#### Acceptance Criteria

1. WHEN o painel "Análise Manual" está aberto (`manualAnalysisOpen === true`), THE Manual_Analysis_Panel SHALL exibir uma opção "Simular reposicionamento de parceiro" como modo alternativo dentro do painel, separado da análise de ponto central existente.
2. WHEN o usuário ativa a opção "Simular reposicionamento de parceiro", THE Map SHALL tornar os marcadores de parceiros Active arrastáveis.
3. WHEN o usuário desativa a opção ou fecha o painel "Análise Manual", THE Map SHALL restaurar todos os marcadores de parceiros Active ao comportamento não arrastável e remover todos os guardrails visuais.
4. WHEN um parceiro Active é arrastado com a opção ativa, THE Map SHALL exibir um círculo de guardrail de 300m ao redor do centroid original do parceiro para delimitar o limite de arrasto permitido.
5. WHEN o usuário solta o marcador dentro do guardrail de 300m, THE What_If_Engine SHALL recalcular `suggested_cap` e `suggested_radius` em tempo real usando os campos `demand_residual` do `heatmapData` carregado no store.
6. WHEN o usuário solta o marcador fora do guardrail de 300m, THE Map SHALL reposicionar o marcador no centroid original do parceiro e exibir uma mensagem de aviso no painel.
7. WHEN o resultado do what-if é calculado, THE Manual_Analysis_Panel SHALL exibir o resultado no painel direito existente, incluindo: nome do parceiro, posição simulada (lat/lon), cap simulado, raio simulado e ganho simulado de ADV.
8. WHEN o `heatmapData` não está carregado no store com a opção ativa, THE Manual_Analysis_Panel SHALL exibir uma mensagem de erro informando que os dados de demanda não estão disponíveis.

---

### Requirement 7: Camada de Comparação no Mapa

**User Story:** Como analista de rede, quero visualizar no mapa a diferença entre a posição atual e a posição sugerida de um parceiro, para que eu possa avaliar visualmente o impacto geográfico da otimização.

#### Acceptance Criteria

1. WHEN um item de oportunidade é selecionado na lista, THE Cap_Comparison_Layer SHALL renderizar um marcador na posição atual do parceiro com estilo de marcador padrão (CircleMarker com cor do status Active).
2. WHEN um item de oportunidade é selecionado na lista, THE Cap_Comparison_Layer SHALL renderizar um marcador na posição sugerida com estilo destacado (CircleMarker com cor diferenciada e borda mais espessa).
3. WHEN um item de oportunidade é selecionado na lista, THE Cap_Comparison_Layer SHALL renderizar um círculo com o raio atual do parceiro centrado na posição atual.
4. WHEN um item de oportunidade é selecionado na lista, THE Cap_Comparison_Layer SHALL renderizar um círculo com o raio sugerido centrado na posição sugerida, com estilo visual diferenciado (cor e opacidade distintas do círculo atual).
5. WHEN o item é desselecionado (toggle), THE Cap_Comparison_Layer SHALL remover todos os elementos visuais de comparação do mapa.
6. THE Cap_Comparison_Layer SHALL ser implementada como um componente React separado, renderizado dentro do MapView.

---

### Requirement 8: Dashboard — Revisão de Apresentação de Attainment e Acuracidade

**User Story:** Como gestor de rede, quero uma visão mais consolidada de saúde da rede no Dashboard, para que eu possa avaliar o estado geral sem distrações visuais desnecessárias.

#### Acceptance Criteria

1. THE Dashboard SHALL apresentar attainment e acuracidade de forma consolidada, sem uso de badges coloridos para classificação de status.
2. THE Dashboard SHALL preservar a estrutura existente de tabelas, gráficos e filtros sem alterações estruturais.
3. WHEN os valores de attainment e acuracidade são exibidos na tabela de territórios, THE Dashboard SHALL usar formatação de texto simples com cor contextual (sem elementos de badge ou pill).
4. THE Dashboard SHALL manter todos os campos e colunas existentes na tabela de territórios sem adição ou remoção de colunas.
5. THE Dashboard SHALL manter a funcionalidade de ordenação por coluna existente sem alterações.

---

### Requirement 9: Popup de Demanda por Hexágono H3

**User Story:** Como analista de rede, quero clicar em hexágonos do heatmap para ver a demanda residual disponível e acumular a soma ao selecionar múltiplos hexágonos, para que eu possa avaliar manualmente o potencial de uma área antes de recrutar ou ajustar um parceiro.

#### Acceptance Criteria

1. WHEN a aba "Área" está ativa e o usuário clica em um hexágono do heatmap, THE HeatmapLayer SHALL exibir um popup com os campos: `demand_daily` (demanda total do hex), `demand_residual` (demanda não coberta), `is_covered` (coberto ou não por parceiro ativo) e `covering_partner_id` (id do parceiro que cobre, quando aplicável).
2. WHEN a aba "Área" está ativa e o usuário clica em múltiplos hexágonos, THE HeatmapLayer SHALL acumular a seleção e exibir no painel direito a soma de `demand_daily` e `demand_residual` de todos os hexágonos selecionados.
3. WHEN a aba "Área" está inativa, THE HeatmapLayer SHALL manter o comportamento atual sem popup de demanda e sem seleção acumulada.
4. WHEN um hexágono já selecionado é clicado novamente, THE HeatmapLayer SHALL remover esse hexágono da seleção e recalcular a soma acumulada.
5. THE HeatmapLayer SHALL destacar visualmente os hexágonos selecionados com borda diferenciada, sem alterar o estilo de cor do heatmap existente.
6. WHEN o usuário aciona "Limpar Análise" ou troca de aba, THE HeatmapLayer SHALL limpar todos os hexágonos selecionados e remover o destaque visual.
7. WHEN a soma acumulada de `demand_residual` dos hexágonos selecionados é exibida, THE AreaAnalysisTab SHALL mostrar também a comparação com o ADV mínimo configurado na seção "Área Recrutável" (quando disponível).
