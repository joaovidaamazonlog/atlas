import React, { useMemo, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { Partner } from '../../store/types';

interface StationRow {
  station: string;
  active: number;
  onboarding: number;
  bgChecks: number;
  prospects: number;
  inactive: number;
  total: number;
}

type SortKey = keyof StationRow;
type SortDir = 'asc' | 'desc';

function groupByStation(data: Partner[]): StationRow[] {
  const map: Record<string, StationRow> = {};
  for (const p of data) {
    const s = p.delivery_station || 'N/A';
    if (!map[s]) {
      map[s] = { station: s, active: 0, onboarding: 0, bgChecks: 0, prospects: 0, inactive: 0, total: 0 };
    }
    map[s].total++;
    if (p.status === 'Active') map[s].active++;
    else if (p.status === 'Onboarding') map[s].onboarding++;
    else if (p.status === 'BG Checks') map[s].bgChecks++;
    else if (p.status === 'Prospect') map[s].prospects++;
    else if (p.status === 'Inactive' || p.status === 'Exited') map[s].inactive++;
  }
  return Object.values(map);
}

const ROW_HEIGHT = 40;
const VIRTUALIZE_THRESHOLD = 100;
// Larguras em percentual para table-fixed — somam 100%
const STATION_COL_WIDTHS = ['22%', '13%', '13%', '13%', '13%', '13%', '13%'];

interface StationsTableProps {
  data: Partner[];
}

const StationsTable: React.FC<StationsTableProps> = React.memo(({ data }) => {
  const { t } = useTranslation();
  const [sortKey, setSortKey] = useState<SortKey>('active');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const parentRef = useRef<HTMLDivElement>(null);

  const COLUMNS: { key: SortKey; label: string }[] = [
    { key: 'station', label: t('dashboard.col_delivery_station') },
    { key: 'active', label: t('dashboard.col_active') },
    { key: 'onboarding', label: t('dashboard.col_onboarding') },
    { key: 'bgChecks', label: t('dashboard.col_bg_checks') },
    { key: 'prospects', label: t('dashboard.col_prospects') },
    { key: 'inactive', label: t('dashboard.col_inactive') },
    { key: 'total', label: t('dashboard.col_total') },
  ];

  const rows = useMemo(() => {
    const grouped = groupByStation(data);
    return [...grouped].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'string' && typeof bv === 'string') {
        return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return sortDir === 'asc' ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }, [data, sortKey, sortDir]);

  const useVirtualization = rows.length > VIRTUALIZE_THRESHOLD;

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    enabled: useVirtualization,
  });

  const handleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortIndicator = ({ col }: { col: SortKey }) => {
    if (col !== sortKey) return <span className="text-atlas-muted ml-1">↕</span>;
    return <span className="text-atlas-accent ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>;
  };

  const renderRow = (row: StationRow, style?: React.CSSProperties) => (
    <tr
      key={row.station}
      style={style}
      className="border-b border-atlas-navy hover:bg-atlas-navy transition-colors"
    >
      <td className="px-3 py-2 text-atlas-light font-medium">{row.station}</td>
      <td className="px-3 py-2 text-green-400 text-center">{row.active}</td>
      <td className="px-3 py-2 text-yellow-400 text-center">{row.onboarding}</td>
      <td className="px-3 py-2 text-blue-400 text-center">{row.bgChecks}</td>
      <td className="px-3 py-2 text-purple-400 text-center">{row.prospects}</td>
      <td className="px-3 py-2 text-red-400 text-center">{row.inactive}</td>
      <td className="px-3 py-2 text-atlas-muted text-center">{row.total}</td>
    </tr>
  );

  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
      {useVirtualization ? (
        <div
          ref={parentRef}
          style={{ height: Math.min(rows.length * ROW_HEIGHT, 400), overflowY: 'auto' }}
        >
          <table className="w-full text-sm table-fixed">
            <colgroup>
              {STATION_COL_WIDTHS.map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
            </colgroup>
            <thead className="bg-atlas-darker sticky top-0 z-10">
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide cursor-pointer select-none hover:text-atlas-light transition-colors whitespace-nowrap"
                  >
                    {col.label}
                    <SortIndicator col={col.key} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(() => {
                const items = virtualizer.getVirtualItems();
                if (items.length === 0) return null;
                const paddingTop = items[0].start;
                const paddingBottom = virtualizer.getTotalSize() - items[items.length - 1].end;
                return (
                  <>
                    {paddingTop > 0 && (
                      <tr aria-hidden="true" style={{ height: paddingTop }}>
                        <td colSpan={STATION_COL_WIDTHS.length} style={{ padding: 0, border: 0 }} />
                      </tr>
                    )}
                    {items.map((v) => renderRow(rows[v.index], { height: ROW_HEIGHT }))}
                    {paddingBottom > 0 && (
                      <tr aria-hidden="true" style={{ height: paddingBottom }}>
                        <td colSpan={STATION_COL_WIDTHS.length} style={{ padding: 0, border: 0 }} />
                      </tr>
                    )}
                  </>
                );
              })()}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm table-fixed">
            <colgroup>
              {STATION_COL_WIDTHS.map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
            </colgroup>
            <thead className="bg-atlas-darker sticky top-0 z-10">
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide cursor-pointer select-none hover:text-atlas-light transition-colors whitespace-nowrap"
                  >
                    {col.label}
                    <SortIndicator col={col.key} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => renderRow(row))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length === 0 && (
        <div className="text-atlas-muted text-center py-6">Nenhuma estação encontrada.</div>
      )}
    </div>
  );
});

StationsTable.displayName = 'StationsTable';

export default StationsTable;
