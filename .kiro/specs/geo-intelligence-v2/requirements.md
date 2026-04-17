# Requirements Document — GeoIntelligence v2

## Introduction

Evolução do pipeline GeoIntelligence para um sistema de expansão logística orientado a dados reais de operação, com aprendizado por similaridade baseado no histórico de parceiros (ativos, exited e seus motivos de saída), pipeline multi-resolução H3 (res 8 para análise de área, res 9 para posicionamento de slots), e arquitetura limpa separando setup (territórios + slots) do daily (matching com parceiros reais).

O objetivo é construir o sistema mais preciso e escalável para decisão de expansão de redes hub delivery, capaz de operar em qualquer mercado global sem dependência de rótulos manuais, aprendendo continuamente com a própria operação.

---

## Glossary

- **Partner_Profile**: Vetor de features H3 (res 8) do hexágono onde um parceiro está localizado, enriquecido com dados de CNPJ, OSM, IBGE e volume histórico.
- **Success_Profile**: Média ponderada por tenure dos Partner_Profiles de parceiros Active com launch_date definida. Representa o "perfil ideal de área" aprendido da operação real.
- **Failure_Profile**: Média ponderada por tenure dos Partner_Profiles de parceiros Exited cuja saída foi causada por problema de área (não de parceiro). Representa o "perfil de área que não funciona".
- **Tenure**: Tempo em dias que um parceiro ficou no programa. Para Active: `today - launch_date`. Para Exited: `exited_date - launch_date`.
- **Exit_Reason_Class**: Classificação do motivo de saída em dois grupos — `area_signal` (volume insuficiente, acesso difícil, sobreposição) e `partner_signal` (falência, desistência, compliance, operacional). Apenas `area_signal` penaliza o score da área.
- **Similarity_Score**: Similaridade coseno entre o embedding UMAP de um hexágono e o Success_Profile, subtraída da similaridade com o Failure_Profile.
- **UMAP_Embedding**: Projeção de baixa dimensionalidade (2-3D) das features H3 gerada pelo algoritmo UMAP, preservando estrutura local para clustering e visualização.
- **Multi_Resolution_Pipeline**: Arquitetura que usa H3 resolução 8 para análise de perfil/morfologia e H3 resolução 9 para posicionamento preciso de slots via CP-SAT.
- **Delivery_Density_Threshold**: Volume mínimo de pacotes/dia em um hexágono res 8 para que ele seja elegível para análise. Filtro de viabilidade, não componente do score.
- **Institutional_Memory**: Conjunto de Partner_Profiles históricos (Active + Exited com motivo) que o modelo usa para aprender quais áreas funcionam e quais não funcionam, sem necessidade de rótulos manuais.

---

## Requirements

### Requirement 1: Ingestão Multi-Fonte com Parceiros Reais

**User Story:** Como gestor de expansão, quero que o setup carregue dados reais de parceiros ativos e exited (com tenure e motivo de saída) junto com dados de pacotes, IBGE, OSM e empresas, para que o modelo aprenda com a história real da operação.

#### Acceptance Criteria

1. WHEN o setup for executado, THE pipeline SHALL carregar parceiros via `load_partners()` e extrair para cada parceiro: `salesforce_id`, `status`, `lat`, `lon`, `launch_date`, `exited_date`, `decision_status`, `decision_reason_code`, `delivery_station`, `origin_hex` (res 8). O campo `decision_reason_code` é mapeado da coluna `Decision_Reason_Code__c` do Excel e representa o motivo de saída do parceiro, usado para classificar `exit_reason_class`.
2. THE pipeline SHALL calcular `tenure_days` para cada parceiro: `(today - launch_date).days` para Active, `(exited_date - launch_date).days` para Exited. Parceiros sem `launch_date` são excluídos do perfil de referência mas mantidos no matching.
3. THE pipeline SHALL classificar cada `exit_reason` em `area_signal` ou `partner_signal` usando um mapeamento configurável em `geo_config.py`. Apenas parceiros Exited com `area_signal` contribuem para o Failure_Profile.
4. THE pipeline SHALL mapear cada parceiro para o H3_Cell de resolução 8 correspondente usando `h3.latlng_to_cell(lat, lon, 8)`.
5. THE pipeline SHALL carregar dados de pacotes via `load_packages()` e agregar volume por H3_Cell resolução 8 para uso como threshold de viabilidade.
6. THE pipeline SHALL aplicar o `Delivery_Density_Threshold` configurável (padrão: 5 pacotes/dia em res 8) para filtrar hexágonos sem demanda mínima antes da análise de perfil.
7. IF `load_partners()` falhar ou retornar DataFrame vazio, THE pipeline SHALL continuar o setup sem perfil de referência, usando apenas clustering morfológico, e registrar aviso no log.

---

### Requirement 2: Feature Engineering Multi-Resolução

**User Story:** Como cientista de dados, quero que o feature engineering opere em resolução 8 para análise de área e preserve resolução 9 para o CP-SAT, para que cada fase use a granularidade adequada ao seu objetivo.

#### Acceptance Criteria

1. THE Feature_Engineer SHALL operar em H3 resolução 8 para todas as etapas de análise de perfil: enriquecimento, imputation, normalização, clustering e cálculo de similarity score.
2. THE Feature_Engineer SHALL incluir `delivery_density_r8` (pacotes/dia no hex res 8, normalizado) como feature de contexto, com peso configurável máximo de 0.10 no potential score para não dominar a seleção por volume histórico.
3. THE Feature_Engineer SHALL calcular features de vizinhança em resolução 8: `grid_disk(h3_id, 1)` cobre ~3 km de contexto, adequado para análise de bairro.
4. THE Feature_Engineer SHALL preservar os H3_Cells de resolução 9 dentro de cada hex res 8 para uso exclusivo pelo CP-SAT na Fase de Ideal Supply.
5. WHEN uma feature for nula em um hex res 8, THE Feature_Engineer SHALL imputar com a mediana dos vizinhos `grid_disk(h3_id, 1)` em res 8. Se todos os vizinhos também forem nulos, imputar com a mediana global da base.
6. THE Feature_Engineer SHALL normalizar features por base (min-max por Delivery_Station) e persistir os parâmetros de normalização para uso no daily e em inferências futuras.
7. THE Feature_Engineer SHALL calcular `commercial_activity_index = (landuse_commercial_ratio + target_business_density) / 2` como feature derivada.

---

### Requirement 3: Construção de Perfis de Referência (Institutional Memory)

**User Story:** Como gestor de expansão, quero que o sistema aprenda automaticamente o perfil de área que funciona e o que não funciona a partir do histórico real de parceiros, sem precisar rotular dados manualmente.

#### Acceptance Criteria

1. THE pipeline SHALL construir o Success_Profile como média ponderada dos Partner_Profiles de parceiros Active, usando `tenure_weight = log(1 + tenure_days)` como peso. Parceiros com tenure < 30 dias são excluídos.
2. THE pipeline SHALL construir o Failure_Profile como média ponderada dos Partner_Profiles de parceiros Exited com `exit_reason_class = area_signal`, usando `failure_weight = abs(area_penalty) * log(1 + tenure_days)` onde `area_penalty` é configurável por motivo de saída.
3. THE pipeline SHALL persistir Success_Profile e Failure_Profile como vetores numpy em arquivo `.npy` por Delivery_Station, versionados com timestamp, mantendo os 3 mais recentes.
4. WHEN menos de 3 parceiros Active com tenure >= 30 dias estiverem disponíveis para uma base, THE pipeline SHALL usar o Success_Profile global (agregado de todas as bases) como fallback e registrar aviso.
5. THE pipeline SHALL calcular `profile_coverage` = percentual de hexágonos da base que têm pelo menos 1 parceiro Active ou Exited no raio de `grid_disk(h3_id, 1)` em res 8. Bases com `profile_coverage < 10%` recebem flag `low_coverage_warning`.
6. THE pipeline SHALL registrar no log: número de parceiros Active usados, número de Exited por `exit_reason_class`, tenure médio, e `profile_coverage` por base.

---

### Requirement 4: UMAP + HDBSCAN com Âncoras Semânticas

**User Story:** Como cientista de dados, quero que o clustering use UMAP para redução dimensional antes do HDBSCAN, com âncoras semânticas opcionais, para que os clusters sejam mais interpretáveis e geograficamente coerentes.

#### Acceptance Criteria

1. THE Classifier SHALL executar UMAP com `n_components=2`, `n_neighbors=15`, `min_dist=0.1`, `random_state=42` sobre o vetor de features normalizadas de cada H3_Cell res 8, antes de aplicar HDBSCAN.
2. THE Classifier SHALL persistir o modelo UMAP treinado em formato joblib por Delivery_Station para uso em inferências incrementais sem re-treinamento.
3. THE Classifier SHALL executar HDBSCAN sobre o embedding UMAP com `min_cluster_size=max(5, n_cells // 20)`.
4. WHEN âncoras semânticas estiverem configuradas em `geo_config.py` (ex: `{"comercial": "hex_id_centro_comercial"}`), THE Classifier SHALL usar o cluster do hex âncora para nomear o RegionType correspondente, em vez do mapeamento por índice sequencial.
5. WHEN HDBSCAN produzir menos de 3 clusters, THE Classifier SHALL executar KMeans com k=6 sobre o embedding UMAP (não sobre as features brutas) como fallback.
6. THE Classifier SHALL calcular silhouette score sobre o embedding UMAP. Se < 0.2, emitir alerta e registrar flag `low_quality_clustering` nos metadados da execução.
7. THE Classifier SHALL gerar e persistir um scatter plot 2D do embedding UMAP colorido por cluster como artefato de validação visual por execução.

---

### Requirement 5: Similarity Score com Perfis de Referência

**User Story:** Como analista de expansão, quero que o potential score de cada hexágono reflita sua similaridade com áreas onde parceiros bem-sucedidos operam, para que a expansão seja guiada por evidência operacional real.

#### Acceptance Criteria

1. THE Potential_Calculator SHALL calcular `similarity_positive = cosine_similarity(cell_embedding_umap, success_profile_umap)` para cada H3_Cell res 8.
2. THE Potential_Calculator SHALL calcular `similarity_negative = cosine_similarity(cell_embedding_umap, failure_profile_umap)` para cada H3_Cell res 8. Se Failure_Profile não existir, `similarity_negative = 0`.
3. THE Potential_Calculator SHALL calcular `raw_score = similarity_positive - (failure_penalty_weight * similarity_negative)`, onde `failure_penalty_weight` é configurável (padrão: 0.5).
4. THE Potential_Calculator SHALL aplicar o `Delivery_Density_Threshold` como filtro binário: hexágonos abaixo do threshold recebem `potential_score = 0` independente do similarity score.
5. THE Potential_Calculator SHALL normalizar `raw_score` para [0, 100] por Delivery_Station.
6. THE Potential_Calculator SHALL calcular `gap = potential_score - (current_partners / ideal_slots * 100)` por território, onde `current_partners` e `ideal_slots` vêm do `territories_index.json`.
7. THE Potential_Calculator SHALL agregar scores de células res 8 para territórios usando média ponderada por `delivery_density_r8`.
8. WHEN um hexágono tiver histórico de parceiro Exited com `area_signal` e tenure < 180 dias (saiu rápido por problema de área), THE Potential_Calculator SHALL aplicar penalidade adicional configurável (padrão: -20 pontos) ao `potential_score` daquele hex.

---

### Requirement 6: Seleção de Áreas por Target de Volume

**User Story:** Como gestor de expansão, quero que o sistema selecione automaticamente o conjunto mínimo de territórios que atinge o target de volume, ordenados por gap decrescente, para que eu saiba exatamente onde atuar para atingir o objetivo.

#### Acceptance Criteria

1. THE Area_Selector SHALL ordenar territórios por `gap` decrescente e selecionar o conjunto mínimo cuja soma de volume de pacotes (res 8) atinja `target_pct%` do volume total da base.
2. THE Area_Selector SHALL retornar `SelectedTerritory[]` com: `territory_id`, `h3_ids_r8` (res 8 para análise), `h3_ids_r9` (res 9 para CP-SAT), `region_type`, `potential_score`, `gap`, `model_confidence`, `high_opportunity`.
3. WHEN `target_pct = 0`, THE Area_Selector SHALL retornar lista vazia. WHEN `target_pct = 100`, SHALL retornar todos os territórios com `gap > 0`.
4. THE Area_Selector SHALL calcular e retornar `coverage_summary`: percentual de volume coberto, número de territórios selecionados, distribuição de RegionTypes selecionados.
5. THE Area_Selector SHALL marcar territórios com histórico de 2+ parceiros Exited por `area_signal` como `repeated_failure = true` no output, para visibilidade do gestor.

---

### Requirement 7: Ideal Supply via CP-SAT em Resolução 9

**User Story:** Como analista de expansão, quero que o posicionamento preciso de slots use resolução 9 dentro dos territórios selecionados, para que a localização sugerida seja precisa o suficiente para orientar a prospecção de parceiros.

#### Acceptance Criteria

1. THE CP_SAT_Solver SHALL operar exclusivamente sobre H3_Cells de resolução 9 dentro dos territórios selecionados pela Area_Selector, usando o volume de pacotes res 9 como demanda.
2. THE CP_SAT_Solver SHALL gerar `GeoIdealSlot` com: `slot_id`, `station_code`, `territory_id`, `origin_hex` (res 9), `radius_s`, `capacity_s`, `lat`, `lon`, `matched_partner_id = None`.
3. THE CP_SAT_Solver SHALL respeitar `min_cap` e `max_cap` configuráveis por base em `geo_config.py`.
4. THE CP_SAT_Solver SHALL persistir os slots no Turso via `TursoWriter.upsert_ideal_supply()` com `matched_partner_id = NULL` (preenchido pelo daily).
5. IF o solver não encontrar solução ótima dentro do tempo limite, THE pipeline SHALL persistir a melhor solução parcial com flag `is_optimal = False`.

---

### Requirement 8: Daily — Matching Sofisticado com Hierarquia de Fallback

**User Story:** Como operador do sistema, quero que o modo daily carregue parceiros reais via `load_partners()`, busque os slots do setup mais recente no Turso e execute o matching com hierarquia completa de fallback, para que o attainment e accuracy reflitam a realidade da rede.

#### Acceptance Criteria

1. WHEN executado com `--mode daily`, THE geo_orchestrator SHALL carregar parceiros via `load_partners()` e slots via `TursoReader.get_ideal_supply(station_code, run_id)` do run mais recente.
2. THE geo_daily SHALL carregar `territories.geojson` para point-in-polygon e `territories_index.json` para fallback de centroide.
3. THE geo_daily SHALL executar matching com hierarquia: Active (1) > Onboarding (2) > BG Checks (3) > Prospect (4) > Inactive/Exited (5).
4. THE geo_daily SHALL determinar `territory_id` de cada parceiro com hierarquia de fallback: (1) hex exato em `hex_ids`, (2) point-in-polygon via Shapely, (3) centroide geométrico do polígono, (4) centroide dos slots do `territories_index`.
5. THE geo_daily SHALL persistir `matched_partner_id` por slot via `TursoWriter.update_supply_match()`.
6. THE geo_daily SHALL persistir `attainment` e `accuracy` por território via `TursoWriter.update_territory_fit()`.
7. THE geo_daily SHALL retornar `GeoDailyResult` com `matched`, `unmatched` e métricas por território.

---

### Requirement 9: Persistência e Rastreabilidade no Turso

**User Story:** Como desenvolvedor, quero que todos os outputs do pipeline sejam persistidos no Turso com `run_id` como chave de rastreabilidade, para que seja possível comparar execuções e fazer rollback.

#### Acceptance Criteria

1. THE TursoWriter SHALL persistir Success_Profile e Failure_Profile como JSON na tabela `geo_partner_profiles` com colunas: `run_id`, `station_code`, `profile_type` (success/failure), `vector_json`, `n_partners`, `avg_tenure_days`, `created_at`.
2. THE TursoWriter SHALL persistir métricas de clustering na tabela `geo_run_metadata`: `umap_params`, `hdbscan_params`, `silhouette_score`, `n_clusters`, `low_quality_clustering` (bool).
3. THE TursoWriter SHALL persistir `exit_reason_class` e `tenure_days` por parceiro Exited na tabela `geo_partner_history` para auditoria e re-treinamento futuro.
4. THE TursoWriter SHALL suportar `update_supply_match(run_id, matches)` e `update_territory_fit(run_id, fits)` para o daily.
5. THE TursoReader SHALL expor `get_latest_run_id(station_code)` filtrando por `status = 'setup_complete'` para garantir que o daily sempre use um setup finalizado.

---

### Requirement 10: Escalabilidade Global

**User Story:** Como arquiteto do sistema, quero que o pipeline seja agnóstico a país/mercado, para que possa ser usado em qualquer operação de hub delivery globalmente sem mudanças estruturais.

#### Acceptance Criteria

1. THE pipeline SHALL ser configurável por mercado via `geo_config.py`: moeda, sistema de coordenadas, fonte de dados censitários (IBGE para BR, Census Bureau para US, Eurostat para EU), e mapeamento de CNAEs/SIC codes.
2. THE pipeline SHALL funcionar sem dados de IBGE ou CNPJ quando indisponíveis, degradando graciosamente para features OSM + volume histórico + perfil de parceiros.
3. THE Exit_Reason_Class mapping SHALL ser configurável por mercado em `geo_config.py`, permitindo adaptar os motivos de saída ao vocabulário local de cada operação.
4. THE pipeline SHALL suportar múltiplas moedas e sistemas de renda per capita, normalizando `avg_income` por PPP (Purchasing Power Parity) quando configurado, para comparabilidade entre mercados.
5. THE pipeline SHALL ser stateless entre execuções — todo estado persistido no Turso, sem dependência de arquivos locais além dos artefatos de modelo versionados.
6. THE pipeline SHALL suportar execução paralela por Delivery_Station sem conflito de estado, usando `run_id` como namespace de isolamento no Turso.
