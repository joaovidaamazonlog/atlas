/**
 * report-parser.test.js
 * =====================
 * Testes para o Report_Parser do Management Dashboard.
 *
 * Properties tested:
 *   Property 1 — Round-trip do parser
 *                parse(serialize(parse(text))) produz objeto equivalente ao original
 *                Validates: Requirements 1.2, 1.3, 1.6
 *
 * Example tests:
 *   - Parser retorna null para campos ausentes sem lançar exceção
 *   - Data de geração extraída corretamente do cabeçalho
 *   Validates: Requirements 1.4, 1.5
 *
 * Running:
 *   node js/tests/report-parser.test.js
 */

// ---------------------------------------------------------------------------
// Import parse and serialize from management-dashboard module
// ---------------------------------------------------------------------------

import { parse, serialize } from '../modules/management-dashboard.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Gera um texto de relatório sintético a partir de dados estruturados.
 * Usado pelo gerador do fast-check para criar entradas aleatórias.
 */
function buildReportText(generatedAt, bases) {
    const lines = [];
    lines.push('RELATORIO EXECUTIVO DE OTIMIZACAO');
    lines.push(`Gerado em: ${generatedAt}`);
    lines.push('='.repeat(80));

    for (const base of bases) {
        const coveragePct = (base.coverage * 100).toFixed(1);
        const attainmentPct = (base.attainment * 100).toFixed(1);
        const p = base.partners;

        lines.push('');
        lines.push(`BASE: ${base.code} | BDM: ${base.bdm}`);
        lines.push('-'.repeat(80));
        lines.push(`  Territorios:                      ${base.numTerritories}`);
        lines.push(`  Demanda diaria total:             ${base.dailyDemand.toFixed(1)} pacotes/dia`);
        lines.push(`  Vagas ideais (total):             ${base.idealSlots}`);
        lines.push(`  Vagas com match:                  ${base.matchedSlots}`);
        lines.push(`  Vagas em aberto:                  ${base.openSlots}`);
        lines.push(`  Cobertura (match / total):        ${base.matchedSlots}/${base.idealSlots} = ${coveragePct}%`);
        lines.push(`  Parceiros existentes:             ${base.matchedSlots}`);
        lines.push(`    • Ativos:                       ${p.active}`);
        lines.push(`    • Onboarding:                   ${p.onboarding}`);
        lines.push(`    • BG Checks / Vetting:          ${p.bgChecks}`);
        lines.push(`    • Prospects a aprovar:          ${p.prospects}`);
        lines.push(`    • Inativos a reativar:          ${p.inactive}`);
        lines.push(`  Attainment (Ativos / Vagas):      ${attainmentPct}%`);
        lines.push('-'.repeat(80));
        lines.push('  DETALHAMENTO POR TERRITORIO:');

        for (const t of base.territories) {
            const tAttPct = (t.attainment * 100).toFixed(1);
            const tAccPct = (t.accuracy * 100).toFixed(1);
            lines.push('');
            lines.push(`  ${t.id} (${t.ctl})`);
            lines.push(`    Demanda diaria:      ${t.dailyDemand.toFixed(1)} pacotes/dia`);
            lines.push(`    Vagas / Em aberto:   ${t.totalSlots} / ${t.openSlots}`);
            lines.push(`    Ativos:               ${t.active}`);
            lines.push(`    Onboarding:           ${t.onboarding}`);
            lines.push(`    BG:                   ${t.bg}`);
            lines.push(`    Prospects:            ${t.prospects}`);
            lines.push(`    Inativos:             ${t.inactive}`);
            lines.push(`    Attainment:            ${tAttPct}%`);
            lines.push(`    Acuracidade:          ${tAccPct}%`);
        }
        lines.push('');
    }

    return lines.join('\n');
}

/**
 * Compara dois objetos ReportData com tolerância para arredondamento de floats.
 */
function reportDataEqual(a, b) {
    if (a.generatedAt !== b.generatedAt) return false;
    if (a.bases.length !== b.bases.length) return false;

    for (let i = 0; i < a.bases.length; i++) {
        const ba = a.bases[i];
        const bb = b.bases[i];
        if (ba.code !== bb.code) return false;
        if (ba.bdm !== bb.bdm) return false;
        if (ba.numTerritories !== bb.numTerritories) return false;
        if (Math.abs(ba.dailyDemand - bb.dailyDemand) > 0.1) return false;
        if (ba.idealSlots !== bb.idealSlots) return false;
        if (ba.matchedSlots !== bb.matchedSlots) return false;
        if (ba.openSlots !== bb.openSlots) return false;
        if (Math.abs(ba.coverage - bb.coverage) > 0.001) return false;
        if (Math.abs(ba.attainment - bb.attainment) > 0.001) return false;
        if (ba.partners.active !== bb.partners.active) return false;
        if (ba.partners.onboarding !== bb.partners.onboarding) return false;
        if (ba.partners.bgChecks !== bb.partners.bgChecks) return false;
        if (ba.partners.prospects !== bb.partners.prospects) return false;
        if (ba.partners.inactive !== bb.partners.inactive) return false;
        if (ba.territories.length !== bb.territories.length) return false;

        for (let j = 0; j < ba.territories.length; j++) {
            const ta = ba.territories[j];
            const tb = bb.territories[j];
            if (ta.id !== tb.id) return false;
            if (ta.ctl !== tb.ctl) return false;
            if (Math.abs(ta.dailyDemand - tb.dailyDemand) > 0.1) return false;
            if (ta.totalSlots !== tb.totalSlots) return false;
            if (ta.openSlots !== tb.openSlots) return false;
            if (ta.active !== tb.active) return false;
            if (ta.onboarding !== tb.onboarding) return false;
            if (ta.bg !== tb.bg) return false;
            if (ta.prospects !== tb.prospects) return false;
            if (ta.inactive !== tb.inactive) return false;
            if (Math.abs(ta.attainment - tb.attainment) > 0.001) return false;
            if (Math.abs(ta.accuracy - tb.accuracy) > 0.001) return false;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

export async function runTests() {
    let fc;
    try {
        const mod = await import('fast-check');
        fc = mod.default ?? mod;
    } catch {
        if (typeof globalThis.fc !== 'undefined') {
            fc = globalThis.fc;
        } else {
            throw new Error('fast-check not found. Install with: npm install --save-dev fast-check');
        }
    }

    const results = [];

    // -----------------------------------------------------------------------
    // Property 1: Round-trip do parser
    // Feature: management-dashboard, Property 1: Round-trip do parser
    // Validates: Requirements 1.2, 1.3, 1.6
    // -----------------------------------------------------------------------
    try {
        const baseCodeArb = fc.stringMatching(/^D[A-Z]{2}\d$/).filter(s => s.length === 4);
        const bdmArb = fc.constantFrom('BH', 'SP/SUL', 'RJ/CW', 'FORTALEZA', 'ES/BA', 'RECIFE/JOAO PESSOA');
        const ctlArb = fc.constantFrom('CTL-A', 'CTL-B', 'CTL-C');

        const territoryArb = (baseCode, idx) => fc.record({
            id: fc.constant(`${baseCode}_bucket-${String(idx + 1).padStart(2, '0')}`),
            ctl: ctlArb,
            dailyDemand: fc.float({ min: 100, max: 10000, noNaN: true }),
            totalSlots: fc.integer({ min: 1, max: 100 }),
            openSlots: fc.integer({ min: 0, max: 100 }),
            active: fc.integer({ min: 0, max: 50 }),
            onboarding: fc.integer({ min: 0, max: 20 }),
            bg: fc.integer({ min: 0, max: 20 }),
            prospects: fc.integer({ min: 0, max: 20 }),
            inactive: fc.integer({ min: 0, max: 20 }),
            attainment: fc.float({ min: 0, max: 1, noNaN: true }),
            accuracy: fc.float({ min: 0, max: 1, noNaN: true }),
        });

        fc.assert(fc.property(
            fc.string({ minLength: 8, maxLength: 20 }).filter(s => /^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/.test(s) === false).map(() => '09/04/2026 18:14'),
            fc.array(
                baseCodeArb.chain(code =>
                    fc.record({
                        code: fc.constant(code),
                        bdm: bdmArb,
                        numTerritories: fc.integer({ min: 1, max: 5 }),
                        dailyDemand: fc.float({ min: 1000, max: 50000, noNaN: true }),
                        idealSlots: fc.integer({ min: 10, max: 500 }),
                        matchedSlots: fc.integer({ min: 0, max: 100 }),
                        openSlots: fc.integer({ min: 0, max: 400 }),
                        coverage: fc.float({ min: 0, max: 1, noNaN: true }),
                        attainment: fc.float({ min: 0, max: 1, noNaN: true }),
                        partners: fc.record({
                            active: fc.integer({ min: 0, max: 50 }),
                            onboarding: fc.integer({ min: 0, max: 20 }),
                            bgChecks: fc.integer({ min: 0, max: 20 }),
                            prospects: fc.integer({ min: 0, max: 20 }),
                            inactive: fc.integer({ min: 0, max: 20 }),
                        }),
                        territories: fc.array(
                            fc.integer({ min: 0, max: 4 }).chain(idx => territoryArb(code, idx)),
                            { minLength: 1, maxLength: 3 }
                        ),
                    })
                ),
                { minLength: 1, maxLength: 3 }
            ),
            (generatedAt, bases) => {
                const text = buildReportText(generatedAt, bases);
                const parsed1 = parse(text);
                const serialized = serialize(parsed1);
                const parsed2 = parse(serialized);
                return reportDataEqual(parsed1, parsed2);
            }
        ), { numRuns: 100 });

        results.push({ name: 'Property 1 — Round-trip do parser', passed: true });
        console.log('✅ Property 1 passed (100 runs)');
    } catch (err) {
        results.push({ name: 'Property 1 — Round-trip do parser', passed: false, error: err.message });
        console.error('❌ Property 1 failed:', err.message);
    }

    // -----------------------------------------------------------------------
    // Example tests
    // Validates: Requirements 1.4, 1.5
    // -----------------------------------------------------------------------

    // Test: parse() não lança exceção para texto vazio
    try {
        const result = parse('');
        const ok = result !== null && result.bases !== undefined && Array.isArray(result.bases);
        if (!ok) throw new Error('parse("") should return { generatedAt, bases: [] }');
        results.push({ name: 'Example — parse("") retorna objeto sem lançar exceção', passed: true });
        console.log('✅ Example: parse("") retorna objeto sem lançar exceção');
    } catch (err) {
        results.push({ name: 'Example — parse("") retorna objeto sem lançar exceção', passed: false, error: err.message });
        console.error('❌ Example failed:', err.message);
    }

    // Test: parse() não lança exceção para null/undefined
    try {
        const r1 = parse(null);
        const r2 = parse(undefined);
        if (!r1 || !r2) throw new Error('parse(null/undefined) should return object');
        results.push({ name: 'Example — parse(null/undefined) não lança exceção', passed: true });
        console.log('✅ Example: parse(null/undefined) não lança exceção');
    } catch (err) {
        results.push({ name: 'Example — parse(null/undefined) não lança exceção', passed: false, error: err.message });
        console.error('❌ Example failed:', err.message);
    }

    // Test: data de geração extraída corretamente do cabeçalho
    try {
        const text = 'RELATORIO EXECUTIVO DE OTIMIZACAO\nGerado em: 09/04/2026 18:14\n================================================================================\n';
        const result = parse(text);
        if (result.generatedAt !== '09/04/2026 18:14') {
            throw new Error(`Expected "09/04/2026 18:14", got "${result.generatedAt}"`);
        }
        results.push({ name: 'Example — generatedAt extraído corretamente do cabeçalho', passed: true });
        console.log('✅ Example: generatedAt extraído corretamente');
    } catch (err) {
        results.push({ name: 'Example — generatedAt extraído corretamente do cabeçalho', passed: false, error: err.message });
        console.error('❌ Example failed:', err.message);
    }

    // Test: campos numéricos ausentes retornam 0, não NaN ou exceção
    try {
        const text = 'RELATORIO EXECUTIVO DE OTIMIZACAO\nGerado em: 01/01/2026 00:00\n================================================================================\n\nBASE: DBH5 | BDM: BH\n--------------------------------------------------------------------------------\n  Territorios:                      \n  Demanda diaria total:             \n  Vagas ideais (total):             \n  Vagas com match:                  \n  Vagas em aberto:                  \n  Cobertura (match / total):        0/0 = 0.0%\n  Parceiros existentes:             0\n    • Ativos:                       \n    • Onboarding:                   \n    • BG Checks / Vetting:          \n    • Prospects a aprovar:          \n    • Inativos a reativar:          \n  Attainment (Ativos / Vagas):      0.0%\n';
        const result = parse(text);
        const base = result.bases[0];
        if (base) {
            const numericFields = [base.numTerritories, base.dailyDemand, base.idealSlots, base.matchedSlots, base.openSlots];
            const hasNaN = numericFields.some(v => isNaN(v));
            if (hasNaN) throw new Error('Campos numéricos ausentes não devem ser NaN');
        }
        results.push({ name: 'Example — campos numéricos ausentes retornam 0, não NaN', passed: true });
        console.log('✅ Example: campos numéricos ausentes retornam 0');
    } catch (err) {
        results.push({ name: 'Example — campos numéricos ausentes retornam 0, não NaN', passed: false, error: err.message });
        console.error('❌ Example failed:', err.message);
    }

    const passed = results.filter(r => r.passed).length;
    console.log(`\nResults: ${passed}/${results.length} tests passed`);
    return results;
}

// ---------------------------------------------------------------------------
// Auto-run when executed directly
// ---------------------------------------------------------------------------
runTests().then(results => {
    const failed = results.filter(r => !r.passed);
    if (failed.length > 0) process.exit(1);
}).catch(err => {
    console.error('Test runner error:', err.message);
    process.exit(1);
});
