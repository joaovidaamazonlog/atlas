/**
 * gmaps-scraper.js
 * ================
 * Busca empresas candidatas a parceiro logístico.
 *
 * Fontes de dados
 * ---------------
 * 1. gmaps_results.json — gerado pelo GitHub Actions (Google Maps scraping)
 * 2. API Receita Federal — busca em tempo real por CEP
 *
 * Filtro
 * ------
 * Quando o usuário clica em "Ver Empresas Candidatas" num slot,
 * os resultados são filtrados pelos CEPs do slot.
 * Se nenhum resultado for encontrado pelos CEPs, exibe todos do território.
 */

import { state }       from '../state.js';
import { DATA_URLS, CNPJ_API_URL } from '../config.js';
import { ProspectCompany } from '../models.js';
import { geocodeBatch } from './ui-manager.js';

/** @type {Object|null} Cache em memória do gmaps_results.json */
let _cache = null;

// ---------------------------------------------------------------------------
// CARREGAMENTO
// ---------------------------------------------------------------------------

/**
 * Carrega gmaps_results.json com cache em memória.
 * Se indisponível, retorna estrutura vazia sem lançar erro.
 * @returns {Promise<Object>}
 */
export async function loadResults() {
    if (_cache) return _cache;
    try {
        const res = await fetch(DATA_URLS.gmapsResults);
        if (!res.ok) {
            console.warn(`[GmapsScraper] gmaps_results.json nao encontrado (${res.status}) — usando apenas API.`);
            _cache = { results: {}, generated_at: null };
            return _cache;
        }
        _cache = await res.json();
    } catch (err) {
        console.warn('[GmapsScraper] gmaps_results.json indisponivel — usando apenas API.', err);
        _cache = { results: {}, generated_at: null };
    }
    return _cache;
}

/**
 * Normaliza os campos de endereço da Receita Federal num formato legível
 * e compatível com geocodificação.
 * Ex: "Rua das Flores, 123 - Centro, Belo Horizonte - MG, 30000-000"
 */
function _normalizeAddress(logradouro, numero, bairro, municipio, uf, cep) {
    // Capitalizar primeira letra de cada palavra, exceto preposições
    const PREPS = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'a', 'o']);
    const titleCase = str => (str || '')
        .toLowerCase()
        .replace(/[^\w\s]/g, c => c) // preservar pontuação
        .split(' ')
        .map((w, i) => (i === 0 || !PREPS.has(w)) ? w.charAt(0).toUpperCase() + w.slice(1) : w)
        .join(' ')
        .trim();

    // Limpar número: remover zeros à esquerda, "S/N" vira "S/N"
    const num = (numero || '').trim().replace(/^0+(\d)/, '$1') || 'S/N';

    // Formatar CEP: 00000000 → 00000-000
    const cepFmt = (cep || '').replace(/\D/g, '').replace(/^(\d{5})(\d{3})$/, '$1-$2');

    const parts = [
        logradouro ? `${titleCase(logradouro)}, ${num}` : null,
        bairro     ? titleCase(bairro)                  : null,
        municipio  ? `${titleCase(municipio)} - ${(uf || '').toUpperCase()}` : null,
        cepFmt     || null,
    ];
    return parts.filter(Boolean).join(', ');
}

/**
 * Busca empresas na API da Receita Federal por lista de CEPs.
 * @param {string[]} ceps
 * @returns {Promise<ProspectCompany[]>}
 */
export async function loadFromApi(ceps) {
    if (!ceps || ceps.length === 0) return [];
    try {
        const res = await fetch(CNPJ_API_URL, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ ceps }),
        });
        if (!res.ok) return [];
        const data = await res.json();
        return (data.empresas || []).map(e => new ProspectCompany({
            nome:             e.razao_social || e.nome_fantasia || 'N/A',
            endereco:         _normalizeAddress(e.endereco, e.numero, e.bairro, e.municipio, e.uf, e.cep),
            telefone_1:       e.telefone_1 || null,
            telefone_2:       e.telefone_2 || null,
            site:             'N/A',
            google_maps_link: 'N/A',
            cep:              e.cep,
            tipo:             'Receita Federal',
            _fonte:           'Receita Federal 🏛️',
        }));
    } catch (err) {
        console.warn('[GmapsScraper] API Receita Federal indisponivel:', err);
        return [];
    }
}

// ---------------------------------------------------------------------------
// BUSCA PRINCIPAL
// ---------------------------------------------------------------------------

/**
 * Chamado pelo botão no popup do slot via chave de estado.
 * Recupera os CEPs do AppState e delega para searchNearby.
 *
 * @param {Event}  event
 * @param {string} territoryId
 * @param {string} slotKey     - Chave em state._slotPopupData
 */
export async function searchNearbyFromState(event, territoryId, slotKey) {
    const ceps = (state._slotPopupData && state._slotPopupData[slotKey]) || [];

    // slotKey é o slot_id sanitizado (ex: "DBH5_bucket_01_S09")
    // Reverter a sanitização para encontrar o slot correto no geojson
    // O slot_id original usa hífens: "DBH5_bucket-01_S09"
    // A sanitização troca "-" por "_", então tentamos ambos os formatos
    const slotFeature = state.idealSupplyData?.find(f => {
        const sid = f.properties.slot_id || '';
        const sidSanitized = sid.replace(/[^a-zA-Z0-9_]/g, '_');
        return sidSanitized === slotKey || sid === slotKey;
    }) || state.idealSupplyData?.find(
        // Fallback: primeiro slot aberto do território
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
 * Combina resultados do Google Maps e da Receita Federal.
 *
 * @param {Event}    event
 * @param {string}   territoryId
 * @param {string[]} slotCeps
 * @param {{lat:number,lon:number,radius_s:number}|null} slotGeo - Para match geográfico
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

        const [gmapsData, apiResults] = await Promise.all([
            loadResults(),
            loadFromApi(cepList),
        ]);

        // ── Google Maps: filtrar ≤1000m e calcular distância ─────────────
        const GMAPS_MAX_DISTANCE_M = 1000;
        const allForTerritory = gmapsData.results?.[territoryId] || [];
        const gmapsResults = allForTerritory
            .map(r => {
                const company = new ProspectCompany({ ...r, _fonte: 'Google Maps 🗺️' });
                if (slotGeo && company.isGeolocated) {
                    const slotPt    = turf.point([slotGeo.lon, slotGeo.lat]);
                    const companyPt = turf.point([company.lon, company.lat]);
                    const distM     = Math.round(turf.distance(slotPt, companyPt, { units: 'meters' }));
                    company.isMatch   = distM <= slotGeo.radius_s;
                    company.distanceM = distM;
                } else {
                    company.isMatch   = null;
                    company.distanceM = null;
                }
                return company;
            })
            // Mostrar apenas empresas a até 1km do slot (quando temos coordenadas)
            .filter(c => c.distanceM === null || c.distanceM <= GMAPS_MAX_DISTANCE_M);

        // ── Receita Federal: pré-filtro por hex via CEP → geocode → distância ─
        const MAX_DISTANCE_M = 1000;

        // 1. Identificar quais hexes cobrem os CEPs do slot
        const slotHexIds = new Set(
            state.heatmapData?.features
                ?.filter(f => Array.isArray(f.properties.ceps) &&
                              f.properties.ceps.some(c => cepSet.has(c)))
                ?.map(f => f.properties.hex_id) ?? []
        );

        // 2. Pré-filtrar: manter apenas empresas cujo CEP pertence a um hex do slot
        const preFiltered = slotHexIds.size > 0
            ? apiResults.filter(r => {
                if (!r.cep) return false;
                const hex = state.heatmapData?.features?.find(
                    f => Array.isArray(f.properties.ceps) && f.properties.ceps.includes(r.cep)
                );
                return hex ? slotHexIds.has(hex.properties.hex_id) : false;
            })
            : apiResults; // sem heatmap, não filtra

        // 3. Geocodificar apenas as empresas pré-filtradas
        const addressesToGeocode = preFiltered
            .map((r, i) => ({ i, address: r.endereco }))
            .filter(({ address }) => !!address);

        const geocoded = addressesToGeocode.length > 0
            ? await geocodeBatch(addressesToGeocode.map(x => x.address))
            : [];

        addressesToGeocode.forEach(({ i }, gi) => {
            const g = geocoded[gi];
            if (g?.lat && g?.lng) {
                preFiltered[i].lat = g.lat;
                preFiltered[i].lon = g.lng;
            }
        });

        // 4. Calcular distância métrica e filtrar ≤1km (igual ao fluxo Maps)
        const apiResultsMapped = preFiltered
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

        const results = [...gmapsResults, ...apiResultsMapped];

        // Ordenar: ✅ dentro do raio/grid primeiro, depois ⚠️ fora, depois sem validação
        results.sort((a, b) => {
            const score = r => r.isMatch === true ? 0 : r.isMatch === false ? 1 : 2;
            return score(a) - score(b);
        });

        showResults(results, territoryId, cepSet.size > 0, gmapsData.generated_at);
    } catch (err) {
        alert(`Erro: ${err.message}`);
        console.error('[GmapsScraper]', err);
    } finally {
        document.getElementById('gmaps-scraper-loading')?.remove();
    }
}

// ---------------------------------------------------------------------------
// MARCADORES DE LEAD NO MAPA
// ---------------------------------------------------------------------------

/** @type {Map<string, L.Marker>} Marcadores de lead fixados no mapa */
const _pinnedLeadMarkers = new Map();

const _pinIcon = L.divIcon({
    className: '',
    html: `<div style="font-size:32px;line-height:1;filter:drop-shadow(0 2px 4px #0008);">📍</div>`,
    iconAnchor: [16, 32],
});

function _leadKey(r) {
    return `${r.nome}|${r.lat}|${r.lon}`;
}

function _togglePin(r, btnEl) {
    const key = _leadKey(r);
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
// EXIBIÇÃO DE RESULTADOS
// ---------------------------------------------------------------------------

/**
 * Exibe os resultados num popup lateral agrupados por tipo de negócio.
 *
 * @param {ProspectCompany[]} results
 * @param {string}            territoryId
 * @param {boolean}           usedCepFilter
 * @param {string|null}       generatedAt
 */
export function showResults(results, territoryId, usedCepFilter, generatedAt) {
    document.getElementById('gmaps-scraper-popup')?.remove();

    const byType = {};
    results.forEach(r => {
        const t = r.tipo || 'outros';
        if (!byType[t]) byType[t] = [];
        byType[t].push(r);
    });

    const dateStr    = generatedAt ? new Date(generatedAt).toLocaleDateString('pt-BR') : 'N/A';
    const apiCount   = results.filter(r => r._fonte?.includes('Receita')).length;
    const gmapsCount = results.length - apiCount;

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
    sub.innerHTML = `${results.length} empresa(s) — 🗺️ ${gmapsCount} Google Maps · 🏛️ ${apiCount} Receita Federal<br>
        ${usedCepFilter ? '🔎 filtrado por CEPs do slot' : '📍 todos do territorio'} · atualizado em ${dateStr}`;
    popup.appendChild(sub);

    // Lista
    const list = document.createElement('div');
    list.style = 'max-height:600px;overflow-y:auto;';

    if (results.length === 0) {
        list.innerHTML = '<div style="color:#888;padding:12px 0;">Nenhuma empresa encontrada.<br>Execute o workflow no GitHub Actions para atualizar os dados.</div>';
    } else {
        for (const [tipo, empresas] of Object.entries(byType)) {
            const groupTitle = document.createElement('h6');
            groupTitle.style = 'margin:10px 0 4px;text-transform:capitalize;color:#333;';
            groupTitle.textContent = `📂 ${tipo} (${empresas.length})`;
            list.appendChild(groupTitle);

            empresas.forEach(r => {
                const card = document.createElement('div');
                card.style = 'border-bottom:1px solid #eee;padding:6px 0;font-size:12px;position:relative;';

                // Badge de distância
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
                    <div style="display:flex;align-items:baseline;gap:4px;color:#555;">
                        <span>📍 ${r.endereco}</span>
                        ${hasCoords ? `<button class="lead-pin-btn" title="Fixar no mapa" style="border:none;background:none;font-size:18px;cursor:pointer;opacity:0;transition:opacity .15s;padding:0;line-height:1;flex-shrink:0;">📌</button>` : ''}
                    </div>
                    ${r.primaryPhone   ? `<span>📞 ${r.primaryPhone}</span><br>`   : ''}
                    ${r.secondaryPhone ? `<span>📞 ${r.secondaryPhone}</span><br>` : ''}
                    ${r.hasSite     ? `<span>🌐 <a href="${r.site}" target="_blank">${r.site}</a></span><br>` : ''}
                    ${r.hasMapsLink ? `<a href="${r.google_maps_link}" target="_blank" style="font-size:11px;">Ver no Google Maps ↗</a>` : ''}
                `;

                if (hasCoords) {
                    const pinBtn = card.querySelector('.lead-pin-btn');
                    pinBtn.onclick = () => _togglePin(r, pinBtn);
                    card.addEventListener('mouseenter', () => { pinBtn.style.opacity = _pinnedLeadMarkers.has(_leadKey(r)) ? '1' : '0.35'; });
                    card.addEventListener('mouseleave', () => { if (!_pinnedLeadMarkers.has(_leadKey(r))) pinBtn.style.opacity = '0'; });
                }

                list.appendChild(card);
            });
        }
    }

    popup.appendChild(list);
    document.body.appendChild(popup);
}
