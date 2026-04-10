/**
 * partner-schema.test.js
 * ======================
 * Property-based tests for the Partner model (Schema_Limpo).
 *
 * Properties tested:
 *   Property 5 — Partner constructor: nenhuma propriedade undefined para raw com Schema_Limpo
 *                Validates: Requirements 6.1, 6.2, 6.3, 8.4
 *   Property 6 — Round-trip: campos chave preservados após new Partner(raw)
 *                Validates: Requirements 3.5, 3.6, 6.1, 6.2, 8.6
 *
 * Running:
 *   node js/tests/partner-schema.test.js
 */

import fc from 'fast-check';

// ---------------------------------------------------------------------------
// Inline Partner class (mirrors js/models.js — sem dependência de DOM/Leaflet)
// ---------------------------------------------------------------------------

const PartnerStatus = {
    ACTIVE:     'Active',
    INACTIVE:   'Inactive',
    ONBOARDING: 'Onboarding',
    BG_CHECKS:  'BG Checks',
    PROSPECT:   'Prospect',
    EXITED:     'Exited',
    NEW:        'New',
};

class OptimizationData {
    constructor(r = 1500, c = 42) { this.radius_suggestion = r; this.cap_suggestion = c; }
    static default() { return new OptimizationData(1500, 42); }
}

class Partner {
    constructor(raw = {}) {
        this.salesforce_id          = raw.salesforce_id          ?? '';
        this.store_id               = raw.store_id               ?? null;
        this.name                   = raw.name                   ?? '';
        this.status                 = raw.status                 ?? PartnerStatus.ACTIVE;
        this.lat                    = raw.lat                    ?? null;
        this.lon                    = raw.lon                    ?? null;
        this.zip_code               = raw.zip_code               ?? null;
        this.city                   = raw.city                   ?? null;
        this.state                  = raw.state                  ?? null;
        this.delivery_station       = raw.delivery_station       ?? '';
        this.supply_run             = raw.supply_run             ?? null;
        this.radius                 = raw.radius                 ?? 0;
        this.capacity               = raw.capacity               ?? 0;
        this.bucket                 = raw.bucket                 ?? null;
        this.jurisdiction_type      = raw.jurisdiction_type      ?? null;
        this.hub_delivey_initiatives = raw.hub_delivey_initiatives ?? null;
        this.HCP_rate_card          = raw.HCP_rate_card          ?? null;
        this.HCP_host_partner       = raw.HCP_host_partner       ?? null;
        this.launch_date            = raw.launch_date            ?? null;
        this.exited_date            = raw.exited_date            ?? null;
        this.telefone               = raw.telefone               ?? null;
        this.owner_id               = raw.owner_id               ?? null;
        this.decision_status        = raw.decision_status        ?? null;
        this.lead_source            = raw.lead_source            ?? null;
        this.tooltip                = raw.tooltip                ?? '';
        // injetados pelo data-manager
        this.bucket_ade             = raw.bucket_ade             ?? '';
        this.regiao                 = raw.regiao                 ?? '';
        this.decision               = raw.decision               ?? '';
        this.reason                 = raw.reason                 ?? '';
        this.optimization           = raw.optimization
            ? new OptimizationData(raw.optimization.radius_suggestion, raw.optimization.cap_suggestion)
            : OptimizationData.default();
        this.ceps                   = raw.ceps                   ?? [];
        this.slot_id                = raw.slot_id                ?? '';
    }
}

// ---------------------------------------------------------------------------
// Schema fields (25 campos do Schema_Limpo)
// ---------------------------------------------------------------------------

const SCHEMA_FIELDS = [
    'salesforce_id', 'store_id', 'name', 'status', 'lead_source',
    'lat', 'lon', 'zip_code', 'city', 'state',
    'delivery_station', 'supply_run', 'radius', 'capacity',
    'bucket', 'jurisdiction_type', 'hub_delivey_initiatives',
    'HCP_rate_card', 'HCP_host_partner',
    'launch_date', 'exited_date', 'telefone',
    'owner_id', 'decision_status', 'tooltip',
];

const KEY_FIELDS = ['salesforce_id', 'lat', 'lon', 'status', 'exited_date', 'lead_source'];

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

const optText = fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null });
const optFloat = fc.option(fc.float({ noNaN: true, noDefaultInfinity: true }), { nil: null });

const rawPartnerArb = fc.record({
    salesforce_id:          fc.string({ minLength: 1, maxLength: 18 }),
    store_id:               optText,
    name:                   fc.string({ minLength: 1, maxLength: 100 }),
    status:                 fc.constantFrom(...Object.values(PartnerStatus)),
    lead_source:            optText,
    lat:                    optFloat,
    lon:                    optFloat,
    zip_code:               optText,
    city:                   optText,
    state:                  optText,
    delivery_station:       fc.string({ minLength: 1, maxLength: 10 }),
    supply_run:             optText,
    radius:                 fc.integer({ min: 200, max: 5000 }),
    capacity:               fc.integer({ min: 1, max: 200 }),
    bucket:                 optText,
    jurisdiction_type:      optText,
    hub_delivey_initiatives: optText,
    HCP_rate_card:          optText,
    HCP_host_partner:       optText,
    launch_date:            optText,
    exited_date:            optText,
    telefone:               optText,
    owner_id:               optText,
    decision_status:        optText,
    tooltip:                fc.string({ minLength: 1, maxLength: 200 }),
});

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

let passed = 0;
let failed = 0;

function assert(condition, message) {
    if (!condition) throw new Error(message);
}

async function runTest(name, fn) {
    try {
        await fn();
        console.log(`  ✓ ${name}`);
        passed++;
    } catch (err) {
        console.error(`  ✗ ${name}`);
        console.error(`    ${err.message}`);
        failed++;
    }
}

// ---------------------------------------------------------------------------
// Property 5 — Partner constructor: nenhuma propriedade undefined
// Feature: pipeline-refactor
// ---------------------------------------------------------------------------

await runTest('Property 5: Partner constructor — nenhuma propriedade undefined para Schema_Limpo', async () => {
    await fc.assert(
        fc.property(rawPartnerArb, (raw) => {
            const partner = new Partner(raw);
            for (const field of SCHEMA_FIELDS) {
                assert(
                    partner[field] !== undefined,
                    `Campo '${field}' é undefined após new Partner(raw)`
                );
            }
        }),
        { numRuns: 200 }
    );
});

// ---------------------------------------------------------------------------
// Property 6 — Round-trip: campos chave preservados
// Feature: pipeline-refactor
// ---------------------------------------------------------------------------

await runTest('Property 6: Round-trip — campos chave preservados após new Partner(raw)', async () => {
    await fc.assert(
        fc.property(rawPartnerArb, (raw) => {
            const partner = new Partner(raw);
            for (const field of KEY_FIELDS) {
                const expected = raw[field] ?? null;
                const actual   = partner[field] ?? null;
                assert(
                    actual === expected,
                    `Campo '${field}': esperado ${JSON.stringify(expected)}, obtido ${JSON.stringify(actual)}`
                );
            }
        }),
        { numRuns: 200 }
    );
});

// ---------------------------------------------------------------------------
// Resultado
// ---------------------------------------------------------------------------

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
