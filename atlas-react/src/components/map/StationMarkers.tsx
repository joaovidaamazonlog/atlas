/**
 * StationMarkers.tsx
 * ==================
 * Camada de marcadores de delivery stations no mapa.
 */

import React from 'react';
import { Marker, Popup } from 'react-leaflet';
import { DivIcon } from 'leaflet';
import { useStore } from '../../store';
import { getStationPopupHtml } from '../../lib/popupUtils';

const warehouseIcon = new DivIcon({
  html: '<span style="font-size:20px;line-height:1;">🏭</span>',
  className: '',
  iconSize: [24, 24],
  iconAnchor: [12, 12],
  popupAnchor: [0, -14],
});

const StationMarkers = React.memo(function StationMarkers() {
  const deliveryStations = useStore((s) => s.deliveryStations);

  return (
    <>
      {deliveryStations.map((station) => (
        <Marker
          key={station.nome}
          position={[station.lat, station.lon]}
          icon={warehouseIcon}
        >
          <Popup maxWidth={280}>
            <div dangerouslySetInnerHTML={{ __html: getStationPopupHtml(station) }} />
          </Popup>
        </Marker>
      ))}
    </>
  );
});

StationMarkers.displayName = 'StationMarkers';

export default StationMarkers;
