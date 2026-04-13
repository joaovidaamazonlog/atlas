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
  return `<a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${id}/view" target="_blank" style="color:#4fc3f7;">Ver no Salesforce</a><br>`;
}

function _waLink(tel: string | null): string {
  if (!tel) return '';
  return `<a href="https://wa.me/${tel}" target="_blank" style="color:#25d366;">WhatsApp</a>`;
}

// ---------------------------------------------------------------------------
// POPUP DE PARCEIRO (principal)
// ---------------------------------------------------------------------------

/**
 * Retorna o HTML do popup de um parceiro com base no seu status.
 * Migrado de `getPopupContent` em ui-manager.js.
 */
export function getPartnerPopupHtml(partner: Partner): string {
  switch (partner.status) {
    case 'Active':
      return _popupActive(partner);
    case 'Inactive':
    case 'Exited':
      return _popupInactive(partner);
    case 'Onboarding':
      return _popupOnboarding(partner);
    case 'BG Checks':
      return _popupVetting(partner);
    case 'Prospect':
      return _popupProspect(partner);
    case 'New':
      return _popupNewPartner(partner);
    default:
      return _popupActive(partner);
  }
}

function _popupActive(p: Partner): string {
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
  </div>`;
}

function _popupInactive(p: Partner): string {
  const capSuggestion =
    p.status === 'Exited' ? p.capacity : p.optimization.cap_suggestion;
  const radiusSuggestion =
    p.status === 'Exited' ? p.radius : p.optimization.radius_suggestion;
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
  </div>`;
}

function _popupOnboarding(p: Partner): string {
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
      _row('Capacidade Sugerida', p.optimization.cap_suggestion + ' pkgs') +
      _row('Raio Sugerido', p.optimization.radius_suggestion + ' m'),
    )}
  </div>`;
}

function _popupVetting(p: Partner): string {
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
      _row('Capacidade Sugerida', p.optimization.cap_suggestion + ' pkgs') +
      _row('Raio Sugerido', p.optimization.radius_suggestion + ' m'),
    )}
  </div>`;
}

function _popupProspect(p: Partner): string {
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
      _row('Capacidade Sugerida', p.optimization.cap_suggestion + ' pkgs') +
      _row('Raio Sugerido', p.optimization.radius_suggestion + ' m'),
    )}
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
