/**
 * MisconfiguredHubsCard.tsx
 * =========================
 * Card de warning exibido no topo da aba "Pacotes & Canais" quando há
 * hubs Active/Onboarding cadastrados no Salesforce com `capacity=0` OU
 * `radius=0`. Esse dado é real (não é ausência de informação): o parceiro
 * existe mas está sem cap ou raio configurado, o que impacta alocação de
 * pacotes. Precisa de ação manual do time de ops.
 *
 * Diferente dos insights de performance (subutilizados, queda súbita),
 * este warning NÃO depende de thresholds ajustáveis — é sempre binário:
 * "cap ou radius zerado" é sempre um problema.
 *
 * Funcionalidades:
 *  - Contagem total + breakdown por DS.
 *  - Lista expansível dos parceiros afetados.
 *  - Botão "Exportar CSV" com o recorte atual (pra enviar para ops).
 */

import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PartnerDeliveryStats } from '../../store/types';

interface Props {
  /** Parceiros já filtrados pelo recorte hierárquico ativo. */
  partners: PartnerDeliveryStats[];
}

function exportCSV(rows: PartnerDeliveryStats[]) {
  if (rows.length === 0) return;
  const header = 'store_id,name,delivery_station,bucket_ade,status,capacity,radius,daily_avg,total\n';
  const body = rows
    .map((p) =>
      [
        p.store_id,
        `"${(p.name || '').replace(/"/g, '""')}"`,
        p.delivery_station,
        p.bucket_ade ?? '',
        p.status ?? '',
        p.capacity,
        p.radius,
        p.daily_avg,
        p.total,
      ].join(','),
    )
    .join('\n');
  const blob = new Blob(['\uFEFF' + header + body], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'hubs_cap_radius_zerados.csv';
  a.click();
  URL.revokeObjectURL(url);
}

const MisconfiguredHubsCard: React.FC<Props> = ({ partners }) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const affected = useMemo(
    () => partners.filter((p) => p.cap_misconfigured),
    [partners],
  );

  const byDs = useMemo(() => {
    const acc: Record<string, number> = {};
    for (const p of affected) {
      acc[p.delivery_station] = (acc[p.delivery_station] || 0) + 1;
    }
    return Object.entries(acc).sort((a, b) => b[1] - a[1]);
  }, [affected]);

  // Quando não há parceiros misconfigured no recorte, o card some — não
  // queremos poluir a UI com um warning vazio.
  if (affected.length === 0) return null;

  return (
    <section className="bg-yellow-500/10 border border-yellow-500/40 rounded-lg p-4 flex flex-col gap-3">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className="text-yellow-400 text-lg leading-tight">⚠️</span>
          <div className="flex flex-col">
            <h3 className="text-yellow-300 font-semibold text-sm">
              {t('packages.misconfigured_title')}
            </h3>
            <span className="text-atlas-muted text-xs">
              {t('packages.misconfigured_subtitle', { n: affected.length })}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => exportCSV(affected)}
            className="text-xs px-2 py-1 rounded border border-yellow-500/50 text-yellow-300 hover:bg-yellow-500/20 transition-colors"
            title={t('packages.misconfigured_export')}
          >
            CSV
          </button>
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-xs px-2 py-1 rounded border border-atlas-navy text-atlas-light hover:bg-atlas-navy transition-colors"
          >
            {expanded ? t('packages.collapse') : t('packages.expand')}
          </button>
        </div>
      </header>

      {/* Breakdown por DS — sempre visível, leve */}
      <div className="flex flex-wrap gap-2">
        {byDs.map(([ds, n]) => (
          <span
            key={ds}
            className="px-2 py-1 bg-atlas-dark border border-atlas-navy rounded text-xs"
          >
            <span className="text-atlas-muted">{ds}</span>
            <span className="mx-1 text-atlas-muted">·</span>
            <span className="text-yellow-300 font-semibold">{n}</span>
          </span>
        ))}
      </div>

      {/* Lista expansível dos parceiros afetados */}
      {expanded && (
        <div className="max-h-[280px] overflow-y-auto bg-atlas-dark border border-atlas-navy rounded">
          <table className="w-full text-xs">
            <thead className="bg-atlas-darker sticky top-0 z-10">
              <tr>
                <th className="text-left px-2 py-1.5 text-atlas-muted">{t('packages.col_partner')}</th>
                <th className="text-left px-2 py-1.5 text-atlas-muted">DS</th>
                <th className="text-right px-2 py-1.5 text-atlas-muted">cap</th>
                <th className="text-right px-2 py-1.5 text-atlas-muted">raio</th>
                <th className="text-right px-2 py-1.5 text-atlas-muted">
                  {t('packages.col_daily_avg')}
                </th>
                <th className="text-right px-2 py-1.5 text-atlas-muted">
                  {t('packages.col_total')}
                </th>
              </tr>
            </thead>
            <tbody>
              {affected.map((p) => (
                <tr key={p.store_id} className="border-t border-atlas-navy">
                  <td className="px-2 py-1 text-atlas-light">{p.name}</td>
                  <td className="px-2 py-1 text-atlas-muted">{p.delivery_station}</td>
                  <td
                    className={`px-2 py-1 text-right font-mono ${
                      p.capacity === 0 ? 'text-yellow-300 font-semibold' : 'text-atlas-light'
                    }`}
                  >
                    {p.capacity}
                  </td>
                  <td
                    className={`px-2 py-1 text-right font-mono ${
                      p.radius === 0 ? 'text-yellow-300 font-semibold' : 'text-atlas-light'
                    }`}
                  >
                    {p.radius}
                  </td>
                  <td className="px-2 py-1 text-right text-atlas-light">
                    {p.daily_avg.toFixed(1)}
                  </td>
                  <td className="px-2 py-1 text-right text-atlas-muted">
                    {p.total.toLocaleString('pt-BR')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};

export default MisconfiguredHubsCard;
