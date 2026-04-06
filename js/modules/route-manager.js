
/**
 * route-manager.js
 * ================
 * Gerencia rotas, paradas e o sistema HCP de sugestao de clusters.
 */

import { state }     from '../state.js';
import { RouteStop } from '../models.js';
import { HCP_CONFIG } from '../config.js';
import { applyFilters } from './data-manager.js';
import { restyleMarkers } from './map-manager.js';

let _stops = [];

export function generateRoute() {
    if (state.routingControl) { state.map.removeControl(state.routingControl); state.routingControl = null; }
    const fromId = document.getElementById('routeFromId')?.value;
    const toId   = document.getElementById('routeToId')?.value;
    let fromData = state.allMarkersData.find(m => m.salesforce_id === fromId) || state.deliveryStations.find(ds => ds.nome === fromId);
    let toData   = state.allMarkersData.find(m => m.salesforce_id === toId)   || state.deliveryStations.find(ds => ds.nome === toId);
    if (!fromData || !toData) { alert('Parceiro ou Delivery Station invalido.'); return; }
    let stopsOrder = _stops;
    if (_stops.length > 1) { stopsOrder = _optimizeStops(fromData, toData, _stops); _stops = stopsOrder; renderStopsList(); }
    const waypoints = [L.latLng(fromData.lat, fromData.lon), ..._stops.map(s => L.latLng(s.lat, s.lon)), L.latLng(toData.lat, toData.lon)];
    state.routingControl = L.Routing.control({
        waypoints, routeWhileDragging: false,
        router: L.Routing.osrmv1({ serviceUrl: 'https://router.project-osrm.org/route/v1' }),
        createMarker: (i, wp) => L.marker(wp.latLng),
        lineOptions: { styles: [{ color: 'blue', opacity: 0.8, weight: 5 }] },
    }).addTo(state.map);
}

export function startRouteFromHere(event, storeId, storeName) {
    event.stopPropagation();
    document.getElementById('routeFromId').value    = storeId;
    document.getElementById('routeFromInput').value = storeName;
    $('#controlTabs a[href="#route-content"]').tab('show');
    document.getElementById('routeToInput')?.focus();
    state.map.closePopup();
}

export function renderStopsList() {
    const list = document.getElementById('stops-list');
    if (!list) return;
    list.innerHTML = '';
    const fromData = state.allMarkersData.find(m => m.store_id === document.getElementById('routeFromId')?.value);
    const toData   = state.allMarkersData.find(m => m.store_id === document.getElementById('routeToId')?.value);
    const points = [];
    if (fromData) points.push({ ...fromData, type: 'origem' });
    _stops.forEach((s, idx) => points.push({ ...s, type: 'parada', idx }));
    if (toData) points.push({ ...toData, type: 'destino' });
    points.forEach(point => {
        const div = document.createElement('div');
        div.className = 'stop-item d-flex align-items-center mb-1';
        const badge = point.type === 'origem' ? 'badge-primary' : point.type === 'destino' ? 'badge-success' : 'badge-info';
        div.innerHTML = `<span class="badge ${badge} mr-2">${point.type}</span>
            <span class="stop-name flex-grow-1">${point.name || point.store_id} (${point.store_id})</span>
            ${point.type === 'parada' ? `
                <button class="btn btn-sm btn-light mx-1" onclick="RouteManager.moveStopUp(${point.idx})"><i class="fas fa-arrow-up"></i></button>
                <button class="btn btn-sm btn-light mx-1" onclick="RouteManager.moveStopDown(${point.idx})"><i class="fas fa-arrow-down"></i></button>
                <button class="btn btn-sm btn-danger mx-1" onclick="RouteManager.removeStop(${point.idx})"><i class="fas fa-times"></i></button>
            ` : ''}`;
        list.appendChild(div);
    });
}

export function moveStopUp(idx)   { if (idx > 0) { [_stops[idx-1], _stops[idx]] = [_stops[idx], _stops[idx-1]]; renderStopsList(); } }
export function moveStopDown(idx) { if (idx < _stops.length-1) { [_stops[idx], _stops[idx+1]] = [_stops[idx+1], _stops[idx]]; renderStopsList(); } }
export function removeStop(idx)   { _stops.splice(idx, 1); renderStopsList(); }

export function clearRoute() {
    if (state.routingControl) { state.map.removeControl(state.routingControl); state.routingControl = null; }
    ['routeFromInput','routeToInput','routeFromId','routeToId'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    _stops = []; renderStopsList();
}

function _optimizeStops(from, to, stops) {
    function permute(arr) { if (arr.length <= 1) return [arr]; return arr.flatMap((v, i) => permute([...arr.slice(0,i), ...arr.slice(i+1)]).map(r => [v, ...r])); }
    function dist(order) { let d = 0, prev = from; order.forEach(s => { d += L.latLng(prev.lat, prev.lon).distanceTo(L.latLng(s.lat, s.lon)); prev = s; }); return d + L.latLng(prev.lat, prev.lon).distanceTo(L.latLng(to.lat, to.lon)); }
    return permute(stops).reduce((best, order) => dist(order) < dist(best) ? order : best, stops);
}

// ---------------------------------------------------------------------------
// HCP — Sistema de sugestao de clusters (3 fases)
// O codigo HCP e extenso e foi mantido identico ao script.js original,
// apenas reorganizado como modulo ES com imports/exports.
// ---------------------------------------------------------------------------

export function getCurrentHcpGroups() {
    const all     = state.currentFilteredData.filter(p => p.status !== 'Exited');
    const hosts   = all.filter(p => p.hub_delivey_initiatives === 'HCP Host Partner');
    const pickups = all.filter(p => p.hub_delivey_initiatives === 'HCP Pick Up Partner');
    const heros   = all.filter(p => p.hub_delivey_initiatives === 'Hub Hero');
    return { hosts, pickups, heros, all };
}

async function _osrmTableMatrix(coords, sources = null, destinations = null) {
    if (!coords || coords.length === 0) throw new Error('coords empty');
    const coordStr = coords.map(c => `${c.lon},${c.lat}`).join(';');
    const params = new URLSearchParams();
    params.set('annotations', 'distance,duration');
    if (sources?.length)      params.set('sources',      sources.join(';'));
    if (destinations?.length) params.set('destinations', destinations.join(';'));
    const res = await fetch(`https://router.project-osrm.org/table/v1/driving/${coordStr}?${params}`);
    if (!res.ok) throw new Error(`OSRM table error ${res.status}`);
    const j = await res.json();
    return { distances: j.distances || null, durations: j.durations || null };
}

function _osrmResult(distances, durations, row, col) {
    if (!distances || !durations) return null;
    const d = distances[row]?.[col], t = durations[row]?.[col];
    if (d == null || t == null) return null;
    return { distance: d, duration: t };
}

export async function hcpSuggestHostClusters() {
    const station = state.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
    if (!state.hcpUsedStores[station]) state.hcpUsedStores[station] = new Set();
    const btn = document.getElementById('suggest-routes-btn');
    const cache = state.hcpSuggestionCache[station];

    if (cache && !state.hcpSuggestionsActive) {
        _applyCacheToState(cache, station);
        _applyHcpSuggestionsToMap(cache.optimized, cache.clustersCombined || []);
        _showHcpPopup(_buildHcpReportHtml(cache.movesPhase1 || [], cache.phase2Assignments || [], cache.phase3Suggestions || []));
        state.hcpSuggestionsActive = true;
        if (btn) { btn.textContent = 'Ocultar Sugestoes'; btn.classList.replace('btn-primary','btn-warning'); btn.onclick = () => resetHcpSuggestions(); }
        return;
    }
    if (cache && state.hcpSuggestionsActive) { resetHcpSuggestions(); return; }

    const loading = document.createElement('div');
    loading.id = 'routes-loading';
    loading.style = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.3);z-index:99999;display:flex;align-items:center;justify-content:center;';
    loading.innerHTML = '<div style="background:#fff;padding:28px;border-radius:8px;"><i class="fas fa-spinner fa-spin mr-2"></i> Calculando sugestoes HCP...</div>';
    document.body.appendChild(loading);

    try {
        const groups = getCurrentHcpGroups();
        const phase1 = await _phase1(groups, station);
        const remainP1 = groups.heros.filter(h => !state.hcpUsedStores[station].has(h.store_id));
        const phase2 = await _phase2({ ...groups, heros: remainP1 }, phase1.hosts, station);
        const remainP2 = phase2.remainingHeros.filter(h => !state.hcpUsedStores[station].has(h.store_id));
        const phase3 = await _phase3({ ...groups, heros: remainP2 }, phase2.hosts, station);
        const combined = _buildCombined(phase1.moves, phase2.assignments, phase3.newHostSuggestions);
        const suggestedHosts   = combined.filter(c => c.type === 'new-host'   && c.host).map(c => c.host.store_id);
        const suggestedPickups = combined.filter(c => c.type === 'new-pickup' && c.pickup).map(c => c.pickup.store_id);
        state.hcpSuggestionCache[station] = { optimized: { hosts: phase2.hosts }, clustersCombined: combined, movesPhase1: phase1.moves, phase2Assignments: phase2.assignments, phase3Suggestions: phase3.newHostSuggestions, suggestedHosts, suggestedPickups };
        _applyHcpSuggestionsToMap({ hosts: phase2.hosts }, combined);
        _showHcpPopup(_buildHcpReportHtml(phase1.moves, phase2.assignments, phase3.newHostSuggestions));
        state.hcpSuggestionsActive = true;
        if (btn) { btn.textContent = 'Ocultar Sugestoes'; btn.classList.replace('btn-primary','btn-warning'); btn.onclick = () => resetHcpSuggestions(); }
    } finally {
        document.getElementById('routes-loading')?.remove();
    }
}

export function resetHcpSuggestions() {
    state.currentFilteredData.forEach(p => { if (p._original_hdi) { p.hub_delivey_initiatives = p._original_hdi; delete p._original_hdi; } });
    state.map.eachLayer(layer => { if (!(layer instanceof L.TileLayer)) state.map.removeLayer(layer); });
    document.getElementById('hcp-suggestions-popup')?.remove();
    const btn = document.getElementById('suggest-routes-btn');
    if (btn) { btn.textContent = 'Sugerir HCP Initiatives'; btn.classList.replace('btn-warning','btn-primary'); btn.onclick = () => hcpSuggestHostClusters(); }
    state.hcpSuggestionsActive = false;
    applyFilters();
}

function _applyCacheToState(cache, station) {
    (cache.suggestedHosts || []).forEach(id => { const it = state.currentFilteredData.find(p => p.store_id === id); if (it) { if (!it._original_hdi) it._original_hdi = it.hub_delivey_initiatives; it.hub_delivey_initiatives = 'New Host'; } });
    (cache.suggestedPickups || []).forEach(id => { const it = state.currentFilteredData.find(p => p.store_id === id); if (it) { if (!it._original_hdi) it._original_hdi = it.hub_delivey_initiatives; it.hub_delivey_initiatives = 'New PickUp'; } });
}

function _showHcpPopup(html) {
    let p = document.getElementById('hcp-suggestions-popup') || document.createElement('div');
    p.id = 'hcp-suggestions-popup';
    p.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;max-width:420px;box-shadow:0 2px 8px #0003;';
    p.innerHTML = html;
    document.body.appendChild(p);
}

function _buildCombined(moves, assignments, suggestions) {
    const combined = [];
    moves.forEach(m => combined.push({ type: 'move', pickup: m.pickup, from: m.from, to: m.to, host: null }));
    (assignments || []).forEach(a => combined.push({ type: 'new-pickup', pickup: a.hero, host: a.host }));
    (suggestions || []).forEach(s => { combined.push({ type: 'new-host', host: s.hostCandidate, pickup: null }); s.pickups.forEach(p => combined.push({ type: 'new-pickup', host: s.hostCandidate, pickup: p })); });
    return combined;
}

function _buildHcpReportHtml(moves, assignments, suggestions) {
    let html = `<div style="display:flex;justify-content:space-between;align-items:center;"><b>Sugestoes HCP</b><button onclick="document.getElementById('hcp-suggestions-popup')?.remove()" style="border:none;background:none;font-size:1.1em;">&times;</button></div><div style="max-height:700px;overflow:auto;padding-top:8px;">`;
    html += '<h4 style="margin-top:8px;">Mudancas sugeridas (Pickups atuais)</h4>';
    if (!moves?.length) html += '<div style="margin-left:12px;color:#666;">Nenhuma mudanca sugerida.</div>';
    else { html += '<ul>'; moves.forEach(m => html += `<li><b>${m.pickup.name}</b> (${m.pickup.store_id}) — mover de <i>${m.from||'N/A'}</i> para <i>${m.to}</i></li>`); html += '</ul>'; }
    html += '<h4 style="margin-top:8px;">Alocacoes em hosts existentes</h4>';
    if (!assignments?.length) html += '<div style="margin-left:12px;color:#666;">Nenhum heroi alocado.</div>';
    else { html += '<ul>'; assignments.forEach(a => html += `<li><b>${a.hero.name}</b> → Host: <b>${a.host.name}</b></li>`); html += '</ul>'; }
    html += '<h4 style="margin-top:8px;">Novos Hosts sugeridos</h4>';
    if (!suggestions?.length) html += '<div style="margin-left:12px;color:#666;">Nenhum novo host sugerido.</div>';
    else suggestions.forEach((s, idx) => { html += `<div style="margin-left:6px;margin-bottom:8px;"><b>Cluster ${idx+1} — Host: ${s.hostCandidate.name}</b><ul>`; s.pickups.forEach(p => html += `<li>${p.name} (${p.store_id})</li>`); html += '</ul></div>'; });
    html += '</div>';
    return html;
}

function _applyHcpSuggestionsToMap(optimized, clusters) {
    const hostIds   = new Set(clusters.filter(c => c.type === 'new-host'   && c.host).map(c => c.host.store_id));
    const pickupIds = new Set(clusters.filter(c => c.type === 'new-pickup' && c.pickup).map(c => c.pickup.store_id));
    state.currentFilteredData.forEach(item => {
        if (!item._original_hdi) item._original_hdi = item.hub_delivey_initiatives;
        if (hostIds.has(item.store_id))   item.hub_delivey_initiatives = 'New Host';
        else if (pickupIds.has(item.store_id)) item.hub_delivey_initiatives = 'New PickUp';
    });
    state.markerObjects.forEach(markerObj => {
        const data = markerObj?.markerData;
        if (!data?.store_id) return;
        const isHost   = hostIds.has(data.store_id);
        const isPickup = pickupIds.has(data.store_id);
        if (!isHost && !isPickup) {
            if (data._hcp_highlight) { try { state.map.removeLayer(data._hcp_highlight); } catch(e){} delete data._hcp_highlight; }
            if (markerObj instanceof L.CircleMarker && data._hcp_original_style) { markerObj.setStyle(data._hcp_original_style); delete data._hcp_original_style; }
            return;
        }
        const color = isHost ? '#8000FF' : '#FF1493';
        if (markerObj instanceof L.CircleMarker) {
            if (!data._hcp_original_style) data._hcp_original_style = { color: markerObj.options.color, fillColor: markerObj.options.fillColor, fillOpacity: markerObj.options.fillOpacity, weight: markerObj.options.weight };
            markerObj.setStyle({ color, fillColor: color, fillOpacity: 0.9, weight: Math.max(2, (data._hcp_original_style?.weight||1)+2) });
        }
    });
    try { restyleMarkers(); } catch(e) {}
}

async function _phase1(groups, station) {
    const hosts   = groups.hosts.map(h => ({ ...h, pickups: groups.pickups.filter(p => p.HCP_host_partner === h.name).slice() }));
    const pickups = groups.pickups.slice();
    const used    = state.hcpUsedStores[station];
    const moves   = [];
    if (!pickups.length || !hosts.length) return { hosts, pickups, moves };
    const coords = [...pickups.map(p => ({ lat: p.lat, lon: p.lon })), ...hosts.map(h => ({ lat: h.lat, lon: h.lon }))];
    const sources = pickups.map((_, i) => i);
    const destinations = hosts.map((_, j) => pickups.length + j);
    let matrix;
    try { matrix = await _osrmTableMatrix(coords, sources, destinations); } catch(e) { return { hosts, pickups, moves }; }
    for (let i = 0; i < pickups.length; i++) {
        const pickup = pickups[i];
        if (used.has(pickup.store_id)) continue;
        const candidates = hosts.map((host, j) => {
            const r = _osrmResult(matrix.distances, matrix.durations, i, j);
            if (!r || r.distance > HCP_CONFIG.maxDistanceM || r.duration > HCP_CONFIG.maxDurationS) return null;
            const cap = host.pickups?.length || 0;
            if (cap >= HCP_CONFIG.maxPickupsPerHost) return null;
            return { host, j, distance: r.distance };
        }).filter(Boolean).sort((a, b) => a.distance - b.distance);
        if (!candidates.length) continue;
        const chosen = candidates[0].host;
        if (pickup.HCP_host_partner !== chosen.name) moves.push({ pickup, from: pickup.HCP_host_partner, to: chosen.name });
        if (!chosen.pickups) chosen.pickups = [];
        if (!chosen.pickups.some(p => p.store_id === pickup.store_id) && chosen.pickups.length < HCP_CONFIG.maxPickupsPerHost) { chosen.pickups.push(pickup); used.add(pickup.store_id); }
    }
    return { hosts, pickups, moves };
}

async function _phase2(groups, currentHosts, station) {
    const hosts = currentHosts.map(h => ({ ...h, pickups: (h.pickups||[]).slice() }));
    const heros = groups.heros.slice();
    const used  = state.hcpUsedStores[station];
    const assignments = [];
    if (!heros.length || !hosts.length) return { hosts, assignments, remainingHeros: heros };
    const coords = [...heros.map(h => ({ lat: h.lat, lon: h.lon })), ...hosts.map(h => ({ lat: h.lat, lon: h.lon }))];
    const sources = heros.map((_, i) => i);
    const destinations = hosts.map((_, j) => heros.length + j);
    let matrix;
    try { matrix = await _osrmTableMatrix(coords, sources, destinations); } catch(e) { return { hosts, assignments, remainingHeros: heros }; }
    const remaining = [];
    for (let i = 0; i < heros.length; i++) {
        const hero = heros[i];
        if (used.has(hero.store_id)) continue;
        const candidates = hosts.map((host, j) => {
            if ((host.pickups?.length||0) >= HCP_CONFIG.maxPickupsPerHost) return null;
            const r = _osrmResult(matrix.distances, matrix.durations, i, j);
            if (!r || r.distance > HCP_CONFIG.maxDistanceM || r.duration > HCP_CONFIG.maxDurationS) return null;
            return { host, distance: r.distance };
        }).filter(Boolean).sort((a, b) => a.distance - b.distance);
        if (!candidates.length) { remaining.push(hero); continue; }
        let assigned = false;
        for (const { host } of candidates) {
            if (!host.pickups) host.pickups = [];
            if (host.pickups.length < HCP_CONFIG.maxPickupsPerHost) { host.pickups.push(hero); assignments.push({ hero, host }); used.add(hero.store_id); assigned = true; break; }
        }
        if (!assigned) remaining.push(hero);
    }
    return { hosts, assignments, remainingHeros: remaining };
}

async function _phase3(groups, currentHosts, station) {
    const turf = window.turf;
    const hosts = currentHosts.map(h => ({ ...h, pickups: (h.pickups||[]).slice() }));
    const heros = groups.heros.slice();
    const used  = state.hcpUsedStores[station];
    const newHostSuggestions = [];
    if (heros.length < HCP_CONFIG.minClusterMembers) return { hosts, newHostSuggestions };
    const k = Math.max(1, Math.ceil(heros.length / 5));
    const fc = turf.featureCollection(heros.map(h => turf.point([h.lon, h.lat], { store_id: h.store_id })));
    let clustered;
    try { clustered = turf.clustersKmeans(fc, { numberOfClusters: k }); } catch(e) { return { hosts, newHostSuggestions }; }
    const clusterMap = new Map();
    clustered.features.forEach(f => { const cid = f.properties.cluster; if (!clusterMap.has(cid)) clusterMap.set(cid, []); clusterMap.get(cid).push(f); });
    for (const [, features] of clusterMap.entries()) {
        let members = features.map(f => heros.find(h => h.store_id === f.properties.store_id)).filter(Boolean);
        if (!members.length) continue;
        if (members.length > HCP_CONFIG.maxClusterMembers) {
            const fcTmp = turf.featureCollection(members.map(m => turf.point([m.lon, m.lat])));
            const cTmp  = turf.centroid(fcTmp);
            members.sort((a, b) => turf.distance(cTmp, turf.point([b.lon, b.lat])) - turf.distance(cTmp, turf.point([a.lon, a.lat])));
            members = members.slice(0, HCP_CONFIG.maxClusterMembers);
        }
        const fc2 = turf.featureCollection(members.map(m => turf.point([m.lon, m.lat])));
        const centroid = turf.centroid(fc2);
        const maxDist = Math.max(...members.map(m => turf.distance(centroid, turf.point([m.lon, m.lat]), { units: 'kilometers' })));
        if (maxDist > HCP_CONFIG.clusterDensityKm || members.length < HCP_CONFIG.minClusterMembers) continue;
        let hostCandidate = null, hostDist = Infinity;
        members.forEach(m => { const d = turf.distance(centroid, turf.point([m.lon, m.lat]), { units: 'kilometers' }); if (d < hostDist) { hostDist = d; hostCandidate = m; } });
        if (!hostCandidate || used.has(hostCandidate.store_id)) continue;
        const pickupCandidates = members.filter(m => m.store_id !== hostCandidate.store_id);
        if (!pickupCandidates.length) continue;
        const coords = [...pickupCandidates.map(p => ({ lat: p.lat, lon: p.lon })), { lat: hostCandidate.lat, lon: hostCandidate.lon }];
        let matrix;
        try { matrix = await _osrmTableMatrix(coords, pickupCandidates.map((_, i) => i), [pickupCandidates.length]); } catch(e) { continue; }
        const valid = pickupCandidates.filter((p, r) => { if (used.has(p.store_id)) return false; const res = _osrmResult(matrix.distances, matrix.durations, r, 0); return res && res.distance <= HCP_CONFIG.maxDistanceM && res.duration <= HCP_CONFIG.maxDurationS; }).slice(0, HCP_CONFIG.maxPickupsPerHost);
        if (valid.length < HCP_CONFIG.minPickupsForNewHost) continue;
        used.add(hostCandidate.store_id);
        valid.forEach(fp => used.add(fp.store_id));
        if (!hostCandidate._original_hdi) hostCandidate._original_hdi = hostCandidate.hub_delivey_initiatives;
        hostCandidate.hub_delivey_initiatives = 'New Host';
        valid.forEach(fp => { if (!fp._original_hdi) fp._original_hdi = fp.hub_delivey_initiatives; fp.hub_delivey_initiatives = 'New PickUp'; });
        newHostSuggestions.push({ hostCandidate, pickups: valid });
        hosts.push({ ...hostCandidate, pickups: valid.slice() });
    }
    return { hosts, newHostSuggestions };
}
