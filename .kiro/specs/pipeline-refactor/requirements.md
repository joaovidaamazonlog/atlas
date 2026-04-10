# Requirements Document

## Introduction

Refatoração do pipeline de dados do sistema ATLAS para eliminar a redundância do JSON intermediário entre `main.py` e `load_partners.py`. O objetivo é unificar o fluxo em um único pipeline onde `load_partners.py` lê diretamente do Excel, produz um único JSON de saída com schema limpo, e o frontend é ajustado para consumir o novo schema sem quebrar nenhuma funcionalidade existente das Fases 3, 4 e 5.

## Glossary

- **Pipeline**: Sequência de etapas de processamento de dados do backend ATLAS, do Excel ao JSON de saída.
- **ExcelHandler**: Classe `backend/data_processing/excel_handler.py` responsável por abrir o arquivo `terra.xlsm`, executar a macro VBA e carregar abas como DataFrames.
- **DataProcessor**: Classe `backend/data_processing/data_processor.py` com métodos de consolidação e cálculo de métricas.
- **JsonGenerator**: Classe `backend/data_processing/json_generator.py` que serializa o DataFrame final para `dados_mapa.json`. Será removida nesta refatoração.
- **load_partners**: Módulo `backend/load_partners.py` que carrega parceiros e jurisdições para as Fases 3/4/5.
- **PartnerData**: Dataclass de saída do `load_partners`, contendo `partners_df`, `web_leads_df` e `jurisdictions`.
- **PartnerMetrics**: Dataclass em `backend/models.py` que representa um parceiro nas Fases 3/4/5.
- **Partner**: Classe JavaScript em `js/models.js` que representa um parceiro no frontend.
- **dados_mapa.json**: Arquivo JSON de saída do pipeline, consumido pelo frontend via `data-manager.js`.
- **Schema_Limpo**: Conjunto exato de campos definidos na seção de requisitos para `allMarkerData`, sem campos de métricas obsoletos.
- **Web_Lead**: Registro com `status = "New"` e `leadSource = "Website Pardot Form"`, tratado separadamente do fluxo operacional.
- **origin_hex**: Identificador H3 do hexágono de origem calculado a partir de `lat`/`lon` de cada parceiro.
- **bucket_ade**: Campo calculado no frontend pelo `_aggregateOptimizationData` a partir do `optimization_data.geojson`, distinto do campo `bucket` gerado pelo backend.
- **optimization**: Objeto `{radius_suggestion, cap_suggestion}` injetado no frontend a partir do `optimization_data.geojson`, não do `dados_mapa.json`.
- **consolidate_stores**: Método de `DataProcessor` que consolida as abas Active, Launches, WebLeads e Jurisdictions em um único DataFrame. Será migrado para dentro de `load_partners.py`.
- **Fases_3_4_5**: Módulos `phase3_partner_fit.py`, `phase4_webleads.py` e `phase5_reports.py` que consomem `PartnerData` e não devem ter sua interface alterada.

## Requirements

### Requirement 1: Pipeline Unificado — Leitura Direta do Excel

**User Story:** Como desenvolvedor do ATLAS, quero que `load_partners.py` leia os dados diretamente do Excel, para que o JSON intermediário `dados_mapa.json` deixe de ser uma dependência interna do backend.

#### Acceptance Criteria

1. WHEN `load_partners` é invocado sem `partners_path` explícito, THE `load_partners` SHALL ler os dados de parceiros diretamente do arquivo `terra.xlsm` via `ExcelHandler`, sem depender de `dados_mapa.json` como entrada.
2. THE `load_partners` SHALL invocar `consolidate_stores` internamente para consolidar as abas `Active`, `Launches`, `WebLeads`, `Delivery Stations` e `Jurisdictions` antes de construir o `PartnerData`.
3. WHEN `consolidate_stores` é executado dentro de `load_partners`, THE `load_partners` SHALL produzir um `PartnerData` com as mesmas colunas e semântica que o pipeline anterior produzia via JSON intermediário.
4. THE `ExcelHandler` SHALL continuar sendo utilizado sem modificações em sua interface pública.
5. IF o arquivo `terra.xlsm` não for encontrado no caminho configurado, THEN THE `load_partners` SHALL lançar `FileNotFoundError` com mensagem descritiva indicando o caminho esperado.

---

### Requirement 2: Remoção dos Métodos Obsoletos de DataProcessor

**User Story:** Como desenvolvedor do ATLAS, quero remover os métodos não utilizados de `DataProcessor`, para que o código não contenha lógica morta que aumenta a complexidade de manutenção.

#### Acceptance Criteria

1. THE `DataProcessor` SHALL remover os métodos `calculate_historical_metrics`, `calculate_perfect_mile_metrics`, `calculate_overlaps` e `enrich_with_overlaps`.
2. THE `DataProcessor` SHALL manter o método `consolidate_stores` com sua assinatura e comportamento atuais.
3. WHEN `main.py` é executado após a refatoração, THE `main.py` SHALL não importar nem invocar nenhum dos métodos removidos de `DataProcessor`.
4. THE `data_processing/json_generator.py` SHALL ser removido do projeto, pois sua responsabilidade é absorvida pela serialização direta no novo pipeline.
5. IF qualquer módulo fora do escopo desta refatoração importar os métodos removidos, THEN THE `Pipeline` SHALL falhar com `ImportError` em tempo de importação, tornando a dependência explícita.

---

### Requirement 3: Schema Limpo do JSON de Saída

**User Story:** Como desenvolvedor do ATLAS, quero que `dados_mapa.json` contenha apenas os campos que o frontend efetivamente consome, para que o arquivo seja menor e o contrato entre backend e frontend seja explícito.

#### Acceptance Criteria

1. THE `Pipeline` SHALL gerar `dados_mapa.json` com exatamente os seguintes campos em cada objeto de `allMarkerData`: `salesforce_id`, `store_id`, `name`, `status`, `lat`, `lon`, `zip_code`, `city`, `state`, `delivery_station`, `supply_run`, `radius`, `capacity`, `bucket`, `jurisdiction_type`, `hub_delivey_initiatives`, `HCP_rate_card`, `HCP_host_partner`, `launch_date`, `exited_date`, `telefone`, `owner_id`, `decision_status`, `lead_source`, `tooltip`.
2. THE `Pipeline` SHALL não incluir os campos `ADV`, `eligible_packages`, `partner_capacity`, `main_store_data`, `overlap_data`, `popup` e `sorte_code` em nenhum objeto de `allMarkerData`.
3. WHEN um campo string do Schema_Limpo não possui valor no Excel, THE `Pipeline` SHALL serializar o campo como `null` (não como `NaN`, `"nan"` ou `"None"`).
4. WHEN um campo numérico (`lat`, `lon`, `radius`, `capacity`) não possui valor no Excel, THE `Pipeline` SHALL serializar o campo como `null`.
5. THE `Pipeline` SHALL serializar o campo `exited_date` em snake_case (não `exitedDate`), alinhando o nome com a convenção dos demais campos do schema.
6. THE `Pipeline` SHALL serializar o campo `lead_source` em snake_case (não `leadSource`), alinhando o nome com a convenção dos demais campos do schema.
7. THE `Pipeline` SHALL manter os campos `period` e `deliveryStations` na raiz do JSON com a mesma estrutura atual.

---

### Requirement 4: Separação Correta de Web Leads

**User Story:** Como desenvolvedor do ATLAS, quero que os web leads continuem sendo separados corretamente do fluxo operacional após a refatoração, para que as Fases 4 e 5 recebam os dados corretos.

#### Acceptance Criteria

1. WHEN `load_partners` processa os registros, THE `load_partners` SHALL identificar como Web_Lead todo registro com `status = "New"` e `lead_source = "Website Pardot Form"`.
2. THE `load_partners` SHALL colocar todos os Web_Leads em `PartnerData.web_leads_df` e nenhum Web_Lead em `PartnerData.partners_df`.
3. WHEN um registro tem `status = "New"` mas `lead_source` diferente de `"Website Pardot Form"`, THE `load_partners` SHALL tratar o registro como parceiro operacional em `partners_df`.
4. THE `PartnerData.web_leads_df` SHALL conter a coluna `zip_clean` com o CEP normalizado (apenas dígitos, 8 caracteres com zero à esquerda) para uso na Fase 4.

---

### Requirement 5: Compatibilidade das Fases 3, 4 e 5

**User Story:** Como desenvolvedor do ATLAS, quero garantir que as Fases 3, 4 e 5 continuem funcionando sem alterações após a refatoração do pipeline, para que o sistema de otimização não seja interrompido.

#### Acceptance Criteria

1. THE `PartnerData` SHALL expor as propriedades `partners_df`, `web_leads_df`, `jurisdictions` e `no_coords_prospects_df` com os mesmos tipos e semântica que antes da refatoração.
2. THE `PartnerData.partners_df` SHALL conter as colunas `station_code`, `partner_name`, `lat`, `lon`, `status`, `salesforce_id`, `store_id`, `origin_hex`, `bucket`, `decision_status`, `exited_date` e `zip_code`.
3. WHEN `load_partners` processa parceiros com `lat` e `lon` válidos, THE `load_partners` SHALL calcular `origin_hex` usando H3 na resolução definida em `Config.H3_RES`.
4. THE `row_to_partner_metrics` SHALL continuar mapeando corretamente as colunas de `partners_df` para `PartnerMetrics`, incluindo o campo `exited_date` (renomeado de `exitedDate`).
5. THE `orchestrator.py` SHALL invocar `load_partners` sem passar `partners_path`, fazendo com que o módulo leia diretamente do Excel.
6. IF `load_partners` é invocado com `partners_path` explícito apontando para um JSON existente, THEN THE `load_partners` SHALL continuar suportando leitura via JSON para compatibilidade com testes e execuções manuais.

---

### Requirement 6: Ajuste do Frontend para o Novo Schema

**User Story:** Como desenvolvedor do ATLAS, quero que o frontend consuma o novo schema do `dados_mapa.json` sem erros, para que o mapa e os filtros continuem funcionando corretamente.

#### Acceptance Criteria

1. THE `Partner` (classe JavaScript) SHALL mapear o campo `exited_date` (snake_case) do JSON para a propriedade `exited_date` do objeto, removendo a referência ao campo `exitedDate` (camelCase).
2. THE `Partner` (classe JavaScript) SHALL mapear o campo `lead_source` (snake_case) do JSON para a propriedade `lead_source` do objeto, removendo a referência ao campo `leadSource` (camelCase).
3. WHEN `new Partner(raw)` é construído com um objeto contendo todos os campos do Schema_Limpo, THE `Partner` SHALL não ter nenhuma propriedade com valor `undefined`.
4. THE `data-manager.js` SHALL continuar injetando `bucket_ade` nos parceiros via `_aggregateOptimizationData` a partir do `optimization_data.geojson`, sem depender do campo `bucket` do JSON para popular filtros de carteira.
5. THE `data-manager.js` SHALL continuar injetando `decision`, `reason` e `optimization` nos parceiros via `_aggregateOptimizationData`, sem depender desses campos no `dados_mapa.json`.
6. THE `ui-manager.js` SHALL continuar gerando popups via `getPopupContent`, sem depender do campo `popup` do JSON.
7. WHERE o campo `popup` era lido do JSON em qualquer módulo frontend, THE `Frontend` SHALL substituir a referência por chamada a `getPopupContent(partner)`.
8. THE `ATLAS.html` SHALL remover a função `toggleMenu` e o elemento `#menuOptions` associado, pois o menu não é mais utilizado.

---

### Requirement 7: Integridade dos Dados — Sem NaN/None em Campos String

**User Story:** Como desenvolvedor do ATLAS, quero que nenhum campo string do JSON contenha valores `NaN` ou `None`, para que o frontend não exiba "nan" ou "null" em popups e tooltips.

#### Acceptance Criteria

1. THE `Pipeline` SHALL converter todo valor `NaN`, `NaT` ou `None` em campos string para `null` (JSON null) antes de serializar.
2. THE `Pipeline` SHALL converter todo valor `NaN` ou `None` em campos numéricos para `null` (JSON null) antes de serializar.
3. WHEN o campo `telefone` está presente e não é nulo, THE `Pipeline` SHALL normalizar o número removendo os caracteres `(`, `)`, ` `, `-` e `+`.
4. THE `Pipeline` SHALL garantir que o campo `tooltip` seja sempre uma string não-nula, usando o formato `"ID: {store_id} | Name: {name} | HUB Delivery Initiatives: {hub_delivey_initiatives}"`, substituindo valores ausentes por string vazia.

---

### Requirement 8: Testes de Propriedade do Pipeline

**User Story:** Como desenvolvedor do ATLAS, quero testes de propriedade que verifiquem as invariantes do pipeline refatorado, para que regressões sejam detectadas automaticamente.

#### Acceptance Criteria

1. THE `Test_Suite` SHALL incluir um teste de propriedade que verifique que, para qualquer conjunto de registros gerado pelo pipeline, cada objeto em `allMarkerData` contém exatamente os campos do Schema_Limpo (nem mais, nem menos).
2. THE `Test_Suite` SHALL incluir um teste de propriedade que verifique que, para qualquer parceiro com `lat` e `lon` válidos em `partners_df`, o campo `origin_hex` é uma string H3 válida na resolução `Config.H3_RES`.
3. THE `Test_Suite` SHALL incluir um teste de propriedade que verifique que, para qualquer conjunto de registros com mistura de Web_Leads e parceiros operacionais, nenhum Web_Lead aparece em `partners_df` e nenhum parceiro operacional aparece em `web_leads_df`.
4. THE `Test_Suite` SHALL incluir um teste de propriedade que verifique que, para qualquer objeto `raw` com os campos do Schema_Limpo, `new Partner(raw)` não produz nenhuma propriedade com valor `undefined`.
5. THE `Test_Suite` SHALL incluir um teste de propriedade que verifique que, para qualquer lista de registros gerada pelo pipeline, nenhum campo string do Schema_Limpo contém os valores `"nan"`, `"None"` ou `"NaN"`.
6. THE `Test_Suite` SHALL incluir um teste de round-trip que verifique que serializar um `Partner` para o formato do Schema_Limpo e desserializar via `new Partner(raw)` produz um objeto com os mesmos valores nos campos chave (`salesforce_id`, `lat`, `lon`, `status`).
