import React, { useMemo, useState } from 'react';
import { useStore } from '../../store';
import { Spinner } from '../ui/Spinner';
import KpiGrid from './KpiGrid';
import ChartsSection from './ChartsSection';
import StationsTable from './StationsTable';

const Dashboard: React.FC = () => {
  const currentFilteredData = useStore((s) => s.currentFilteredData);
  const deliveryStations = useStore((s) => s.deliveryStations);
  const isLoading = useStore((s) => s.isLoading);
  const error = useStore((s) => s.error);

  const [selectedStation, setSelectedStation] = useState<string>('all');

  // Unique station names from data
  const stationOptions = useMemo(() => {
    const names = new Set(currentFilteredData.map((p) => p.delivery_station).filter(Boolean));
    return Array.from(names).sort();
  }, [currentFilteredData]);

  // Filter data locally by selected station (does not affect global store)
  const filteredData = useMemo(() => {
    if (selectedStation === 'all') return currentFilteredData;
    return currentFilteredData.filter((p) => p.delivery_station === selectedStation);
  }, [currentFilteredData, selectedStation]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-3 text-atlas-muted">
        <Spinner size="lg" />
        <span>Carregando dados...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-2 text-red-400 p-4">
        <span className="text-2xl">⚠</span>
        <span className="text-center">{error}</span>
      </div>
    );
  }

  if (currentFilteredData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[200px] gap-2 text-atlas-muted p-4">
        <span className="text-2xl">📊</span>
        <span className="text-center">Nenhum dado disponível. Carregue os dados ou ajuste os filtros.</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 bg-atlas-darker min-h-full">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 bg-atlas-dark border border-atlas-navy rounded-lg p-3">
        <label className="text-atlas-muted text-sm whitespace-nowrap">Delivery Station:</label>
        <select
          value={selectedStation}
          onChange={(e) => setSelectedStation(e.target.value)}
          className="bg-atlas-darker border border-atlas-navy text-atlas-light text-sm rounded px-2 py-1 focus:outline-none focus:border-atlas-accent"
        >
          <option value="all">Todas ({currentFilteredData.length} parceiros)</option>
          {stationOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {deliveryStations.length > 0 && (
          <span className="text-atlas-muted text-xs ml-auto">
            {deliveryStations.length} estações cadastradas
          </span>
        )}
      </div>

      {/* KPI Grid */}
      <section>
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">KPIs</h2>
        <KpiGrid />
      </section>

      {/* Charts */}
      <section>
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">Gráficos</h2>
        <ChartsSection data={filteredData} />
      </section>

      {/* Stations Table */}
      <section>
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">
          Por Delivery Station
        </h2>
        <StationsTable data={filteredData} />
      </section>
    </div>
  );
};

export default Dashboard;
