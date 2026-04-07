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
            endereco:         [e.endereco, e.bairro, e.cep, e.uf].filter(Boolean).join(', '),
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

        // ── Receita Federal: match via H3 grid_disk usando heatmap.geojson ─
        // Constrói índice CEP → hex_id a partir do heatmap carregado no estado
        const apiResultsMapped = apiResults.map(r => {
            if (!r.cep) {
                r.isMatch = null; r.distanceM = null; return r;
            }

            // Buscar o hex que contém este CEP no heatmap
            const hexFeature = state.heatmapData?.features?.find(
                f => Array.isArray(f.properties.ceps) && f.properties.ceps.includes(r.cep)
            );

            if (hexFeature && slotGeo) {
                // Calcular distância H3 entre o hex da empresa e o origin_hex do slot
                // Usamos o slotFeature para pegar o origin_hex
                const slotFeature = state.idealSupplyData?.find(
                    f => f.properties.territory_id === (r.territory_id || '')
                );
                const slotOriginHex = slotFeature?.properties?.origin_hex;
                const companyHex    = hexFeature.properties.hex_id;

                if (slotOriginHex && companyHex && window.h3) {
                    try {
                        const gridDist = h3.gridDistance(companyHex, slotOriginHex);
                        r.isMatch   = gridDist <= 1; // grid_disk=1 ≈ 900m
                        r.gridDist  = gridDist;
                        r.distanceM = null; // não temos distância métrica exata
                    } catch {
                        // hexes em resoluções diferentes — fallback por CEP
                        r.isMatch   = cepSet.has(r.cep);
                        r.distanceM = null;
                    }
                } else {
                    // Sem origin_hex disponível — fallback por CEP
                    r.isMatch   = cepSet.has(r.cep);
                    r.distanceM = null;
                }
            } else {
                // Sem heatmap ou sem slotGeo — fallback por CEP
                r.isMatch   = cepSet.size > 0 ? cepSet.has(r.cep) : null;
                r.distanceM = null;
            }
            return r;
        });

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

    // Agrupar por tipo
    /** @type {Object.<string, ProspectCompany[]>} */
    const byType = {};
    results.forEach(r => {
        const t = r.tipo || 'outros';
        if (!byType[t]) byType[t] = [];
        byType[t].push(r);
    });

    const dateStr    = generatedAt ? new Date(generatedAt).toLocaleDateString('pt-BR') : 'N/A';
    const apiCount   = results.filter(r => r._fonte?.includes('Receita')).length;
    const gmapsCount = results.length - apiCount;

    let html = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <b>🏪 Empresas Candidatas — ${territoryId}</b>
            <button onclick="document.getElementById('gmaps-scraper-popup').remove()"
                style="border:none;background:none;font-size:1.3em;line-height:1;">&times;</button>
        </div>
        <div style="font-size:11px;color:#666;margin-bottom:8px;">
            ${results.length} empresa(s) — 🗺️ ${gmapsCount} Google Maps · 🏛️ ${apiCount} Receita Federal<br>
            ${usedCepFilter ? '🔎 filtrado por CEPs do slot' : '📍 todos do territorio'} · atualizado em ${dateStr}
        </div>
        <div style="max-height:600px;overflow-y:auto;">
    `;

    if (results.length === 0) {
        html += '<div style="color:#888;padding:12px 0;">Nenhuma empresa encontrada.<br>Execute o workflow no GitHub Actions para atualizar os dados.</div>';
    } else {
        for (const [tipo, empresas] of Object.entries(byType)) {
            html += `<h6 style="margin:10px 0 4px;text-transform:capitalize;color:#333;">📂 ${tipo} (${empresas.length})</h6>`;
            empresas.forEach(r => {
                // Badge de validação geográfica
                let matchBadge = '';
                if (r.isMatch === true) {
                    const dist = r.distanceM !== null ? ` (${r.distanceM}m)` : r.gridDist !== undefined ? ` (grid_disk=${r.gridDist})` : '';
                    matchBadge = `<div style="margin:2px 0;"><span style="color:#16a34a;font-weight:bold;">✅ Dentro do raio do slot</span><span style="font-size:10px;color:#666;">${dist}</span></div>`;
                } else if (r.isMatch === false) {
                    const dist = r.distanceM !== null ? ` (${r.distanceM}m)` : r.gridDist !== undefined ? ` (grid_disk=${r.gridDist})` : '';
                    matchBadge = `<div style="margin:2px 0;"><span style="color:#d97706;">⚠️ Fora do raio</span><span style="font-size:10px;color:#666;">${dist}</span></div>`;
                }

                html += `
                    <div style="border-bottom:1px solid #eee;padding:6px 0;font-size:12px;">
                        <b>${r.nome}</b>
                        <span style="float:right;font-size:10px;color:#888;">${r._fonte || ''}</span><br>
                        ${matchBadge}
                        <span style="color:#555;">📍 ${r.endereco}</span><br>
                        ${r.primaryPhone   ? `<span>📞 ${r.primaryPhone}</span><br>`   : ''}
                        ${r.secondaryPhone ? `<span>📞 ${r.secondaryPhone}</span><br>` : ''}
                        ${r.hasSite     ? `<span>🌐 <a href="${r.site}" target="_blank">${r.site}</a></span><br>` : ''}
                        ${r.hasMapsLink ? `<a href="${r.google_maps_link}" target="_blank" style="font-size:11px;">Ver no Google Maps ↗</a>` : ''}
                    </div>
                `;
            });
        }
    }

    html += '</div>';

    const popup = document.createElement('div');
    popup.id = 'gmaps-scraper-popup';
    popup.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;width:420px;max-width:95vw;box-shadow:0 2px 12px #0004;';
    popup.innerHTML = html;
    document.body.appendChild(popup);
}
