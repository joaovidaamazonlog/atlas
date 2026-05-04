/**
 * AreaAlignmentWarning.tsx
 * ========================
 * Card de "sanidade" que cruza o plano (CP-SAT) com a execução real
 * (Fase 6) na área de análise manual e sinaliza divergências.
 *
 * Respostas que esse card entrega:
 *
 *   - Plano e realidade estão alinhados? (cor do semáforo)
 *   - Se divergem, para que lado e qual a hipótese mais provável?
 *     * Plano aloca muito mas execução é fraca → cap/raio cadastrado pode
 *       estar desalinhado com a operação (parceiros não entregam o que
 *       o otimizador assumiu que entregariam).
 *     * Plano aloca pouco mas execução é forte → volume cresceu ou
 *       parceiros estão absorvendo acima do cap cadastrado.
 *
 * Thresholds de divergência (em pontos percentuais, comparando
 * `planAllocatedPct` com `hubSharePct`):
 *
 *   |Δ| < 15  → verde  (alinhado)
 *   |Δ| 15–35 → amarelo (divergência moderada)
 *   |Δ| > 35  → vermelho (divergência crítica)
 *
 * Este componente NÃO decide viabilidade — é puramente informativo.
 * A decisão de "viável / não viável" continua vindo do CP-SAT,
 * preservando a semântica de planejamento.
 */

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import type { EvaluatorResult, HexDeliveryBreakdown } from '../../store/types';

interface Props {
  result: EvaluatorResult;
}

type Severity = 'aligned' | 'moderate' | 'critical';

const SEVERITY_BG: Record<Severity, string> = {
  aligned: 'bg-green-500/5 border-green-500/30',
  moderate: 'bg-yellow-500/5 border-yellow-500/30',
  critical: 'bg-red-500/5 border-red-500/40',
};

const SEVERITY_TEXT: Record<Severity, string> = {
  aligned: 'text-green-400',
  moderate: 'text-yellow-400',
  critical: 'text-red-400',
};

const SEVERITY_ICON: Record<Severity, string> = {
  aligned: '✅',
  moderate: '⚠️',
  critical: '🚨',
};

const AreaAlignmentWarning: React.FC<Props> = ({ result }) => {
  const { t } = useTranslation();
  const byHex = useStore((s) => s.deliveries.byHex);

  // Mesmos ids já calculados pelo evaluator — deixamos local aqui para
  // evitar prop-drilling do painel pai.
  const selectedHexIds = useMemo(() => {
    const ids = new Set<string>();
    for (const f of result.selectedCells) {
      const hid = f.properties?.hex_id;
      if (hid) ids.add(String(hid));
    }
    return ids;
  }, [result.selectedCells]);

  // Computa execução real agregando o deliveries_by_hex nos hexes da área.
  const execution = useMemo(() => {
    if (!byHex || selectedHexIds.size === 0) {
      return null;
    }
    let totalAbs = 0;
    let ihsAbs = 0;
    let dspAbs = 0;
    const relevant: HexDeliveryBreakdown[] = byHex.hexes.filter((h) =>
      selectedHexIds.has(h.hex_id),
    );
    for (const h of relevant) {
      totalAbs += h.total;
      ihsAbs += h.ihs;
      dspAbs += h.dsp;
    }
    const days = Math.max(byHex.period.days || 1, 1);
    return {
      totalDaily: totalAbs / days,
      ihsDaily: ihsAbs / days,
      dspDaily: dspAbs / days,
      totalAbs,
      ihsAbs,
      dspAbs,
      days,
    };
  }, [byHex, selectedHexIds]);

  // Compara plano × realidade e deriva severidade + hipótese narrativa.
  const analysis = useMemo(() => {
    if (!execution || execution.totalAbs === 0) return null;
    if (result.totalDemand <= 0) return null;

    const { totalDemand, residualDemand } = result;

    // Share que o plano aloca a parceiros Active no território
    const planAllocatedDaily = Math.max(totalDemand - residualDemand, 0);
    const planAllocatedPct = Math.min(
      (planAllocatedDaily / Math.max(totalDemand, 1e-9)) * 100,
      100,
    );

    // Share real entregue por Hub Delivery (vs DSP)
    const hubSharePct =
      execution.totalDaily > 0
        ? (execution.ihsDaily / execution.totalDaily) * 100
        : 0;
    const dspSharePct =
      execution.totalDaily > 0
        ? (execution.dspDaily / execution.totalDaily) * 100
        : 0;

    // Divergência — ponto-percentual entre plano (% alocado) e real (% Hub)
    const delta = planAllocatedPct - hubSharePct;
    const absDelta = Math.abs(delta);

    let severity: Severity = 'aligned';
    if (absDelta > 35) severity = 'critical';
    else if (absDelta > 15) severity = 'moderate';

    // Hipótese narrativa. `delta > 0` = plano aloca mais do que a realidade
    // entrega via Hub; `delta < 0` = realidade supera o plano.
    //
    // Pistas adicionais para escolher a mensagem:
    //   - DSP alto + plano > real  → cadastro provavelmente desatualizado
    //     (raio ou cap diferente da operação) permitindo o DSP entrar.
    //   - DSP baixo + plano > real → parceiro ativo mas ocioso (cap cheio
    //     no cadastro, mas entrega menos no mundo real).
    //   - plano < real              → operação superou o plano (volume
    //     cresceu, parceiros absorvem além do cap cadastrado).
    let hypothesisKey: string;
    if (severity === 'aligned') {
      hypothesisKey = 'manual_analysis.alignment_ok';
    } else if (delta > 0) {
      // Plano superou realidade
      if (dspSharePct > 25) {
        hypothesisKey = 'manual_analysis.alignment_cadastro_vs_dsp';
      } else {
        hypothesisKey = 'manual_analysis.alignment_parceiro_ocioso';
      }
    } else {
      // Realidade superou plano
      hypothesisKey = 'manual_analysis.alignment_volume_cresceu';
    }

    return {
      severity,
      delta,
      absDelta,
      planAllocatedPct,
      hubSharePct,
      dspSharePct,
      hypothesisKey,
    };
  }, [execution, result]);

  // Estados vazios — sem execução ou sem plano, não há o que comparar.
  if (!analysis || !execution) return null;

  const { severity, planAllocatedPct, hubSharePct, dspSharePct, absDelta, hypothesisKey } =
    analysis;

  return (
    <div
      className={`rounded-lg p-3 border flex flex-col gap-2 ${SEVERITY_BG[severity]}`}
      data-testid="area-alignment-warning"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-sm" aria-hidden="true">
          {SEVERITY_ICON[severity]}
        </span>
        <span className={`text-xs font-semibold uppercase tracking-wider ${SEVERITY_TEXT[severity]}`}>
          {t(`manual_analysis.alignment_title_${severity}`)}
        </span>
        <span className="ml-auto text-[10px] text-atlas-muted font-mono">
          Δ {absDelta.toFixed(0)}pp
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded bg-atlas-darker/60 px-2 py-1.5">
          <div className="text-atlas-muted text-[10px]">
            {t('manual_analysis.alignment_plan_allocated')}
          </div>
          <div className="text-atlas-light font-semibold">
            {planAllocatedPct.toFixed(0)}%
          </div>
        </div>
        <div className="rounded bg-atlas-darker/60 px-2 py-1.5">
          <div className="text-atlas-muted text-[10px]">
            {t('manual_analysis.alignment_real_hub')}
          </div>
          <div className="text-atlas-light font-semibold">
            {hubSharePct.toFixed(0)}%
            {dspSharePct > 0 && (
              <span className="text-atlas-muted font-normal ml-1">
                · DSP {dspSharePct.toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      </div>

      <p className="text-xs text-atlas-light leading-snug">{t(hypothesisKey)}</p>
    </div>
  );
};

export default AreaAlignmentWarning;
