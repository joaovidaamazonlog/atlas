/**
 * gmaps-scraper.js
 * ================
 * Busca empresas candidatas a parceiro logístico via API unificada.
 *
 * Fonte de dados
 * --------------
 * POST /api/empresas — retorna Receita Federal + Google Maps com flag contactada
 * POST /api/empresas/contactada — toggle de empresa contactada
 */

import { state }        from '../state.js';
import { API_BASE_URL } from '../config.js';
import { ProspectCompany } from '../models.js';
import { geocodeBatch }    from './ui-manager.js';

// ---------------------------------------------------------------------------
// BUSCA PRINCIPAL
// ---------------------------------------------------------------------------

/**
 * Chamado pelo botão no popup do slot via chave de estado.
 */
export async function searchNearbyFromState(event, territoryId, slotKey) {
    const ceps = (state._slotPopupData && state._slotPopupData[slotKey]) || [];

    const slotFeature = state.idealSupplyData?.find(f => {
        const sid = f.properties.slot_id || '';
        const sidSanitized = sid.replace(/[^a-zA-Z0-9_]/g, '_');
        return sidSanitized === slotKey || sid === slotKey;
    }) || state.idealSupplyData?.find(
        f => f.properties.territory_id === territoryId && f.properties.type === 'IDEAL_SLOT'
    );

    const slotGeo = slotFeature ? {
        lat:      slotFeature.geometry.coordinates[1],
        lon:      slotFeature.geometry.coordinates[0],
        radius_s: slotFeature.properties.radius_s,
        slot_id:  slotFeature.properties.slot_id,
    } : null;

    return searchNearby(event, territoryId, ceps, slotGeo);
}

/**
 * Busca empresas candidatas para um slot/território.
 * Um único request à API retorna Receita Federal + Maps + flag contactada.
 */
export async function searchNearby(event, territoryId, slotCeps, slotGeo = null) {
    event.stopPropagation();

    const loading = document.createElement('div');
    loading.id = 'gmaps-scraper-loading';
    loading.style = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.3);z-index:99999;display:flex;align-items:center;justify-content:center;';
    loading.innerHTML = '<div style="background:#fff;padding:28px;border-radius:8px;"><i class="fas fa-spinner fa-spin mr-2"></i> Carregando empresas...</div>';
    document.body.appendChild(loading);

    try {
        const cepList = (Array.isArray(slotCeps) ? slotCeps : String(slotCeps).split(','))
            .map(c => c.trim().replace(/\D/g, ''))
            .filter(c => c.length === 8);

        const cepSet = new Set(cepList);

        // ── Request único à API ───────────────────────────────────────────
        const res = await fetch(`${API_BASE_URL}/api/empresas`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ ceps: cepList, territory_id: territoryId }),
        });

        if (!res.ok) throw new Error(`API retornou ${res.status}`);
        const data = await res.json();

        // ── Mapear para ProspectCompany e calcular distâncias ─────────────
        const MAX_DISTANCE_M = 1000;

        // Separar por fonte para processamento específico
        const rawMaps    = (data.empresas || []).filter(e => e.fonte === 'Google Maps');
        const rawReceita = (data.empresas || []).filter(e => e.fonte === 'Receita Federal');

        // Maps — calcular distância diretamente (já tem lat/lon)
        const mapsResults = rawMaps
            .map(e => {
                const company = new ProspectCompany({ ...e, _fonte: 'Google Maps 🗺️' });
                if (slotGeo && company.isGeolocated) {
                    const distM = Math.round(turf.distance(
                        turf.point([slotGeo.lon, slotGeo.lat]),
                        turf.point([company.lon, company.lat]),
                        { units: 'meters' }
                    ));
                    company.isMatch   = distM <= slotGeo.radius_s;
                    company.distanceM = distM;
                } else {
                    company.isMatch   = null;
                    company.distanceM = null;
                }
                return company;
            })
            .filter(c => c.distanceM === null || c.distanceM <= MAX_DISTANCE_M);

        // Receita Federal — pré-filtro por hex → geocode → distância
        const slotHexIds = new Set(
            state.heatmapData?.features
                ?.filter(f => Array.isArray(f.properties.ceps) &&
                              f.properties.ceps.some(c => cepSet.has(c)))
                ?.map(f => f.properties.hex_id) ?? []
        );

        const preFiltered = slotHexIds.size > 0
            ? rawReceita.filter(r => {
                if (!r.cep) return false;
                const hex = state.heatmapData?.features?.find(
                    f => Array.isArray(f.properties.ceps) && f.properties.ceps.includes(r.cep)
                );
                return hex ? slotHexIds.has(hex.properties.hex_id) : false;
            })
            : rawReceita;

        // Normalizar endereço Receita Federal
        const receitaObjs = preFiltered.map(e => new ProspectCompany({
            ...e,
            nome:     e.razao_social || e.nome_fantasia || 'N/A',
            endereco: _normalizeAddress(e.endereco, e.numero, e.bairro, e.municipio, e.uf, e.cep),
            _fonte:   'Receita Federal 🏛️',
        }));

        // Geocodificar e calcular distância
        const addressesToGeocode = receitaObjs
            .map((r, i) => ({ i, address: r.endereco }))
            .filter(({ address }) => !!address);

        const geocoded = addressesToGeocode.length > 0
            ? await geocodeBatch(addressesToGeocode.map(x => x.address))
            : [];

        addressesToGeocode.forEach(({ i }, gi) => {
            const g = geocoded[gi];
            if (g?.lat && g?.lng) {
                receitaObjs[i].lat = g.lat;
                receitaObjs[i].lon = g.lng;
            }
        });

        const receitaResults = receitaObjs
            .map(r => {
                if (slotGeo && r.lat != null && r.lon != null) {
                    const distM = Math.round(turf.distance(
                        turf.point([slotGeo.lon, slotGeo.lat]),
                        turf.point([r.lon, r.lat]),
                        { units: 'meters' }
                    ));
                    r.isMatch   = distM <= slotGeo.radius_s;
                    r.distanceM = distM;
                } else {
                    r.isMatch   = cepSet.size > 0 ? cepSet.has(r.cep) : null;
                    r.distanceM = null;
                }
                return r;
            })
            .filter(r => r.distanceM === null || r.distanceM <= MAX_DISTANCE_M);

        const results = [...mapsResults, ...receitaResults];
        showResults(results, territoryId, cepSet.size > 0);

    } catch (err) {
        alert(`Erro: ${err.message}`);
        console.error('[GmapsScraper]', err);
    } finally {
        document.getElementById('gmaps-scraper-loading')?.remove();
    }
}

// ---------------------------------------------------------------------------
// TOGGLE CONTACTADA
// ---------------------------------------------------------------------------

function _leadKey(r) {
    if (r.google_maps_link && r.google_maps_link !== 'N/A') return r.google_maps_link;
    return `${r.nome}|${r.endereco}`;
}

async function _toggleContactada(r) {
    const key    = _leadKey(r);
    const action = r.contactada ? 'remove' : 'add';

    try {
        const res = await fetch(`${API_BASE_URL}/api/empresas/contactada`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                lead_key:   key,
                lead_nome:  r.nome        || '',
                territorio: r.territory_id || '',
                fonte:      r._fonte       || '',
                action,
            }),
        });
        if (!res.ok) console.warn('[Contactada] API falhou:', res.status);
    } catch (err) {
        console.warn('[Contactada] Erro:', err);
    }

    return action === 'add';
}

// ---------------------------------------------------------------------------
// MARCADORES DE LEAD NO MAPA
// ---------------------------------------------------------------------------

const _pinnedLeadMarkers = new Map();

const _pinIcon = L.divIcon({
    className: '',
    html: `<div style="font-size:32px;line-height:1;filter:drop-shadow(0 2px 4px #0008);">📍</div>`,
    iconAnchor: [16, 32],
});

function _mapLeadKey(r) {
    return `${r.nome}|${r.lat}|${r.lon}`;
}

function _togglePin(r, btnEl) {
    const key = _mapLeadKey(r);
    if (_pinnedLeadMarkers.has(key)) {
        _pinnedLeadMarkers.get(key).remove();
        _pinnedLeadMarkers.delete(key);
        btnEl.title = 'Fixar no mapa';
        btnEl.style.opacity = '0.35';
    } else {
        const phone = r.primaryPhone || r.secondaryPhone;
        const marker = L.marker([r.lat, r.lon], { icon: _pinIcon })
            .addTo(state.map)
            .bindPopup(`
                <b>${r.nome}</b><br>
                <span style="font-size:11px;">${r.endereco}</span>
                ${phone ? `<br><span style="font-size:11px;">📞 ${phone}</span>` : ''}
            `)
            .openPopup();
        state.map.setView([r.lat, r.lon], Math.max(state.map.getZoom(), 15));
        _pinnedLeadMarkers.set(key, marker);
        btnEl.title = 'Remover do mapa';
        btnEl.style.opacity = '1';
    }
}

function _clearAllPins() {
    _pinnedLeadMarkers.forEach(m => m.remove());
    _pinnedLeadMarkers.clear();
}

// ---------------------------------------------------------------------------
// NORMALIZAÇÃO DE ENDEREÇO (Receita Federal)
// ---------------------------------------------------------------------------

function _normalizeAddress(logradouro, numero, bairro, municipio, uf, cep) {
    const PREPS = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'a', 'o']);
    const titleCase = str => (str || '')
        .toLowerCase()
        .split(' ')
        .map((w, i) => (i === 0 || !PREPS.has(w)) ? w.charAt(0).toUpperCase() + w.slice(1) : w)
        .join(' ')
        .trim();

    const num    = (numero || '').trim().replace(/^0+(\d)/, '$1') || 'S/N';
    const cepFmt = (cep || '').replace(/\D/g, '').replace(/^(\d{5})(\d{3})$/, '$1-$2');

    return [
        logradouro ? `${titleCase(logradouro)}, ${num}` : null,
        bairro     ? titleCase(bairro)                  : null,
        municipio  ? `${titleCase(municipio)} - ${(uf || '').toUpperCase()}` : null,
        cepFmt     || null,
    ].filter(Boolean).join(', ');
}

// ---------------------------------------------------------------------------
// EXIBIÇÃO DE RESULTADOS
// ---------------------------------------------------------------------------

export function showResults(results, territoryId, usedCepFilter) {
    document.getElementById('gmaps-scraper-popup')?.remove();

    // Ordenar: dentro do raio → fora → sem validação → contactadas por último
    results.sort((a, b) => {
        const saved = r => r.contactada ? 1 : 0;
        const score = r => r.isMatch === true ? 0 : r.isMatch === false ? 1 : 2;
        return (saved(a) - saved(b)) || (score(a) - score(b));
    });

    const byType     = {};
    const mapsCount  = results.filter(r => r._fonte?.includes('Maps')).length;
    const rfCount    = results.filter(r => r._fonte?.includes('Receita')).length;
    const savedCount = results.filter(r => r.contactada).length;

    results.forEach(r => {
        const t = r.tipo || 'outros';
        if (!byType[t]) byType[t] = [];
        byType[t].push(r);
    });

    const popup = document.createElement('div');
    popup.id = 'gmaps-scraper-popup';
    popup.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;width:420px;max-width:95vw;box-shadow:0 2px 12px #0004;';

    // Header
    const header = document.createElement('div');
    header.style = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;';
    header.innerHTML = `<b>🏪 Empresas Candidatas — ${territoryId}</b>`;
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
    closeBtn.style = 'border:none;background:none;font-size:1.3em;line-height:1;cursor:pointer;';
    closeBtn.onclick = () => { _clearAllPins(); popup.remove(); };
    header.appendChild(closeBtn);
    popup.appendChild(header);

    // Subtítulo
    const sub = document.createElement('div');
    sub.style = 'font-size:11px;color:#666;margin-bottom:8px;';
    const updateSub = () => {
        const sc = results.filter(r => r.contactada).length;
        sub.innerHTML = `${results.length} empresa(s) — 🗺️ ${mapsCount} Google Maps · 🏛️ ${rfCount} Receita Federal`
            + (sc > 0 ? ` · <span style="color:#16a34a;">✅ ${sc} contactada(s)</span>` : '')
            + `<br>${usedCepFilter ? '🔎 filtrado por CEPs do slot' : '📍 todos do território'}`;
    };
    updateSub();
    popup.appendChild(sub);

    // Lista
    const list = document.createElement('div');
    list.style = 'max-height:600px;overflow-y:auto;';

    if (results.length === 0) {
        list.innerHTML = '<div style="color:#888;padding:12px 0;">Nenhuma empresa encontrada.</div>';
    } else {
        for (const [tipo, empresas] of Object.entries(byType)) {
            const groupTitle = document.createElement('h6');
            groupTitle.style = 'margin:10px 0 4px;text-transform:capitalize;color:#333;';
            groupTitle.textContent = `📂 ${tipo} (${empresas.length})`;
            list.appendChild(groupTitle);

            empresas.forEach(r => {
                const card = document.createElement('div');
                card.style = `border-bottom:1px solid #eee;padding:6px 0;font-size:12px;position:relative;${r.contactada ? 'opacity:0.6;' : ''}`;

                let matchBadge = '';
                if (r.isMatch === true) {
                    const dist = r.distanceM !== null ? ` (${r.distanceM}m)` : '';
                    matchBadge = `<div style="margin:2px 0;"><span style="color:#16a34a;font-weight:bold;">✅ Dentro do raio do slot</span><span style="font-size:10px;color:#666;">${dist}</span></div>`;
                } else if (r.isMatch === false) {
                    const dist = r.distanceM !== null ? ` (${r.distanceM}m)` : '';
                    matchBadge = `<div style="margin:2px 0;"><span style="color:#d97706;">⚠️ Fora do raio</span><span style="font-size:10px;color:#666;">${dist}</span></div>`;
                }

                const hasCoords = r.lat != null && r.lon != null;

                card.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                        <b style="flex:1;margin-right:4px;">${r.nome}</b>
                        <span style="font-size:10px;color:#888;white-space:nowrap;">${r._fonte || ''}</span>
                    </div>
                    ${matchBadge}
                    <div style="display:flex;align-items:baseline;justify-content:space-between;color:#555;">
                        <span style="flex:1;">📍 ${r.endereco}</span>
                        ${hasCoords ? `<button class="lead-pin-btn" title="Fixar no mapa" style="border:none;background:none;font-size:18px;cursor:pointer;opacity:0;transition:opacity .15s;padding:0;line-height:1;flex-shrink:0;margin-left:4px;">📌</button>` : ''}
                    </div>
                    ${r.primaryPhone   ? `<span>📞 ${r.primaryPhone}</span><br>`   : ''}
                    ${r.secondaryPhone ? `<span>📞 ${r.secondaryPhone}</span><br>` : ''}
                    <div style="margin-top:3px;">
                        <button class="lead-save-btn" style="border:none;background:none;font-size:11px;cursor:pointer;padding:0;color:${r.contactada ? '#16a34a' : '#999'};">
                            ${r.contactada ? '✅ Empresa contactada' : '☐ Marcar como contactada'}
                        </button>
                    </div>
                    ${r.hasSite     ? `<span>🌐 <a href="${r.site}" target="_blank">${r.site}</a></span><br>` : ''}
                    ${r.hasMapsLink ? `<a href="${r.google_maps_link}" target="_blank" style="font-size:11px;">Ver no Google Maps ↗</a>` : ''}
                `;

                // Toggle contactada
                const saveBtn = card.querySelector('.lead-save-btn');
                saveBtn.onclick = async (e) => {
                    e.stopPropagation();
                    saveBtn.disabled = true;
                    saveBtn.textContent = '⏳ Salvando...';
                    const nowSaved = await _toggleContactada(r);
                    r.contactada = nowSaved;
                    saveBtn.disabled = false;
                    saveBtn.textContent = nowSaved ? '✅ Empresa contactada' : '☐ Marcar como contactada';
                    saveBtn.style.color = nowSaved ? '#16a34a' : '#999';
                    card.style.opacity  = nowSaved ? '0.6' : '1';
                    updateSub();
                };

                if (hasCoords) {
                    const pinBtn = card.querySelector('.lead-pin-btn');
                    pinBtn.onclick = () => _togglePin(r, pinBtn);
                    card.addEventListener('mouseenter', () => { pinBtn.style.opacity = _pinnedLeadMarkers.has(_mapLeadKey(r)) ? '1' : '0.35'; });
                    card.addEventListener('mouseleave', () => { if (!_pinnedLeadMarkers.has(_mapLeadKey(r))) pinBtn.style.opacity = '0'; });
                }

                list.appendChild(card);
            });
        }
    }

    popup.appendChild(list);
    document.body.appendChild(popup);
}
