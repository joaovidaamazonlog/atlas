/**
 * PartnerDrillDown.tsx
 * ====================
 * Drill-down de um parceiro hub específico, dentro da aba "Pacotes & Canais".
 *
 * Conteúdo:
 * - Gráfico de barras: volume por dia nos últimos dias da janela.
 * - Tabela paginada: tracking_id, scan_datetime_br, reason_code, botão 📍.
 * - Botão 📍 fecha o dashboard, coloca pin no mapa via `setPackagePin`.
 *
 * Detalhes carregados lazy: dispara `loadDeliveryDetailForDS` e filtra
 * localmente por `store_id`. Cache feito no store para evitar re-fetch.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bar } from 'react-chartjs-2';
import { useStore } from '../../store';
import type { PartnerDeliveryStats } from '../../store/types';

interface Props {
  partner: PartnerDeliveryStats;
  onRequestClose: () => void;
}

const PAGE_SIZE = 50;

const PartnerDrillDown: React.FC<Props> = ({ partner, onRequestClose }) => {
  const { t } = useTranslation();
  const loadDetail = useStore((s) => s.loadDeliveryDetailForDS);
  const detailByDs = useStore((s) => s.deliveries.detailByDs);
  const loadingDetailDs = useStore((s) => s.deliveries.loadingDetailDs);
  const setPackagePin = useStore((s) => s.setPackagePin);
  const setActiveTab = useStore((s) => s.setActiveTab);
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);

  const [page, setPage] = useState(0);

  const ds = partner.delivery_station;
  const allRecords = detailByDs[ds];
  const isLoading = loadingDetailDs === ds && !allRecords;

  useEffect(() => {
    if (!allRecords) {
      loadDetail(ds);
    }
  }, [ds, allRecords, loadDetail]);

  // Filtra o detalhe pelo store_id do parceiro atual
  const records = useMemo(() => {
    if (!allRecords) return [];
    return allRecords
      .filter((r) => r.st === partner.store_id)
      .sort((a, b) => b.sdt.localeCompare(a.sdt));
  }, [allRecords, partner.store_id]);

  const totalPages = Math.ceil(records.length / PAGE_SIZE);
  const pageRecords = records.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Dados do gráfico (daily_series já vem do summary)
  const chartData = useMemo(
    () => ({
      labels: partner.daily_series.map((d) => d.date.slice(5)),
      datasets: [
        {
          label: t('packages.drill_daily_label'),
          data: partner.daily_series.map((d) => d.total),
          backgroundColor: '#00a8e1cc',
          borderColor: '#00a8e1',
          borderWidth: 1,
        },
      ],
    }),
    [partner.daily_series, t],
  );

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#7b8fa3', font: { size: 10 } }, grid: { display: false } },
      y: { ticks: { color: '#7b8fa3', font: { size: 10 } }, grid: { color: '#1e2a38' } },
    },
  };

  const handlePinPackage = (rec: typeof pageRecords[number]) => {
    if (rec.lat === undefined || rec.lon === undefined) return;
    setPackagePin({
      lat: rec.lat,
      lon: rec.lon,
      tracking_id: rec.tid,
      scan_datetime_br: rec.sdt,
      reason_code: rec.rc,
      partner_name: rec.ne || partner.name,
      canal: rec.ch,
    });
    // Fecha o dashboard e dá fitBounds
    onRequestClose();
    setActiveTab('filters');
    // Timeout curto para o mapa estar totalmente em foco antes do fit.
    setTimeout(() => {
      fitBoundsRef.current?.([[rec.lat!, rec.lon!]]);
    }, 120);
  };

  return (
    <div className="bg-atlas-darker border border-atlas-accent rounded-lg p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col">
          <h3 className="text-atlas-light font-semibold text-base">
            {partner.name}
            {partner.is_unknown && (
              <span className="ml-2 px-2 py-0.5 text-[10px] rounded bg-yellow-500/20 border border-yellow-500/40 text-yellow-300 font-normal">
                {t('packages.unknown_badge')}
              </span>
            )}
          </h3>
          <span className="text-atlas-muted text-xs">
            {partner.delivery_station}
            {partner.bucket_ade ? ` · ${partner.bucket_ade}` : ''} ·{' '}
            store_id {partner.store_id}
          </span>
        </div>
        <button
          onClick={onRequestClose}
          className="text-atlas-muted hover:text-atlas-light text-lg leading-none"
          aria-label={t('common.close')}
        >
          ×
        </button>
      </div>

      {/* Chart */}
      <div style={{ height: 180 }} className="bg-atlas-dark rounded border border-atlas-navy p-2">
        <Bar data={chartData} options={chartOptions} />
      </div>

      {/* Tabela */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-atlas-muted text-xs uppercase tracking-widest">
            {t('packages.drill_packages_title')}
          </span>
          <span className="text-atlas-muted text-xs">
            {records.length.toLocaleString('pt-BR')} {t('packages.packages_unit')}
          </span>
        </div>

        {isLoading ? (
          <div className="text-atlas-muted text-sm py-6 text-center">
            {t('packages.drill_loading')}
          </div>
        ) : records.length === 0 ? (
          <div className="text-atlas-muted text-sm py-6 text-center">
            {t('packages.drill_no_records')}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto border border-atlas-navy rounded bg-atlas-dark">
              <table className="w-full text-xs">
                <thead className="bg-atlas-darker">
                  <tr>
                    <th className="px-2 py-2 text-left text-atlas-muted font-semibold">
                      tracking_id
                    </th>
                    <th className="px-2 py-2 text-left text-atlas-muted font-semibold">
                      {t('packages.col_datetime')}
                    </th>
                    <th className="px-2 py-2 text-left text-atlas-muted font-semibold">
                      reason_code
                    </th>
                    <th className="px-2 py-2 text-right text-atlas-muted font-semibold">
                      &nbsp;
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {pageRecords.map((rec) => (
                    <tr
                      key={rec.tid}
                      className="border-t border-atlas-navy hover:bg-atlas-navy transition-colors"
                    >
                      <td className="px-2 py-1.5 text-atlas-light font-mono">{rec.tid}</td>
                      <td className="px-2 py-1.5 text-atlas-muted">{rec.sdt}</td>
                      <td className="px-2 py-1.5 text-atlas-muted">{rec.rc || '—'}</td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          onClick={() => handlePinPackage(rec)}
                          disabled={rec.lat === undefined || rec.lon === undefined}
                          className="px-2 py-0.5 text-[11px] rounded border border-atlas-accent text-atlas-accent hover:bg-atlas-accent hover:text-white disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-atlas-accent transition-colors"
                          title={t('packages.view_on_map')}
                        >
                          📍 {t('packages.view_on_map')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-2 text-xs">
                <span className="text-atlas-muted">
                  {t('packages.page')} {page + 1} / {totalPages}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="px-2 py-1 rounded bg-atlas-dark border border-atlas-navy text-atlas-light disabled:opacity-40"
                  >
                    ← {t('packages.prev')}
                  </button>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page >= totalPages - 1}
                    className="px-2 py-1 rounded bg-atlas-dark border border-atlas-navy text-atlas-light disabled:opacity-40"
                  >
                    {t('packages.next')} →
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default PartnerDrillDown;
