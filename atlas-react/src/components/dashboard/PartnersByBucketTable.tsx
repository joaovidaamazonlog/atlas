import React, { useMemo, useState } from 'react';
import type { Partner } from '../../store/types';

interface PartnerRow {
  name: string;
  store_id: string;
  bucket_ade: string;
}

interface Props {
  data: Partner[];
  selectedStation?: string;
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

const PartnersByBucketTable: React.FC<Props> = ({ data, selectedStation }) => {
  const [search, setSearch] = useState('');

  const rows = useMemo<PartnerRow[]>(() => {
    return data
      .filter(
        (p) =>
          p.status === 'Active' &&
          p.bucket_ade &&
          (!selectedStation || selectedStation === 'all' || p.delivery_station === selectedStation),
      )
      .map((p) => ({ name: p.name, store_id: p.store_id ?? '', bucket_ade: p.bucket_ade }))
      .sort((a, b) => a.bucket_ade.localeCompare(b.bucket_ade, undefined, { numeric: true }));
  }, [data, selectedStation]);

  const filtered = useMemo(() => {
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        r.store_id.includes(q) ||
        r.bucket_ade.toLowerCase().includes(q),
    );
  }, [rows, search]);

  if (rows.length === 0) return null;

  return (
    <section>
      <div className="flex items-center justify-between mb-2 gap-2">
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest">
          Parceiros Ativos por Bucket ({rows.length})
        </h2>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Buscar..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-atlas-dark border border-atlas-navy text-atlas-light text-xs rounded px-2 py-1 w-36 focus:outline-none focus:border-atlas-accent"
          />
          <button
            onClick={() => exportCSV(filtered)}
            className="px-3 py-1 bg-atlas-accent text-white text-xs font-semibold rounded hover:opacity-90 transition-opacity whitespace-nowrap"
          >
            ⬇ Exportar CSV
          </button>
        </div>
      </div>

      <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-atlas-darker sticky top-0 z-10">
              <tr>
                <th className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap">
                  Nome
                </th>
                <th className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap">
                  Store ID
                </th>
                <th className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide whitespace-nowrap">
                  Bucket
                </th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={row.store_id + row.bucket_ade}
                  className="border-b border-atlas-navy hover:bg-atlas-navy transition-colors"
                >
                  <td className="px-3 py-2 text-atlas-light">{row.name}</td>
                  <td className="px-3 py-2 text-atlas-muted font-mono">{row.store_id}</td>
                  <td className="px-3 py-2 text-atlas-accent">{row.bucket_ade}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-4 text-center text-atlas-muted text-xs">
                    Nenhum resultado encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

export default PartnersByBucketTable;
