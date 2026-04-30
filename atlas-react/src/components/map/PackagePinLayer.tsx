/**
 * PackagePinLayer.tsx
 * ===================
 * Renderiza um marker único no mapa quando o Dashboard solicita
 * visualização de um pacote específico (drill-down por tracking_id).
 *
 * Ativado via `store.packagePin` (preenchido por `setPackagePin` a partir
 * do botão 📍 na tabela de drill-down de parceiros).
 *
 * O popup é simples por design: mostra tracking_id, data/hora, reason_code,
 * parceiro e canal. Ao clicar fora ou pressionar ESC no popup aberto,
 * o próprio Leaflet fecha — mas o pin só é removido quando o usuário
 * clicar no X do popup ou chamar `setPackagePin(null)` de outro lugar.
 */

import React, { useEffect } from 'react';
import { Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../store';

// Ícone customizado (cor accent do app)
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
  const pin = useStore((s) => s.packagePin);
  const setPin = useStore((s) => s.setPackagePin);
  const map = useMap();

  // Ao aparecer um pin, centraliza/aproxima sem fazer zoom agressivo.
  useEffect(() => {
    if (!pin) return;
    const current = map.getCenter();
    const distance = map.distance(current, [pin.lat, pin.lon]);
    if (distance > 500) {
      const targetZoom = Math.max(map.getZoom(), 16);
      map.setView([pin.lat, pin.lon], targetZoom, { animate: true });
    }
  }, [pin, map]);

  if (!pin) return null;

  return (
    <Marker position={[pin.lat, pin.lon]} icon={packageIcon}>
      <Popup onClose={() => setPin(null)}>
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
  );
};

export default PackagePinLayer;
