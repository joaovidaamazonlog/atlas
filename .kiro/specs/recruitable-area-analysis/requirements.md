# Requirements Document

## Introduction

A funcionalidade de **Avaliação de Área Recrutável** adiciona à aba "Análise de Área" (AreaAnalysisTab) do ATLAS uma análise explícita e interativa para determinar se uma área geográfica possui demanda suficiente para justificar o recrutamento de um novo parceiro logístico last-mile.

Hoje, a viabilidade de recrutamento é calculada implicitamente durante o modo daily (matching hierárquico de parceiros com slots), gerando demanda residual — volume não coberto por parceiros ativos. Esta feature torna esse cálculo explícito, configurável e auditável pelo usuário, permitindo que mesmo leads classificados como "No Go" sejam analisados com transparência sobre o motivo da não qualificação.

A análise é baseada em dois insumos principais:
1. **heatmap.geojson** — hexágonos H3 com `demand_total` e `demand_daily` por célula
2. **Demanda residual** — volume não atribuído a parceiros ativos após o matching hierárquico

---

## Glossary

- **ATLAS**: Sistema de gestão e otimização de rede de parceiros logísticos last-mile (hub delivery)
- **AreaAnalysisTab**: Componente React da aba "Análise de Área" no painel de controles do ATLAS
- **Recruitable_Area_Evaluator**: Módulo de cálculo de viabilidade de área recrutável, executado no frontend
- **Heatmap**: Camada GeoJSON com hexágonos H3 contendo `demand_total` e `demand_daily` por célula geográfica
- **Demanda_Residual**: Volume de entregas diárias não coberto por parceiros ativos após o matching hierárquico do modo daily
- **ADV**: Average Daily Volume — volume médio diário de entregas esperado para um parceiro
- **Cap**: Capacidade diária máxima de entregas de um parceiro (slots ideais)
- **Raio_de_Entrega**: Distância máxima em metros a partir de um ponto central dentro da qual o parceiro opera
- **Slot_Ideal**: Posição geográfica e capacidade calculada pelo sistema para um parceiro ideal em uma área
- **Viabilidade**: Classificação binária (Viável / Não Viável) de uma área para recrutamento, baseada em ADV mínimo e cobertura de demanda residual
- **Lead**: Empresa prospectada como candidata a parceiro logístico
- **No_Go**: Classificação de um lead como inviável para recrutamento no modo daily
- **H3_Cell**: Hexágono da grade H3 (Uber H3) usado como unidade geográfica no heatmap
- **Ponto_Central**: Coordenada geográfica (lat/lon) usada como centro do raio de análise

---

## Requirements

### Requirement 1: Configuração de Parâmetros de Análise

**User Story:** Como analista de rede, quero configurar o ADV mínimo esperado e o raio de entrega antes de executar a análise, para que a avaliação reflita os critérios reais de viabilidade do parceiro que desejo recrutar.

#### Acceptance Criteria

1. THE AreaAnalysisTab SHALL exibir um campo numérico para o usuário informar o ADV mínimo esperado (Cap mínimo), com valor padrão de 40 pacotes/dia e unidade explícita "pacotes/dia"
2. THE AreaAnalysisTab SHALL exibir um campo numérico para o usuário informar o raio de entrega, com valor padrão de 1500 metros e unidade explícita "metros"
3. WHEN o usuário altera o valor do ADV mínimo, THE AreaAnalysisTab SHALL aceitar apenas valores inteiros positivos maiores que zero
4. WHEN o usuário altera o valor do raio de entrega, THE AreaAnalysisTab SHALL aceitar apenas valores inteiros positivos maiores que zero
5. IF o usuário informar um valor inválido (zero, negativo ou não numérico) em qualquer campo, THEN THE AreaAnalysisTab SHALL exibir uma mensagem de validação inline e desabilitar o botão de análise
6. THE AreaAnalysisTab SHALL preservar os valores configurados pelo usuário durante a sessão, sem resetar ao alternar entre abas

---

### Requirement 2: Seleção de Ponto Central de Análise

**User Story:** Como analista de rede, quero definir o ponto central da área a ser analisada, para que o sistema calcule a demanda disponível dentro do raio configurado a partir desse ponto.

#### Acceptance Criteria

1. THE AreaAnalysisTab SHALL exibir campos de entrada para latitude e longitude do ponto central de análise
2. WHEN o usuário clica em um ponto no mapa enquanto a aba "Análise de Área" está ativa, THE AreaAnalysisTab SHALL capturar automaticamente as coordenadas do clique e preencher os campos de latitude e longitude
3. IF os campos de latitude ou longitude estiverem vazios ao acionar a análise, THEN THE Recruitable_Area_Evaluator SHALL retornar um erro de validação indicando que o ponto central é obrigatório
4. WHEN as coordenadas do ponto central são definidas, THE AreaAnalysisTab SHALL exibir um marcador visual no mapa na posição informada
5. WHEN as coordenadas do ponto central são definidas, THE AreaAnalysisTab SHALL exibir um círculo no mapa com o raio configurado, centrado no ponto informado

---

### Requirement 3: Cálculo de Demanda Disponível na Área

**User Story:** Como analista de rede, quero que o sistema calcule automaticamente a demanda disponível dentro do raio configurado, para que eu possa avaliar se há volume suficiente para um novo parceiro.

#### Acceptance Criteria

1. WHEN o usuário aciona a análise, THE Recruitable_Area_Evaluator SHALL selecionar todas as H3_Cells do Heatmap cujo centroide está dentro do Raio_de_Entrega a partir do Ponto_Central
2. WHEN o usuário aciona a análise, THE Recruitable_Area_Evaluator SHALL calcular a demanda total da área como a soma de `demand_daily` de todas as H3_Cells selecionadas
3. WHEN o usuário aciona a análise, THE Recruitable_Area_Evaluator SHALL calcular a demanda residual da área como a soma de `demand_daily` das H3_Cells selecionadas que não possuem cobertura de parceiros ativos
4. IF o Heatmap não estiver carregado no momento da análise, THEN THE Recruitable_Area_Evaluator SHALL retornar um erro indicando que os dados de demanda são necessários para a análise
5. IF nenhuma H3_Cell for encontrada dentro do raio configurado, THEN THE Recruitable_Area_Evaluator SHALL retornar resultado indicando demanda zero e classificação Não Viável

---

### Requirement 4: Classificação de Viabilidade da Área

**User Story:** Como analista de rede, quero que o sistema classifique automaticamente a área como Viável ou Não Viável, para que eu possa tomar decisões de recrutamento com base em critérios objetivos.

#### Acceptance Criteria

1. WHEN o cálculo de demanda é concluído, THE Recruitable_Area_Evaluator SHALL classificar a área como **Viável** se a demanda residual calculada for maior ou igual ao ADV mínimo configurado pelo usuário
2. WHEN o cálculo de demanda é concluído, THE Recruitable_Area_Evaluator SHALL classificar a área como **Não Viável** se a demanda residual calculada for menor que o ADV mínimo configurado pelo usuário
3. WHEN a classificação é Não Viável, THE Recruitable_Area_Evaluator SHALL identificar e retornar o motivo principal entre: "Demanda residual insuficiente", "Área sem cobertura de heatmap" ou "Demanda total insuficiente"
4. THE Recruitable_Area_Evaluator SHALL retornar os seguintes valores no resultado: demanda total da área, demanda residual, ADV mínimo configurado, gap entre demanda residual e ADV mínimo, classificação de viabilidade e motivo (quando Não Viável)

---

### Requirement 5: Exibição do Resultado da Análise

**User Story:** Como analista de rede, quero visualizar o resultado da análise de forma clara e comparativa, para que eu entenda rapidamente se a área é viável e qual é o gap de demanda.

#### Acceptance Criteria

1. WHEN a análise é concluída, THE AreaAnalysisTab SHALL exibir o resultado em um painel de resultado dedicado, separado visualmente dos controles de configuração
2. THE AreaAnalysisTab SHALL exibir a classificação de viabilidade com destaque visual: verde para Viável, vermelho para Não Viável
3. THE AreaAnalysisTab SHALL exibir os seguintes valores numéricos no resultado: demanda total da área (pacotes/dia), demanda residual (pacotes/dia), ADV mínimo configurado (pacotes/dia) e gap entre demanda residual e ADV mínimo
4. WHEN a classificação é Não Viável, THE AreaAnalysisTab SHALL exibir o motivo da não viabilidade em destaque
5. WHEN um lead está selecionado no contexto da análise, THE AreaAnalysisTab SHALL exibir a decisão atual do lead (Go/No Go) e o motivo registrado, permitindo comparação com o resultado da análise de área
6. THE AreaAnalysisTab SHALL exibir uma barra de progresso visual indicando a proporção entre demanda residual e ADV mínimo configurado, com escala de 0% a 100%+ (podendo ultrapassar 100% quando viável)

---

### Requirement 6: Integração com Contexto de Lead

**User Story:** Como analista de rede, quero analisar a área de um lead classificado como No Go, para que eu entenda se a não qualificação é por falta de demanda ou por outro motivo operacional.

#### Acceptance Criteria

1. THE AreaAnalysisTab SHALL exibir uma seção opcional "Analisar Lead" onde o usuário pode selecionar um lead (Prospect) da lista de parceiros carregados
2. WHEN um lead é selecionado na seção "Analisar Lead", THE AreaAnalysisTab SHALL pré-preencher automaticamente o Ponto_Central com as coordenadas do lead (lat/lon) e o Raio_de_Entrega com o valor de `optimization.radius_suggestion` do lead
3. WHEN um lead é selecionado na seção "Analisar Lead", THE AreaAnalysisTab SHALL pré-preencher o ADV mínimo com o valor de `optimization.cap_suggestion` do lead
4. WHEN um lead com decisão No Go é selecionado, THE AreaAnalysisTab SHALL exibir o motivo do No Go registrado no campo `reason` do lead, antes de executar a análise
5. IF o lead selecionado não possuir coordenadas (lat/lon nulos), THEN THE AreaAnalysisTab SHALL exibir um aviso indicando que o lead não pode ser analisado por falta de geolocalização

---

### Requirement 7: Visualização no Mapa

**User Story:** Como analista de rede, quero visualizar no mapa as células H3 que compõem a área analisada, para que eu tenha contexto geográfico da demanda calculada.

#### Acceptance Criteria

1. WHEN a análise é concluída, THE AreaAnalysisTab SHALL destacar no mapa as H3_Cells selecionadas dentro do raio, diferenciando visualmente células com demanda residual (sem cobertura ativa) das células com cobertura já atribuída
2. WHEN a análise é concluída, THE AreaAnalysisTab SHALL exibir o círculo de raio configurado no mapa, centrado no Ponto_Central
3. WHEN o usuário fecha o painel de resultado ou limpa a análise, THE AreaAnalysisTab SHALL remover do mapa os destaques das H3_Cells e o círculo de raio
4. WHERE o Heatmap estiver habilitado na StyleConfig, THE AreaAnalysisTab SHALL sobrepor os destaques da análise recrutável sobre a camada de heatmap existente, sem substituí-la

---

### Requirement 8: Limpeza e Reset da Análise

**User Story:** Como analista de rede, quero limpar os resultados da análise atual para iniciar uma nova avaliação sem resíduos visuais ou de dados.

#### Acceptance Criteria

1. THE AreaAnalysisTab SHALL exibir um botão "Limpar Análise" após a execução de uma análise
2. WHEN o usuário aciona "Limpar Análise", THE AreaAnalysisTab SHALL remover o resultado exibido, limpar os campos de Ponto_Central e remover os destaques do mapa
3. WHEN o usuário aciona "Limpar Análise", THE AreaAnalysisTab SHALL preservar os valores de ADV mínimo e Raio_de_Entrega configurados pelo usuário
4. WHEN o usuário altera qualquer parâmetro de configuração após uma análise concluída, THE AreaAnalysisTab SHALL invalidar o resultado anterior e exibir indicação visual de que a análise está desatualizada
