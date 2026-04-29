/**
 * RoutePickPinsLayer.tsx
 * ======================
 * Pins arrastáveis no mapa para cada ponto escolhido no RoutesTab antes do
 * cálculo da rota (origem, destino e paradas). Permite ao usuário refinar a
 * posição arrastando o pin; ao soltar, dispara `atlas:route-pin-dragged`
 * com `{ field, lat, lng }` para o RoutesTab atualizar o campo correspondente.
 *
 * Os pins ficam ocultos quando a rota está desenhada (route.length >= 2) —
 * nesse caso quem mostra os marcadores é o RouteLayer via leaflet-routing-machine.
 */

import L from 'leaflet';
import { useMemo } from 'react';
import { Marker, Tooltip } from 'react-leaflet';
import { useStore } from '../../store';

function makePinIcon(kind: 'origin' | 'dest' | 'stop') {
  const color =
    kind === 'origin' ? '#22c55e' :
    kind === 'dest'   ? '#ef4444' :
                        '#3b82f6';
  const letter =
    kind === 'origin' ? 'A' :
    kind === 'dest'   ? 'B' :
                        '';
  // SVG único: pin + (letra branca OU bolinha branca central)
  const inner = letter
    ? `<text x="13" y="17" text-anchor="middle" font-family="Inter, system-ui, sans-serif"
             font-size="12" font-weight="700" fill="#ffffff">${letter}</text>`
    : `<circle cx="13" cy="13" r="3.2" fill="#ffffff"/>`;

  const html = `
    <svg width="26" height="36" viewBox="0 0 26 36" xmlns="http://www.w3.org/2000/svg"
         style="display:block; filter: drop-shadow(0 2px 3px rgba(0,0,0,0.4));">
      <path d="M13 0C5.82 0 0 5.82 0 13c0 9.75 13 23 13 23s13-13.25 13-23C26 5.82 20.18 0 13 0z"
            fill="${color}" stroke="#ffffff" stroke-width="1.5"/>
      ${inner}
    </svg>
  `;
  return L.divIcon({
    className: 'atlas-route-pick-pin',
    html,
    iconSize: [26, 36],
    iconAnchor: [13, 36],
    tooltipAnchor: [0, -28],
  });
}

export default function RoutePickPinsLayer() {
  const pins = useStore((s) => s.routePickPins);
  const route = useStore((s) => s.route);

  // Quando há rota calculada, o RouteLayer já mostra os marcadores.
  const hideBecauseRoute = route.length >= 2;

  // Memoiza os ícones — só 3 variações possíveis.
  const icons = useMemo(() => ({
    origin: makePinIcon('origin'),
    dest:   makePinIcon('dest'),
    stop:   makePinIcon('stop'),
  }), []);

  if (hideBecauseRoute || pins.length === 0) return null;

  return (
    <>
      {pins.map((pin) => {
        const kind: 'origin' | 'dest' | 'stop' =
          pin.field === 'origin' ? 'origin' :
          pin.field === 'dest'   ? 'dest'   :
                                    'stop';
        const defaultLabel =
          kind === 'origin' ? 'Origem' :
          kind === 'dest'   ? 'Destino' :
                              'Parada';
        return (
          <Marker
            key={pin.field}
            position={[pin.lat, pin.lon]}
            draggable
            icon={icons[kind]}
            eventHandlers={{
              dragend: (e) => {
                const m = e.target as L.Marker;
                const { lat, lng } = m.getLatLng();
                document.dispatchEvent(
                  new CustomEvent('atlas:route-pin-dragged', {
                    detail: { field: pin.field, lat, lng },
                  })
                );
              },
            }}
          >
            <Tooltip direction="top" offset={[0, -28]} opacity={0.95}>
              <div style={{ fontSize: 11, lineHeight: 1.3 }}>
                <div style={{ fontWeight: 600 }}>{defaultLabel}</div>
                {pin.label && (
                  <div style={{ maxWidth: 260, opacity: 0.85 }}>{pin.label}</div>
                )}
                <div style={{ opacity: 0.7, marginTop: 2 }}>Arraste para ajustar</div>
              </div>
            </Tooltip>
          </Marker>
        );
      })}
    </>
  );
}
