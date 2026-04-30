/**
 * deliveriesInsights.ts
 * =====================
 * Computa insights operacionais a partir das métricas base entregues
 * pelo backend (deliveries_summary.json + deliveries_by_hex.json +
 * dados_mapa.json) e dos thresholds ajustáveis pelo usuário via sliders.
 *
 * Por que no frontend e não no backend
 * ------------------------------------
 * Os thresholds são ajustados em tempo real pelos gerentes de operação.
 * Recomputar no frontend evita regenerar artefato a cada ajuste e mantém
 * a interação instantânea. O custo é aceitável: O(n) sobre ~2k parceiros
 * e ~30k hexes — milissegundos.
 *
 * Insights implementados
 * ----------------------
 * 1. Parceiros subutilizados         — daily_avg / capacity < threshold
 * 2. Territórios com DSP dominante    — existe hub ativo e DSP > threshold
 * 3. Hexes órfãos de alto volume      — volume diário > threshold sem hub
 * 4. Parceiros com queda súbita       — trend_7d_pct <= -threshold
 * 5. Ranking de prospecção por DS     — score combinando DSP share, hexes
 *                                       órfãos e gap de cap dos hubs ativos
 * 6. Parceiros fora de curva geográfica — share no DS alto mas raio setado
 *                                         menor que a média dos parceiros
 */

import type {
  DeliverySummary,
  DeliveriesByHex,
  InsightThresholds,
  Partner,
  PartnerDeliveryStats,
  HexDeliveryBreakdown,
} from '../store/types';
import type { HierarchyIndex, TerritoryMeta } from './deliveriesHierarchy';
import {
  filterPartnersByHierarchy,
  filterHexesByHierarchy,
  territoryMatchesFilters,
  baseMatchesFilters,
} from './deliveriesHierarchy';
import type { DashboardFilters } from './reportUtils';

// ---------------------------------------------------------------------------
// DEFAULTS
// ---------------------------------------------------------------------------

export const DEFAULT_THRESHOLDS: InsightThresholds = {
  cap_utilization_pct_threshold: 60,
  trend_drop_pct_threshold: 30,
  dsp_dominance_share_pct_threshold: 50,
  orphan_hex_min_daily_volume: 3,
};

// ---------------------------------------------------------------------------
// TIPOS DE SAÍDA
// ---------------------------------------------------------------------------

export interface UnderutilizedPartner {
  store_id: string;
  name: string;
  delivery_station: string;
  bucket_ade: string | null;
  capacity: number;
  daily_avg: number;
  cap_utilization_pct: number;
  gap_absolute: number;
}

export interface DspDominantTerritory {
  bucket_ade: string;
  delivery_station: string;
  total: number;
  ihs: number;
  dsp: number;
  dsp_share_pct: number;
  active_hubs_in_territory: number;
  active_hubs_names: string[];
}

export interface OrphanHex {
  hex_id: string;
  daily_volume: number;
  total_volume: number;
  dsp_share_pct: number;
}

export interface PartnerTrendDrop {
  store_id: string;
  name: string;
  delivery_station: string;
  trend_7d_pct: number;
  daily_avg: number;
  total: number;
}

export interface ProspectRankingEntry {
  delivery_station: string;
  score: number;
  dsp_share_pct: number;
  orphan_hexes: number;
  underutilized_hubs: number;
  total_volume: number;
}

/**
 * Nó do ranking hierárquico de prospecção.
 * Cada nó representa um nível da hierarquia (BDM/DS/CTL/ADE) com score
 * agregado dos filhos e métricas somadas. Permite drill-down na UI.
 */
export interface ProspectRankingNode {
  /** Nível da hierarquia: 'bdm' | 'ds' | 'ctl' | 'ade'. */
  level: 'bdm' | 'ds' | 'ctl' | 'ade';
  /** Rótulo exibido (nome do BDM, código da DS, etc). */
  label: string;
  /** Valor chave do nível (usado para filtrar o próximo nível). */
  key: string;
  score: number;
  total_volume: number;
  ihs: number;
  dsp: number;
  dsp_share_pct: number;
  orphan_hexes: number;
  underutilized_hubs: number;
  /** Nós do nível abaixo (vazio no nível ADE). */
  children: ProspectRankingNode[];
}

export interface GeographicOutlier {
  store_id: string;
  name: string;
  delivery_station: string;
  radius: number;
  avg_radius_ds: number;
  share_ds_ihs_pct: number;
  capacity: number;
}

export interface InsightsResult {
  underutilized: UnderutilizedPartner[];
  dspDominant: DspDominantTerritory[];
  orphanHexes: OrphanHex[];
  trendDrops: PartnerTrendDrop[];
  prospectRanking: ProspectRankingEntry[];
  /** Ranking hierárquico BDM → DS → CTL → ADE. */
  prospectRankingTree: ProspectRankingNode[];
  geographicOutliers: GeographicOutlier[];
  /** Hubs Active/Onboarding com cap ou radius = 0 no Salesforce. */
  misconfiguredHubs: MisconfiguredHub[];
}

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function isActiveHub(p: Partner): boolean {
  return (p.status === 'Active' || p.status === 'Onboarding') && !!p.store_id;
}

// ---------------------------------------------------------------------------
// INSIGHTS INDIVIDUAIS
// ---------------------------------------------------------------------------

/**
 * Parceiros cujo volume médio diário nos últimos dias está abaixo de
 * `threshold` % do `capacity` setado. Filtra apenas parceiros Active/Onboarding
 * conhecidos (unknown não tem capacity comparável).
 *
 * Parceiros com `cap_misconfigured=true` (capacity ou radius zerados no
 * Salesforce) são EXCLUÍDOS — eles têm card de warning próprio e entrar
 * aqui inflaria o alerta de performance com dados-ausentes.
 */
export function computeUnderutilized(
  partners: PartnerDeliveryStats[],
  thresholds: InsightThresholds,
): UnderutilizedPartner[] {
  const limit = thresholds.cap_utilization_pct_threshold;
  return partners
    .filter((p) =>
      !p.is_unknown &&
      !p.cap_misconfigured &&
      p.capacity > 0 &&
      p.cap_utilization_pct < limit &&
      (p.status === 'Active' || p.status === 'Onboarding'),
    )
    .map((p) => ({
      store_id: p.store_id,
      name: p.name,
      delivery_station: p.delivery_station,
      bucket_ade: p.bucket_ade,
      capacity: p.capacity,
      daily_avg: p.daily_avg,
      cap_utilization_pct: p.cap_utilization_pct,
      gap_absolute: Math.max(p.capacity - p.daily_avg, 0),
    }))
    .sort((a, b) => b.gap_absolute - a.gap_absolute);
}

/**
 * Hubs Active/Onboarding com cap ou radius = 0 no Salesforce. Warning
 * operacional dedicado — precisa de ação manual do time de ops para
 * corrigir o cadastro. Isolado dos insights de performance para não
 * mascarar problemas diferentes.
 */
export interface MisconfiguredHub {
  store_id: string;
  name: string;
  delivery_station: string;
  bucket_ade: string | null;
  capacity: number;
  radius: number;
  daily_avg: number;
  total: number;
  status: string | null;
}

export function computeMisconfiguredHubs(
  partners: PartnerDeliveryStats[],
): MisconfiguredHub[] {
  return partners
    .filter((p) => p.cap_misconfigured)
    .map((p) => ({
      store_id: p.store_id,
      name: p.name,
      delivery_station: p.delivery_station,
      bucket_ade: p.bucket_ade,
      capacity: p.capacity,
      radius: p.radius,
      daily_avg: p.daily_avg,
      total: p.total,
      status: p.status,
    }))
    // Ordenar por quem tem mais pacotes entregues primeiro — esses são os
    // que mais "puxam" volume mesmo sem cap/raio configurado; prioridade
    // de correção.
    .sort((a, b) => b.total - a.total);
}

/**
 * Territórios (bucket_ade) onde há pelo menos um hub ativo, mas DSP
 * ainda responde por mais de `threshold` % do volume. Indica parceiro
 * hub que deveria estar capturando mais pacotes.
 *
 * Requer `summary.partners` (para mapear volume por bucket) e a lista
 * completa de parceiros do store (para identificar hubs ativos).
 */
export function computeDspDominantTerritories(
  summary: DeliverySummary,
  allPartners: Partner[],
  thresholds: InsightThresholds,
): DspDominantTerritory[] {
  const limit = thresholds.dsp_dominance_share_pct_threshold;

  // Map bucket_ade → [activeHubs]
  const hubsByBucket = new Map<string, Partner[]>();
  for (const p of allPartners) {
    if (!isActiveHub(p) || !p.bucket_ade) continue;
    if (!hubsByBucket.has(p.bucket_ade)) hubsByBucket.set(p.bucket_ade, []);
    hubsByBucket.get(p.bucket_ade)!.push(p);
  }

  // Map bucket_ade → {total, ihs, dsp} a partir dos partners stats
  // Como summary.partners tem share_territory_pct por parceiro (já
  // computado em cima de territory_totals), usamos territory_totals
  // direto para total e acumulamos IHS/DSP via partners + o resíduo
  // (pacotes sem store_id) inferido do total do DS.
  //
  // Estratégia simples e correta: tratar cada bucket como:
  //   total = territory_totals[bucket]
  //   ihs   = soma de `total` dos partners com esse bucket
  //            (partner.canal_dominante === 'IHS_STORE')
  //   dsp   = total - ihs  (assume que o resto é DSP; em prática o
  //                         campo 'other' dos agregados do DS é residual
  //                         e muito pequeno).
  const byBucket = new Map<string, { total: number; ihs: number }>();
  for (const [bucket, total] of Object.entries(summary.territory_totals)) {
    byBucket.set(bucket, { total, ihs: 0 });
  }
  for (const p of summary.partners) {
    if (!p.bucket_ade) continue;
    if (p.canal_dominante !== 'IHS_STORE') continue;
    const entry = byBucket.get(p.bucket_ade);
    if (entry) entry.ihs += p.total;
  }

  const result: DspDominantTerritory[] = [];
  for (const [bucket, { total, ihs }] of byBucket) {
    if (total <= 0) continue;
    const dsp = Math.max(total - ihs, 0);
    const dspSharePct = (dsp / total) * 100;
    if (dspSharePct < limit) continue;

    const hubs = hubsByBucket.get(bucket) || [];
    if (hubs.length === 0) continue; // interessa apenas territórios COM hub ativo

    // delivery_station do bucket — usa o primeiro hub (todos do mesmo DS).
    const ds = hubs[0].delivery_station;

    result.push({
      bucket_ade: bucket,
      delivery_station: ds,
      total,
      ihs,
      dsp,
      dsp_share_pct: Math.round(dspSharePct * 100) / 100,
      active_hubs_in_territory: hubs.length,
      active_hubs_names: hubs.map((h) => h.name),
    });
  }

  return result.sort((a, b) => b.dsp_share_pct - a.dsp_share_pct);
}

/**
 * Hexes com volume diário médio > threshold onde não há nenhum hub entre
 * os top_partners. São candidatos diretos para prospecção.
 */
export function computeOrphanHexes(
  byHex: DeliveriesByHex,
  partnerIndex: Set<string>,
  thresholds: InsightThresholds,
): OrphanHex[] {
  const days = Math.max(byHex.period.days || 1, 1);
  const limit = thresholds.orphan_hex_min_daily_volume;

  const result: OrphanHex[] = [];
  for (const h of byHex.hexes) {
    const dailyVolume = h.total / days;
    if (dailyVolume < limit) continue;

    // "Órfão" = nenhum store_id entre os top_partners é um hub conhecido.
    const hasHub = h.top_partners.some((tp) => partnerIndex.has(tp.store_id));
    if (hasHub) continue;

    result.push({
      hex_id: h.hex_id,
      daily_volume: Math.round(dailyVolume * 100) / 100,
      total_volume: h.total,
      dsp_share_pct: h.dsp_share_pct,
    });
  }

  return result.sort((a, b) => b.daily_volume - a.daily_volume);
}

/**
 * Parceiros com queda > threshold% nos últimos 7d vs os 7d anteriores.
 */
export function computeTrendDrops(
  partners: PartnerDeliveryStats[],
  thresholds: InsightThresholds,
): PartnerTrendDrop[] {
  const limit = thresholds.trend_drop_pct_threshold;
  return partners
    .filter((p) => !p.is_unknown && p.trend_7d_pct <= -limit && p.total > 0)
    .map((p) => ({
      store_id: p.store_id,
      name: p.name,
      delivery_station: p.delivery_station,
      trend_7d_pct: p.trend_7d_pct,
      daily_avg: p.daily_avg,
      total: p.total,
    }))
    .sort((a, b) => a.trend_7d_pct - b.trend_7d_pct);
}

/**
 * Score de prospecção por DS combinando:
 *   - DSP share do DS (quanto maior, mais espaço para novos hubs)
 *   - nº de hexes órfãos de alto volume no DS
 *   - nº de hubs ativos subutilizados no DS (indica cap aproveitado mal)
 *
 * Normalização simples (min-max por fator) e soma ponderada.
 */
export function computeProspectRanking(
  summary: DeliverySummary,
  orphanHexesByDs: Record<string, number>,
  underutilizedByDs: Record<string, number>,
): ProspectRankingEntry[] {
  const stations = Object.keys(summary.station_totals);
  if (stations.length === 0) return [];

  const maxOrphan = Math.max(1, ...Object.values(orphanHexesByDs));
  const maxUnder = Math.max(1, ...Object.values(underutilizedByDs));
  const maxDspShare = Math.max(
    1,
    ...stations.map((s) => summary.station_totals[s].dsp_share_pct),
  );

  return stations
    .map((ds) => {
      const st = summary.station_totals[ds];
      const orphan = orphanHexesByDs[ds] || 0;
      const under = underutilizedByDs[ds] || 0;

      // Pesos empíricos — fácil ajustar depois se o time pedir.
      const score =
        (st.dsp_share_pct / maxDspShare) * 50 +
        (orphan / maxOrphan) * 30 +
        (under / maxUnder) * 20;

      return {
        delivery_station: ds,
        score: Math.round(score * 100) / 100,
        dsp_share_pct: st.dsp_share_pct,
        orphan_hexes: orphan,
        underutilized_hubs: under,
        total_volume: st.total,
      };
    })
    .sort((a, b) => b.score - a.score);
}

/**
 * Hubs ativos com share alto no DS porém raio relativamente pequeno —
 * sinal de que talvez estejam performando bem apesar de cobertura
 * subdimensionada. Ou, ao contrário, hubs com raio enorme e share baixo
 * (desperdício de capacidade alocada).
 *
 * Implementação: compara o radius do parceiro com a média dos Active
 * do mesmo DS. Fora de curva: |radius - mean| / mean > 30%.
 */
export function computeGeographicOutliers(
  summary: DeliverySummary,
  allPartners: Partner[],
): GeographicOutlier[] {
  // Média de raio por DS (somente Active/Onboarding com radius válido)
  const sumByDs: Record<string, { sum: number; n: number }> = {};
  for (const p of allPartners) {
    if (!isActiveHub(p)) continue;
    if (!p.radius || p.radius <= 0) continue;
    if (!sumByDs[p.delivery_station]) sumByDs[p.delivery_station] = { sum: 0, n: 0 };
    sumByDs[p.delivery_station].sum += p.radius;
    sumByDs[p.delivery_station].n += 1;
  }
  const avgByDs: Record<string, number> = {};
  for (const [ds, { sum, n }] of Object.entries(sumByDs)) {
    avgByDs[ds] = n > 0 ? sum / n : 0;
  }

  const partnerBySid = new Map(summary.partners.map((p) => [p.store_id, p]));

  const result: GeographicOutlier[] = [];
  for (const p of allPartners) {
    if (!isActiveHub(p) || !p.store_id) continue;
    const avg = avgByDs[p.delivery_station];
    if (!avg || avg <= 0) continue;
    const deviation = Math.abs(p.radius - avg) / avg;
    if (deviation < 0.3) continue;

    const stats = partnerBySid.get(p.store_id);
    if (!stats) continue;
    // Apenas chamam atenção parceiros com volume relevante (> 0 no período).
    if (stats.total <= 0) continue;

    result.push({
      store_id: p.store_id,
      name: p.name,
      delivery_station: p.delivery_station,
      radius: p.radius,
      avg_radius_ds: Math.round(avg),
      share_ds_ihs_pct: stats.share_ds_ihs_pct,
      capacity: p.capacity,
    });
  }

  return result.sort((a, b) => Math.abs(b.radius - b.avg_radius_ds) - Math.abs(a.radius - a.avg_radius_ds));
}

/**
 * Ranking hierárquico BDM → DS → CTL → ADE.
 *
 * Agrega os parceiros (IHS_STORE — hubs conhecidos) e hexes órfãos
 * pelo nível correspondente, computando score composto em cada nó.
 * Os filhos de cada nó somam para o pai.
 *
 * O score usa os mesmos pesos do ranking simples (%DSP × 50 + órfãos ×
 * 30 + under × 20), mas calculado por nó. Cada nó é ordenado desc por
 * score entre seus irmãos.
 */
export function computeProspectRankingTree(
  summary: DeliverySummary,
  byHex: DeliveriesByHex | null,
  allPartners: Partner[],
  index: HierarchyIndex,
  thresholds: InsightThresholds,
): ProspectRankingNode[] {
  // ---------- (1) Coletar métricas crus por bucket_ade ----------

  // bucket_ade → {total, ihs, dsp, underutilized}
  const perTerritory = new Map<
    string,
    { total: number; ihs: number; dsp: number; under: number }
  >();

  // Garantir entrada para todos os buckets que existem no summary
  for (const [bucket, total] of Object.entries(summary.territory_totals)) {
    perTerritory.set(bucket, { total, ihs: 0, dsp: 0, under: 0 });
  }

  for (const p of summary.partners) {
    if (!p.bucket_ade) continue;
    let entry = perTerritory.get(p.bucket_ade);
    if (!entry) {
      // caso um parceiro tenha bucket_ade que não apareceu em territory_totals
      // (raro, mas defensivo)
      entry = { total: 0, ihs: 0, dsp: 0, under: 0 };
      perTerritory.set(p.bucket_ade, entry);
    }
    if (p.canal_dominante === 'IHS_STORE') entry.ihs += p.total;
    else if (p.canal_dominante === 'DSP') entry.dsp += p.total;

    // Parceiro contribui para o "underutilized" do seu bucket se aplicável.
    const isActive = p.status === 'Active' || p.status === 'Onboarding';
    if (
      !p.is_unknown &&
      isActive &&
      p.capacity > 0 &&
      p.cap_utilization_pct < thresholds.cap_utilization_pct_threshold
    ) {
      entry.under += 1;
    }
  }

  // Hexes órfãos por bucket_ade.
  const orphanByTerritory = new Map<string, number>();
  if (byHex) {
    const partnerIndex = new Set(
      allPartners.filter((p) => !!p.store_id).map((p) => p.store_id as string),
    );
    const days = Math.max(byHex.period.days || 1, 1);
    for (const h of byHex.hexes) {
      const daily = h.total / days;
      if (daily < thresholds.orphan_hex_min_daily_volume) continue;
      const hasHub = h.top_partners.some((tp) => partnerIndex.has(tp.store_id));
      if (hasHub) continue;
      if (!h.territory_id) continue;
      orphanByTerritory.set(
        h.territory_id,
        (orphanByTerritory.get(h.territory_id) || 0) + 1,
      );
    }
  }

  // DSP inferido = total − IHS (mesma heurística do insight "DSP dominante").
  for (const entry of perTerritory.values()) {
    if (entry.dsp === 0) entry.dsp = Math.max(entry.total - entry.ihs, 0);
  }

  // ---------- (2) Montar árvore ----------

  // Estrutura temporária aninhada Map antes de virar array.
  type Aggr = { total: number; ihs: number; dsp: number; under: number; orphan: number };
  const newAggr = (): Aggr => ({ total: 0, ihs: 0, dsp: 0, under: 0, orphan: 0 });

  const add = (a: Aggr, b: Aggr) => {
    a.total += b.total;
    a.ihs += b.ihs;
    a.dsp += b.dsp;
    a.under += b.under;
    a.orphan += b.orphan;
  };

  // Hierarquia a partir dos buckets: bucket → meta (bdm, base, ctl, ade)
  const tree = new Map<
    string, // bdm
    {
      aggr: Aggr;
      ds: Map<
        string,
        {
          aggr: Aggr;
          ctl: Map<
            string,
            {
              aggr: Aggr;
              ade: Map<string, Aggr>;
            }
          >;
        }
      >;
    }
  >();

  for (const [territoryId, entry] of perTerritory) {
    const meta = index.territoryToMeta.get(territoryId);
    if (!meta) continue;

    const base: Aggr = {
      total: entry.total,
      ihs: entry.ihs,
      dsp: entry.dsp,
      under: entry.under,
      orphan: orphanByTerritory.get(territoryId) || 0,
    };

    // BDM
    if (!tree.has(meta.bdm)) tree.set(meta.bdm, { aggr: newAggr(), ds: new Map() });
    const bdmNode = tree.get(meta.bdm)!;
    add(bdmNode.aggr, base);

    // DS
    if (!bdmNode.ds.has(meta.base)) bdmNode.ds.set(meta.base, { aggr: newAggr(), ctl: new Map() });
    const dsNode = bdmNode.ds.get(meta.base)!;
    add(dsNode.aggr, base);

    // CTL (fallback '(sem CTL)' quando vazio)
    const ctlKey = meta.ctl || '(sem CTL)';
    if (!dsNode.ctl.has(ctlKey)) dsNode.ctl.set(ctlKey, { aggr: newAggr(), ade: new Map() });
    const ctlNode = dsNode.ctl.get(ctlKey)!;
    add(ctlNode.aggr, base);

    // ADE (fallback '(sem ADE)' quando vazio)
    const adeKey = meta.ade || '(sem ADE)';
    const prev = ctlNode.ade.get(adeKey) || newAggr();
    add(prev, base);
    ctlNode.ade.set(adeKey, prev);
  }

  // ---------- (3) Normalização dos pesos do score ----------
  // Para comparar entre irmãos, normalizamos pelos máximos no nível.

  const scoreNode = (aggr: Aggr, maxOrphan: number, maxUnder: number): number => {
    const dspPct = aggr.total > 0 ? (aggr.dsp / aggr.total) * 100 : 0;
    // Pesos: DSP share (50) + órfãos (30) + under (20)
    return (
      (dspPct / 100) * 50 +
      (maxOrphan > 0 ? (aggr.orphan / maxOrphan) * 30 : 0) +
      (maxUnder > 0 ? (aggr.under / maxUnder) * 20 : 0)
    );
  };

  // ---------- (4) Converter Map → array ordenado ----------

  const bdmArr = Array.from(tree.entries());
  const maxOrphanBdm = Math.max(0, ...bdmArr.map(([, v]) => v.aggr.orphan));
  const maxUnderBdm = Math.max(0, ...bdmArr.map(([, v]) => v.aggr.under));

  const result: ProspectRankingNode[] = bdmArr.map(([bdm, bdmNode]) => {
    const dsArr = Array.from(bdmNode.ds.entries());
    const maxOrphanDs = Math.max(0, ...dsArr.map(([, v]) => v.aggr.orphan));
    const maxUnderDs = Math.max(0, ...dsArr.map(([, v]) => v.aggr.under));

    const dsChildren = dsArr.map(([ds, dsNode]) => {
      const ctlArr = Array.from(dsNode.ctl.entries());
      const maxOrphanCtl = Math.max(0, ...ctlArr.map(([, v]) => v.aggr.orphan));
      const maxUnderCtl = Math.max(0, ...ctlArr.map(([, v]) => v.aggr.under));

      const ctlChildren = ctlArr.map(([ctl, ctlNode]) => {
        const adeArr = Array.from(ctlNode.ade.entries());
        const maxOrphanAde = Math.max(0, ...adeArr.map(([, v]) => v.orphan));
        const maxUnderAde = Math.max(0, ...adeArr.map(([, v]) => v.under));

        const adeChildren: ProspectRankingNode[] = adeArr
          .map(([ade, aggr]) => ({
            level: 'ade' as const,
            label: ade,
            key: ade,
            score: Math.round(scoreNode(aggr, maxOrphanAde, maxUnderAde) * 100) / 100,
            total_volume: aggr.total,
            ihs: aggr.ihs,
            dsp: aggr.dsp,
            dsp_share_pct: aggr.total > 0 ? Math.round((aggr.dsp / aggr.total) * 10000) / 100 : 0,
            orphan_hexes: aggr.orphan,
            underutilized_hubs: aggr.under,
            children: [],
          }))
          .sort((a, b) => b.score - a.score);

        return {
          level: 'ctl' as const,
          label: ctl,
          key: ctl,
          score: Math.round(scoreNode(ctlNode.aggr, maxOrphanCtl, maxUnderCtl) * 100) / 100,
          total_volume: ctlNode.aggr.total,
          ihs: ctlNode.aggr.ihs,
          dsp: ctlNode.aggr.dsp,
          dsp_share_pct:
            ctlNode.aggr.total > 0
              ? Math.round((ctlNode.aggr.dsp / ctlNode.aggr.total) * 10000) / 100
              : 0,
          orphan_hexes: ctlNode.aggr.orphan,
          underutilized_hubs: ctlNode.aggr.under,
          children: adeChildren,
        };
      }).sort((a, b) => b.score - a.score);

      return {
        level: 'ds' as const,
        label: ds,
        key: ds,
        score: Math.round(scoreNode(dsNode.aggr, maxOrphanDs, maxUnderDs) * 100) / 100,
        total_volume: dsNode.aggr.total,
        ihs: dsNode.aggr.ihs,
        dsp: dsNode.aggr.dsp,
        dsp_share_pct:
          dsNode.aggr.total > 0
            ? Math.round((dsNode.aggr.dsp / dsNode.aggr.total) * 10000) / 100
            : 0,
        orphan_hexes: dsNode.aggr.orphan,
        underutilized_hubs: dsNode.aggr.under,
        children: ctlChildren,
      };
    }).sort((a, b) => b.score - a.score);

    return {
      level: 'bdm' as const,
      label: bdm,
      key: bdm,
      score: Math.round(scoreNode(bdmNode.aggr, maxOrphanBdm, maxUnderBdm) * 100) / 100,
      total_volume: bdmNode.aggr.total,
      ihs: bdmNode.aggr.ihs,
      dsp: bdmNode.aggr.dsp,
      dsp_share_pct:
        bdmNode.aggr.total > 0
          ? Math.round((bdmNode.aggr.dsp / bdmNode.aggr.total) * 10000) / 100
          : 0,
      orphan_hexes: bdmNode.aggr.orphan,
      underutilized_hubs: bdmNode.aggr.under,
      children: dsChildren,
    };
  }).sort((a, b) => b.score - a.score);

  return result;
}

// ---------------------------------------------------------------------------
// ENTRYPOINT
// ---------------------------------------------------------------------------

/**
 * Executa todos os insights. Retorna estruturas prontas para renderizar.
 * Todos os insights respeitam o recorte {filters, hierarchyIndex}:
 *
 * @param summary    - deliveries_summary.json
 * @param byHex      - deliveries_by_hex.json (pode ser null se ainda não carregado)
 * @param allPartners - lista de parceiros do store (dados_mapa.json)
 * @param thresholds - ajustáveis via sliders na aba Insights
 * @param filters    - filtros hierárquicos ativos (BDM/Base/CTL/ADE/Territory)
 * @param hierarchyIndex - índice derivado do reportData
 */
export function computeAllInsights(
  summary: DeliverySummary | null,
  byHex: DeliveriesByHex | null,
  allPartners: Partner[],
  thresholds: InsightThresholds,
  filters: DashboardFilters,
  hierarchyIndex: HierarchyIndex,
): InsightsResult {
  if (!summary) {
    return {
      underutilized: [],
      dspDominant: [],
      orphanHexes: [],
      trendDrops: [],
      prospectRanking: [],
      prospectRankingTree: [],
      geographicOutliers: [],
      misconfiguredHubs: [],
    };
  }

  // Recortar partners/hexes/parceiros brutos pela hierarquia antes de alimentar
  // cada insight.
  const scopedPartnerStats = filterPartnersByHierarchy(summary.partners, filters, hierarchyIndex);
  const scopedHexes = byHex
    ? filterHexesByHierarchy(byHex.hexes, filters, hierarchyIndex)
    : [];
  const scopedPartners = allPartners.filter((p) => {
    if (!p.bucket_ade) {
      return baseMatchesFilters(p.delivery_station, filters, hierarchyIndex);
    }
    const meta = hierarchyIndex.territoryToMeta.get(p.bucket_ade);
    if (!meta) return baseMatchesFilters(p.delivery_station, filters, hierarchyIndex);
    return territoryMatchesFilters(meta, filters);
  });

  const underutilized = computeUnderutilized(scopedPartnerStats, thresholds);
  const dspDominant = computeDspDominantTerritories(
    { ...summary, partners: scopedPartnerStats },
    scopedPartners,
    thresholds,
  );
  const trendDrops = computeTrendDrops(scopedPartnerStats, thresholds);

  // Partner index para órfãos considera TODOS os parceiros conhecidos
  // (independente de recorte) — o conceito de "órfão" é baseado em existência
  // de hub no top_partners, não em filtro visual.
  const partnerIndex = new Set(
    allPartners.filter((p) => !!p.store_id).map((p) => p.store_id as string),
  );
  // Mas a lista exibida de órfãos só inclui os que caem no recorte.
  const scopedByHex = byHex ? { ...byHex, hexes: scopedHexes } : null;
  const orphanHexes = scopedByHex
    ? computeOrphanHexes(scopedByHex, partnerIndex, thresholds)
    : [];

  // Ranking simples por DS (mantido por compatibilidade com o card de ranking
  // que pode continuar existindo em formato resumido).
  const orphanHexesByDs: Record<string, number> = {};
  if (scopedByHex) {
    for (const h of scopedByHex.hexes) {
      if (!h.station_code) continue;
      const daily = h.total / Math.max(scopedByHex.period.days || 1, 1);
      if (daily < thresholds.orphan_hex_min_daily_volume) continue;
      const hasHub = h.top_partners.some((tp) => partnerIndex.has(tp.store_id));
      if (hasHub) continue;
      orphanHexesByDs[h.station_code] = (orphanHexesByDs[h.station_code] || 0) + 1;
    }
  }
  const underutilizedByDs: Record<string, number> = {};
  for (const u of underutilized) {
    underutilizedByDs[u.delivery_station] = (underutilizedByDs[u.delivery_station] || 0) + 1;
  }

  // Station totals recortados (somente DSs presentes no recorte).
  const scopedStationTotals: DeliverySummary['station_totals'] = {};
  const stationsInScope = new Set(scopedPartnerStats.map((p) => p.delivery_station).filter(Boolean));
  for (const [ds, totals] of Object.entries(summary.station_totals)) {
    if (stationsInScope.has(ds)) scopedStationTotals[ds] = totals;
  }

  const prospectRanking = computeProspectRanking(
    { ...summary, station_totals: scopedStationTotals, partners: scopedPartnerStats },
    orphanHexesByDs,
    underutilizedByDs,
  );

  const prospectRankingTree = computeProspectRankingTree(
    { ...summary, partners: scopedPartnerStats },
    scopedByHex,
    scopedPartners,
    hierarchyIndex,
    thresholds,
  );

  const geographicOutliers = computeGeographicOutliers(
    { ...summary, partners: scopedPartnerStats },
    scopedPartners,
  );

  const misconfiguredHubs = computeMisconfiguredHubs(scopedPartnerStats);

  return {
    underutilized,
    dspDominant,
    orphanHexes,
    trendDrops,
    prospectRanking,
    prospectRankingTree,
    geographicOutliers,
    misconfiguredHubs,
  };
}
