/**
 * ShareIhsDspCard.tsx
 * ===================
 * Card resumo do %share de entregas IHS vs DSP, com seletor de DS.
 * Quando a DS é "all", mostra agregação geral.
 *
 * Usa um donut simples em SVG (sem chart.js) pra manter o card leve
 * e sem flicker de re-hydratação.
 */

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { DeliveryStationTotals } from '../../store/types';

interface Props {
  /** Totais por DS já recortados pela hierarquia aplicada. */
  stationTotals: Record<string, DeliveryStationTotals>;
  /** Nº de dias da janela (fonte de verdade: summary.period.days). */
  periodDays: number;
  selectedDs: string;
  onChangeDs: (ds: string) => void;
}

const RADIUS = 48;
const STROKE = 14;
const C = 2 * Math.PI * RADIUS;

const Donut: React.FC<{
  ihs: number;
  dsp: number;
  other: number;
}> = ({ ihs, dsp, other }) => {
  const total = ihs + dsp + other;
  if (total === 0) {
    return (
      <svg width={120} height={120} viewBox="0 0 120 120" aria-hidden="true">
        <circle cx={60} cy={60} r={RADIUS} fill="none" stroke="#263447" strokeWidth={STROKE} />
      </svg>
    );
  }
  const ihsLen = (ihs / total) * C;
  const dspLen = (dsp / total) * C;
  const otherLen = (other / total) * C;
  return (
    <svg width={120} height={120} viewBox="0 0 120 120" aria-hidden="true">
      <g transform="rotate(-90 60 60)">
        <circle cx={60} cy={60} r={RADIUS} fill="none" stroke="#263447" strokeWidth={STROKE} />
        {/* IHS — azul accent */}
        <circle
          cx={60}
          cy={60}
          r={RADIUS}
          fill="none"
          stroke="#00a8e1"
          strokeWidth={STROKE}
          strokeDasharray={`${ihsLen} ${C - ihsLen}`}
          strokeDashoffset={0}
        />
        {/* DSP — laranja */}
        <circle
          cx={60}
          cy={60}
          r={RADIUS}
          fill="none"
          stroke="#ff8c42"
          strokeWidth={STROKE}
          strokeDasharray={`${dspLen} ${C - dspLen}`}
          strokeDashoffset={-ihsLen}
        />
        {/* Other */}
        {otherLen > 0 && (
          <circle
            cx={60}
            cy={60}
            r={RADIUS}
            fill="none"
            stroke="#7b8fa3"
            strokeWidth={STROKE}
            strokeDasharray={`${otherLen} ${C - otherLen}`}
            strokeDashoffset={-(ihsLen + dspLen)}
          />
        )}
      </g>
    </svg>
  );
};

const ShareIhsDspCard: React.FC<Props> = ({ stationTotals, periodDays, selectedDs, onChangeDs }) => {
  const { t } = useTranslation();

  // Lista de DSs para o dropdown
  const stations = useMemo(
    () => Object.keys(stationTotals).sort(),
    [stationTotals],
  );

  // Dados do DS atual (ou agregado quando "all")
  const data = useMemo(() => {
    if (selectedDs === 'all') {
      let ihs = 0;
      let dsp = 0;
      let other = 0;
      for (const st of Object.values(stationTotals)) {
        ihs += st.ihs;
        dsp += st.dsp;
        other += st.other;
      }
      const total = ihs + dsp + other;
      return {
        ihs,
        dsp,
        other,
        total,
        ihs_pct: total ? (ihs / total) * 100 : 0,
        dsp_pct: total ? (dsp / total) * 100 : 0,
      };
    }
    const st = stationTotals[selectedDs];
    if (!st) return null;
    return {
      ihs: st.ihs,
      dsp: st.dsp,
      other: st.other,
      total: st.total,
      ihs_pct: st.ihs_share_pct,
      dsp_pct: st.dsp_share_pct,
    };
  }, [stationTotals, selectedDs]);

  if (!data) {
    return (
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4 text-atlas-muted text-sm">
        {t('packages.no_data_for_station')}
      </div>
    );
  }

  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-atlas-muted text-xs uppercase tracking-widest">
          {t('packages.share_title')}
        </h3>
        <select
          value={selectedDs}
          onChange={(e) => onChangeDs(e.target.value)}
          className="bg-atlas-darker border border-atlas-navy rounded px-2 py-1 text-atlas-light text-xs focus:outline-none focus:border-atlas-accent"
        >
          <option value="all">{t('packages.all_stations')}</option>
          {stations.map((ds) => (
            <option key={ds} value={ds}>
              {ds}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-4">
        <Donut ihs={data.ihs} dsp={data.dsp} other={data.other} />
        <div className="flex-1 flex flex-col gap-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#00a8e1' }} />
            <span className="text-atlas-light font-semibold">IHS</span>
            <span className="ml-auto text-atlas-muted">
              {data.ihs.toLocaleString('pt-BR')} ({data.ihs_pct.toFixed(1)}%)
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#ff8c42' }} />
            <span className="text-atlas-light font-semibold">DSP</span>
            <span className="ml-auto text-atlas-muted">
              {data.dsp.toLocaleString('pt-BR')} ({data.dsp_pct.toFixed(1)}%)
            </span>
          </div>
          {data.other > 0 && (
            <div className="flex items-center gap-2">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ background: '#7b8fa3' }} />
              <span className="text-atlas-light">Outros</span>
              <span className="ml-auto text-atlas-muted">
                {data.other.toLocaleString('pt-BR')}
              </span>
            </div>
          )}
          <div className="pt-2 mt-1 border-t border-atlas-navy">
            <span className="text-atlas-muted text-xs">
              {t('packages.total_label')}:{' '}
            </span>
            <span className="text-atlas-light font-semibold">
              {data.total.toLocaleString('pt-BR')}
            </span>
            <span className="text-atlas-muted text-xs ml-1">
              ({periodDays}d)
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ShareIhsDspCard;
