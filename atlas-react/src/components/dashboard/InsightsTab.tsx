/**
 * InsightsTab.tsx
 * ===============
 * Aba "Insights & Oportunidades" do Dashboard Operacional.
 * Renderiza 6 cards de insight recomputados em tempo real a partir de:
 *   - deliveries_summary.json
 *   - deliveries_by_hex.json (lazy-loaded quando a aba abre)
 *   - dados_mapa.json (Partner[] do store)
 *   - relatorio_executivo.json (hierarquia BDM/CTL/ADE)
 *
 * Sliders ajustáveis controlam os thresholds dos insights sem precisar
 * regerar artefatos no backend. Todos os insights respeitam o recorte
 * hierárquico global (BDM → Base → CTL → ADE → Território) aplicado
 * pelo FilterCascade no topo do Dashboard.
 *
 * Ranking de prospecção vem como árvore BDM → DS → CTL → ADE com
 * drill-down — o gerente expande o nível que quer olhar.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import { Spinner } from '../ui/Spinner';
import {
  DEFAULT_THRESHOLDS,
  computeAllInsights,
  type ProspectRankingNode,
} from '../../lib/deliveriesInsights';
import type { InsightThresholds } from '../../store/types';
import type { DashboardFilters, ReportData } from '../../lib/reportUtils';
import { buildHierarchyIndex } from '../../lib/deliveriesHierarchy';

// ---------------------------------------------------------------------------
// SLIDER COMPONENT
// ---------------------------------------------------------------------------

const Slider: React.FC<{
  label: string;
  description?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onChange: (v: number) => void;
}> = ({ label, description, value, min, max, step, suffix = '', onChange }) => (
  <div className="flex flex-col gap-1">
    <div className="flex items-center justify-between">
      <span className="text-xs text-atlas-light font-medium">{label}</span>
      <span className="text-xs text-atlas-accent font-mono">
        {value}
        {suffix}
      </span>
    </div>
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full accent-atlas-accent"
    />
    {description && <span className="text-[11px] text-atlas-muted">{description}</span>}
  </div>
);

// ---------------------------------------------------------------------------
// CARD WRAPPER
// ---------------------------------------------------------------------------

const InsightCard: React.FC<{
  title: string;
  subtitle?: string;
  count: number;
  children: React.ReactNode;
}> = ({ title, subtitle, count, children }) => {
  const { t } = useTranslation();
  return (
    <section className="bg-atlas-dark border border-atlas-navy rounded-lg p-4 flex flex-col gap-3">
      <header className="flex items-baseline justify-between">
        <div className="flex flex-col">
          <h3 className="text-atlas-light font-semibold text-sm">{title}</h3>
          {subtitle && <span className="text-atlas-muted text-xs">{subtitle}</span>}
        </div>
        <span className="text-atlas-accent text-lg font-mono">{count}</span>
      </header>
      {count === 0 ? (
        <div className="text-atlas-muted text-xs text-center py-4">
          {t('insights.no_items')}
        </div>
      ) : (
        children
      )}
    </section>
  );
};

// ---------------------------------------------------------------------------
// RANKING TREE ROW
// ---------------------------------------------------------------------------

const LEVEL_COLORS: Record<ProspectRankingNode['level'], string> = {
  bdm: 'text-atlas-light font-semibold',
  ds: 'text-atlas-light',
  ctl: 'text-atlas-muted',
  ade: 'text-atlas-muted italic',
};

const LEVEL_INDENT: Record<ProspectRankingNode['level'], number> = {
  bdm: 0,
  ds: 16,
  ctl: 32,
  ade: 48,
};

const RankingTreeRow: React.FC<{
  node: ProspectRankingNode;
  expanded: Set<string>;
  onToggle: (path: string) => void;
  path: string;
}> = ({ node, expanded, onToggle, path }) => {
  const hasChildren = node.children.length > 0;
  const isOpen = expanded.has(path);

  return (
    <>
      <tr
        className={`border-t border-atlas-navy ${hasChildren ? 'cursor-pointer hover:bg-atlas-navy' : ''}`}
        onClick={() => hasChildren && onToggle(path)}
      >
        <td className="py-1.5 px-2">
          <div
            className={`flex items-center gap-2 ${LEVEL_COLORS[node.level]}`}
            style={{ paddingLeft: LEVEL_INDENT[node.level] }}
          >
            {hasChildren ? (
              <span className="text-atlas-accent text-xs w-3">{isOpen ? '▾' : '▸'}</span>
            ) : (
              <span className="w-3" />
            )}
            <span className="uppercase text-[9px] font-mono text-atlas-accent mr-1">
              {node.level}
            </span>
            <span className="truncate max-w-[200px]">{node.label}</span>
          </div>
        </td>
        <td className="py-1.5 px-2 text-right text-atlas-accent font-mono">
          {node.score.toFixed(1)}
        </td>
        <td className="py-1.5 px-2 text-right text-orange-400">
          {node.dsp_share_pct.toFixed(1)}%
        </td>
        <td className="py-1.5 px-2 text-right text-atlas-light">
          {node.orphan_hexes}
        </td>
        <td className="py-1.5 px-2 text-right text-atlas-light">
          {node.underutilized_hubs}
        </td>
        <td className="py-1.5 px-2 text-right text-atlas-muted">
          {node.total_volume.toLocaleString('pt-BR')}
        </td>
      </tr>
      {hasChildren && isOpen &&
        node.children.map((child) => (
          <RankingTreeRow
            key={`${path}/${child.key}`}
            node={child}
            expanded={expanded}
            onToggle={onToggle}
            path={`${path}/${child.key}`}
          />
        ))}
    </>
  );
};

// ---------------------------------------------------------------------------
// MAIN
// ---------------------------------------------------------------------------

interface InsightsTabProps {
  filters: DashboardFilters;
  reportData: ReportData | null;
}

const InsightsTab: React.FC<InsightsTabProps> = ({ filters, reportData }) => {
  const { t } = useTranslation();
  const summary = useStore((s) => s.deliveries.summary);
  const byHex = useStore((s) => s.deliveries.byHex);
  const isLoadingSummary = useStore((s) => s.deliveries.isLoadingSummary);
  const isLoadingByHex = useStore((s) => s.deliveries.isLoadingByHex);
  const loadByHex = useStore((s) => s.loadDeliveriesByHex);
  const allPartners = useStore((s) => s.allMarkersData);

  const [thresholds, setThresholds] = useState<InsightThresholds>(DEFAULT_THRESHOLDS);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());

  // Lazy-load do byHex ao abrir a aba
  useEffect(() => {
    if (!byHex && !isLoadingByHex) {
      loadByHex();
    }
  }, [byHex, isLoadingByHex, loadByHex]);

  const hierarchyIndex = useMemo(() => buildHierarchyIndex(reportData), [reportData]);

  const insights = useMemo(
    () => computeAllInsights(summary, byHex, allPartners, thresholds, filters, hierarchyIndex),
    [summary, byHex, allPartners, thresholds, filters, hierarchyIndex],
  );

  const toggleNode = (path: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  if (isLoadingSummary) {
    return (
      <div className="flex items-center justify-center p-12 gap-3 text-atlas-muted">
        <Spinner size="lg" />
        <span className="text-sm">{t('packages.loading')}</span>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-atlas-muted text-sm">
        <span className="text-3xl">💡</span>
        <p className="text-center max-w-md">{t('insights.empty_state')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Thresholds */}
      <section className="bg-atlas-dark border border-atlas-navy rounded-lg p-4">
        <h3 className="text-atlas-muted text-xs uppercase tracking-widest mb-3">
          {t('insights.thresholds_title')}
        </h3>
        <div className="grid grid-cols-1 tablet:grid-cols-2 laptop:grid-cols-4 gap-4">
          <Slider
            label={t('insights.slider_cap')}
            description={t('insights.slider_cap_desc')}
            value={thresholds.cap_utilization_pct_threshold}
            min={10}
            max={100}
            step={5}
            suffix="%"
            onChange={(v) =>
              setThresholds((th) => ({ ...th, cap_utilization_pct_threshold: v }))
            }
          />
          <Slider
            label={t('insights.slider_trend')}
            description={t('insights.slider_trend_desc')}
            value={thresholds.trend_drop_pct_threshold}
            min={10}
            max={80}
            step={5}
            suffix="%"
            onChange={(v) =>
              setThresholds((th) => ({ ...th, trend_drop_pct_threshold: v }))
            }
          />
          <Slider
            label={t('insights.slider_dsp')}
            description={t('insights.slider_dsp_desc')}
            value={thresholds.dsp_dominance_share_pct_threshold}
            min={10}
            max={90}
            step={5}
            suffix="%"
            onChange={(v) =>
              setThresholds((th) => ({
                ...th,
                dsp_dominance_share_pct_threshold: v,
              }))
            }
          />
          <Slider
            label={t('insights.slider_orphan')}
            description={t('insights.slider_orphan_desc')}
            value={thresholds.orphan_hex_min_daily_volume}
            min={1}
            max={30}
            step={1}
            suffix=" pct/d"
            onChange={(v) =>
              setThresholds((th) => ({ ...th, orphan_hex_min_daily_volume: v }))
            }
          />
        </div>
      </section>

      {/* Ranking hierárquico (largura total) */}
      <InsightCard
        title={t('insights.card_rank_title')}
        subtitle={t('insights.card_rank_subtitle')}
        count={insights.prospectRankingTree.length}
      >
        {isLoadingByHex && !byHex ? (
          <div className="py-4 text-center text-atlas-muted text-xs">
            <Spinner size="sm" /> {t('packages.loading')}
          </div>
        ) : (
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-atlas-muted bg-atlas-darker sticky top-0 z-10">
                <tr>
                  <th className="text-left py-1.5 px-2">{t('insights.col_level')}</th>
                  <th className="text-right py-1.5 px-2">score</th>
                  <th className="text-right py-1.5 px-2">%DSP</th>
                  <th className="text-right py-1.5 px-2">{t('insights.col_orphan')}</th>
                  <th className="text-right py-1.5 px-2">{t('insights.col_under')}</th>
                  <th className="text-right py-1.5 px-2">{t('insights.col_volume')}</th>
                </tr>
              </thead>
              <tbody>
                {insights.prospectRankingTree.map((bdm) => (
                  <RankingTreeRow
                    key={bdm.key}
                    node={bdm}
                    expanded={expandedNodes}
                    onToggle={toggleNode}
                    path={bdm.key}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </InsightCard>

      {/* Demais cards em grid 2 colunas */}
      <div className="grid grid-cols-1 tablet:grid-cols-2 gap-4">
        {/* 1. Subutilizados */}
        <InsightCard
          title={t('insights.card_under_title')}
          subtitle={t('insights.card_under_subtitle', {
            pct: thresholds.cap_utilization_pct_threshold,
          })}
          count={insights.underutilized.length}
        >
          <div className="max-h-[280px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-atlas-muted">
                <tr>
                  <th className="text-left py-1">{t('packages.col_partner')}</th>
                  <th className="text-left py-1">DS</th>
                  <th className="text-right py-1">cap</th>
                  <th className="text-right py-1">d/d</th>
                  <th className="text-right py-1">%</th>
                  <th className="text-right py-1">gap</th>
                </tr>
              </thead>
              <tbody>
                {insights.underutilized.slice(0, 25).map((u) => (
                  <tr key={u.store_id} className="border-t border-atlas-navy">
                    <td className="py-1 text-atlas-light">{u.name}</td>
                    <td className="py-1 text-atlas-muted">{u.delivery_station}</td>
                    <td className="py-1 text-right text-atlas-light">{u.capacity}</td>
                    <td className="py-1 text-right text-atlas-light">{u.daily_avg.toFixed(1)}</td>
                    <td className="py-1 text-right text-red-400">
                      {u.cap_utilization_pct.toFixed(1)}%
                    </td>
                    <td className="py-1 text-right text-atlas-light">
                      {u.gap_absolute.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </InsightCard>

        {/* 2. DSP dominante */}
        <InsightCard
          title={t('insights.card_dsp_title')}
          subtitle={t('insights.card_dsp_subtitle', {
            pct: thresholds.dsp_dominance_share_pct_threshold,
          })}
          count={insights.dspDominant.length}
        >
          <div className="max-h-[280px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-atlas-muted">
                <tr>
                  <th className="text-left py-1">Bucket</th>
                  <th className="text-left py-1">DS</th>
                  <th className="text-right py-1">%DSP</th>
                  <th className="text-right py-1">Hubs</th>
                </tr>
              </thead>
              <tbody>
                {insights.dspDominant.slice(0, 25).map((d) => (
                  <tr key={d.bucket_ade} className="border-t border-atlas-navy">
                    <td className="py-1 text-atlas-light">{d.bucket_ade}</td>
                    <td className="py-1 text-atlas-muted">{d.delivery_station}</td>
                    <td className="py-1 text-right text-orange-400">
                      {d.dsp_share_pct.toFixed(1)}%
                    </td>
                    <td
                      className="py-1 text-right text-atlas-light"
                      title={d.active_hubs_names.join(', ')}
                    >
                      {d.active_hubs_in_territory}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </InsightCard>

        {/* 3. Hexes órfãos */}
        <InsightCard
          title={t('insights.card_orphan_title')}
          subtitle={t('insights.card_orphan_subtitle', {
            n: thresholds.orphan_hex_min_daily_volume,
          })}
          count={insights.orphanHexes.length}
        >
          {isLoadingByHex && !byHex ? (
            <div className="py-4 text-center text-atlas-muted text-xs">
              <Spinner size="sm" /> {t('packages.loading')}
            </div>
          ) : (
            <div className="max-h-[280px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="text-atlas-muted">
                  <tr>
                    <th className="text-left py-1">hex_id</th>
                    <th className="text-right py-1">d/dia</th>
                    <th className="text-right py-1">total</th>
                    <th className="text-right py-1">%DSP</th>
                  </tr>
                </thead>
                <tbody>
                  {insights.orphanHexes.slice(0, 25).map((o) => (
                    <tr key={o.hex_id} className="border-t border-atlas-navy">
                      <td className="py-1 font-mono text-atlas-light truncate max-w-[160px]">
                        {o.hex_id}
                      </td>
                      <td className="py-1 text-right text-atlas-light">
                        {o.daily_volume.toFixed(1)}
                      </td>
                      <td className="py-1 text-right text-atlas-muted">
                        {o.total_volume}
                      </td>
                      <td className="py-1 text-right text-orange-400">
                        {o.dsp_share_pct.toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </InsightCard>

        {/* 4. Queda súbita */}
        <InsightCard
          title={t('insights.card_drop_title')}
          subtitle={t('insights.card_drop_subtitle', {
            pct: thresholds.trend_drop_pct_threshold,
          })}
          count={insights.trendDrops.length}
        >
          <div className="max-h-[280px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-atlas-muted">
                <tr>
                  <th className="text-left py-1">{t('packages.col_partner')}</th>
                  <th className="text-left py-1">DS</th>
                  <th className="text-right py-1">Δ 7d</th>
                  <th className="text-right py-1">d/d</th>
                </tr>
              </thead>
              <tbody>
                {insights.trendDrops.slice(0, 25).map((d) => (
                  <tr key={d.store_id} className="border-t border-atlas-navy">
                    <td className="py-1 text-atlas-light">{d.name}</td>
                    <td className="py-1 text-atlas-muted">{d.delivery_station}</td>
                    <td className="py-1 text-right text-red-400">
                      ↓ {Math.abs(d.trend_7d_pct).toFixed(1)}%
                    </td>
                    <td className="py-1 text-right text-atlas-light">
                      {d.daily_avg.toFixed(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </InsightCard>

        {/* 5. Outliers geográficos */}
        <InsightCard
          title={t('insights.card_outlier_title')}
          subtitle={t('insights.card_outlier_subtitle')}
          count={insights.geographicOutliers.length}
        >
          <div className="max-h-[280px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="text-atlas-muted">
                <tr>
                  <th className="text-left py-1">{t('packages.col_partner')}</th>
                  <th className="text-left py-1">DS</th>
                  <th className="text-right py-1">raio</th>
                  <th className="text-right py-1">média DS</th>
                  <th className="text-right py-1">%IHS</th>
                </tr>
              </thead>
              <tbody>
                {insights.geographicOutliers.slice(0, 25).map((o) => (
                  <tr key={o.store_id} className="border-t border-atlas-navy">
                    <td className="py-1 text-atlas-light">{o.name}</td>
                    <td className="py-1 text-atlas-muted">{o.delivery_station}</td>
                    <td className="py-1 text-right text-atlas-light">{o.radius}m</td>
                    <td className="py-1 text-right text-atlas-muted">{o.avg_radius_ds}m</td>
                    <td className="py-1 text-right text-atlas-light">
                      {o.share_ds_ihs_pct.toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </InsightCard>
      </div>
    </div>
  );
};

export default InsightsTab;
