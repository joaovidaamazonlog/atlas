/**
 * backfill_h3.js
 * ==============
 * Preenche h3_r8_id e h3_r9_id nos registros de gmaps_leads
 * que já existem no Turso mas ainda não têm esses campos.
 *
 * Uso:
 *   node backfill_h3.js
 *   node backfill_h3.js --batch 200   # tamanho do lote (padrão: 100)
 *   node backfill_h3.js --dry-run     # só mostra quantos seriam atualizados
 */

const { latLngToCell } = require('h3-js');

const TURSO_URL   = process.env.TURSO_URL;
const TURSO_TOKEN = process.env.TURSO_TOKEN;

if (!TURSO_URL || !TURSO_TOKEN) {
    console.error('TURSO_URL e TURSO_TOKEN são obrigatórios');
    process.exit(1);
}

const TURSO_HTTP_URL = TURSO_URL.replace(/^libsql:\/\//, 'https://');

function _arg(v) {
    if (v === null || v === undefined) return { type: 'null' };
    if (typeof v === 'number')         return { type: 'float', value: v };
    return { type: 'text', value: String(v) };
}

async function tursoExecute(sql, args = []) {
    const res = await fetch(`${TURSO_HTTP_URL}/v2/pipeline`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${TURSO_TOKEN}`,
            'Content-Type':  'application/json',
        },
        body: JSON.stringify({
            requests: [
                { type: 'execute', stmt: { sql, args: args.map(_arg) } },
                { type: 'close' },
            ],
        }),
    });
    if (!res.ok) throw new Error(`Turso HTTP ${res.status}: ${await res.text()}`);
    const data   = await res.json();
    const result = data.results[0];
    if (result?.type === 'error') return [];
    const inner = result?.response?.result ?? {};
    const cols  = (inner.cols ?? []).map(c => c.name);
    return (inner.rows ?? []).map(row =>
        Object.fromEntries(cols.map((c, i) => [c, row[i]?.type === 'null' ? null : row[i]?.value]))
    );
}

async function tursoBatch(statements) {
    // statements: [{sql, args}]
    const requests = [
        ...statements.map(s => ({
            type: 'execute',
            stmt: { sql: s.sql, args: s.args.map(_arg) },
        })),
        { type: 'close' },
    ];
    const res = await fetch(`${TURSO_HTTP_URL}/v2/pipeline`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${TURSO_TOKEN}`,
            'Content-Type':  'application/json',
        },
        body: JSON.stringify({ requests }),
    });
    if (!res.ok) throw new Error(`Turso batch HTTP ${res.status}: ${await res.text()}`);
}

function parseArgs() {
    const batchIdx = process.argv.indexOf('--batch');
    const batchSize = batchIdx !== -1 ? parseInt(process.argv[batchIdx + 1], 10) : 100;
    const dryRun = process.argv.includes('--dry-run');
    return { batchSize, dryRun };
}

async function main() {
    const { batchSize, dryRun } = parseArgs();

    console.log('\n=== BACKFILL H3 — gmaps_leads ===');
    if (dryRun) console.log('  [DRY RUN — nenhuma alteração será feita]');

    // Garante que as colunas existem
    for (const col of ['h3_r8_id', 'h3_r9_id']) {
        try {
            await tursoExecute(`ALTER TABLE gmaps_leads ADD COLUMN ${col} TEXT`);
            console.log(`  Coluna ${col} adicionada.`);
        } catch (_) { /* já existe */ }
    }
    await tursoExecute(`CREATE INDEX IF NOT EXISTS idx_gmaps_leads_h3_r8 ON gmaps_leads (h3_r8_id)`);
    await tursoExecute(`CREATE INDEX IF NOT EXISTS idx_gmaps_leads_h3_r9 ON gmaps_leads (h3_r9_id)`);

    // Busca registros sem h3 mas com lat/lon
    const rows = await tursoExecute(
        `SELECT id, lat, lon FROM gmaps_leads
         WHERE (h3_r8_id IS NULL OR h3_r9_id IS NULL)
           AND lat IS NOT NULL AND lon IS NOT NULL`
    );

    console.log(`  ${rows.length} registros para atualizar.`);
    if (rows.length === 0 || dryRun) {
        console.log('  Nada a fazer.\n');
        return;
    }

    let updated = 0;
    for (let i = 0; i < rows.length; i += batchSize) {
        const chunk = rows.slice(i, i + batchSize);
        const statements = chunk.map(row => {
            const lat = parseFloat(row.lat);
            const lon = parseFloat(row.lon);
            const h3r8 = latLngToCell(lat, lon, 8);
            const h3r9 = latLngToCell(lat, lon, 9);
            return {
                sql: `UPDATE gmaps_leads SET h3_r8_id = ?, h3_r9_id = ? WHERE id = ?`,
                args: [h3r8, h3r9, row.id],
            };
        });

        await tursoBatch(statements);
        updated += chunk.length;
        console.log(`  [${updated}/${rows.length}] atualizados...`);
    }

    console.log(`\n  Concluído — ${updated} registros atualizados.`);
    console.log('=================================\n');
}

main().catch(err => {
    console.error('Erro fatal:', err);
    process.exit(1);
});
