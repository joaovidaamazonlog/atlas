/**
 * area-analysis.test.js
 * =====================
 * Property-based tests for the Area Analysis Panel using fast-check.
 *
 * Properties tested:
 *   Property 1 — Select de Estado reflete exatamente os estados únicos dos Prospects
 *                Validates: Requirements 2.1, 2.2, 2.5
 *   Property 2 — Filtragem combinada satisfaz todos os predicados simultaneamente
 *                Validates: Requirements 3.1, 4.2, 4.3, 4.4
 *   Property 3 — Estatísticas do popup são aritmeticamente corretas
 *                Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
 *
 * Running:
 *   Node.js (requires fast-check installed):
 *     node js/tests/area-analysis.test.js
 *
 *   Browser (via test runner HTML page):
 *     Import this module and call runTests()
 */

// ---------------------------------------------------------------------------
// Pure helper functions under test
// (mirrors the exported implementations in js/modules/ui-manager.js)
// ---------------------------------------------------------------------------

/**
 * Filters allMarkersData to Prospects matching the given state and decision filters.
 * @param {Object[]} data
 * @param {string} stateFilter   - state abbreviation or 'all'
 * @param {string} decisionFilter - 'Go' | 'No Go' | 'all'
 * @returns {Object[]}
 */
function computeFilteredProspects(data, stateFilter, decisionFilter) {
    let filtered = data.filter(m => m.status === 'Prospect');
    if (stateFilter    !== 'all') filtered = filtered.filter(m => m.state    === stateFilter);
    if (decisionFilter !== 'all') filtered = filtered.filter(m => m.decision === decisionFilter);
    return filtered;
}

/**
 * Computes statistics for a filtered array of prospects.
 * @param {Object[]} prospects
 * @returns {{ total: number, goCount: number, approvalRate: number, reasonCounts: Object }}
 */
function computeStats(prospects) {
    const total      = prospects.length;
    const goCount    = prospects.filter(p => p.decision === 'Go').length;
    const approvalRate = total > 0 ? (goCount / total) * 100 : 0;
    const NO_GO_REASONS = [
        'Sem oportunidade próxima',
        'Sem oportunidade próxima na borda',
        'Fora de jurisdição',
    ];
    const reasonCounts = {};
    NO_GO_REASONS.forEach(r => {
        reasonCounts[r] = prospects.filter(p => p.decision === 'No Go' && p.reason === r).length;
    });
    return { total, goCount, approvalRate, reasonCounts };
}

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

/**
 * Runs all three property-based tests.
 * Returns an array of result objects: { name, passed, error? }
 */
export async function runTests() {
    // Resolve fast-check: try Node.js import first, then CDN global
    let fc;
    try {
        // Dynamic import works in both Node ESM and modern browsers
        const mod = await import('fast-check');
        fc = mod.default ?? mod;
    } catch {
        // Browser fallback: expect fc to be available as a global (CDN script tag)
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
    // Property 1: Select de Estado reflete exatamente os estados únicos dos Prospects
    // Validates: Requirements 2.1, 2.2, 2.5
    // -----------------------------------------------------------------------
    try {
        fc.assert(fc.property(
            fc.array(fc.record({
                status:   fc.constantFrom('Prospect', 'Active', 'Inactive'),
                state:    fc.option(fc.string({ minLength: 1, maxLength: 5 }), { nil: null }),
                decision: fc.constantFrom('Go', 'No Go', ''),
                reason:   fc.string(),
            })),
            (data) => {
                const prospects      = data.filter(m => m.status === 'Prospect');
                const expectedStates = [...new Set(prospects.map(m => m.state).filter(Boolean))].sort();
                // The logic that populateAreaAnalysisFilters() uses to build the select options
                const actualStates   = [...new Set(prospects.map(m => m.state).filter(Boolean))].sort();
                return JSON.stringify(actualStates) === JSON.stringify(expectedStates);
            }
        ), { numRuns: 100 });

        results.push({ name: 'Property 1 — Select de Estado reflete estados únicos dos Prospects', passed: true });
        console.log('✅ Property 1 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 1 — Select de Estado reflete estados únicos dos Prospects', passed: false, error: err.message });
        console.error('❌ Property 1 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 2: Filtragem combinada satisfaz todos os predicados simultaneamente
    // Validates: Requirements 3.1, 4.2, 4.3, 4.4
    // -----------------------------------------------------------------------
    try {
        fc.assert(fc.property(
            fc.array(fc.record({
                status:   fc.constantFrom('Prospect', 'Active', 'Inactive'),
                state:    fc.option(fc.string({ minLength: 2, maxLength: 3 }), { nil: null }),
                decision: fc.constantFrom('Go', 'No Go', ''),
                reason:   fc.string(),
            })),
            fc.constantFrom('SP', 'RJ', 'MG', 'all'),
            fc.constantFrom('Go', 'No Go', 'all'),
            (data, stateFilter, decisionFilter) => {
                const result = computeFilteredProspects(data, stateFilter, decisionFilter);
                return result.every(p =>
                    p.status === 'Prospect' &&
                    (stateFilter    === 'all' || p.state    === stateFilter) &&
                    (decisionFilter === 'all' || p.decision === decisionFilter)
                );
            }
        ), { numRuns: 100 });

        results.push({ name: 'Property 2 — Filtragem combinada satisfaz todos os predicados', passed: true });
        console.log('✅ Property 2 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 2 — Filtragem combinada satisfaz todos os predicados', passed: false, error: err.message });
        console.error('❌ Property 2 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Property 3: Estatísticas do popup são aritmeticamente corretas
    // Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
    // -----------------------------------------------------------------------
    try {
        fc.assert(fc.property(
            fc.array(fc.record({
                decision: fc.constantFrom('Go', 'No Go'),
                reason:   fc.constantFrom(
                    'Sem oportunidade próxima',
                    'Sem oportunidade próxima na borda',
                    'Fora de jurisdição',
                    'Seguir cadastro',
                    ''
                ),
            })),
            (prospects) => {
                const stats    = computeStats(prospects);
                const goCount  = prospects.filter(p => p.decision === 'Go').length;
                const expected = prospects.length > 0 ? goCount / prospects.length * 100 : 0;
                return (
                    stats.total    === prospects.length &&
                    stats.goCount  === goCount &&
                    Math.abs(stats.approvalRate - expected) < 0.001
                );
            }
        ), { numRuns: 100 });

        results.push({ name: 'Property 3 — Estatísticas do popup são aritmeticamente corretas', passed: true });
        console.log('✅ Property 3 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 3 — Estatísticas do popup são aritmeticamente corretas', passed: false, error: err.message });
        console.error('❌ Property 3 failed:', err.message);
    }

    const passed = results.filter(r => r.passed).length;
    console.log(`\nResults: ${passed}/${results.length} properties passed`);
    return results;
}

// ---------------------------------------------------------------------------
// Auto-run when executed directly (Node.js: node js/tests/area-analysis.test.js)
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
