# Requirements Document

## Introduction

O sistema de Geointeligência para Expansão Logística é um módulo do projeto Atlas que classifica automaticamente territórios geográficos (conjuntos de hexágonos H3 resolução 9) quanto à sua morfologia urbana e perfil socioeconômico, estima o potencial de parceiros logísticos por região, compara com a capacidade atual e identifica gaps de cobertura. O objetivo é substituir a análise baseada exclusivamente em volume de pacotes por uma visão multidimensional que integra dados de CNPJ (Receita Federal), OpenStreetMap, IBGE e dados internos do Atlas, gerando insights acionáveis para expansão territorial e definindo as melhores áreas para atuação dado um percentual esperado de participação no volume total de pacotes por base.

---

## Glossary

- **Territory**: Conjunto de hexágonos H3 resolução 9 que forma uma unidade de análise geográfica dentro de uma base de entrega (delivery station). Equivale ao conceito de `bucket` já existente no Atlas.
- **H3_Cell**: Hexágono individual da grade H3 (resolução 9, ~0.1 km²) identificado por um `h3_id` único.
- **GeoIntelligence_Pipeline**: Pipeline Python responsável por ingerir, enriquecer, processar e classificar territórios com dados multidimensionais.
- **Feature_Engineer**: Módulo do pipeline que calcula features por H3_Cell a partir das fontes de dados integradas.
- **Classifier**: Modelo de IA (HDBSCAN para clusterização não supervisionada; Random Forest/XGBoost para classificação supervisionada) que atribui um `region_type` a cada H3_Cell.
- **Potential_Calculator**: Módulo que computa o `potential_score` de um território com base nas features econômicas, urbanas e socioeconômicas.
- **Territory_Output**: Registro de saída por território contendo: `territory_id`, `h3_ids`, `region_type`, `potential_score`, `current_partners`, `gap`, `model_confidence`.
- **GeoIntelligence_API**: Endpoint FastAPI/Flask no backend Python que expõe os resultados do pipeline para o frontend Atlas.
- **GeoIntelligence_Map**: Componente React integrado ao MapView existente do Atlas que renderiza camadas de geointeligência via react-leaflet.
- **GeoIntelligence_Dashboard**: Painel de análise no Atlas que exibe KPIs, rankings de territórios e insights de expansão.
- **OSM_Enricher**: Módulo que consulta o OpenStreetMap (via osmnx) para extrair features urbanas por H3_Cell.
- **IBGE_Enricher**: Módulo que integra dados de setores censitários do IBGE (renda média, densidade populacional) por H3_Cell.
- **CNPJ_Enricher**: Módulo que processa a base de CNPJs da Receita Federal para calcular features econômicas por H3_Cell.
- **Region_Type**: Classificação morfológica de uma região. Valores: `favela_comunidade`, `residencial_baixa_renda`, `residencial_media_renda`, `residencial_alta_renda`, `comercial`, `industrial`, `rural`, `alto_padrao`.
- **Potential_Score**: Valor numérico normalizado [0–100] que representa a capacidade estimada de absorção de parceiros logísticos em um território.
- **Gap**: Diferença entre `potential_score` e a capacidade atual de parceiros (`current_partners`). Valores positivos indicam oportunidade de expansão.
- **Expansion_Target**: Percentual esperado de participação no volume total de pacotes por base, usado para priorizar territórios de expansão.
- **Model_Confidence**: Score [0–1] que indica a confiança do modelo de classificação para um dado território.
- **Delivery_Station**: Base de entrega logística já existente no Atlas (ex: DSP2, DRJ3).
- **BDM**: Business Development Manager. Gestor responsável por um conjunto de Delivery_Stations, representando o nível hierárquico acima da DS no scorecard de potencial.
- **Ideal_Supply**: Localização geográfica ótima (lat/lng) calculada pelo CP_Model_Optimizer para posicionamento de um parceiro em uma área, representando o ponto de máxima eficiência de cobertura.
- **CP_Model_Optimizer**: Módulo de otimização baseado em OR-Tools CP-SAT (Constraint Programming) que determina, para cada Delivery_Station, as áreas de atuação, o número de parceiros necessários, as localizações Ideal_Supply e os perfis de parceiro (raio de atuação e capacidade em volume de pacotes).
- **Setup_Mode**: Modo de execução do pipeline (`--mode setup`) que substitui a lógica anterior de geração de territórios e slots fixos, passando a usar o CP_Model_Optimizer para gerar uma configuração otimizada orientada ao Expansion_Target.

---

## Requirements

### Requirement 1: Pipeline de Ingestão e Enriquecimento de Dados

**User Story:** Como analista de expansão, quero que o sistema colete e integre automaticamente dados de múltiplas fontes (CNPJ, OSM, IBGE) por hexágono H3, para que eu tenha uma base de dados multidimensional atualizada para análise territorial.

#### Acceptance Criteria

1. THE GeoIntelligence_Pipeline SHALL processar dados de pacotes existentes no Atlas e mapear cada registro para o H3_Cell de resolução 9 correspondente usando as coordenadas geográficas (lat/lng) disponíveis.
2. WHEN o CNPJ_Enricher recebe uma lista de H3_Cells, THE CNPJ_Enricher SHALL calcular para cada célula: densidade de empresas por km², diversidade de CNAEs (índice de Shannon), e densidade de negócios-alvo (CNAEs logísticos relevantes).
3. WHEN o OSM_Enricher recebe uma lista de H3_Cells, THE OSM_Enricher SHALL extrair via osmnx: densidade de construções, proporção de uso do solo por categoria (residencial, comercial, industrial, verde), densidade de pontos de interesse (POIs) e índice de conectividade viária.
4. WHEN o IBGE_Enricher recebe uma lista de H3_Cells, THE IBGE_Enricher SHALL associar dados de setores censitários correspondentes, retornando renda média e densidade populacional por célula.
5. IF uma fonte de dados externa (OSM ou IBGE) estiver indisponível durante a ingestão, THEN THE GeoIntelligence_Pipeline SHALL registrar o erro, preencher as features afetadas com valor nulo e continuar o processamento das demais fontes.
6. THE GeoIntelligence_Pipeline SHALL persistir os dados enriquecidos por H3_Cell em formato Parquet ou GeoJSON para reuso nas fases subsequentes sem necessidade de re-ingestão.
7. WHEN o pipeline é executado para uma Delivery_Station, THE GeoIntelligence_Pipeline SHALL processar apenas os H3_Cells pertencentes aos territórios daquela base, reutilizando o `hex_to_territory` já gerado pelo sistema de territórios existente do Atlas.

---

### Requirement 2: Feature Engineering por H3_Cell

**User Story:** Como cientista de dados, quero que o sistema calcule automaticamente um conjunto padronizado de features por hexágono H3, para que os modelos de IA tenham inputs consistentes e reproduzíveis.

#### Acceptance Criteria

1. THE Feature_Engineer SHALL calcular as seguintes features econômicas por H3_Cell: `company_density` (empresas/km²), `cnae_diversity_index` (índice de Shannon sobre CNAEs), `target_business_density` (empresas de CNAEs logísticos-alvo/km²).
2. THE Feature_Engineer SHALL calcular as seguintes features urbanas por H3_Cell: `building_density` (construções/km²), `avg_building_size_m2` (tamanho médio de construções em m²), `landuse_residential_ratio`, `landuse_commercial_ratio`, `poi_density` (POIs/km²), `road_connectivity_index`.
3. THE Feature_Engineer SHALL calcular as seguintes features socioeconômicas por H3_Cell: `avg_income` (renda média em R$), `population_density` (habitantes/km²).
4. THE Feature_Engineer SHALL calcular as seguintes features indiretas por H3_Cell: `bars_restaurants_density`, `churches_density`, `schools_density`, `dealerships_density`, `petshops_density`.
5. THE Feature_Engineer SHALL calcular as seguintes features avançadas por H3_Cell: `landuse_entropy` (entropia de Shannon sobre categorias de uso do solo), `road_centrality_index` (centralidade de betweenness normalizada do grafo viário), `local_clustering_coefficient`.
6. WHEN uma feature não puder ser calculada por ausência de dados para uma H3_Cell específica, THE Feature_Engineer SHALL preencher o valor com a mediana da feature calculada para as células vizinhas de primeiro anel H3.
7. THE Feature_Engineer SHALL normalizar todas as features numéricas para o intervalo [0, 1] usando min-max scaling por Delivery_Station antes de alimentar os modelos, preservando os parâmetros de normalização para uso na inferência.

---

### Requirement 3: Classificação de Morfologia Urbana

**User Story:** Como analista de expansão, quero que o sistema classifique automaticamente cada território quanto ao seu tipo de região urbana, para que eu possa entender o perfil de cada área e tomar decisões de expansão mais informadas.

#### Acceptance Criteria

1. THE Classifier SHALL executar clusterização não supervisionada usando HDBSCAN sobre o vetor de features de cada H3_Cell, agrupando células com perfis similares em clusters morfológicos.
2. WHEN o HDBSCAN não convergir ou produzir menos de 3 clusters para uma Delivery_Station, THE Classifier SHALL executar KMeans com k=6 como algoritmo de fallback e registrar o evento no log de execução.
3. THE Classifier SHALL atribuir um Region_Type a cada H3_Cell com base no cluster ao qual pertence, usando um mapeamento configurável entre cluster_id e Region_Type.
4. WHEN dados rotulados de territórios estiverem disponíveis (mínimo 50 amostras por classe), THE Classifier SHALL treinar um modelo supervisionado (Random Forest como padrão, XGBoost como alternativa configurável) para refinar a classificação.
5. THE Classifier SHALL calcular e persistir o Model_Confidence para cada H3_Cell classificada, representando a probabilidade da classe predita no modelo supervisionado ou a distância normalizada ao centróide do cluster no modelo não supervisionado.
6. WHEN o Model_Confidence de uma H3_Cell for inferior a 0.5, THE Classifier SHALL marcar a célula com flag `low_confidence = true` no Territory_Output.
7. THE Classifier SHALL persistir os modelos treinados em formato joblib (scikit-learn) ou equivalente, permitindo inferência incremental sem re-treinamento completo.

---

### Requirement 4: Cálculo de Potencial e Gap de Cobertura (Scorecard Multinível)

**User Story:** Como gestor de expansão, quero que o sistema calcule o potencial de parceiros logísticos em três níveis hierárquicos (Território, DS e BDM) e compare com a capacidade atual, para que eu possa identificar onde há maior oportunidade de crescimento em qualquer nível de granularidade.

#### Acceptance Criteria

1. THE Potential_Calculator SHALL calcular o `potential_score` de cada Territory usando a fórmula: `f(target_business_density, avg_income, population_density, region_type_weight, road_connectivity_index, commercial_activity_index)`, onde os pesos de cada componente são configuráveis via arquivo de configuração.
2. THE Potential_Calculator SHALL normalizar o `potential_score` de nível Territory para o intervalo [0–100] por Delivery_Station, onde 100 representa o território de maior favorabilidade para ter um parceiro naquela base.
3. THE Potential_Calculator SHALL calcular o `potential_score` de nível Delivery_Station como a agregação ponderada dos `potential_score` dos territórios pertencentes àquela base, usando o volume de pacotes de cada território como peso.
4. THE Potential_Calculator SHALL calcular o `potential_score` de nível BDM como a agregação ponderada dos `potential_score` das Delivery_Stations sob responsabilidade do BDM, usando o volume total de pacotes de cada DS como peso.
5. THE Potential_Calculator SHALL normalizar os `potential_score` de nível DS e BDM para o intervalo [0–100] dentro de seus respectivos grupos, garantindo comparabilidade entre DSs e entre BDMs.
6. THE Potential_Calculator SHALL calcular o `gap` de cada Territory como: `gap = potential_score - (current_partners / ideal_slots * 100)`, onde `current_partners` e `ideal_slots` são obtidos do sistema de territórios existente do Atlas.
7. WHEN o `gap` de um Territory for maior que 20 pontos, THE Potential_Calculator SHALL classificar o território como `high_opportunity` no Territory_Output.
8. THE Potential_Calculator SHALL gerar rankings separados por `gap` decrescente para cada nível hierárquico: ranking de territórios por DS, ranking de DSs por BDM, e ranking global de BDMs.
9. WHEN um percentual de Expansion_Target for fornecido como parâmetro, THE Potential_Calculator SHALL selecionar o conjunto mínimo de territórios de maior `gap` cuja soma de `potential_score` atinja o percentual alvo do volume total de pacotes da base.

---

### Requirement 5: Geração de Territory_Output

**User Story:** Como desenvolvedor de integração, quero que o pipeline gere um output estruturado e padronizado por território, para que o frontend Atlas possa consumir os dados de geointeligência de forma consistente.

#### Acceptance Criteria

1. THE GeoIntelligence_Pipeline SHALL gerar um Territory_Output para cada Territory processado, contendo obrigatoriamente: `territory_id`, `h3_ids` (lista de H3_Cells), `region_type`, `potential_score`, `current_partners`, `ideal_slots`, `gap`, `model_confidence`, `low_confidence` (flag booleana).
2. THE GeoIntelligence_Pipeline SHALL serializar os Territory_Outputs em formato GeoJSON, onde cada feature representa um Territory com sua geometria (união dos polígonos H3) e as métricas como propriedades.
3. THE GeoIntelligence_Pipeline SHALL serializar os Territory_Outputs em formato JSON plano (sem geometria) para consumo pela GeoIntelligence_API.
4. WHEN o pipeline for executado, THE GeoIntelligence_Pipeline SHALL gerar um arquivo de metadados de execução contendo: timestamp, Delivery_Station processada, número de territórios, distribuição de Region_Types, e métricas de qualidade do modelo (silhouette score para clusterização, accuracy/F1 para classificação supervisionada).
5. THE GeoIntelligence_Pipeline SHALL manter compatibilidade com o schema de `territories.geojson` e `territories_index.json` já existentes no Atlas, adicionando as novas propriedades de geointeligência sem remover campos existentes.

---

### Requirement 6: API de Geointeligência

**User Story:** Como desenvolvedor frontend, quero uma API REST que exponha os dados de geointeligência por território, para que o Atlas possa exibir as análises no mapa e no dashboard sem acesso direto ao filesystem.

#### Acceptance Criteria

1. THE GeoIntelligence_API SHALL expor um endpoint `GET /geo-intelligence/{station_code}/territories` que retorna a lista de Territory_Outputs em formato JSON para uma Delivery_Station.
2. THE GeoIntelligence_API SHALL expor um endpoint `GET /geo-intelligence/{station_code}/territories/{territory_id}` que retorna o Territory_Output detalhado de um território específico, incluindo o breakdown de features por H3_Cell.
3. THE GeoIntelligence_API SHALL expor um endpoint `GET /geo-intelligence/{station_code}/geojson` que retorna o GeoJSON completo com geometrias e propriedades de todos os territórios da base.
4. THE GeoIntelligence_API SHALL expor um endpoint `POST /geo-intelligence/{station_code}/expansion-targets` que recebe um `expansion_target_pct` (float, 0–100) e retorna a lista priorizada de territórios recomendados para atingir o percentual alvo.
5. WHEN uma requisição for feita para uma Delivery_Station sem dados de geointeligência processados, THE GeoIntelligence_API SHALL retornar HTTP 404 com mensagem descritiva indicando que o pipeline precisa ser executado para aquela base.
6. THE GeoIntelligence_API SHALL suportar filtro por `region_type` e `min_gap` nos endpoints de listagem via query parameters.
7. THE GeoIntelligence_API SHALL retornar respostas em menos de 2 segundos para bases com até 500 territórios, utilizando cache em memória dos dados processados.

---

### Requirement 7: Visualização no Atlas (GeoIntelligence_Map)

**User Story:** Como analista de expansão, quero visualizar os territórios classificados e seus scores de potencial no mapa do Atlas, para que eu possa explorar geograficamente as oportunidades de expansão.

#### Acceptance Criteria

1. THE GeoIntelligence_Map SHALL renderizar os territórios como polígonos coloridos sobre o mapa react-leaflet existente do Atlas, usando uma escala de cores configurável baseada no `potential_score` (gradiente de frio para quente).
2. THE GeoIntelligence_Map SHALL renderizar uma camada de heatmap baseada no `gap` dos territórios, sobreposta ao mapa base, usando o componente HeatmapLayer já existente no Atlas.
3. WHEN o usuário clicar em um território no mapa, THE GeoIntelligence_Map SHALL exibir um popup com: `territory_id`, `region_type`, `potential_score`, `current_partners`, `gap`, `model_confidence` e flag de `low_confidence`.
4. THE GeoIntelligence_Map SHALL permitir filtrar a visualização por `region_type` via seletor no painel de controle, ocultando territórios dos tipos não selecionados.
5. THE GeoIntelligence_Map SHALL destacar visualmente (borda mais espessa e cor diferenciada) os territórios classificados como `high_opportunity`.
6. THE GeoIntelligence_Map SHALL exibir uma legenda de cores correlacionando a escala de `potential_score` com as cores dos polígonos, integrada ao componente MapLegend existente do Atlas.
7. WHILE a camada de geointeligência estiver carregando dados da GeoIntelligence_API, THE GeoIntelligence_Map SHALL exibir um indicador de carregamento usando o componente LoadingIndicator existente do Atlas.

---

### Requirement 8: Dashboard de Geointeligência (Substituição do Dashboard Atual)

**User Story:** Como gestor de expansão, quero que o dashboard principal do Atlas seja reformulado para exibir a visão de geointeligência como visão principal, com KPIs e rankings multinível, para que eu possa tomar decisões estratégicas de expansão com base em dados consolidados sem precisar alternar entre painéis.

#### Acceptance Criteria

1. THE GeoIntelligence_Dashboard SHALL substituir o dashboard atual do Atlas como visão principal do frontend, reformulando a interface para exibir a visão de geointeligência por padrão ao acessar o sistema.
2. THE GeoIntelligence_Dashboard SHALL exibir os seguintes KPIs por Delivery_Station: total de territórios analisados, número de territórios `high_opportunity`, gap médio, potencial total da base e percentual de cobertura atual.
3. THE GeoIntelligence_Dashboard SHALL exibir KPIs agregados por BDM: número de DSs sob responsabilidade, `potential_score` médio das DSs, número total de territórios `high_opportunity` e gap médio consolidado.
4. THE GeoIntelligence_Dashboard SHALL exibir uma tabela ranqueada de territórios ordenada por `gap` decrescente, com colunas: `territory_id`, `region_type`, `potential_score`, `current_partners`, `gap`, `model_confidence`.
5. THE GeoIntelligence_Dashboard SHALL exibir um ranking de Delivery_Stations por `potential_score` de nível DS, permitindo comparação entre bases dentro do mesmo BDM.
6. THE GeoIntelligence_Dashboard SHALL exibir um ranking de BDMs por `potential_score` de nível BDM, permitindo comparação entre gestores.
7. THE GeoIntelligence_Dashboard SHALL exibir a distribuição de Region_Types da base em um gráfico de barras ou pizza, mostrando a contagem e percentual de territórios por tipo.
8. THE GeoIntelligence_Dashboard SHALL permitir ao usuário inserir um `expansion_target_pct` e exibir a lista de territórios recomendados para atingir o alvo, com o potencial acumulado estimado.
9. WHEN o usuário selecionar um território na tabela do GeoIntelligence_Dashboard, THE GeoIntelligence_Map SHALL centralizar e destacar o território selecionado no mapa.
10. THE GeoIntelligence_Dashboard SHALL permitir exportar a tabela de territórios ranqueados em formato CSV, incluindo todas as colunas visíveis.

---

### Requirement 9: Qualidade e Rastreabilidade do Modelo

**User Story:** Como cientista de dados, quero que o sistema registre métricas de qualidade e rastreabilidade de cada execução do pipeline, para que eu possa monitorar a evolução dos modelos e auditar os resultados.

#### Acceptance Criteria

1. THE GeoIntelligence_Pipeline SHALL registrar em log estruturado (JSON) cada execução, incluindo: timestamp de início e fim, Delivery_Station, número de H3_Cells processadas, features calculadas com sucesso vs. nulas, algoritmo de clusterização utilizado e métricas de qualidade.
2. WHEN o modelo supervisionado for treinado, THE Classifier SHALL calcular e registrar: accuracy, precision, recall e F1-score por classe no arquivo de metadados de execução.
3. WHEN o modelo de clusterização for executado, THE Classifier SHALL calcular e registrar o silhouette score médio no arquivo de metadados de execução.
4. THE GeoIntelligence_Pipeline SHALL versionar os artefatos de modelo (arquivos joblib) com timestamp de treinamento, mantendo os 3 últimos modelos por Delivery_Station para rollback.
5. IF o silhouette score de uma execução for inferior a 0.2, THEN THE GeoIntelligence_Pipeline SHALL emitir um alerta no log indicando baixa qualidade de clusterização e recomendar revisão das features ou dos dados de entrada.

---

### Requirement 10: Integração com o Sistema de Territórios Existente

**User Story:** Como desenvolvedor do Atlas, quero que o módulo de geointeligência se integre ao sistema de territórios e parceiros já existente sem quebrar funcionalidades atuais, para que o Atlas continue operando normalmente enquanto o novo módulo é adicionado.

#### Acceptance Criteria

1. THE GeoIntelligence_Pipeline SHALL ler os arquivos `territories.geojson` e `territories_index.json` gerados pelo pipeline existente do Atlas como fonte primária de definição de territórios, sem modificar esses arquivos.
2. THE GeoIntelligence_Pipeline SHALL ler os dados de parceiros ativos por território a partir do output existente do Atlas (`dados_mapa.json` ou equivalente) para calcular o `current_partners` de cada Territory.
3. THE GeoIntelligence_Map SHALL ser implementado como uma nova camada opcional no MapView existente, ativável/desativável via toggle no StyleTab ou em um novo tab dedicado no ControlPanel, sem alterar o comportamento das camadas existentes.
4. THE GeoIntelligence_Dashboard SHALL substituir o dashboard atual do Atlas, migrando os KPIs e funcionalidades existentes para a nova interface de geointeligência, de forma que nenhuma informação anteriormente disponível seja perdida.
5. WHEN o módulo de geointeligência não tiver dados processados para uma Delivery_Station, THE GeoIntelligence_Map SHALL ocultar automaticamente a camada de geointeligência para aquela base, sem exibir erros ao usuário.

---

### Requirement 11: Setup Inteligente com Otimização por CP-Model (--mode setup)

**User Story:** Como gestor de expansão, quero que o modo de setup do pipeline use inteligência artificial e otimização por programação por restrições para determinar automaticamente onde atuar, quantos parceiros são necessários e onde posicioná-los, para que a configuração de cada base seja orientada a dados e maximize o atingimento do Expansion_Target.

#### Acceptance Criteria

1. WHEN o GeoIntelligence_Pipeline for executado com `--mode setup`, THE CP_Model_Optimizer SHALL substituir a lógica anterior de geração de territórios e slots fixos, executando um modelo de otimização baseado em OR-Tools CP-SAT para determinar a configuração ótima da Delivery_Station.
2. THE CP_Model_Optimizer SHALL determinar, para cada Delivery_Station, quais áreas (conjuntos de H3_Cells) dentro da jurisdição da DS serão ativadas para atuação, com base nos `potential_score` calculados pelo Potential_Calculator e no Expansion_Target fornecido.
3. THE CP_Model_Optimizer SHALL determinar o número de parceiros necessários por área ativada, respeitando as restrições de capacidade mínima e máxima por parceiro configuráveis via arquivo de configuração.
4. THE CP_Model_Optimizer SHALL calcular o Ideal_Supply de cada parceiro planejado, representando a localização geográfica ótima (lat/lng) dentro da área que maximiza a cobertura dos H3_Cells atribuídos, usando o centróide ponderado pelo `potential_score` das células.
5. THE CP_Model_Optimizer SHALL determinar o perfil de cada parceiro planejado, especificando: raio de atuação em km e capacidade em volume de pacotes por dia, derivados das características da área e do volume esperado com base no Expansion_Target.
6. WHEN o CP_Model_Optimizer concluir a otimização, THE GeoIntelligence_Pipeline SHALL persistir o resultado como um `setup_output` contendo: lista de áreas ativadas, número de parceiros por área, Ideal_Supply de cada parceiro e perfil (raio, capacidade).
7. THE CP_Model_Optimizer SHALL garantir que a soma da capacidade dos parceiros planejados seja suficiente para absorver o volume de pacotes correspondente ao Expansion_Target da Delivery_Station, respeitando uma tolerância configurável de ±10%.
8. IF o CP_Model_Optimizer não encontrar solução viável dentro do tempo limite configurável (padrão: 300 segundos), THEN THE GeoIntelligence_Pipeline SHALL registrar o evento no log, retornar a melhor solução parcial encontrada e sinalizar o resultado como `suboptimal` no `setup_output`.
9. THE GeoIntelligence_Map SHALL renderizar os Ideal_Supply calculados pelo CP_Model_Optimizer como marcadores de posicionamento sugerido no mapa, diferenciados visualmente dos parceiros ativos existentes.
