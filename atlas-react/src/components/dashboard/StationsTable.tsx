import React, { useMemo, useState, useRef } from 'react';
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

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'station', label: 'Delivery Station' },
  { key: 'active', label: 'Ativos' },
  { key: 'onboarding', label: 'Onboarding' },
  { key: 'bgChecks', label: 'BG Checks' },
  { key: 'prospects', label: 'Prospects' },
  { key: 'inactive', label: 'Inativos' },
  { key: 'total', label: 'Total' },
];

const ROW_HEIGHT = 40;
const VIRTUALIZE_THRESHOLD = 100;

interface StationsTableProps {
  data: Partner[];
}

const StationsTable: React.FC<StationsTableProps> = React.memo(({ data }) => {
  const [sortKey, setSortKey] = useState<SortKey>('active');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const parentRef = useRef<HTMLDivElement>(null);

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
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
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
        </table>
        {useVirtualization ? (
          <div
            ref={parentRef}
            style={{ height: Math.min(rows.length * ROW_HEIGHT, 400), overflowY: 'auto' }}
          >
            <table className="w-full text-sm" style={{ height: virtualizer.getTotalSize() }}>
              <tbody>
                {virtualizer.getVirtualItems().map((virtualRow) => {
                  const row = rows[virtualRow.index];
                  return renderRow(row, {
                    position: 'absolute',
                    top: virtualRow.start,
                    left: 0,
                    width: '100%',
                    height: ROW_HEIGHT,
                  });
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {rows.map((row) => renderRow(row))}
            </tbody>
          </table>
        )}
      </div>
      {rows.length === 0 && (
        <div className="text-atlas-muted text-center py-6">Nenhuma estação encontrada.</div>
      )}
    </div>
  );
});

StationsTable.displayName = 'StationsTable';

export default StationsTable;
