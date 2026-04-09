# Requirements Document

## Introduction

Esta feature transforma a aba "Destaques" (div `#highlight-content`) do painel de controles do ATLAS em um painel de "Análise de Área". O painel permite ao usuário filtrar parceiros em prospecção por Estado e Decisão, aplicar o filtro e visualizar um popup com estatísticas consolidadas dos prospects resultantes. O filtro por `status = "Prospect"` é fixo e sempre aplicado. O popup fecha automaticamente ao trocar de aba no painel de controles.

## Glossary

- **Area_Analysis_Panel**: O painel de "Análise de Área", localizado na aba anteriormente chamada "Destaques" (`#highlight-content`) dentro do painel de controles flutuante do ATLAS.
- **Prospect**: Parceiro com `status === "Prospect"` nos dados de `dados_mapa.json`.
- **Estado**: Campo `state` do parceiro (ex: "SP", "RJ", "MG"). Pode ser nulo.
- **Decision**: Campo `decision` do parceiro. Valor binário: `"Go"` (prospect aprovado para seguir cadastro) ou `"No Go"` (prospect não aprovado). Gerado pelo backend na Fase 3.
- **Reason**: Campo `reason` do parceiro. String com o motivo específico da decisão. Para prospects `"Go"`, o valor é `"Seguir cadastro"`. Para prospects `"No Go"`, os valores possíveis são: `"Sem oportunidade próxima"`, `"Sem oportunidade próxima na borda"` ou `"Fora de jurisdição"`.
- **Stats_Popup**: Popup flutuante exibido sobre o mapa com as estatísticas calculadas dos prospects filtrados.
- **PartnerMetrics**: Estrutura de dados do backend (`models.py`) que representa um parceiro ou prospect, contendo os campos `decision` e `reason` após a refatoração da Fase 3.
- **dados_mapa.json**: Arquivo JSON gerado pelo backend contendo todos os `PartnerMetrics` serializados, consumido pelo frontend do ATLAS.

## Requirements

### Requirement 1: Renomear e refatorar a aba "Destaques" para "Análise de Área"

**User Story:** Como analista de expansão, quero que a aba "Destaques" seja renomeada para "Análise de Área", para que o propósito do painel fique claro e alinhado com a nova funcionalidade.

#### Acceptance Criteria

1. THE Area_Analysis_Panel SHALL exibir o rótulo "Análise de Área" na aba de navegação do painel de controles, substituindo o rótulo "Destaques".
2. THE Area_Analysis_Panel SHALL manter o mesmo `id="highlight-content"` na div da aba para preservar compatibilidade com o sistema de abas Bootstrap existente.
3. THE Area_Analysis_Panel SHALL substituir o conteúdo anterior de highlight de parceiros (campos Eligible Packages, Overlapping Count, ADV, Status e botões Highlight/Reset) pelo novo conteúdo de filtros de análise de área.

---

### Requirement 2: Filtros configuráveis de Estado e Decisão

**User Story:** Como analista de expansão, quero selecionar um Estado e uma Decisão antes de aplicar a análise, para que eu possa segmentar os prospects por região geográfica e estágio de avaliação.

#### Acceptance Criteria

1. THE Area_Analysis_Panel SHALL exibir um campo de seleção (`select`) com o rótulo "Estado" populado com os valores únicos e ordenados do campo `state` dos parceiros com `status === "Prospect"` presentes em `state.allMarkersData`.
2. THE Area_Analysis_Panel SHALL incluir a opção "Todos" como primeira opção do select de Estado, selecionada por padrão.
3. THE Area_Analysis_Panel SHALL exibir um campo de seleção (`select`) com o rótulo "Decisão" populado com as opções fixas `"Go"`, `"No Go"` e `"Todos"`, correspondentes aos valores possíveis do campo `decision` dos parceiros com `status === "Prospect"`.
4. THE Area_Analysis_Panel SHALL incluir a opção "Todos" como primeira opção do select de Decisão, selecionada por padrão.
5. WHEN `state.allMarkersData` é atualizado, THE Area_Analysis_Panel SHALL repopular o select de Estado com os valores atualizados.
6. THE Area_Analysis_Panel SHALL exibir um texto informativo fixo indicando que o filtro de `status = "Prospect"` é sempre aplicado (ex: "Filtro fixo: Status = Prospect").

---

### Requirement 3: Filtro fixo por status "Prospect"

**User Story:** Como analista de expansão, quero que a análise sempre considere apenas parceiros com status "Prospect", para que os resultados sejam sempre relevantes para o pipeline de prospecção.

#### Acceptance Criteria

1. WHEN o usuário aciona a análise de área, THE Area_Analysis_Panel SHALL filtrar `state.allMarkersData` incluindo apenas registros onde `status === "Prospect"`.
2. THE Area_Analysis_Panel SHALL aplicar o filtro de status "Prospect" antes de qualquer outro filtro configurável pelo usuário.
3. IF nenhum parceiro com `status === "Prospect"` for encontrado após a aplicação dos filtros, THEN THE Stats_Popup SHALL exibir uma mensagem informando que não há prospects para os filtros selecionados.

---

### Requirement 4: Aplicar filtros e exibir popup de estatísticas

**User Story:** Como analista de expansão, quero clicar em um botão para aplicar os filtros e ver um popup com as estatísticas dos prospects, para que eu possa analisar rapidamente o pipeline de uma área.

#### Acceptance Criteria

1. THE Area_Analysis_Panel SHALL exibir um botão "Analisar Área" que, quando acionado, calcula e exibe o Stats_Popup.
2. WHEN o botão "Analisar Área" é acionado, THE Area_Analysis_Panel SHALL aplicar os filtros de Estado e Decisão (além do filtro fixo de Prospect) sobre `state.allMarkersData`.
3. WHEN o botão "Analisar Área" é acionado com Estado diferente de "Todos", THE Area_Analysis_Panel SHALL incluir apenas prospects onde `state === valorSelecionado`.
4. WHEN o botão "Analisar Área" é acionado com Decisão diferente de "Todos", THE Area_Analysis_Panel SHALL incluir apenas prospects onde `decision === valorSelecionado` (`"Go"` ou `"No Go"`).
5. WHEN o botão "Analisar Área" é acionado, THE Stats_Popup SHALL ser exibido sobre o mapa com posição fixa (canto superior direito da tela).

---

### Requirement 5: Conteúdo do popup de estatísticas

**User Story:** Como analista de expansão, quero ver métricas consolidadas dos prospects no popup, para que eu possa tomar decisões informadas sobre o pipeline de uma área.

#### Acceptance Criteria

1. THE Stats_Popup SHALL exibir o total de prospects encontrados após a aplicação de todos os filtros.
2. THE Stats_Popup SHALL exibir a quantidade de prospects aprovados, definidos como aqueles com `decision === "Go"`.
3. THE Stats_Popup SHALL exibir, para cada valor único de `reason` presente nos prospects com `decision === "No Go"` nos dados filtrados, a quantidade de prospects com aquele motivo de não aprovação. Os valores possíveis de `reason` para `"No Go"` são: `"Sem oportunidade próxima"`, `"Sem oportunidade próxima na borda"` e `"Fora de jurisdição"`.
4. THE Stats_Popup SHALL exibir o índice de aprovação, calculado como `(quantidade com decision "Go" / total de prospects) * 100`, formatado com uma casa decimal e sufixo "%".
5. THE Stats_Popup SHALL exibir, para cada motivo de não aprovação (`reason`), a porcentagem que ele representa sobre o total de prospects, calculada como `(quantidade do motivo / total de prospects) * 100`, formatada com uma casa decimal e sufixo "%".
6. THE Stats_Popup SHALL exibir um botão de fechar ("×") que, quando acionado, remove o popup do DOM.
7. THE Stats_Popup SHALL exibir o título "Análise de Área" e os filtros ativos aplicados (Estado e Decisão selecionados).

---

### Requirement 6: Refatorar campo `decision` do backend para estrutura binária Go/No Go

**User Story:** Como desenvolvedor, quero que o backend produza um campo `decision` binário (`"Go"` / `"No Go"`) acompanhado de um campo `reason` com o motivo específico, para que o frontend possa filtrar e agrupar prospects de forma clara e consistente.

#### Acceptance Criteria

1. THE PartnerMetrics SHALL conter um campo `decision` com valor `"Go"` quando o prospect for matched com uma vaga ideal na Fase 3.
2. THE PartnerMetrics SHALL conter um campo `decision` com valor `"No Go"` quando o prospect não for matched com nenhuma vaga ideal na Fase 3.
3. THE PartnerMetrics SHALL conter um campo `reason` com o motivo específico da decisão, conforme o mapeamento:
   - Prospect matched com vaga → `reason: "Seguir cadastro"`
   - Prospect sem vaga próxima (dentro da jurisdição) → `reason: "Sem oportunidade próxima"`
   - Prospect de borda sem vaga (fora de jurisdição mas próximo a slot) → `reason: "Sem oportunidade próxima na borda"`
   - Prospect fora de jurisdição completamente → `reason: "Fora de jurisdição"`
4. THE dados_mapa.json SHALL serializar os campos `decision` e `reason` de cada `PartnerMetrics` com os valores definidos nos critérios 1–3.
5. IF um `PartnerMetrics` possui `decision === "No Go"`, THEN THE PartnerMetrics SHALL conter um `reason` com um dos três valores possíveis: `"Sem oportunidade próxima"`, `"Sem oportunidade próxima na borda"` ou `"Fora de jurisdição"`.
6. IF um `PartnerMetrics` possui `decision === "Go"`, THEN THE PartnerMetrics SHALL conter `reason === "Seguir cadastro"`.

---

### Requirement 7: Fechar popup automaticamente ao trocar de aba

**User Story:** Como analista de expansão, quero que o popup de estatísticas feche automaticamente quando eu trocar de aba no painel de controles, para que o popup não obstrua a visualização do mapa ao usar outras funcionalidades.

#### Acceptance Criteria

1. WHEN o usuário seleciona a aba "Filtros" (`#filter-content`) no painel de controles, THE Stats_Popup SHALL ser removido do DOM se estiver visível.
2. WHEN o usuário seleciona a aba "Rotas" (`#route-content`) no painel de controles, THE Stats_Popup SHALL ser removido do DOM se estiver visível.
3. WHEN o usuário seleciona a aba "Análise de Área" (`#highlight-content`), THE Stats_Popup SHALL permanecer no DOM se já estiver visível (a troca para a própria aba não fecha o popup).
