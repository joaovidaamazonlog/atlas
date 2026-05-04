/**
 * DeliveriesInAreaPanel.tsx
 * =========================
 * Bloco do ManualAnalysisPanel que mostra a composição REAL de entregas
 * (Hub Delivery vs DSP, parceiros presentes) dentro do raio da análise manual.
 *
 * Diferente do RecruitableResultPanel (que fala de DEMANDA), este bloco
 * mostra EXECUÇÃO: quem de fato está entregando na área nos últimos 15d.
 *
 * Reutiliza `selectedCells` já resolvido pelo evaluator (hexes dentro
 * do raio + jurisdição) — batemos esses hex_ids contra o
 * `deliveries_by_hex.json` para somar Hub/DSP e rankear parceiros.
 *
 * Botão CSV: exporta os tracking_id dos pacotes da área. Carrega sob
 * demanda o `deliveries_detail/{DS}.jsonl.gz` (só quando o usuário clica),
 * filtra por `hex ∈ selectedHexIds` e gera o arquivo localmente via Blob.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import type { HexDeliveryBreakdown, EvaluatorResult } from '../../store/types';

interface Props {
  result: EvaluatorResult;
}

// ---------------------------------------------------------------------------
// CSV helpers
// ---------------------------------------------------------------------------

/**
 * Escapa um valor para uma célula CSV conforme RFC 4180: se tiver vírgula,
 * aspas ou quebra de linha, envolve em aspas e duplica as aspas internas.
 */
function csvEscape(value: string | number | undefined | null): string {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function triggerDownload(filename: string, content: string) {
  // BOM no início faz o Excel abrir UTF-8 corretamente (acentos).
  const blob = new Blob(['\uFEFF' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoga o object URL no próximo tick — evita vazamento de memória sem
  // cancelar o download em curso.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DeliveriesInAreaPanel: React.FC<Props> = ({ result }) => {
  const { t } = useTranslation();
  const byHex = useStore((s) => s.deliveries.byHex);
  const isLoadingByHex = useStore((s) => s.deliveries.isLoadingByHex);
  const errorByHex = useStore((s) => s.deliveries.errorByHex);
  const loadByHex = useStore((s) => s.loadDeliveriesByHex);
  const detailByDs = useStore((s) => s.deliveries.detailByDs);
  const loadDetail = useStore((s) => s.loadDeliveryDetailForDS);

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

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

  // ---- CSV export ----
  //
  // Identifica as DSs relevantes a partir dos hexes selecionados
  // (não depende de `result.recommendedStation` para cobrir o caso raro
  // de hexes vizinhos caírem em DSs diferentes). Carrega o detalhe de
  // cada DS necessária e filtra por `hex ∈ selectedHexIds`.
  const relevantStations = useMemo(() => {
    if (!byHex) return [] as string[];
    const set = new Set<string>();
    for (const h of byHex.hexes) {
      if (!selectedHexIds.has(h.hex_id)) continue;
      if (h.station_code) set.add(h.station_code);
    }
    return Array.from(set);
  }, [byHex, selectedHexIds]);

  const handleExportCsv = async () => {
    if (stats.total === 0 || relevantStations.length === 0) return;
    setIsExporting(true);
    setExportError(null);
    try {
      // Carrega os detalhes das DSs em paralelo. Se já estão em cache,
      // `loadDeliveryDetailForDS` é um no-op.
      await Promise.all(
        relevantStations.map((ds) =>
          detailByDs[ds] ? Promise.resolve() : loadDetail(ds),
        ),
      );

      // Lê do cache do store (o loader popula detailByDs).
      // Acessamos via getState para pegar a versão mais recente pós-await.
      const cache = useStore.getState().deliveries.detailByDs;

      const rows: string[] = [];
      // Cabeçalho — colunas úteis para amarrar com o sistema interno.
      rows.push(
        [
          'tracking_id',
          'scan_datetime_br',
          'reason_code',
          'canal_entrega',
          'store_id',
          'nome_empresa',
          'station_code',
          'hex_id',
          'latitude',
          'longitude',
        ].join(','),
      );

      let count = 0;
      for (const ds of relevantStations) {
        const records = cache[ds];
        if (!records) continue;
        for (const r of records) {
          if (!selectedHexIds.has(r.hex)) continue;
          rows.push(
            [
              csvEscape(r.tid),
              csvEscape(r.sdt),
              csvEscape(r.rc),
              csvEscape(r.ch),
              csvEscape(r.st),
              csvEscape(r.ne),
              csvEscape(ds),
              csvEscape(r.hex),
              csvEscape(r.lat ?? ''),
              csvEscape(r.lon ?? ''),
            ].join(','),
          );
          count++;
        }
      }

      if (count === 0) {
        setExportError(t('manual_analysis.deliveries_csv_empty'));
        return;
      }

      // Filename com timestamp compacto pra usuário não sobrescrever quando
      // exporta várias análises seguidas.
      const ts = new Date()
        .toISOString()
        .replace(/[-:]/g, '')
        .replace(/\..+/, '')
        .replace('T', '_');
      triggerDownload(`atlas_entregas_area_${ts}.csv`, rows.join('\r\n'));
    } catch (err) {
      console.error('[DeliveriesInAreaPanel] CSV export falhou:', err);
      setExportError(t('manual_analysis.deliveries_csv_error'));
    } finally {
      setIsExporting(false);
    }
  };

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
      <header className="flex items-baseline justify-between gap-2">
        <h4 className="text-atlas-light text-xs font-semibold uppercase tracking-wider">
          {t('manual_analysis.deliveries_title')}
        </h4>
        <div className="flex items-center gap-2">
          <span className="text-atlas-muted text-[10px]">
            {byHex.period.days}d · {stats.total.toLocaleString('pt-BR')} pct
          </span>
          <button
            type="button"
            onClick={handleExportCsv}
            disabled={isExporting || stats.total === 0}
            title={t('manual_analysis.deliveries_csv_tooltip')}
            className="px-2 py-1 text-[10px] rounded border border-atlas-accent text-atlas-accent hover:bg-atlas-accent hover:text-white transition-colors flex items-center gap-1 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-atlas-accent"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3 h-3"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
            {isExporting ? '…' : 'CSV'}
          </button>
        </div>
      </header>

      {exportError && (
        <div className="rounded px-2 py-1 bg-red-500/10 border border-red-500/30 text-red-400 text-[10px]">
          {exportError}
        </div>
      )}

      {/* Barra de share horizontal */}
      <div>
        <div className="flex h-3 rounded overflow-hidden border border-atlas-navy">
          <div
            className="bg-atlas-accent flex items-center justify-center text-[9px] font-bold text-white"
            style={{ width: `${stats.ihs_pct}%` }}
            title={`Hub Delivery: ${stats.ihs}`}
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
            Hub Delivery {stats.ihs.toLocaleString('pt-BR')} ({stats.ihs_pct.toFixed(1)}%)
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
