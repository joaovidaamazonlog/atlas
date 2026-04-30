/**
 * DeliveriesInAreaPanel.tsx
 * =========================
 * Bloco do ManualAnalysisPanel que mostra a composição REAL de entregas
 * (IHS vs DSP, parceiros presentes) dentro do raio da análise manual.
 *
 * Diferente do RecruitableResultPanel (que fala de DEMANDA), este bloco
 * mostra EXECUÇÃO: quem de fato está entregando na área nos últimos 15d.
 *
 * Reutiliza `selectedCells` já resolvido pelo evaluator (hexes dentro
 * do raio + jurisdição) — batemos esses hex_ids contra o
 * `deliveries_by_hex.json` para somar IHS/DSP e rankear parceiros.
 */

import React, { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import type { HexDeliveryBreakdown, EvaluatorResult } from '../../store/types';

interface Props {
  result: EvaluatorResult;
}

const DeliveriesInAreaPanel: React.FC<Props> = ({ result }) => {
  const { t } = useTranslation();
  const byHex = useStore((s) => s.deliveries.byHex);
  const isLoadingByHex = useStore((s) => s.deliveries.isLoadingByHex);
  const errorByHex = useStore((s) => s.deliveries.errorByHex);
  const loadByHex = useStore((s) => s.loadDeliveriesByHex);

  // Lazy-load: primeira vez que este painel monta, dispara o fetch.
  useEffect(() => {
    if (!byHex && !isLoadingByHex) {
      loadByHex();
    }
  }, [byHex, isLoadingByHex, loadByHex]);

  // IDs dos hexes selecionados pelo evaluator (strings)
  const selectedHexIds = useMemo(() => {
    const ids = new Set<string>();
    for (const f of result.selectedCells) {
      const hid = f.properties?.hex_id;
      if (hid) ids.add(String(hid));
    }
    return ids;
  }, [result.selectedCells]);

  // Somatório por canal + ranking de parceiros dentro da área
  const stats = useMemo(() => {
    if (!byHex || selectedHexIds.size === 0) {
      return { total: 0, ihs: 0, dsp: 0, ihs_pct: 0, dsp_pct: 0, partners: [] as Array<{ store_id: string; nome_empresa: string; count: number; share_pct: number }> };
    }

    let total = 0;
    let ihs = 0;
    let dsp = 0;
    const partnerCounts = new Map<string, { nome_empresa: string; count: number }>();

    const relevant: HexDeliveryBreakdown[] = byHex.hexes.filter((h) => selectedHexIds.has(h.hex_id));

    for (const h of relevant) {
      total += h.total;
      ihs += h.ihs;
      dsp += h.dsp;
      for (const tp of h.top_partners) {
        const prev = partnerCounts.get(tp.store_id);
        if (prev) {
          prev.count += tp.count;
        } else {
          partnerCounts.set(tp.store_id, {
            nome_empresa: tp.nome_empresa,
            count: tp.count,
          });
        }
      }
    }

    const partners = Array.from(partnerCounts.entries())
      .map(([store_id, v]) => ({
        store_id,
        nome_empresa: v.nome_empresa,
        count: v.count,
        share_pct: total > 0 ? (v.count / total) * 100 : 0,
      }))
      .sort((a, b) => b.count - a.count);

    return {
      total,
      ihs,
      dsp,
      ihs_pct: total > 0 ? (ihs / total) * 100 : 0,
      dsp_pct: total > 0 ? (dsp / total) * 100 : 0,
      partners,
    };
  }, [byHex, selectedHexIds]);

  // ---------- Estados ----------

  if (result.selectedCells.length === 0) return null;

  if (errorByHex) {
    return (
      <div className="rounded-lg p-3 bg-atlas-darker border border-yellow-500/40 text-yellow-300 text-xs">
        ⚠️ {t('manual_analysis.deliveries_load_error')}
      </div>
    );
  }

  if (!byHex && isLoadingByHex) {
    return (
      <div className="rounded-lg p-3 bg-atlas-darker text-atlas-muted text-xs text-center">
        {t('manual_analysis.deliveries_loading')}
      </div>
    );
  }

  if (!byHex) {
    // Summary ainda não chegou nem loading — silencioso (provável pipeline
    // ainda não foi rodado no ambiente).
    return null;
  }

  if (stats.total === 0) {
    return (
      <div className="rounded-lg p-3 bg-atlas-darker text-atlas-muted text-xs">
        {t('manual_analysis.deliveries_no_data')}
      </div>
    );
  }

  return (
    <div className="rounded-lg p-3 bg-atlas-darker flex flex-col gap-3">
      <header className="flex items-baseline justify-between">
        <h4 className="text-atlas-light text-xs font-semibold uppercase tracking-wider">
          {t('manual_analysis.deliveries_title')}
        </h4>
        <span className="text-atlas-muted text-[10px]">
          {byHex.period.days}d · {stats.total.toLocaleString('pt-BR')} pct
        </span>
      </header>

      {/* Barra de share horizontal */}
      <div>
        <div className="flex h-3 rounded overflow-hidden border border-atlas-navy">
          <div
            className="bg-atlas-accent flex items-center justify-center text-[9px] font-bold text-white"
            style={{ width: `${stats.ihs_pct}%` }}
            title={`IHS: ${stats.ihs}`}
          >
            {stats.ihs_pct > 15 && `${stats.ihs_pct.toFixed(0)}%`}
          </div>
          <div
            className="flex items-center justify-center text-[9px] font-bold text-white"
            style={{ width: `${stats.dsp_pct}%`, background: '#ff8c42' }}
            title={`DSP: ${stats.dsp}`}
          >
            {stats.dsp_pct > 15 && `${stats.dsp_pct.toFixed(0)}%`}
          </div>
        </div>
        <div className="flex items-center justify-between mt-1 text-[10px] text-atlas-muted">
          <span>
            <span className="inline-block w-2 h-2 rounded-sm bg-atlas-accent mr-1" />
            IHS {stats.ihs.toLocaleString('pt-BR')} ({stats.ihs_pct.toFixed(1)}%)
          </span>
          <span>
            <span
              className="inline-block w-2 h-2 rounded-sm mr-1"
              style={{ background: '#ff8c42' }}
            />
            DSP {stats.dsp.toLocaleString('pt-BR')} ({stats.dsp_pct.toFixed(1)}%)
          </span>
        </div>
      </div>

      {/* Top parceiros na área */}
      {stats.partners.length > 0 && (
        <div>
          <span className="text-atlas-muted text-[10px] uppercase tracking-wider">
            {t('manual_analysis.deliveries_partners_title')}
          </span>
          <ul className="mt-1 flex flex-col gap-1">
            {stats.partners.slice(0, 8).map((p) => (
              <li
                key={p.store_id}
                className="flex items-center justify-between text-xs bg-atlas-dark px-2 py-1 rounded"
              >
                <span className="text-atlas-light truncate max-w-[60%]">
                  {p.nome_empresa}
                </span>
                <span className="text-atlas-muted flex gap-2">
                  <span>{p.count.toLocaleString('pt-BR')}</span>
                  <span className="text-atlas-accent">{p.share_pct.toFixed(1)}%</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default DeliveriesInAreaPanel;
