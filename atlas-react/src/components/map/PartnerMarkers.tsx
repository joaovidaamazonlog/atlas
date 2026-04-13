/**
 * PartnerMarkers.tsx
 * ==================
 * Camada de marcadores de parceiros no mapa.
 * Usa React.memo para evitar re-renders desnecessários.
 */

import React, { useMemo } from 'react';
import { CircleMarker, Circle, Popup, Tooltip } from 'react-leaflet';
import { useStore } from '../../store';
import { buildColorMaps, getMarkerStyle } from '../../lib/colorUtils';
import { getPartnerPopupHtml } from '../../lib/popupUtils';
import type { Partner } from '../../store/types';

function hasValidCoords(partner: Partner): partner is Partner & { lat: number; lon: number } {
  return (
    partner.lat !== null &&
    partner.lat !== 0 &&
    partner.lon !== null &&
    partner.lon !== 0
  );
}

const PartnerMarkers = React.memo(function PartnerMarkers() {
  const data = useStore((s) => s.currentFilteredData);
  const styleConfig = useStore((s) => s.styleConfig);

  const colorMaps = useMemo(
    () => buildColorMaps(data, styleConfig),
    [data, styleConfig],
  );

  const primary = styleConfig.primaryField as keyof Partner;
  const secondary = styleConfig.secondaryField as keyof Partner;

  return (
    <>
      {data.filter(hasValidCoords).map((partner) => {
        const style = getMarkerStyle(partner, primary, secondary, colorMaps);
        const popupHtml = getPartnerPopupHtml(partner);

        return (
          <React.Fragment key={partner.salesforce_id}>
            <CircleMarker
              center={[partner.lat, partner.lon]}
              radius={7}
              pathOptions={{
                color: style.color,
                fillColor: style.fillColor,
                weight: style.weight,
                fillOpacity: style.fillOpacity,
              }}
            >
              <Popup maxWidth={320}>
                <div dangerouslySetInnerHTML={{ __html: popupHtml }} />
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
