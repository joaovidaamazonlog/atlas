import React from 'react';
import { useTranslation } from 'react-i18next';

interface KpiCardProps {
  label: string;
  value: string | number;
  unit?: string;
  trend?: 'up' | 'down' | 'neutral';
  goal?: number;
  className?: string;
  /**
   * Classe extra aplicada no valor numérico (sobrescreve `valueColor`
   * interno quando informada). Usado para KPIs que têm semântica de
   * cor própria — ex: variação positiva/negativa — sem depender de
   * `goal`.
   */
  valueClassName?: string;
}

const TrendIcon: React.FC<{ trend: 'up' | 'down' | 'neutral' }> = ({ trend }) => {
  if (trend === 'up') return <span className="text-green-400 text-sm">▲</span>;
  if (trend === 'down') return <span className="text-red-400 text-sm">▼</span>;
  return <span className="text-atlas-muted text-sm">—</span>;
};

const KpiCard: React.FC<KpiCardProps> = React.memo(
  ({ label, value, unit, trend, goal, className = '', valueClassName }) => {
    const { t } = useTranslation();
    const numericValue = typeof value === 'number' ? value : parseFloat(String(value));
    const isNA = value === 'N/A' || isNaN(numericValue);

    let valueColor = 'text-atlas-light';
    if (!isNA && goal !== undefined) {
      valueColor = numericValue >= goal ? 'text-green-400' : 'text-red-400';
    }
    // Override explícito tem prioridade sobre a lógica baseada em goal.
    if (valueClassName) valueColor = valueClassName;

    return (
      <div
        className={`bg-atlas-dark border border-atlas-navy rounded-lg p-3 flex flex-col gap-0.5 ${className}`}
      >
        <span className="text-atlas-muted text-[10px] uppercase tracking-wide truncate">{label}</span>
        <div className="flex items-end gap-1">
          <span className={`text-xl font-bold leading-none ${valueColor}`}>{value}</span>
          {unit && !isNA && (
            <span className="text-atlas-muted text-xs mb-0.5">{unit}</span>
          )}
          {trend && (
            <span className="mb-0.5 ml-1">
              <TrendIcon trend={trend} />
            </span>
          )}
        </div>
        {goal !== undefined && !isNA && (
          <span className="text-atlas-muted text-[10px]">{t('dashboard.kpi_goal')} {goal}{unit ?? ''}</span>
        )}
      </div>
    );
  }
);

KpiCard.displayName = 'KpiCard';

export default KpiCard;
