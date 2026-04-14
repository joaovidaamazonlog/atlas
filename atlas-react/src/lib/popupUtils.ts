/**
 * popupUtils.ts
 * =============
 * Funções puras que geram HTML de popups para o mapa.
 * Migrado de frontend/js/modules/ui-manager.js para TypeScript.
 * Sem dependências de DOM — retornam strings HTML.
 */

import type { Partner, DeliveryStation } from '../store/types';

// ---------------------------------------------------------------------------
// HELPERS INTERNOS
// ---------------------------------------------------------------------------

function _row(label: string, value: string | number | null | undefined): string {
  return `<tr><td style="width:40%"><b>${label}:</b></td><td style="width:60%">${value ?? 'N/A'}</td></tr>`;
}

function _table(rows: string): string {
  return `<table style="width:100%"><tbody>${rows}</tbody></table>`;
}

function _sfLink(id: string): string {
  // Salesforce cloud logo
  return `<a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${id}/view" target="_blank" style="color:#4fc3f7;display:inline-flex;align-items:center;gap:4px;">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19.125 8.4A5.37 5.37 0 0014.25 6a5.38 5.38 0 00-4.875 3.075A4.126 4.126 0 006 13.125 4.125 4.125 0 0010.125 17.25h8.625A3.75 3.75 0 0022.5 13.5a3.75 3.75 0 00-3.375-3.1z"/></svg>
    Salesforce</a><br>`;
}

function _waLink(tel: string | null): string {
  if (!tel) return '';
  return `<a href="https://wa.me/${tel}" target="_blank" style="color:#25d366;display:inline-flex;align-items:center;gap:4px;">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/><path d="M12 0C5.373 0 0 5.373 0 12c0 2.127.558 4.126 1.533 5.858L.057 23.5l5.797-1.52A11.93 11.93 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.885 0-3.65-.52-5.16-1.426l-.37-.22-3.44.902.918-3.352-.24-.386A9.944 9.944 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/></svg>
    WhatsApp</a>`;
}

function _actionButtons(p: Partner, routeOriginActive = false): string {
  const routeBtn = `<button
    data-action="route-from-here"
    data-store-id="${p.salesforce_id}"
    data-name="${p.name.replace(/"/g, '&quot;')}"
    style="width:100%;margin-top:4px;padding:5px 8px;background:#3b82f6;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;justify-content:center;">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M21 3L3 10.53v.98l6.84 2.65L12.48 21h.98L21 3z"/></svg>
    Rota a Partir Daqui
  </button>`;

  const addStopBtn = routeOriginActive ? `<button
    data-action="route-add-stop"
    data-store-id="${p.salesforce_id}"
    data-name="${p.name.replace(/"/g, '&quot;')}"
    style="width:100%;margin-top:4px;padding:5px 8px;background:#f59e0b;color:#1a1a1a;border:none;border-radius:4px;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;justify-content:center;">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
    Adicionar na Rota
  </button>` : '';

  const destBtn = routeOriginActive ? `<button
    data-action="route-set-dest"
    data-store-id="${p.salesforce_id}"
    data-name="${p.name.replace(/"/g, '&quot;')}"
    style="width:100%;margin-top:4px;padding:5px 8px;background:#10b981;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;justify-content:center;">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
    Definir como Destino
  </button>` : '';

  const rescueBtn = p.status === 'Active' ? `<button
    data-action="request-rescue"
    data-store-id="${p.store_id}"
    style="width:100%;margin-top:4px;padding:5px 8px;background:#0ea5e9;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:4px;justify-content:center;">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M6.62 10.79c1.44 2.83 3.76 5.14 6.59 6.59l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02l-2.2 2.2z"/></svg>
    Solicitar Resgate
  </button>` : '';

  return `<div style="margin-top:8px;">${routeBtn}${addStopBtn}${destBtn}${rescueBtn}</div>`;
}

// Helper para acessar optimization de forma segura
// (suporte a dados brutos que não passaram pela classe Partner)
function _opt(p: Partner) {
  return p.optimization ?? {
    cap_suggestion: (p as unknown as Record<string, number>).cap_suggestion ?? p.capacity ?? 0,
    radius_suggestion: (p as unknown as Record<string, number>).radius_suggestion ?? p.radius ?? 0,
  };
}
// ---------------------------------------------------------------------------

/**
 * Retorna o HTML do popup de um parceiro com base no seu status.
 * Migrado de `getPopupContent` em ui-manager.js.
 */
export function getPartnerPopupHtml(partner: Partner, routeOriginActive = false): string {
  switch (partner.status) {
    case 'Active':
      return _popupActive(partner, routeOriginActive);
    case 'Inactive':
    case 'Exited':
      return _popupInactive(partner, routeOriginActive);
    case 'Onboarding':
      return _popupOnboarding(partner, routeOriginActive);
    case 'BG Checks':
      return _popupVetting(partner, routeOriginActive);
    case 'Prospect':
      return _popupProspect(partner, routeOriginActive);
    case 'New':
      return _popupNewPartner(partner);
    default:
      return _popupActive(partner, routeOriginActive);
  }
}

function _popupActive(p: Partner, routeOriginActive = false): string {
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">${p.name}</h5>
    ${_table(
      _row('Store ID', p.store_id) +
      _row('Status', p.status) +
      _row('Carteira', p.bucket_ade) +
      _row('Delivery Station', p.delivery_station) +
      _row('Launch Date', p.launch_date) +
      _row('HCP Initiatives', p.hub_delivey_initiatives) +
      _row('HCP Host Partner', p.HCP_host_partner) +
      _row('HCP Rate Card', p.HCP_rate_card) +
      _row('Radius', p.radius + ' m') +
      _row('Capacity', p.capacity + ' pkgs'),
    )}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_sfLink(p.salesforce_id)}${_waLink(p.telefone)}
    ${_actionButtons(p, routeOriginActive)}
  </div>`;
}

function _popupInactive(p: Partner, routeOriginActive = false): string {
  const capSuggestion = p.status === 'Exited' ? p.capacity : _opt(p).cap_suggestion;
  const radiusSuggestion = p.status === 'Exited' ? p.radius : _opt(p).radius_suggestion;
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">${p.name}</h5>
    ${_table(
      _row('Store ID', p.store_id) +
      _row('Status', p.status) +
      _row('Carteira', p.bucket_ade) +
      _row('Delivery Station', p.delivery_station),
    )}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_sfLink(p.salesforce_id)}${_waLink(p.telefone)}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_table(
      _row('Decisão', p.decision) +
      _row('Capacidade Sugerida', capSuggestion + ' pkgs') +
      _row('Raio Sugerido', radiusSuggestion + ' m'),
    )}
    ${_actionButtons(p, routeOriginActive)}
  </div>`;
}

function _popupOnboarding(p: Partner, routeOriginActive = false): string {
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">${p.name}</h5>
    ${_table(
      _row('Store ID', p.store_id) +
      _row('Status', p.status) +
      _row('Carteira', p.bucket_ade) +
      _row('Delivery Station', p.delivery_station) +
      _row('Launch Date', p.launch_date) +
      _row('HCP Initiatives', p.hub_delivey_initiatives) +
      _row('HCP Host Partner', p.HCP_host_partner) +
      _row('HCP Rate Card', p.HCP_rate_card),
    )}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_sfLink(p.salesforce_id)}${_waLink(p.telefone)}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_table(
      _row('Capacidade Sugerida', _opt(p).cap_suggestion + ' pkgs') +
      _row('Raio Sugerido', _opt(p).radius_suggestion + ' m'),
    )}
    ${_actionButtons(p, routeOriginActive)}
  </div>`;
}

function _popupVetting(p: Partner, routeOriginActive = false): string {
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">${p.name}</h5>
    ${_table(
      _row('Store ID', p.store_id) +
      _row('Status', p.status) +
      _row('Carteira', p.bucket_ade) +
      _row('Delivery Station', p.delivery_station) +
      _row('Launch Date', p.launch_date),
    )}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_sfLink(p.salesforce_id)}${_waLink(p.telefone)}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_table(
      _row('Capacidade Sugerida', _opt(p).cap_suggestion + ' pkgs') +
      _row('Raio Sugerido', _opt(p).radius_suggestion + ' m'),
    )}
    ${_actionButtons(p, routeOriginActive)}
  </div>`;
}

function _popupProspect(p: Partner, routeOriginActive = false): string {
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">${p.name}</h5>
    ${_table(
      _row('Store ID', p.store_id) +
      _row('Status', p.status) +
      _row('Carteira', p.bucket_ade) +
      _row('Delivery Station', p.delivery_station),
    )}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_sfLink(p.salesforce_id)}
    <hr style="border-color:#4a5568;margin:8px 0;">
    ${_table(
      _row('Decisão', p.reason) +
      _row('Capacidade Sugerida', _opt(p).cap_suggestion + ' pkgs') +
      _row('Raio Sugerido', _opt(p).radius_suggestion + ' m'),
    )}
    ${_actionButtons(p, routeOriginActive)}
  </div>`;
}

function _popupNewPartner(p: Partner): string {
  const cepsDisplay = Array.isArray(p.ceps) ? p.ceps.join(', ') : (p.ceps ?? '');
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">New Partner</h5>
    ${_table(
      _row('Delivery Station', p.delivery_station) +
      _row('Bucket', p.bucket_ade),
    )}
    <hr style="border-color:#4a5568;margin:8px 0;">
    <div style="max-height:220px;overflow-y:auto;">
      ${_table(
        _row('CEPs Alvo', cepsDisplay) +
        _row('Volume máximo', p.capacity + ' pkgs') +
        _row('Raio Sugerido', p.radius + ' m'),
      )}
    </div>
  </div>`;
}

// ---------------------------------------------------------------------------
// POPUP DE COMPARAÇÃO
// ---------------------------------------------------------------------------

/**
 * Retorna o HTML do popup de comparação entre dois parceiros.
 */
export function getComparisonPopupHtml(p1: Partner, p2: Partner): string {
  const fields: Array<{ label: string; key: keyof Partner }> = [
    { label: 'Status', key: 'status' },
    { label: 'Delivery Station', key: 'delivery_station' },
    { label: 'Carteira', key: 'bucket_ade' },
    { label: 'Radius', key: 'radius' },
    { label: 'Capacity', key: 'capacity' },
    { label: 'HCP Initiatives', key: 'hub_delivey_initiatives' },
    { label: 'HCP Rate Card', key: 'HCP_rate_card' },
    { label: 'Launch Date', key: 'launch_date' },
  ];

  const rows = fields
    .map(
      ({ label, key }) =>
        `<tr>
          <td style="padding:3px 6px;font-weight:600;color:#a0aec0;">${label}</td>
          <td style="padding:3px 6px;">${p1[key] ?? 'N/A'}</td>
          <td style="padding:3px 6px;">${p2[key] ?? 'N/A'}</td>
        </tr>`,
    )
    .join('');

  return `<div style="width:420px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">Comparação de Parceiros</h5>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:1px solid #4a5568;">
          <th style="padding:4px 6px;text-align:left;color:#a0aec0;">Campo</th>
          <th style="padding:4px 6px;text-align:left;">${p1.name}</th>
          <th style="padding:4px 6px;text-align:left;">${p2.name}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ---------------------------------------------------------------------------
// POPUP DE SLOT IDEAL
// ---------------------------------------------------------------------------

/**
 * Retorna o HTML do popup de um slot ideal (oportunidade sem parceiro).
 */
export function getSlotPopupHtml(partner: Partner): string {
  const cepsDisplay = Array.isArray(partner.ceps)
    ? partner.ceps.join(', ')
    : (partner.ceps ?? '');
  return `<div style="width:300px;font-size:12px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:10px;">
    <h5 style="font-weight:bold;margin-bottom:8px;">🎯 Slot Ideal</h5>
    ${_table(
      _row('Delivery Station', partner.delivery_station) +
      _row('Território', partner.bucket_ade) +
      _row('Slot ID', partner.slot_id) +
      _row('Capacidade Sugerida', partner.capacity + ' pkgs') +
      _row('Raio Sugerido', partner.radius + ' m') +
      _row('CEPs Alvo', cepsDisplay),
    )}
  </div>`;
}

// ---------------------------------------------------------------------------
// POPUP DE DELIVERY STATION
// ---------------------------------------------------------------------------

/**
 * Retorna o HTML do popup de uma delivery station.
 */
export function getStationPopupHtml(station: DeliveryStation): string {
  return `<div style="font-size:13px;background:#1e2a38;color:#ecf0f1;border-radius:6px;padding:8px 12px;">
    <b>${station.nome}</b><br>
    <span style="color:#a0aec0;font-size:11px;">${station.lat.toFixed(4)}, ${station.lon.toFixed(4)}</span>
  </div>`;
}
