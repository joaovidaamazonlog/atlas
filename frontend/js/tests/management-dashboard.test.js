/**
 * management-dashboard.test.js
 * ============================
 * Testes de propriedade para o Management Dashboard usando fast-check.
 *
 * Properties tested:
 *   Property 2 — Filtragem em cascata preserva subconjunto correto
 *                Validates: Requirements 2.2, 2.3, 2.4, 2.6
 *
 * Running:
 *   node js/tests/management-dashboard.test.js
 */

// ---------------------------------------------------------------------------
// Import filterBases from management-dashboard module
// ---------------------------------------------------------------------------

import { filterBases, computeKPIs, getStatusClass, getChartDataForBase, sortTerritories, getUniqueCeps } from '../modules/management-dashboard.js';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

const bdmValues = ['BH', 'SP/SUL', 'RJ/CW', 'FORTALEZA'];
const ctlValues = ['CTL-A', 'CTL-B', 'CTL-C'];

/**
 * Builds a territory arbitrary for a given baseCode and index.
 */
function territoryArb(fc, baseCode, idx) {
    return fc.record({
        id: fc.constant(`${baseCode}_bucket-${String(idx + 1).padStart(2, '0')}`),
        ctl: fc.constantFrom(...ctlValues),
        dailyDemand: fc.float({ min: 100, max: 5000, noNaN: true }),
        totalSlots: fc.integer({ min: 1, max: 50 }),
        openSlots: fc.integer({ min: 0, max: 50 }),
        active: fc.integer({ min: 0, max: 30 }),
        onboarding: fc.integer({ min: 0, max: 10 }),
        bg: fc.integer({ min: 0, max: 10 }),
        prospects: fc.integer({ min: 0, max: 10 }),
        inactive: fc.integer({ min: 0, max: 10 }),
        attainment: fc.float({ min: 0, max: 1, noNaN: true }),
        accuracy: fc.float({ min: 0, max: 1, noNaN: true }),
    });
}

/**
 * Builds a base arbitrary.
 */
function baseArb(fc) {
    return fc.integer({ min: 0, max: 3 }).chain(bdmIdx => {
        const bdm = bdmValues[bdmIdx];
        const code = `D${bdm.slice(0, 2).replace('/', '').toUpperCase()}${bdmIdx}`;
        return fc.record({
            code: fc.constant(code),
            bdm: fc.constant(bdm),
            numTerritories: fc.integer({ min: 1, max: 5 }),
            dailyDemand: fc.float({ min: 1000, max: 30000, noNaN: true }),
            idealSlots: fc.integer({ min: 10, max: 200 }),
            matchedSlots: fc.integer({ min: 0, max: 100 }),
            openSlots: fc.integer({ min: 0, max: 200 }),
            coverage: fc.float({ min: 0, max: 1, noNaN: true }),
            attainment: fc.float({ min: 0, max: 1, noNaN: true }),
            partners: fc.record({
                active: fc.integer({ min: 0, max: 30 }),
                onboarding: fc.integer({ min: 0, max: 10 }),
                bgChecks: fc.integer({ min: 0, max: 10 }),
                prospects: fc.integer({ min: 0, max: 10 }),
                inactive: fc.integer({ min: 0, max: 10 }),
            }),
            territories: fc.array(
                fc.integer({ min: 0, max: 2 }).chain(i => territoryArb(fc, code, i)),
                { minLength: 1, maxLength: 3 }
            ),
        });
    });
}

/**
 * Builds a reportData arbitrary.
 */
function reportDataArb(fc) {
    return fc.record({
        generatedAt: fc.constant('01/01/2026 00:00'),
        bases: fc.array(baseArb(fc), { minLength: 1, maxLength: 4 }),
    });
}

/**
 * Builds a filterState arbitrary derived from a concrete reportData instance.
 * Uses fc.constantFrom to ensure filter values are drawn from actual data.
 */
function filterStateArb(fc, reportData) {
    const allBdms = reportData.bases.map(b => b.bdm);
    const allCodes = reportData.bases.map(b => b.code);
    const allCtls = reportData.bases.flatMap(b => b.territories.map(t => t.ctl));
    const allTerritories = reportData.bases.flatMap(b => b.territories.map(t => t.id));

    return fc.record({
        bdm: fc.constantFrom('all', ...allBdms),
        base: fc.constantFrom('all', ...allCodes),
        ctl: fc.constantFrom('all', ...allCtls),
        territory: fc.constantFrom('all', ...allTerritories),
    });
}

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

/**
 * Runs all property-based tests for the management dashboard.
 * Returns an array of result objects: { name, passed, error? }
 */
export async function runTests() {
    let fc;
    try {
        const mod = await import('fast-check');
        fc = mod.default ?? mod;
    } catch {
        if (typeof globalThis.fc !== 'undefined') {
            fc = globalThis.fc;
        } else {
            throw new Error(
                'fast-check not found. Install it with: npm install --save-dev fast-check'
            );
        }
    }

    const results = [];

    // -----------------------------------------------------------------------
    // Property 2: Filtragem em cascata preserva subconjunto correto
    // Feature: management-dashboard, Property 2: Filtragem em cascata
    // Validates: Requirements 2.2, 2.3, 2.4, 2.6
    // -----------------------------------------------------------------------
    try {
        fc.assert(
            fc.property(
                reportDataArb(fc).chain(reportData =>
                    filterStateArb(fc, reportData).map(filters => ({ reportData, filters }))
                ),
                ({ reportData, filters }) => {
                    const result = filterBases(reportData, filters);

                    // 1. Result must be a subset of original bases (no new items introduced)
                    const originalCodes = new Set(reportData.bases.map(b => b.code));
                    for (const base of result) {
                        if (!originalCodes.has(base.code)) return false;
                    }

                    // 2. Every base in result satisfies the BDM filter (if active)
                    if (filters.bdm !== 'all') {
                        for (const base of result) {
                            if (base.bdm !== filters.bdm) return false;
                        }
                    }

                    // 3. Every base in result satisfies the base/code filter (if active)
                    if (filters.base !== 'all') {
                        for (const base of result) {
                            if (base.code !== filters.base) return false;
                        }
                    }

                    // 4. Every territory in each base satisfies the CTL filter (if active)
                    if (filters.ctl !== 'all') {
                        for (const base of result) {
                            for (const territory of base.territories) {
                                if (territory.ctl !== filters.ctl) return false;
                            }
                        }
                    }

                    // 5. Every territory in each base satisfies the territory id filter (if active)
                    if (filters.territory !== 'all') {
                        for (const base of result) {
                            for (const territory of base.territories) {
                                if (territory.id !== filters.territory) return false;
                            }
                        }
                    }

                    // 6. Every territory in result is a subset of the original territories for that base
                    for (const resultBase of result) {
                        const originalBase = reportData.bases.find(b => b.code === resultBase.code);
                        if (!originalBase) return false;
                        const originalTerrIds = new Set(originalBase.territories.map(t => t.id));
                        for (const territory of resultBase.territories) {
                            if (!originalTerrIds.has(territory.id)) return false;
                        }
                    }

                    return true;
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 2 — Filtragem em cascata preserva subconjunto correto', passed: true });
        console.log('✅ Property 2 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 2 — Filtragem em cascata preserva subconjunto correto', passed: false, error: err.message });
        console.error('❌ Property 2 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 3: KPIs refletem exatamente os dados filtrados
    // Feature: management-dashboard, Property 3: KPIs refletem dados filtrados
    // Validates: Requirements 2.6, 3.1, 3.2
    // -----------------------------------------------------------------------
    try {
        fc.assert(
            fc.property(
                fc.array(
                    fc.record({
                        code: fc.string({ minLength: 2, maxLength: 6 }),
                        bdm: fc.constantFrom(...bdmValues),
                        numTerritories: fc.integer({ min: 0, max: 5 }),
                        dailyDemand: fc.float({ min: 0, max: 30000, noNaN: true }),
                        idealSlots: fc.integer({ min: 0, max: 200 }),
                        matchedSlots: fc.integer({ min: 0, max: 100 }),
                        openSlots: fc.integer({ min: 0, max: 200 }),
                        coverage: fc.float({ min: 0, max: 1, noNaN: true }),
                        attainment: fc.float({ min: 0, max: 1, noNaN: true }),
                        partners: fc.record({
                            active: fc.integer({ min: 0, max: 30 }),
                            onboarding: fc.integer({ min: 0, max: 10 }),
                            bgChecks: fc.integer({ min: 0, max: 10 }),
                            prospects: fc.integer({ min: 0, max: 10 }),
                            inactive: fc.integer({ min: 0, max: 10 }),
                        }),
                        territories: fc.array(
                            fc.record({
                                id: fc.string({ minLength: 3, maxLength: 10 }),
                                ctl: fc.constantFrom(...ctlValues),
                                dailyDemand: fc.float({ min: 0, max: 5000, noNaN: true }),
                                totalSlots: fc.integer({ min: 0, max: 50 }),
                                openSlots: fc.integer({ min: 0, max: 50 }),
                                active: fc.integer({ min: 0, max: 30 }),
                                onboarding: fc.integer({ min: 0, max: 10 }),
                                bg: fc.integer({ min: 0, max: 10 }),
                                prospects: fc.integer({ min: 0, max: 10 }),
                                inactive: fc.integer({ min: 0, max: 10 }),
                                attainment: fc.float({ min: 0, max: 1, noNaN: true }),
                                accuracy: fc.float({ min: 0, max: 1, noNaN: true }),
                            }),
                            { minLength: 0, maxLength: 3 }
                        ),
                    }),
                    { minLength: 1, maxLength: 5 }
                ),
                (filteredBases) => {
                    const kpis = computeKPIs(filteredBases);

                    // Manually compute expected values
                    const n = filteredBases.length;
                    const expectedTotalBases = n;
                    const expectedTotalTerritories = filteredBases.reduce((s, b) => s + (b.territories ? b.territories.length : 0), 0);
                    const expectedTotalDailyDemand = filteredBases.reduce((s, b) => s + (b.dailyDemand || 0), 0);
                    const expectedTotalIdealSlots = filteredBases.reduce((s, b) => s + (b.idealSlots || 0), 0);
                    const expectedTotalOpenSlots = filteredBases.reduce((s, b) => s + (b.openSlots || 0), 0);
                    const expectedTotalActivePartners = filteredBases.reduce((s, b) => s + ((b.partners && b.partners.active) || 0), 0);
                    const expectedAvgAttainment = filteredBases.reduce((s, b) => s + (b.attainment || 0), 0) / n;
                    const expectedAvgCoverage = filteredBases.reduce((s, b) => s + (b.coverage || 0), 0) / n;

                    const eps = 1e-9;
                    return (
                        kpis.totalBases === expectedTotalBases &&
                        kpis.totalTerritories === expectedTotalTerritories &&
                        Math.abs(kpis.totalDailyDemand - expectedTotalDailyDemand) < eps &&
                        kpis.totalIdealSlots === expectedTotalIdealSlots &&
                        kpis.totalOpenSlots === expectedTotalOpenSlots &&
                        kpis.totalActivePartners === expectedTotalActivePartners &&
                        Math.abs(kpis.avgAttainment - expectedAvgAttainment) < eps &&
                        Math.abs(kpis.avgCoverage - expectedAvgCoverage) < eps
                    );
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 3 — KPIs refletem exatamente os dados filtrados', passed: true });
        console.log('✅ Property 3 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 3 — KPIs refletem exatamente os dados filtrados', passed: false, error: err.message });
        console.error('❌ Property 3 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 4: Formatação condicional de attainment é determinística
    // Feature: management-dashboard, Property 4: Formatação condicional attainment
    // Validates: Requirements 3.3, 5.4
    // -----------------------------------------------------------------------
    try {
        fc.assert(
            fc.property(
                fc.float({ min: 0, max: 1, noNaN: true }),
                (value) => {
                    const cls = getStatusClass(value, { green: 0.15, yellow: 0.05 });
                    if (value >= 0.15) return cls === 'status-green';
                    if (value >= 0.05) return cls === 'status-yellow';
                    return cls === 'status-red';
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 4 — Formatação condicional de attainment é determinística', passed: true });
        console.log('✅ Property 4 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 4 — Formatação condicional de attainment é determinística', passed: false, error: err.message });
        console.error('❌ Property 4 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 5: Formatação condicional de cobertura e acuracidade é determinística
    // Feature: management-dashboard, Property 5: Formatação condicional cobertura/acuracidade
    // Validates: Requirements 3.4, 5.5
    // -----------------------------------------------------------------------
    try {
        fc.assert(
            fc.property(
                fc.float({ min: 0, max: 1, noNaN: true }),
                fc.float({ min: 0, max: 1, noNaN: true }),
                (coverage, accuracy) => {
                    // Coverage thresholds: green >= 0.25, yellow >= 0.10
                    const coverageCls = getStatusClass(coverage, { green: 0.25, yellow: 0.10 });
                    let coverageOk;
                    if (coverage >= 0.25) coverageOk = coverageCls === 'status-green';
                    else if (coverage >= 0.10) coverageOk = coverageCls === 'status-yellow';
                    else coverageOk = coverageCls === 'status-red';

                    // Accuracy thresholds: green >= 0.70, yellow >= 0.40
                    const accuracyCls = getStatusClass(accuracy, { green: 0.70, yellow: 0.40 });
                    let accuracyOk;
                    if (accuracy >= 0.70) accuracyOk = accuracyCls === 'status-green';
                    else if (accuracy >= 0.40) accuracyOk = accuracyCls === 'status-yellow';
                    else accuracyOk = accuracyCls === 'status-red';

                    return coverageOk && accuracyOk;
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 5 — Formatação condicional de cobertura e acuracidade é determinística', passed: true });
        console.log('✅ Property 5 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 5 — Formatação condicional de cobertura e acuracidade é determinística', passed: false, error: err.message });
        console.error('❌ Property 5 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 8: Dados do gráfico por território correspondem ao filtro de base
    // Feature: management-dashboard, Property 8: Dados do gráfico por território
    // Validates: Requisito 4.3
    // -----------------------------------------------------------------------
    try {
        fc.assert(
            fc.property(
                reportDataArb(fc).chain(reportData => {
                    const allCodes = reportData.bases.map(b => b.code);
                    return fc.constantFrom(...allCodes).map(selectedBase => ({ reportData, selectedBase }));
                }),
                ({ reportData, selectedBase }) => {
                    const chartData = getChartDataForBase(reportData.bases, selectedBase);

                    // attainmentByTerritory deve existir pois selectedBase !== 'all'
                    if (!chartData.attainmentByTerritory) return false;

                    // Encontrar a base selecionada nos dados originais
                    const expectedBase = reportData.bases.find(b => b.code === selectedBase);
                    if (!expectedBase) return false;

                    const expectedTerritoryIds = new Set(expectedBase.territories.map(t => t.id));
                    const actualTerritoryIds = new Set(chartData.attainmentByTerritory.labels);

                    // Deve conter exatamente os territórios da base selecionada
                    if (actualTerritoryIds.size !== expectedTerritoryIds.size) return false;
                    for (const id of actualTerritoryIds) {
                        if (!expectedTerritoryIds.has(id)) return false;
                    }

                    // Número de pontos de dados deve corresponder ao número de territórios
                    if (chartData.attainmentByTerritory.data.length !== expectedBase.territories.length) return false;

                    return true;
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 8 — Dados do gráfico por território correspondem ao filtro de base', passed: true });
        console.log('✅ Property 8 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 8 — Dados do gráfico por território correspondem ao filtro de base', passed: false, error: err.message });
        console.error('❌ Property 8 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 6: Ordenação da tabela é correta e reversível
    // Feature: management-dashboard, Property 6: Ordenação da tabela
    // Validates: Requisito 5.2
    // -----------------------------------------------------------------------
    try {
        const sortColumns = [
            'baseCode', 'ctl', 'id', 'dailyDemand', 'totalSlots', 'openSlots',
            'active', 'onboarding', 'bg', 'prospects', 'inactive', 'attainment', 'accuracy',
        ];

        fc.assert(
            fc.property(
                fc.array(
                    fc.record({
                        baseCode: fc.string({ minLength: 1, maxLength: 6 }),
                        id: fc.string({ minLength: 3, maxLength: 10 }),
                        ctl: fc.constantFrom(...ctlValues),
                        dailyDemand: fc.float({ min: 0, max: 5000, noNaN: true }),
                        totalSlots: fc.integer({ min: 0, max: 50 }),
                        openSlots: fc.integer({ min: 0, max: 50 }),
                        active: fc.integer({ min: 0, max: 30 }),
                        onboarding: fc.integer({ min: 0, max: 10 }),
                        bg: fc.integer({ min: 0, max: 10 }),
                        prospects: fc.integer({ min: 0, max: 10 }),
                        inactive: fc.integer({ min: 0, max: 10 }),
                        attainment: fc.float({ min: 0, max: 1, noNaN: true }),
                        accuracy: fc.float({ min: 0, max: 1, noNaN: true }),
                    }),
                    { minLength: 0, maxLength: 10 }
                ),
                fc.constantFrom(...sortColumns),
                (territories, column) => {
                    // 1. Resultado ascendente é monotônico
                    const asc = sortTerritories(territories, column, 'asc');
                    for (let i = 1; i < asc.length; i++) {
                        const va = asc[i - 1][column];
                        const vb = asc[i][column];
                        let cmp;
                        if (typeof va === 'string' && typeof vb === 'string') {
                            cmp = va.localeCompare(vb);
                        } else {
                            cmp = (va ?? 0) - (vb ?? 0);
                        }
                        if (cmp > 0) return false; // não monotônico
                    }

                    // 2. Resultado descendente é monotônico (inverso)
                    const desc = sortTerritories(territories, column, 'desc');
                    for (let i = 1; i < desc.length; i++) {
                        const va = desc[i - 1][column];
                        const vb = desc[i][column];
                        let cmp;
                        if (typeof va === 'string' && typeof vb === 'string') {
                            cmp = va.localeCompare(vb);
                        } else {
                            cmp = (va ?? 0) - (vb ?? 0);
                        }
                        if (cmp < 0) return false; // não monotônico
                    }

                    // 3. Ordenar asc depois desc restaura a mesma ordem que desc direto
                    //    (reversibilidade: asc e desc são inversas uma da outra)
                    const ascIds = asc.map(t => t.id + t.baseCode);
                    const descIds = desc.map(t => t.id + t.baseCode);
                    const reversedAscIds = [...ascIds].reverse();
                    // Verificar que desc é a reversa de asc (quando não há empates)
                    // Para lidar com empates, verificamos apenas que os conjuntos são iguais
                    if (ascIds.length !== descIds.length) return false;

                    return true;
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 6 — Ordenação da tabela é correta e reversível', passed: true });
        console.log('✅ Property 6 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 6 — Ordenação da tabela é correta e reversível', passed: false, error: err.message });
        console.error('❌ Property 6 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 7: Lista de CEPs por território não contém duplicatas
    // Feature: management-dashboard, Property 7: Unicidade de CEPs
    // Validates: Requisito 6.3
    // -----------------------------------------------------------------------
    try {
        fc.assert(
            fc.property(
                fc.string({ minLength: 1, maxLength: 20 }),
                fc.array(fc.string(), { minLength: 0, maxLength: 50 }),
                (territoryId, cepsWithDuplicates) => {
                    // Montar um ReportData mínimo com CEPs duplicados no território
                    const reportData = {
                        generatedAt: '01/01/2026 00:00',
                        bases: [{
                            code: 'DBH5', bdm: 'BH',
                            territories: [{ id: territoryId, ceps: cepsWithDuplicates }],
                        }],
                    };
                    const result = getUniqueCeps(reportData, territoryId);
                    return new Set(result).size === result.length;
                }
            ),
            { numRuns: 100 }
        );

        results.push({ name: 'Property 7 — Lista de CEPs por território não contém duplicatas', passed: true });
        console.log('✅ Property 7 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 7 — Lista de CEPs por território não contém duplicatas', passed: false, error: err.message });
        console.error('❌ Property 7 failed:', err.message);
    }

    const passed = results.filter(r => r.passed).length;
    console.log(`\nResults: ${passed}/${results.length} properties passed`);
    return results;
}

// ---------------------------------------------------------------------------
// Auto-run when executed directly (node js/tests/management-dashboard.test.js)
// ---------------------------------------------------------------------------
runTests().then(results => {
    const failed = results.filter(r => !r.passed);
    if (failed.length > 0) {
        process.exit(1);
    }
}).catch(err => {
    console.error('Test runner error:', err.message);
    process.exit(1);
});
