/**
 * run_batch.js
 * ============
 * Roda o scraping do Google Maps para todos os territórios com slots em aberto.
 * Agrupa por territory_id para minimizar o número de buscas.
 *
 * Fluxo:
 *   1. Lê data/ideal_supply.json → coleta territórios com slots em aberto
 *   2. Lê data/territories_index.json → obtém centroide lat/lon de cada território
 *   3. Para cada território × tipo de negócio → roda scrapeGmaps()
 *   4. Salva resultado em data/gmaps_results.json
 *
 * Uso:
 *   node run_batch.js
 *   node run_batch.js --stations DSP2 DBH5   (filtrar bases)
 */

const fs   = require('fs');
const path = require('path');
const { scrapeGmaps } = require('./scraper');

// ---------------------------------------------------------------------------
// CONFIGURAÇÃO
// ---------------------------------------------------------------------------

const BUSINESS_TYPES = [
    'lanchonete',
    'açaí e sorveteria',
    'chaveiro',
    'assistência técnica',
];

const DATA_DIR          = path.join(__dirname, '..', 'data');
const IDEAL_SUPPLY_PATH = path.join(DATA_DIR, 'ideal_supply.json');
const TERRITORIES_PATH  = path.join(DATA_DIR, 'territories_index.json');
const OUTPUT_PATH       = path.join(DATA_DIR, 'gmaps_results.json');

// Delay entre buscas para evitar bloqueio (ms)
const DELAY_MS = 3000;

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function parseStationsArg() {
    const idx = process.argv.indexOf('--stations');
    if (idx === -1) return null;
    const stations = [];
    for (let i = idx + 1; i < process.argv.length; i++) {
        if (process.argv[i].startsWith('--')) break;
        stations.push(process.argv[i]);
    }
    return stations.length > 0 ? stations : null;
}

// ---------------------------------------------------------------------------
// MAIN
// ---------------------------------------------------------------------------

async function main() {
    const filterStations = parseStationsArg();

    // Carregar artefatos
    if (!fs.existsSync(IDEAL_SUPPLY_PATH)) {
        console.error(`ideal_supply.json não encontrado em ${DATA_DIR}`);
        process.exit(1);
    }
    if (!fs.existsSync(TERRITORIES_PATH)) {
        console.error(`territories_index.json não encontrado em ${DATA_DIR}`);
        process.exit(1);
    }

    const idealSupply     = JSON.parse(fs.readFileSync(IDEAL_SUPPLY_PATH, 'utf8'));
    const territoriesIndex = JSON.parse(fs.readFileSync(TERRITORIES_PATH, 'utf8'));

    // Coletar territórios com slots em aberto
    const openTerritories = new Set();
    for (const [tid, slots] of Object.entries(idealSupply.slots || {})) {
        const hasOpen = slots.some(s => !s.matched_partner_id);
        if (!hasOpen) continue;

        const meta = territoriesIndex[tid];
        if (!meta) continue;
        if (filterStations && !filterStations.includes(meta.station_code)) continue;

        openTerritories.add(tid);
    }

    console.log(`\n${'='.repeat(60)}`);
    console.log(`  GMAPS BATCH SCRAPER`);
    console.log(`  Territórios com slots em aberto: ${openTerritories.size}`);
    console.log(`  Tipos de negócio: ${BUSINESS_TYPES.length}`);
    console.log(`  Total de buscas: ${openTerritories.size * BUSINESS_TYPES.length}`);
    console.log(`${'='.repeat(60)}\n`);

    // Carregar resultado existente para merge incremental
    let existing = {};
    if (fs.existsSync(OUTPUT_PATH)) {
        try {
            const prev = JSON.parse(fs.readFileSync(OUTPUT_PATH, 'utf8'));
            existing = prev.results || {};
            console.log(`  Merge com ${Object.keys(existing).length} territórios existentes.\n`);
        } catch (e) {
            console.warn('  WARN: não foi possível ler gmaps_results.json existente — sobrescrevendo.');
        }
    }

    const results = { ...existing };
    let done = 0;
    const total = openTerritories.size * BUSINESS_TYPES.length;

    for (const tid of openTerritories) {
        const meta = territoriesIndex[tid];
        const lat  = meta.centroid_lat;
        const lon  = meta.centroid_lon;

        if (!results[tid]) results[tid] = [];

        for (const type of BUSINESS_TYPES) {
            done++;
            console.log(`  [${done}/${total}] ${tid} | "${type}" @ ${lat},${lon}`);

            try {
                const items = await scrapeGmaps(type, String(lat), String(lon));
                const formatted = items.map(item => ({
                    nome:             item.name    || 'N/A',
                    endereco:         item.address || 'N/A',
                    telefone:         item.phone   || 'N/A',
                    site:             item.website || 'N/A',
                    google_maps_link: item.link    || 'N/A',
                    lat:              item.lat     ?? null,
                    lon:              item.lon     ?? null,
                    tipo:             type,
                    territory_id:     tid,
                    station_code:     meta.station_code,
                    cep:              item.cep || extractCep(item.address || ''),
                }));

                // Merge: chave primária = google_maps_link (único por estabelecimento)
                // Fallback = nome (para entradas antigas sem link)
                // Sempre prefere a versão com endereço completo
                for (const item of formatted) {
                    const newHasAddress = item.endereco && item.endereco !== 'N/A';

                    // Tentar match pelo link primeiro
                    let existingIdx = item.google_maps_link && item.google_maps_link !== 'N/A'
                        ? results[tid].findIndex(e => e.google_maps_link === item.google_maps_link)
                        : -1;

                    // Fallback: match pelo nome
                    if (existingIdx === -1) {
                        existingIdx = results[tid].findIndex(e => e.nome === item.nome);
                    }

                    if (existingIdx === -1) {
                        results[tid].push(item);
                    } else {
                        const prev = results[tid][existingIdx];
                        const prevHasAddress = prev.endereco && prev.endereco !== 'N/A';
                        if (!prevHasAddress && newHasAddress) {
                            results[tid][existingIdx] = item;
                        }
                    }
                }

                console.log(`    → ${formatted.length} empresas encontradas`);
            } catch (err) {
                console.error(`    ERR: ${err.message}`);
            }

            await sleep(DELAY_MS);
        }
    }

    // Salvar resultado
    const output = {
        generated_at: new Date().toISOString(),
        n_territories: Object.keys(results).length,
        n_companies:   Object.values(results).reduce((s, arr) => s + arr.length, 0),
        business_types: BUSINESS_TYPES,
        results,
    };

    fs.writeFileSync(OUTPUT_PATH, JSON.stringify(output, null, 2), 'utf8');

    console.log(`\n${'='.repeat(60)}`);
    console.log(`  CONCLUÍDO`);
    console.log(`  ${output.n_territories} territórios | ${output.n_companies} empresas`);
    console.log(`  Salvo em: ${OUTPUT_PATH}`);
    console.log(`${'='.repeat(60)}\n`);
}

/**
 * Tenta extrair um CEP brasileiro (8 dígitos) de uma string de endereço.
 */
function extractCep(address) {
    const match = address.match(/\b(\d{5})-?(\d{3})\b/);
    return match ? match[1] + match[2] : null;
}

main().catch(err => {
    console.error('Erro fatal:', err);
    process.exit(1);
});
