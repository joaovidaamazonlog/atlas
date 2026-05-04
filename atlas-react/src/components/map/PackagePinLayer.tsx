/**
 * PackagePinLayer.tsx
 * ===================
 * Renderiza N markers no mapa — um por pin em `store.packagePins`.
 *
 * Cada pin representa uma entrega individual plotada pelo botão 📍 na
 * tabela de drill-down de parceiros. O usuário pode acumular múltiplos
 * pins para comparar distâncias, clusters, ou apenas visualizar todas
 * as entregas de um parceiro de uma vez (botão "Ver todos no mapa").
 *
 * Ao clicar no X do popup de um pin específico, apenas aquele pin é
 * removido — os demais permanecem. Para limpar tudo, o drill-down
 * dispara `clearPackagePins()` ao fechar.
 *
 * Comportamento de zoom: quando o conjunto de pins muda, só fazemos
 * fit-bounds se houver ≥ 2 pins OU se o único pin está longe da view
 * atual — preserva o zoom quando o usuário está navegando.
 */

import React, { useEffect, useRef } from 'react';
import { Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../store';

// Ícone customizado (cor accent do app).
const packageIcon = new L.DivIcon({
  className: '',
  html: `
    <div style="
      background:#00a8e1;
      border:2px solid #fff;
      width:22px;height:22px;
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      box-shadow:0 2px 6px rgba(0,0,0,.4);
      display:flex;align-items:center;justify-content:center;
      font-size:10px;color:#fff;font-weight:700;
    ">
      <span style="transform:rotate(45deg)">📦</span>
    </div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 22],
  popupAnchor: [0, -22],
});

const PackagePinLayer: React.FC = () => {
  const pins = useStore((s) => s.packagePins);
  const removePin = useStore((s) => s.removePackagePin);
  const map = useMap();

  // Refaz o bounds quando a contagem de pins muda de 0→1 ou ao ganhar
  // pins novos. Ignoramos mudanças internas (reorder) para não causar
  // jitter quando o usuário está examinando os pins.
  const prevCountRef = useRef(0);
  useEffect(() => {
    const count = pins.length;
    const prev = prevCountRef.current;
    prevCountRef.current = count;
    if (count === 0) return;
    // Só refoca ao ganhar pins (não ao perder).
    if (count <= prev) return;

    // `invalidateSize` + double RAF garante que o Leaflet use o tamanho
    // real do container antes de centralizar. Sem isso, a centralização
    // usa o viewport desatualizado (ex: logo após o dashboard abrir e
    // comprimir o mapa em 35%).
    const focus = () => {
      map.invalidateSize({ animate: false });
      if (count === 1) {
        const p = pins[0];
        const current = map.getCenter();
        const distance = map.distance(current, [p.lat, p.lon]);
        if (distance > 500) {
          const targetZoom = Math.max(map.getZoom(), 16);
          map.setView([p.lat, p.lon], targetZoom, { animate: true });
        }
      } else {
        const bounds = L.latLngBounds(
          pins.map((p) => [p.lat, p.lon] as [number, number]),
        );
        map.fitBounds(bounds, { padding: [60, 60], maxZoom: 17, animate: true });
      }
    };
    const id1 = requestAnimationFrame(() => {
      const id2 = requestAnimationFrame(focus);
      return () => cancelAnimationFrame(id2);
    });
    return () => cancelAnimationFrame(id1);
  }, [pins, map]);

  if (pins.length === 0) return null;

  return (
    <>
      {pins.map((pin) => (
        <Marker key={pin.tracking_id} position={[pin.lat, pin.lon]} icon={packageIcon}>
          <Popup onClose={() => removePin(pin.tracking_id)}>
            <div style={{ minWidth: 220, fontSize: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 4, color: '#00a8e1' }}>
                📦 Pacote
              </div>
              <div style={{ fontFamily: 'monospace', fontSize: 11, marginBottom: 6 }}>
                {pin.tracking_id}
              </div>
              <table style={{ width: '100%', fontSize: 11 }}>
                <tbody>
                  <tr>
                    <td style={{ color: '#7b8fa3', paddingRight: 8 }}>Quando</td>
                    <td>{pin.scan_datetime_br}</td>
                  </tr>
                  <tr>
                    <td style={{ color: '#7b8fa3', paddingRight: 8 }}>Reason</td>
                    <td>{pin.reason_code || '—'}</td>
                  </tr>
                  <tr>
                    <td style={{ color: '#7b8fa3', paddingRight: 8 }}>Parceiro</td>
                    <td>{pin.partner_name}</td>
                  </tr>
                  <tr>
                    <td style={{ color: '#7b8fa3', paddingRight: 8 }}>Canal</td>
                    <td>
                      <span
                        style={{
                          padding: '1px 6px',
                          borderRadius: 3,
                          fontSize: 10,
                          fontWeight: 600,
                          background: pin.canal === 'IHS_STORE' ? '#00a8e1' : '#ff8c42',
                          color: '#fff',
                        }}
                      >
                        {pin.canal}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Popup>
        </Marker>
      ))}
    </>
  );
};

export default PackagePinLayer;
