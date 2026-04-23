/**
 * PartnerMarkers.tsx
 * ==================
 * Camada de marcadores de parceiros no mapa.
 * Usa React.memo para evitar re-renders desnecessários.
 */

import React, { useMemo, useCallback, useEffect, useRef } from 'react';
import { CircleMarker, Circle, Popup, Tooltip, useMap } from 'react-leaflet';
import type { LeafletEventHandlerFnMap } from 'leaflet';
import L from 'leaflet';
import { useStore } from '../../store';
import { buildColorMaps, getMarkerStyle } from '../../lib/colorUtils';
import { getPartnerPopupHtml } from '../../lib/popupUtils';
import { useRescuePopup } from './RescuePopup';
import type { Partner } from '../../store/types';

function hasValidCoords(partner: Partner): partner is Partner & { lat: number; lon: number } {
  return (
    partner.lat !== null &&
    partner.lat !== 0 &&
    partner.lon !== null &&
    partner.lon !== 0
  );
}

// Escuta atlas:open-partner-popup e abre o popup + voa até o marcador
function OpenPartnerPopupListener({
  markerRefs,
}: {
  markerRefs: React.MutableRefObject<Map<string, L.CircleMarker>>;
}) {
  const map = useMap();
  useEffect(() => {
    const handler = (e: Event) => {
      const { salesforceId, lat, lon } = (e as CustomEvent<{ salesforceId: string; lat: number; lon: number }>).detail;
      map.flyTo([lat, lon], Math.max(map.getZoom(), 15), { duration: 0.8 });
      // Abre o popup após o voo
      setTimeout(() => {
        const marker = markerRefs.current.get(salesforceId);
        marker?.openPopup();
      }, 900);
    };
    window.addEventListener('atlas:open-partner-popup', handler);
    return () => window.removeEventListener('atlas:open-partner-popup', handler);
  }, [map, markerRefs]);
  return null;
}

const PartnerMarkers = React.memo(function PartnerMarkers() {
  const data = useStore((s) => s.currentFilteredData);
  const styleConfig = useStore((s) => s.styleConfig);
  const allMarkersData = useStore((s) => s.allMarkersData);
  const routeOriginActive = useStore((s) => s.routeOriginActive);
  const prospectActive = useStore((s) => s.prospectState.companies.length > 0);
  const whatIfModeActive = useStore((s) => s.whatIfModeActive);

  // No modo what-if mostra apenas parceiros ativos (os demais ficam ocultos
  // para não poluir o mapa com os marcadores arrastáveis do PartnerWhatIfLayer)
  const visibleData = useMemo(
    () => whatIfModeActive ? data.filter((p) => p.status === 'Active') : data,
    [data, whatIfModeActive],
  );

  const rescuePopup = useRescuePopup();

  // Refs dos marcadores para abrir popup programaticamente
  const markerRefs = useRef<Map<string, L.CircleMarker>>(new Map());

  const colorMaps = useMemo(
    () => buildColorMaps(data, styleConfig),
    [data, styleConfig],
  );

  const primary = styleConfig.primaryField as keyof Partner;
  const secondary = styleConfig.secondaryField as keyof Partner;

  // Handle popup button clicks delegated via data-action attributes
  const handlePopupClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const btn = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!btn) return;
    const action = btn.dataset.action;
    const storeId = btn.dataset.storeId;
    const name = btn.dataset.name ?? '';
    const partner = allMarkersData.find((p) => p.salesforce_id === storeId);

    if (action === 'route-from-here') {
      if (partner && partner.lat != null && partner.lon != null) {
        window.dispatchEvent(new CustomEvent('atlas:set-route-origin', {
          detail: { id: partner.salesforce_id, name, lat: partner.lat, lon: partner.lon }
        }));
        window.dispatchEvent(new CustomEvent('atlas:open-tab', { detail: 'routes' }));
      }
    } else if (action === 'route-add-stop') {
      if (partner && partner.lat != null && partner.lon != null) {
        window.dispatchEvent(new CustomEvent('atlas:add-route-stop', {
          detail: { id: partner.salesforce_id, name, lat: partner.lat, lon: partner.lon }
        }));
        window.dispatchEvent(new CustomEvent('atlas:open-tab', { detail: 'routes' }));
      }
    } else if (action === 'route-set-dest') {
      if (partner && partner.lat != null && partner.lon != null) {
        window.dispatchEvent(new CustomEvent('atlas:set-route-dest', {
          detail: { id: partner.salesforce_id, name, lat: partner.lat, lon: partner.lon }
        }));
        window.dispatchEvent(new CustomEvent('atlas:open-tab', { detail: 'routes' }));
      }
    } else if (action === 'request-rescue') {
      // storeId here is store_id (not salesforce_id)
      window.dispatchEvent(new CustomEvent('atlas:request-rescue', { detail: storeId }));
    }
  }, [allMarkersData]);

  return (
    <>
      <OpenPartnerPopupListener markerRefs={markerRefs} />
      {rescuePopup}
      {!prospectActive && visibleData.filter(hasValidCoords).map((partner) => {
        const style = getMarkerStyle(partner, primary, secondary, colorMaps);
        const popupHtml = getPartnerPopupHtml(partner, routeOriginActive);

        return (
          <React.Fragment key={partner.salesforce_id}>
            <CircleMarker
              center={[partner.lat, partner.lon]}
              radius={7}
              pane="markersPane"
              ref={(ref) => {
                if (ref) markerRefs.current.set(partner.salesforce_id, ref);
                else markerRefs.current.delete(partner.salesforce_id);
              }}
              pathOptions={{
                color: style.color,
                fillColor: style.fillColor,
                weight: style.weight,
                fillOpacity: style.fillOpacity,
              }}
            >
              <Popup minWidth={276} maxWidth={300} autoPan={true} autoPanPadding={[16, 16]}>
                <div dangerouslySetInnerHTML={{ __html: popupHtml }} onClick={handlePopupClick} />
              </Popup>
              {partner.tooltip && (
                <Tooltip direction="top" sticky className="custom-tooltip">
                  {partner.tooltip}
                </Tooltip>
              )}
            </CircleMarker>

            {styleConfig.showRadii && (
              <Circle
                center={[partner.lat, partner.lon]}
                radius={partner.radius}
                pathOptions={{
                  color: style.color,
                  fillOpacity: 0.05,
                  weight: 1,
                  interactive: false,
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </>
  );
});

export default PartnerMarkers;
