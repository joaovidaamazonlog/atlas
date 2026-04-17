/**
 * useGeoIntelligence.ts
 * =====================
 * Hook que carrega e expõe os dados de geointeligência para uma DS.
 * Chama `loadGeoIntelligence` no mount e sempre que `stationCode` mudar.
 */

import { useEffect } from 'react';
import { useStore } from '../store';

/**
 * @param stationCode - Código da Delivery Station (ex: "DSP2").
 *                      Passar `null` ou `undefined` desativa o fetch.
 */
export function useGeoIntelligence(stationCode: string | null | undefined) {
  const loadGeoIntelligence = useStore((s) => s.loadGeoIntelligence);
  const territories = useStore((s) => s.geoIntelligence.territories);
  const geojson = useStore((s) => s.geoIntelligence.geojson);
  const scorecard = useStore((s) => s.geoIntelligence.scorecard);
  const isLoading = useStore((s) => s.geoIntelligence.isLoading);
  const error = useStore((s) => s.geoIntelligence.error);

  useEffect(() => {
    if (!stationCode) return;
    void loadGeoIntelligence(stationCode);
  }, [stationCode, loadGeoIntelligence]);

  return { territories, geojson, scorecard, isLoading, error };
}
