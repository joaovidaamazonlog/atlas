/**
 * BasesHierarchy.tsx
 * ==================
 * Renders bases in a parent-child hierarchy: each canonical base is followed
 * by its anchored satellites (indented with `pl-8` and a `└─` glyph) and a
 * total row summing canonical + satellites.
 *
 * Satellite entries (`parentCanonical` is truthy) are suppressed at the top
 * level — they are only rendered underneath their parent canonical.
 *
 * Expansion state is persisted in `localStorage` under
 * `atlas-dashboard-expanded-canonicals`. On first load, all canonicals are
 * expanded by default.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseData } from '../../lib/reportUtils';

const STORAGE_KEY = 'atlas-dashboard-expanded-canonicals';

interface BasesHierarchyProps {
  bases: BaseData[];
}

// ---------------------------------------------------------------------------
// Aggregation helpers
// ---------------------------------------------------------------------------

interface TotalRow {
  numTerritories: number;
  dailyDemand: number;
  idealSlots: number;
  openSlots: number;
  coverage: number;     // weighted by idealSlots
  attainment: number;   // weighted by idealSlots
  activePartners: number;
}

/**
 * Computes the canonical + satellites total row at render time.
 * Never mutates any of its inputs.
 *
 * - numTerritories, dailyDemand, idealSlots, openSlots, partners.active:
 *   simple sum over canonical + satellites.
 * - coverage and attainment: weighted average by idealSlots; falls back to
 *   simple average when total idealSlots is zero (so the cell is never NaN).
 */
function computeTotalRow(canonical: BaseData, satellites: BaseData[]): TotalRow {
  const rows = [canonical, ...satellites];

  let numTerritories = 0;
  let dailyDemand = 0;
  let idealSlots = 0;
  let openSlots = 0;
  let activePartners = 0;
  let weightedCoverage = 0;
  let weightedAttainment = 0;

  for (const r of rows) {
    numTerritories += r.numTerritories || 0;
    dailyDemand += r.dailyDemand || 0;
    idealSlots += r.idealSlots || 0;
    openSlots += r.openSlots || 0;
    activePartners += (r.partners && r.partners.active) || 0;
    weightedCoverage += (r.coverage || 0) * (r.idealSlots || 0);
    weightedAttainment += (r.attainment || 0) * (r.idealSlots || 0);
  }

  const coverage =
    idealSlots > 0
      ? weightedCoverage / idealSlots
      : rows.reduce((s, r) => s + (r.coverage || 0), 0) / Math.max(rows.length, 1);
  const attainment =
    idealSlots > 0
      ? weightedAttainment / idealSlots
      : rows.reduce((s, r) => s + (r.attainment || 0), 0) / Math.max(rows.length, 1);

  return {
    numTerritories,
    dailyDemand,
    idealSlots,
    openSlots,
    coverage,
    attainment,
    activePartners,
  };
}

// ---------------------------------------------------------------------------
// LocalStorage helpers — isolated so they never throw on SSR / disabled storage
// ---------------------------------------------------------------------------

function readExpandedFromStorage(): Set<string> | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return new Set(parsed.filter((x): x is string => typeof x === 'string'));
  } catch {
    return null;
  }
}

function writeExpandedToStorage(expanded: Set<string>): void {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...expanded]));
  } catch {
    // Ignore quota / privacy errors — expansion is best-effort.
  }
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtDemand(n: number): string {
  return n.toLocaleString('pt-BR', { maximumFractionDigits: 1 });
}

function fmtInt(n: number): string {
  return n.toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const BasesHierarchy: React.FC<BasesHierarchyProps> = ({ bases }) => {
  const { t } = useTranslation();

  // Only canonicals render at the top level. Satellites are rendered under
  // their parent canonical (via the `satellites` array on the canonical row).
  const canonicals = useMemo(
    () => bases.filter((b) => !b.parentCanonical),
    [bases],
  );

  // Initialize expandedCanonicals: hydrate from localStorage if available,
  // otherwise default to "all canonicals expanded".
  const [expandedCanonicals, setExpandedCanonicals] = useState<Set<string>>(() => {
    const stored = readExpandedFromStorage();
    if (stored !== null) return stored;
    return new Set(canonicals.map((c) => c.code));
  });

  // On first render, if we defaulted to "all expanded" but the canonicals
  // array was empty at init time, re-populate once bases arrive.
  useEffect(() => {
    if (expandedCanonicals.size === 0 && canonicals.length > 0) {
      const stored = readExpandedFromStorage();
      if (stored === null) {
        setExpandedCanonicals(new Set(canonicals.map((c) => c.code)));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canonicals.length]);

  // Persist expansion state whenever it changes.
  useEffect(() => {
    writeExpandedToStorage(expandedCanonicals);
  }, [expandedCanonicals]);

  const toggleCanonical = useCallback((code: string) => {
    setExpandedCanonicals((prev) => {
      const next = new Set(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.add(code);
      }
      return next;
    });
  }, []);

  if (canonicals.length === 0) {
    return (
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg text-atlas-muted text-center py-6 text-sm">
        {t('dashboard.no_territory_found')}
      </div>
    );
  }

  const headerCells: { key: string; label: string; align: 'left' | 'right' }[] = [
    { key: 'code', label: t('dashboard.col_base'), align: 'left' },
    { key: 'bdm', label: t('dashboard.filter_bdm'), align: 'left' },
    { key: 'numTerritories', label: t('dashboard.kpi_territories'), align: 'right' },
    { key: 'dailyDemand', label: t('dashboard.col_daily_demand'), align: 'right' },
    { key: 'coverage', label: t('dashboard.kpi_avg_coverage'), align: 'right' },
    { key: 'attainment', label: t('dashboard.col_attainment'), align: 'right' },
    { key: 'partners', label: t('dashboard.kpi_active_partners_summary'), align: 'right' },
    { key: 'expand', label: '', align: 'left' },
  ];

  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-atlas-darker">
            <tr>
              {headerCells.map((h) => (
                <th
                  key={h.key}
                  className={`px-3 py-3 text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap ${
                    h.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {canonicals.map((canonical) => {
              const satellites = canonical.satellites ?? [];
              const hasSatellites = satellites.length > 0;
              const isExpanded = expandedCanonicals.has(canonical.code);
              const total = hasSatellites
                ? computeTotalRow(canonical, satellites)
                : null;

              return (
                <React.Fragment key={canonical.code}>
                  {/* Canonical row */}
                  <tr className="border-b border-atlas-navy hover:bg-atlas-navy transition-colors">
                    <td className="px-3 py-2 text-atlas-light font-semibold whitespace-nowrap">
                      {canonical.code}
                    </td>
                    <td className="px-3 py-2 text-atlas-muted whitespace-nowrap">
                      {canonical.bdmName ?? canonical.bdm}
                    </td>
                    <td className="px-3 py-2 text-atlas-light text-right">
                      {fmtInt(canonical.numTerritories)}
                    </td>
                    <td className="px-3 py-2 text-atlas-light text-right">
                      {fmtDemand(canonical.dailyDemand)}
                    </td>
                    <td className="px-3 py-2 text-atlas-light text-right">
                      {fmtPct(canonical.coverage)}
                    </td>
                    <td className="px-3 py-2 text-atlas-light text-right">
                      {fmtPct(canonical.attainment)}
                    </td>
                    <td className="px-3 py-2 text-green-400 text-right">
                      {fmtInt(canonical.partners?.active ?? 0)}
                    </td>
                    <td className="px-3 py-2">
                      {hasSatellites ? (
                        <button
                          type="button"
                          onClick={() => toggleCanonical(canonical.code)}
                          aria-expanded={isExpanded}
                          aria-label={
                            isExpanded
                              ? t('dashboard.toggle_collapse')
                              : t('dashboard.toggle_expand')
                          }
                          className="min-h-[44px] min-w-[44px] flex items-center justify-center text-atlas-accent hover:text-atlas-light transition-colors"
                        >
                          <span
                            aria-hidden="true"
                            className={`inline-block transition-transform ${
                              isExpanded ? 'rotate-90' : ''
                            }`}
                          >
                            ▶
                          </span>
                        </button>
                      ) : null}
                    </td>
                  </tr>

                  {/* Satellite rows — rendered only when expanded */}
                  {hasSatellites && isExpanded &&
                    satellites.map((sat) => (
                      <tr
                        key={`${canonical.code}-${sat.code}`}
                        className="border-b border-atlas-navy bg-atlas-darker/50 hover:bg-atlas-navy transition-colors"
                      >
                        <td className="pl-8 pr-3 py-2 text-atlas-light whitespace-nowrap">
                          <span className="text-atlas-muted mr-2" aria-hidden="true">
                            └─
                          </span>
                          {sat.code}
                        </td>
                        <td className="px-3 py-2 text-atlas-muted whitespace-nowrap">
                          {sat.bdmName ?? sat.bdm}
                        </td>
                        <td className="px-3 py-2 text-atlas-light text-right">
                          {fmtInt(sat.numTerritories)}
                        </td>
                        <td className="px-3 py-2 text-atlas-light text-right">
                          {fmtDemand(sat.dailyDemand)}
                        </td>
                        <td className="px-3 py-2 text-atlas-light text-right">
                          {fmtPct(sat.coverage)}
                        </td>
                        <td className="px-3 py-2 text-atlas-light text-right">
                          {fmtPct(sat.attainment)}
                        </td>
                        <td className="px-3 py-2 text-green-400 text-right">
                          {fmtInt(sat.partners?.active ?? 0)}
                        </td>
                        <td className="px-3 py-2" />
                      </tr>
                    ))}

                  {/* Total row — only when canonical has satellites */}
                  {hasSatellites && total && (
                    <tr className="border-b-2 border-atlas-accent/30 bg-atlas-darker">
                      <td
                        colSpan={2}
                        className="px-3 py-2 text-atlas-accent font-semibold whitespace-nowrap"
                      >
                        {t('dashboard.total_row_label', { canonical: canonical.code })}
                      </td>
                      <td className="px-3 py-2 text-atlas-accent text-right font-semibold">
                        {fmtInt(total.numTerritories)}
                      </td>
                      <td className="px-3 py-2 text-atlas-accent text-right font-semibold">
                        {fmtDemand(total.dailyDemand)}
                      </td>
                      <td className="px-3 py-2 text-atlas-accent text-right font-semibold">
                        {fmtPct(total.coverage)}
                      </td>
                      <td className="px-3 py-2 text-atlas-accent text-right font-semibold">
                        {fmtPct(total.attainment)}
                      </td>
                      <td className="px-3 py-2 text-atlas-accent text-right font-semibold">
                        {fmtInt(total.activePartners)}
                      </td>
                      <td className="px-3 py-2" />
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default BasesHierarchy;
