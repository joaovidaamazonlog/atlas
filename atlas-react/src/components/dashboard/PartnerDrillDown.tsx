/**
 * PartnerDrillDown.tsx
 * ====================
 * Drill-down de um parceiro hub específico, dentro da aba "Dive Deep".
 *
 * Conteúdo:
 * - Gráfico de barras diário com valor em cima de cada coluna.
 * - Tabela paginada: tracking_id, scan_datetime_br, reason_code, botão 📍.
 * - Botão 📍 por linha: adiciona o pacote aos pins do mapa (não fecha
 *   o dashboard). Múltiplos pins acumulam.
 * - Botão "Ver todos no mapa": plota todos os pacotes do parceiro.
 * - Botão "Limpar pins": remove todos os pins de pacote ativos.
 *
 * Ao montar: foca o mapa só neste parceiro (`focusedPartnerSalesforceId`)
 * e centraliza a view na posição dele. Ao fechar: limpa o foco e todos
 * os pins ativos.
 *
 * Detalhes carregados lazy: dispara `loadDeliveryDetailForDS` e filtra
 * localmente por `store_id`. Cache feito no store para evitar re-fetch.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bar } from 'react-chartjs-2';
import type { ChartOptions, Plugin } from 'chart.js';
import { useStore } from '../../store';
import type { PartnerDeliveryStats } from '../../store/types';

interface Props {
  partner: PartnerDeliveryStats;
  onRequestClose: () => void;
}

const PAGE_SIZE = 50;

/**
 * Plugin Chart.js inline para renderizar o valor numérico em cima de cada
 * barra. Evita a dependência pesada do `chartjs-plugin-datalabels` — para
 * este caso (barras verticais, números simples), basta iterar os metas
 * do dataset no afterDatasetsDraw.
 */
const barValueLabelsPlugin: Plugin<'bar'> = {
  id: 'barValueLabels',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    chart.data.datasets.forEach((dataset, idx) => {
      const meta = chart.getDatasetMeta(idx);
      if (meta.hidden) return;
      meta.data.forEach((element, pointIdx) => {
        const raw = (dataset.data as number[])[pointIdx];
        if (raw == null || raw === 0) return;
        const { x, y } = element.getProps(['x', 'y'], true) as { x: number; y: number };
        ctx.save();
        ctx.font = '600 10px sans-serif';
        ctx.fillStyle = '#d5e1ee';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(String(raw), x, y - 2);
        ctx.restore();
      });
    });
  },
};

const PartnerDrillDown: React.FC<Props> = ({ partner, onRequestClose }) => {
  const { t } = useTranslation();
  const loadDetail = useStore((s) => s.loadDeliveryDetailForDS);
  const detailByDs = useStore((s) => s.deliveries.detailByDs);
  const loadingDetailDs = useStore((s) => s.deliveries.loadingDetailDs);
  const addPackagePin = useStore((s) => s.addPackagePin);
  const clearPackagePins = useStore((s) => s.clearPackagePins);
  const packagePins = useStore((s) => s.packagePins);
  const setFocused = useStore((s) => s.setFocusedPartnerSalesforceId);
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);
  const allMarkers = useStore((s) => s.allMarkersData);

  const [page, setPage] = useState(0);
  // Filtros locais da tabela — NÃO afetam o gráfico (daily_series vem do
  // summary e mantém a visão mensal completa) nem o contador total.
  const [searchTid, setSearchTid] = useState('');
  const [filterDate, setFilterDate] = useState('');

  const ds = partner.delivery_station;
  const allRecords = detailByDs[ds];
  const isLoading = loadingDetailDs === ds && !allRecords;

  useEffect(() => {
    if (!allRecords) {
      loadDetail(ds);
    }
  }, [ds, allRecords, loadDetail]);

  // ---- Foco no parceiro no mapa: mount/unmount ----
  // Ao abrir o drill-down, centralizamos e escondemos os outros parceiros.
  // Ao fechar, limpamos o foco e os pins — a visualização do mapa volta
  // ao normal (todos os parceiros visíveis, sem pins de pacotes).
  useEffect(() => {
    setFocused(partner.salesforce_id);
    // Tenta centralizar no parceiro. Se o summary traz lat/lon usa direto,
    // senão busca em allMarkers pelo salesforce_id (fonte autoritativa).
    const pLat = partner.lat ?? null;
    const pLon = partner.lon ?? null;
    const fallback = allMarkers.find((p) => p.salesforce_id === partner.salesforce_id);
    const targetLat = pLat ?? fallback?.lat ?? null;
    const targetLon = pLon ?? fallback?.lon ?? null;
    if (targetLat != null && targetLon != null) {
      // Dois frames de delay: o primeiro garante que o layout React já
      // aplicou o split (dashboard abrindo altera o viewport do mapa);
      // o segundo cede tempo para o ResizeObserver invalidar o tamanho
      // antes do fit-bounds. Sem isso, o mapa centraliza na posição usando
      // o viewport antigo e o parceiro fica fora da área visível.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          fitBoundsRef.current?.([[targetLat, targetLon]]);
        });
      });
    }
    return () => {
      setFocused(null);
      clearPackagePins();
    };
    // Intencional: roda só no mount/unmount por drill-down aberto.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partner.salesforce_id]);

  // Lista completa do parceiro (sem filtros locais). Usada para
  // determinar disponibilidade de dados e range de datas.
  const recordsAll = useMemo(() => {
    if (!allRecords) return [];
    return allRecords
      .filter((r) => r.st === partner.store_id)
      .sort((a, b) => b.sdt.localeCompare(a.sdt));
  }, [allRecords, partner.store_id]);

  // Range [dateMin, dateMax] disponível no parceiro (YYYY-MM-DD) — alimenta
  // os atributos `min`/`max` do input date para o usuário não conseguir
  // escolher uma data fora da janela da Fase 6.
  const dateRange = useMemo(() => {
    if (recordsAll.length === 0) return { min: '', max: '' };
    let min = recordsAll[0].sdt.slice(0, 10);
    let max = min;
    for (const r of recordsAll) {
      const d = r.sdt.slice(0, 10);
      if (d < min) min = d;
      if (d > max) max = d;
    }
    return { min, max };
  }, [recordsAll]);

  // Lista filtrada pela busca de tracking_id + data. É o que alimenta
  // a tabela, o contador "N pacotes", o botão "Ver todos no mapa" e a
  // paginação. O gráfico diário NÃO é afetado — continua mostrando a
  // janela completa vinda do summary.
  const records = useMemo(() => {
    const q = searchTid.trim().toLowerCase();
    return recordsAll.filter((r) => {
      if (filterDate && !r.sdt.startsWith(filterDate)) return false;
      if (q && !r.tid.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [recordsAll, searchTid, filterDate]);

  // Reseta paginação quando os filtros mudam — evita ficar preso numa
  // página vazia depois de digitar/selecionar data.
  useEffect(() => {
    setPage(0);
  }, [searchTid, filterDate]);

  // Pacotes com coordenadas (elegíveis para pin)
  const recordsWithCoords = useMemo(
    () => records.filter((r) => r.lat !== undefined && r.lon !== undefined),
    [records],
  );

  const totalPages = Math.ceil(records.length / PAGE_SIZE);
  const pageRecords = records.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const pinnedTrackingIds = useMemo(
    () => new Set(packagePins.map((p) => p.tracking_id)),
    [packagePins],
  );

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

  const chartOptions: ChartOptions<'bar'> = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      // Espaço extra no topo do eixo Y para o label do valor não cortar
      // quando o ponto está no máximo.
      layout: { padding: { top: 14 } },
      scales: {
        x: {
          ticks: { color: '#7b8fa3', font: { size: 10 } },
          grid: { display: false },
        },
        y: {
          ticks: { color: '#7b8fa3', font: { size: 10 } },
          grid: { color: '#1e2a38' },
        },
      },
    }),
    [],
  );

  const handlePinPackage = (rec: (typeof pageRecords)[number]) => {
    if (rec.lat === undefined || rec.lon === undefined) return;
    addPackagePin({
      lat: rec.lat,
      lon: rec.lon,
      tracking_id: rec.tid,
      scan_datetime_br: rec.sdt,
      reason_code: rec.rc,
      partner_name: rec.ne || partner.name,
      canal: rec.ch,
    });
  };

  const handlePinAll = () => {
    for (const rec of recordsWithCoords) {
      addPackagePin({
        lat: rec.lat!,
        lon: rec.lon!,
        tracking_id: rec.tid,
        scan_datetime_br: rec.sdt,
        reason_code: rec.rc,
        partner_name: rec.ne || partner.name,
        canal: rec.ch,
      });
    }
  };

  const handleClearAll = () => {
    clearPackagePins();
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
      <div style={{ height: 200 }} className="bg-atlas-dark rounded border border-atlas-navy p-2">
        <Bar data={chartData} options={chartOptions} plugins={[barValueLabelsPlugin]} />
      </div>

      {/* Tabela */}
      <div>
        <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
          <span className="text-atlas-muted text-xs uppercase tracking-widest">
            {t('packages.drill_packages_title')}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-atlas-muted text-xs">
              {records.length === recordsAll.length
                ? `${records.length.toLocaleString('pt-BR')} ${t('packages.packages_unit')}`
                : `${records.length.toLocaleString('pt-BR')} / ${recordsAll.length.toLocaleString('pt-BR')} ${t('packages.packages_unit')}`}
            </span>
            {recordsWithCoords.length > 0 && (
              <button
                onClick={handlePinAll}
                disabled={recordsWithCoords.length === 0}
                className="px-2 py-1 text-[11px] rounded border border-atlas-accent text-atlas-accent hover:bg-atlas-accent hover:text-white transition-colors flex items-center gap-1"
                title={t('packages.view_all_on_map')}
              >
                📍 {t('packages.view_all_on_map')} ({recordsWithCoords.length})
              </button>
            )}
            {packagePins.length > 0 && (
              <button
                onClick={handleClearAll}
                className="px-2 py-1 text-[11px] rounded border border-atlas-navy text-atlas-muted hover:text-red-400 hover:border-red-400 transition-colors flex items-center gap-1"
                title={t('packages.clear_packages')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                {t('packages.clear_packages')} ({packagePins.length})
              </button>
            )}
          </div>
        </div>

        {/* Filtros locais da tabela — não afetam o gráfico diário.
            O search de tracking_id usa matching case-insensitive por substring,
            útil quando o usuário cola só os últimos 4–5 caracteres de um TID. */}
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <input
            type="search"
            value={searchTid}
            onChange={(e) => setSearchTid(e.target.value)}
            placeholder={t('packages.filter_tid_placeholder')}
            className="flex-1 min-w-[180px] bg-atlas-darker border border-atlas-navy rounded px-3 py-1.5 text-xs text-atlas-light placeholder-atlas-muted focus:outline-none focus:border-atlas-accent"
          />
          <input
            type="date"
            value={filterDate}
            min={dateRange.min}
            max={dateRange.max}
            onChange={(e) => setFilterDate(e.target.value)}
            title={t('packages.filter_date_label')}
            className="bg-atlas-darker border border-atlas-navy rounded px-2 py-1.5 text-xs text-atlas-light focus:outline-none focus:border-atlas-accent"
          />
          {(searchTid || filterDate) && (
            <button
              type="button"
              onClick={() => {
                setSearchTid('');
                setFilterDate('');
              }}
              className="px-2 py-1 text-[11px] rounded border border-atlas-navy text-atlas-muted hover:text-atlas-light hover:border-atlas-light transition-colors"
              title={t('packages.filter_clear')}
            >
              ✕ {t('packages.filter_clear')}
            </button>
          )}
        </div>

        {isLoading ? (
          <div className="text-atlas-muted text-sm py-6 text-center">
            {t('packages.drill_loading')}
          </div>
        ) : records.length === 0 ? (
          <div className="text-atlas-muted text-sm py-6 text-center">
            {recordsAll.length > 0
              ? t('packages.drill_no_records_filtered')
              : t('packages.drill_no_records')}
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
                  {pageRecords.map((rec) => {
                    const isPinned = pinnedTrackingIds.has(rec.tid);
                    return (
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
                            className={`px-2 py-0.5 text-[11px] rounded border transition-colors ${
                              isPinned
                                ? 'border-atlas-accent bg-atlas-accent/20 text-atlas-accent'
                                : 'border-atlas-accent text-atlas-accent hover:bg-atlas-accent hover:text-white'
                            } disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-atlas-accent`}
                            title={
                              isPinned
                                ? t('packages.pinned_on_map')
                                : t('packages.view_on_map')
                            }
                          >
                            📍 {isPinned ? t('packages.pinned_on_map') : t('packages.view_on_map')}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
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
