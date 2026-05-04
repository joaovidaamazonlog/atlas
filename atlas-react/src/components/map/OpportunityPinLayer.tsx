/**
 * OpportunityPinLayer.tsx
 * =======================
 * Renderiza um pin único no mapa quando a aba Insights solicita
 * "Ver no mapa" para um hex órfão de alto volume (oportunidade).
 *
 * Ativado via `store.opportunityPin` (preenchido pelo botão 📍 na tabela
 * de Maiores Oportunidades). O pin mostra um popup com DS, bucket,
 * volume diário, volume total no período e % DSP — contexto suficiente
 * para o gerente decidir se vale uma visita de prospecção ali.
 */

import React, { useEffect } from 'react';
import { Marker, Popup, useMap } from 'react-leaflet';
import { useTranslation } from 'react-i18next';
import L from 'leaflet';
import { useStore } from '../../store';

// Ícone laranja (cor usada para DSP/oportunidades — bate com o resto da UI).
const opportunityIcon = new L.DivIcon({
  className: '',
  html: `
    <div style="
      background:#ff8c42;
      border:2px solid #fff;
      width:22px;height:22px;
      border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      box-shadow:0 2px 6px rgba(0,0,0,.4);
      display:flex;align-items:center;justify-content:center;
      font-size:10px;color:#fff;font-weight:700;
    ">
      <span style="transform:rotate(45deg)">💡</span>
    </div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 22],
  popupAnchor: [0, -22],
});

const OpportunityPinLayer: React.FC = () => {
  const { t } = useTranslation();
  const pin = useStore((s) => s.opportunityPin);
  const setPin = useStore((s) => s.setOpportunityPin);
  const map = useMap();

  // Centraliza / aproxima ao aparecer um pin, sem zoom agressivo se o
  // usuário já estava próximo. Usa double RAF + invalidateSize para o
  // caso de o dashboard estar abrindo ao mesmo tempo — sem isso o Leaflet
  // usa o viewport antigo e a centralização fica fora da área visível.
  useEffect(() => {
    if (!pin) return;
    const id1 = requestAnimationFrame(() => {
      const id2 = requestAnimationFrame(() => {
        map.invalidateSize({ animate: false });
        const current = map.getCenter();
        const distance = map.distance(current, [pin.lat, pin.lon]);
        if (distance > 500) {
          const targetZoom = Math.max(map.getZoom(), 15);
          map.setView([pin.lat, pin.lon], targetZoom, { animate: true });
        }
      });
      return () => cancelAnimationFrame(id2);
    });
    return () => cancelAnimationFrame(id1);
  }, [pin, map]);

  if (!pin) return null;

  return (
    <Marker position={[pin.lat, pin.lon]} icon={opportunityIcon}>
      <Popup onClose={() => setPin(null)}>
        <div style={{ minWidth: 220, fontSize: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 4, color: '#ff8c42' }}>
            💡 {t('insights.opportunity_pin_title')}
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 10, marginBottom: 6, color: '#7b8fa3' }}>
            {pin.hex_id}
          </div>
          <table style={{ width: '100%', fontSize: 11 }}>
            <tbody>
              <tr>
                <td style={{ color: '#7b8fa3', paddingRight: 8 }}>DS</td>
                <td>{pin.delivery_station || '—'}</td>
              </tr>
              {pin.territory_id && (
                <tr>
                  <td style={{ color: '#7b8fa3', paddingRight: 8 }}>Bucket</td>
                  <td>{pin.territory_id}</td>
                </tr>
              )}
              <tr>
                <td style={{ color: '#7b8fa3', paddingRight: 8 }}>
                  {t('insights.opportunity_daily')}
                </td>
                <td style={{ fontWeight: 600 }}>{pin.daily_volume.toFixed(1)}</td>
              </tr>
              <tr>
                <td style={{ color: '#7b8fa3', paddingRight: 8 }}>
                  {t('insights.opportunity_total')}
                </td>
                <td>{pin.total_volume.toLocaleString('pt-BR')}</td>
              </tr>
              <tr>
                <td style={{ color: '#7b8fa3', paddingRight: 8 }}>%DSP</td>
                <td>
                  <span
                    style={{
                      padding: '1px 6px',
                      borderRadius: 3,
                      fontSize: 10,
                      fontWeight: 600,
                      background: '#ff8c42',
                      color: '#fff',
                    }}
                  >
                    {pin.dsp_share_pct.toFixed(0)}%
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

export default OpportunityPinLayer;
