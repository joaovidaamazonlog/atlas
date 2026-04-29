import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Partner } from '../../store/types';
import type { DashboardFilters, ReportData } from '../../lib/reportUtils';
import { filterBases } from '../../lib/reportUtils';
import { useRowVirtualization } from './useRowVirtualization';

interface PartnerRow {
  name: string;
  store_id: string;
  bucket_ade: string;
}

interface Props {
  data: Partner[];
  filters: DashboardFilters;
  reportData: ReportData | null;
}

function exportCSV(rows: PartnerRow[]) {
  const header = 'name,store_id,bucket_ade\n';
  const body = rows
    .map((r) => `"${r.name}",${r.store_id},${r.bucket_ade}`)
    .join('\n');
  const blob = new Blob(['\uFEFF' + header + body], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'parceiros_ativos_por_bucket.csv';
  a.click();
  URL.revokeObjectURL(url);
}

const PartnersByBucketTable: React.FC<Props> = ({ data, filters, reportData }) => {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  // Deriva o conjunto de territory IDs visíveis a partir dos filtros aplicados no reportData.
  // Isso honra todos os níveis: BDM → Base → CTL → ADE → Território.
  const allowedBuckets = useMemo<Set<string> | null>(() => {
    // Se nenhum filtro além de base está ativo, não precisamos restringir por bucket
    const hasFilter =
      filters.bdm !== 'all' ||
      filters.ctl !== 'all' ||
      filters.ade !== 'all' ||
      filters.territory !== 'all';

    if (!hasFilter) return null; // null = sem restrição por bucket (só base)

    if (!reportData) return new Set();

    const filtered = filterBases(reportData, filters);
    const ids = filtered.flatMap((b) => b.territories.map((t) => t.id));
    return new Set(ids);
  }, [reportData, filters]);

  const rows = useMemo<PartnerRow[]>(() => {
    return data
      .filter((p) => {
        if (p.status !== 'Active') return false;
        if (!p.bucket_ade) return false;

        // Filtro por base
        if (filters.base !== 'all' && p.delivery_station !== filters.base) return false;

        // Filtro por buckets derivados dos filtros de CTL/ADE/território
        if (allowedBuckets !== null && !allowedBuckets.has(p.bucket_ade)) return false;

        return true;
      })
      .map((p) => ({
        name: p.name,
        store_id: p.store_id ?? '',
        bucket_ade: p.bucket_ade,
      }))
      .sort((a, b) => a.bucket_ade.localeCompare(b.bucket_ade, undefined, { numeric: true }));
  }, [data, filters, allowedBuckets]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.store_id && r.store_id.toLowerCase().includes(q)),
    );
  }, [rows, search]);

  // Virtualização: ativada quando filtered.length > threshold (default 100).
  const PBT_ROW_HEIGHT = 40;
  // Larguras em percentual — table-fixed com pixels+auto colapsa colunas
  const PBT_COL_WIDTHS = ['50%', '25%', '25%']; // name, store_id, bucket
  const { parentRef, virtualizer, enabled: virtualizeOn, containerStyle } =
    useRowVirtualization({
      rowCount: filtered.length,
      rowHeight: PBT_ROW_HEIGHT,
    });

  if (rows.length === 0 && !search) return null;

  const colgroup = (
    <colgroup>
      {PBT_COL_WIDTHS.map((w, i) => (
        <col key={i} style={{ width: w }} />
      ))}
    </colgroup>
  );

  const renderRow = (row: PartnerRow, idx: number, style?: React.CSSProperties) => (
    <tr
      key={`${row.store_id}-${row.bucket_ade}-${idx}`}
      style={style}
      className="border-b border-atlas-navy hover:bg-atlas-navy transition-colors"
    >
      <td className="px-3 py-2 text-atlas-light overflow-hidden text-ellipsis whitespace-nowrap">
        {row.name}
      </td>
      <td className="px-3 py-2 text-atlas-muted font-mono">{row.store_id}</td>
      <td className="px-3 py-2 text-atlas-accent">{row.bucket_ade}</td>
    </tr>
  );

  const theadContent = (
    <thead className="bg-atlas-darker sticky top-0 z-10">
      <tr>
        <th className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap">
          {t('dashboard.col_name')}
        </th>
        <th className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap">
          {t('dashboard.col_store_id')}
        </th>
        <th className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap">
          {t('dashboard.col_bucket')}
        </th>
      </tr>
    </thead>
  );

  return (
    <section>
      <div className="flex items-center justify-between mb-2 gap-2">
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest">
          {t('dashboard.partners_by_bucket_title')} ({filtered.length})
        </h2>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder={t('dashboard.search_placeholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-atlas-dark border border-atlas-navy text-atlas-light text-xs rounded px-2 py-1 w-36 focus:outline-none focus:border-atlas-accent"
          />
          <button
            onClick={() => exportCSV(filtered)}
            className="px-3 py-1 bg-atlas-accent text-white text-xs font-semibold rounded hover:opacity-90 transition-opacity whitespace-nowrap"
          >
            {t('dashboard.export_csv')}
          </button>
        </div>
      </div>

      <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
        {filtered.length === 0 ? (
          <div className="px-3 py-4 text-center text-atlas-muted text-xs">
            {t('dashboard.no_territory_found')}
          </div>
        ) : virtualizeOn ? (
          <div ref={parentRef} style={containerStyle}>
            <table
              className="w-full text-sm table-fixed"
              style={{ height: virtualizer.getTotalSize() + 44, position: 'relative' }}
            >
              {colgroup}
              {theadContent}
              <tbody>
                {virtualizer.getVirtualItems().map((v) => {
                  const row = filtered[v.index];
                  return renderRow(row, v.index, {
                    position: 'absolute',
                    top: v.start + 44,
                    left: 0,
                    width: '100%',
                    height: PBT_ROW_HEIGHT,
                  });
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm table-fixed">
              {colgroup}
              {theadContent}
              <tbody>{filtered.map((row, idx) => renderRow(row, idx))}</tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
};

export default PartnersByBucketTable;
