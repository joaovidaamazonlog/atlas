/**
 * management-dashboard.js
 * =======================
 * Módulo ES6 do Dashboard Gerencial.
 * Substitui o conteúdo do #stats-panel por uma visão consolidada
 * dos dados do relatorio_executivo.json gerado pelo backend.
 *
 * Exporta: init(), render(), filterBases(), computeKPIs(), getStatusClass(),
 *          getChartDataForBase(), sortTerritories(), getUniqueCeps()
 */

import { DATA_URLS } from '../config.js';
import { state } from '../state.js';

// ---------------------------------------------------------------------------
// Estado interno
// ---------------------------------------------------------------------------

let _reportData = null;
let _activeFilters = { bdm: 'all', base: 'all', ctl: 'all', territory: 'all' };
let _sortState = { column: null, direction: 'asc' };
let _charts = {};
let _initialized = false;

// ---------------------------------------------------------------------------
// Report_Parser — funções puras de parsing e serialização
// ---------------------------------------------------------------------------

/**
 * Converte uma string percentual (ex: "3.8%") para decimal (0.038).
 * Usa parseFloat com fallback 0. Nunca lança exceção.
 * @param {string} str
 * @returns {number}
 */
function _pct(str) {
    return (parseFloat((str || '').replace(',', '.')) || 0) / 100;
}

/**
 * Converte uma string numérica (ex: "18,396.0") para número.
 * Remove separadores de milhar (vírgulas) antes de parsear.
 * Usa parseFloat com fallback 0. Nunca lança exceção.
 * @param {string} str
 * @returns {number}
 */
function _num(str) {
    return parseFloat((str || '').replace(/,/g, '')) || 0;
}

/**
 * Parseia o conteúdo do RELATORIO_EXECUTIVO.txt e retorna um objeto ReportData.
 * Função pura — não faz fetch, recebe string e retorna objeto.
 * Nunca lança exceção; retorna null para campos não parseáveis.
 *
 * @param {string} text - conteúdo completo do relatório como string
 * @returns {{ generatedAt: string|null, bases: Array }} objeto ReportData
 */
export function parse(text) {
    if (!text || typeof text !== 'string') {
        return { generatedAt: null, bases: [] };
    }

    // Extrair data de geração do cabeçalho
    const headerMatch = text.match(/Gerado em:\s*(.+)/);
    const generatedAt = headerMatch ? headerMatch[1].trim() : null;

    const bases = [];

    // Dividir o texto em blocos de BASE usando o separador "BASE: XXXX | BDM: YYYY"
    // Cada bloco começa com "BASE:" e vai até o próximo "BASE:" ou fim do texto
    const basePattern = /BASE:\s*(\S+)\s*\|\s*BDM:\s*(.+?)\n([\s\S]*?)(?=\nBASE:\s|\s*$)/g;
    let baseMatch;

    while ((baseMatch = basePattern.exec(text)) !== null) {
        const code = baseMatch[1].trim();
        const bdm = baseMatch[2].trim();
        const baseBody = baseMatch[3];

        // Extrair campos do sumário da base
        const numTerritoriesMatch = baseBody.match(/Territorios:\s*([\d,]+)/);
        const dailyDemandMatch = baseBody.match(/Demanda diaria total:\s*([\d,\.]+)/);
        const idealSlotsMatch = baseBody.match(/Vagas ideais \(total\):\s*([\d,]+)/);
        const matchedSlotsMatch = baseBody.match(/Vagas com match:\s*([\d,]+)/);
        const openSlotsMatch = baseBody.match(/Vagas em aberto:\s*([\d,]+)/);
        const coverageMatch = baseBody.match(/Cobertura \(match \/ total\):\s*[\d\/\s]+=\s*([\d,\.]+%)/);
        const activeMatch = baseBody.match(/Ativos:\s*([\d,]+)/);
        const onboardingMatch = baseBody.match(/Onboarding:\s*([\d,]+)/);
        const bgChecksMatch = baseBody.match(/BG Checks \/ Vetting:\s*([\d,]+)/);
        const prospectsMatch = baseBody.match(/Prospects a aprovar:\s*([\d,]+)/);
        const inactiveMatch = baseBody.match(/Inativos a reativar:\s*([\d,]+)/);
        const attainmentMatch = baseBody.match(/Attainment \(Ativos \/ Vagas\):\s*([\d,\.]+%)/);

        // Extrair territórios do bloco DETALHAMENTO POR TERRITORIO
        const territories = [];
        // Each territory block: "  ID (CTL)\n    fields..."
        const terrPattern = /(\S+_bucket-\d+)\s*\(([^)]+)\)\s*\n([\s\S]*?)(?=\n\s+\S+_bucket-|\n\nBASE:|\n================|$)/g;
        let terrMatch;

        while ((terrMatch = terrPattern.exec(baseBody)) !== null) {
            const terrId = terrMatch[1].trim();
            const ctl = terrMatch[2].trim();
            const terrBody = terrMatch[3];

            const tDemandMatch = terrBody.match(/Demanda diaria:\s*([\d,\.]+)/);
            const tSlotsMatch = terrBody.match(/Vagas \/ Em aberto:\s*([\d,]+)\s*\/\s*([\d,]+)/);
            const tActiveMatch = terrBody.match(/Ativos:\s*([\d,]+)/);
            const tOnboardingMatch = terrBody.match(/Onboarding:\s*([\d,]+)/);
            const tBgMatch = terrBody.match(/BG:\s*([\d,]+)/);
            const tProspectsMatch = terrBody.match(/Prospects:\s*([\d,]+)/);
            const tInactiveMatch = terrBody.match(/Inativos:\s*([\d,]+)/);
            const tAttainmentMatch = terrBody.match(/Attainment:\s*([\d,\.]+%)/);
            const tAccuracyMatch = terrBody.match(/Acuracidade:\s*([\d,\.]+%)/);

            territories.push({
                id: terrId,
                ctl: ctl,
                dailyDemand: _num(tDemandMatch ? tDemandMatch[1] : '0'),
                totalSlots: tSlotsMatch ? (_num(tSlotsMatch[1])) : 0,
                openSlots: tSlotsMatch ? (_num(tSlotsMatch[2])) : 0,
                active: _num(tActiveMatch ? tActiveMatch[1] : '0'),
                onboarding: _num(tOnboardingMatch ? tOnboardingMatch[1] : '0'),
                bg: _num(tBgMatch ? tBgMatch[1] : '0'),
                prospects: _num(tProspectsMatch ? tProspectsMatch[1] : '0'),
                inactive: _num(tInactiveMatch ? tInactiveMatch[1] : '0'),
                attainment: _pct(tAttainmentMatch ? tAttainmentMatch[1] : '0%'),
                accuracy: _pct(tAccuracyMatch ? tAccuracyMatch[1] : '0%'),
            });
        }

        bases.push({
            code,
            bdm,
            numTerritories: _num(numTerritoriesMatch ? numTerritoriesMatch[1] : '0'),
            dailyDemand: _num(dailyDemandMatch ? dailyDemandMatch[1] : '0'),
            idealSlots: _num(idealSlotsMatch ? idealSlotsMatch[1] : '0'),
            matchedSlots: _num(matchedSlotsMatch ? matchedSlotsMatch[1] : '0'),
            openSlots: _num(openSlotsMatch ? openSlotsMatch[1] : '0'),
            coverage: _pct(coverageMatch ? coverageMatch[1] : '0%'),
            partners: {
                active: _num(activeMatch ? activeMatch[1] : '0'),
                onboarding: _num(onboardingMatch ? onboardingMatch[1] : '0'),
                bgChecks: _num(bgChecksMatch ? bgChecksMatch[1] : '0'),
                prospects: _num(prospectsMatch ? prospectsMatch[1] : '0'),
                inactive: _num(inactiveMatch ? inactiveMatch[1] : '0'),
            },
            attainment: _pct(attainmentMatch ? attainmentMatch[1] : '0%'),
            territories,
        });
    }

    return { generatedAt, bases };
}

/**
 * Serializa um objeto ReportData de volta para o formato texto do relatório.
 * Necessário para o teste de round-trip (Propriedade 1).
 *
 * @param {{ generatedAt: string|null, bases: Array }} data - objeto ReportData
 * @returns {string} texto no formato do RELATORIO_EXECUTIVO.txt
 */
export function serialize(data) {
    if (!data || !Array.isArray(data.bases)) {
        return '';
    }

    const lines = [];
    lines.push('RELATORIO EXECUTIVO DE OTIMIZACAO');
    lines.push(`Gerado em: ${data.generatedAt || ''}`);
    lines.push('='.repeat(80));

    for (const base of data.bases) {
        lines.push('');
        lines.push(`BASE: ${base.code} | BDM: ${base.bdm}`);
        lines.push('-'.repeat(80));

        const coveragePct = ((base.coverage || 0) * 100).toFixed(1);
        const attainmentPct = ((base.attainment || 0) * 100).toFixed(1);
        const p = base.partners || {};

        lines.push(`  Territorios:                      ${base.numTerritories}`);
        lines.push(`  Demanda diaria total:             ${base.dailyDemand.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pacotes/dia`);
        lines.push(`  Vagas ideais (total):             ${base.idealSlots}`);
        lines.push(`  Vagas com match:                  ${base.matchedSlots}`);
        lines.push(`  Vagas em aberto:                  ${base.openSlots}`);
        lines.push(`  Cobertura (match / total):        ${base.matchedSlots}/${base.idealSlots} = ${coveragePct}%`);
        lines.push(`  Parceiros existentes:             ${base.matchedSlots}`);
        lines.push(`    • Ativos:                       ${p.active || 0}`);
        lines.push(`    • Onboarding:                   ${p.onboarding || 0}`);
        lines.push(`    • BG Checks / Vetting:          ${p.bgChecks || 0}`);
        lines.push(`    • Prospects a aprovar:          ${p.prospects || 0}`);
        lines.push(`    • Inativos a reativar:          ${p.inactive || 0}`);
        lines.push(`  Attainment (Ativos / Vagas):      ${attainmentPct}%`);
        lines.push('-'.repeat(80));
        lines.push('  DETALHAMENTO POR TERRITORIO:');

        for (const t of (base.territories || [])) {
            const tAttainmentPct = ((t.attainment || 0) * 100).toFixed(1);
            const tAccuracyPct = ((t.accuracy || 0) * 100).toFixed(1);
            lines.push('');
            lines.push(`  ${t.id} (${t.ctl})`);
            lines.push(`    Demanda diaria:      ${t.dailyDemand.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pacotes/dia`);
            lines.push(`    Vagas / Em aberto:   ${t.totalSlots} / ${t.openSlots}`);
            lines.push(`    Ativos:               ${t.active}`);
            lines.push(`    Onboarding:           ${t.onboarding}`);
            lines.push(`    BG:                   ${t.bg}`);
            lines.push(`    Prospects:            ${t.prospects}`);
            lines.push(`    Inativos:             ${t.inactive}`);
            lines.push(`    Attainment:            ${tAttainmentPct}%`);
            lines.push(`    Acuracidade:          ${tAccuracyPct}%`);
        }
        lines.push('');
    }

    return lines.join('\n');
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Filter_Bar — funções puras e componente de filtros
// ---------------------------------------------------------------------------

/**
 * Retorna as bases filtradas de acordo com os filtros ativos.
 * Função pura exportada — necessária para testes de propriedade (Property 2).
 *
 * @param {{ generatedAt: string|null, bases: Array }} reportData
 * @param {{ bdm: string, base: string, ctl: string, territory: string }} filters
 * @returns {Array} bases filtradas, cada uma com seus territórios filtrados
 */
export function filterBases(reportData, filters) {
    if (!reportData || !Array.isArray(reportData.bases)) return [];

    let bases = reportData.bases;

    // Filtrar por BDM
    if (filters.bdm && filters.bdm !== 'all') {
        bases = bases.filter(b => b.bdm === filters.bdm);
    }

    // Filtrar por Base
    if (filters.base && filters.base !== 'all') {
        bases = bases.filter(b => b.code === filters.base);
    }

    // Filtrar territórios por CTL e/ou Território dentro de cada base
    bases = bases.map(base => {
        let territories = base.territories || [];

        if (filters.ctl && filters.ctl !== 'all') {
            territories = territories.filter(t => t.ctl === filters.ctl);
        }

        if (filters.territory && filters.territory !== 'all') {
            territories = territories.filter(t => t.id === filters.territory);
        }

        return { ...base, territories };
    });

    // Excluir bases que ficaram sem territórios quando filtros de CTL/Território estão ativos
    if ((filters.ctl && filters.ctl !== 'all') || (filters.territory && filters.territory !== 'all')) {
        bases = bases.filter(b => b.territories.length > 0);
    }

    return bases;
}

/**
 * Retorna valores únicos e ordenados de um array.
 * @param {string[]} arr
 * @returns {string[]}
 */
function _unique(arr) {
    return [...new Set(arr)].sort();
}

/**
 * Popula um <select> com opções, preservando o valor selecionado.
 * Sempre inclui a opção "Todos" como primeira opção.
 *
 * @param {HTMLSelectElement} select
 * @param {string[]} values - valores das opções
 * @param {string} currentValue - valor a preservar como selecionado
 */
function _populateSelect(select, values, currentValue) {
    const prev = currentValue !== undefined ? currentValue : select.value;
    select.innerHTML = '<option value="all">Todos</option>';
    for (const v of values) {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        select.appendChild(opt);
    }
    // Preservar seleção anterior se ainda disponível
    if (prev && prev !== 'all' && values.includes(prev)) {
        select.value = prev;
    } else {
        select.value = 'all';
    }
}

/**
 * Lê os valores atuais dos 4 selects, atualiza _activeFilters e
 * restringe as opções dos selects dependentes em cascata.
 * Reseta selects dependentes para "all" quando o pai muda.
 *
 * @param {string} changedId - ID do select que disparou a mudança
 */
function _applyFilterCascade(changedId) {
    const bdmSel = document.getElementById('md-filter-bdm');
    const baseSel = document.getElementById('md-filter-base');
    const ctlSel = document.getElementById('md-filter-ctl');
    const terrSel = document.getElementById('md-filter-territory');

    if (!bdmSel || !baseSel || !ctlSel || !terrSel) return;

    const bdmVal = bdmSel.value;
    const baseVal = baseSel.value;
    const ctlVal = ctlSel.value;

    // Determinar quais bases estão visíveis dado o BDM selecionado
    let visibleBases = _reportData ? _reportData.bases : [];
    if (bdmVal !== 'all') {
        visibleBases = visibleBases.filter(b => b.bdm === bdmVal);
    }

    // Quando BDM muda, resetar Base, CTL e Território
    if (changedId === 'md-filter-bdm') {
        const baseCodes = _unique(visibleBases.map(b => b.code));
        _populateSelect(baseSel, baseCodes, 'all');
        const allCtls = _unique(visibleBases.flatMap(b => b.territories.map(t => t.ctl)));
        _populateSelect(ctlSel, allCtls, 'all');
        const allTerrs = _unique(visibleBases.flatMap(b => b.territories.map(t => t.id)));
        _populateSelect(terrSel, allTerrs, 'all');
    }

    // Quando Base muda, resetar CTL e Território
    if (changedId === 'md-filter-base') {
        let filteredBases = visibleBases;
        if (baseVal !== 'all') {
            filteredBases = filteredBases.filter(b => b.code === baseVal);
        }
        const ctls = _unique(filteredBases.flatMap(b => b.territories.map(t => t.ctl)));
        _populateSelect(ctlSel, ctls, 'all');
        const terrs = _unique(filteredBases.flatMap(b => b.territories.map(t => t.id)));
        _populateSelect(terrSel, terrs, 'all');
    }

    // Quando CTL muda, atualizar Território
    if (changedId === 'md-filter-ctl') {
        let filteredBases = visibleBases;
        if (baseVal !== 'all') {
            filteredBases = filteredBases.filter(b => b.code === baseVal);
        }
        const newCtlVal = ctlSel.value;
        let terrs;
        if (newCtlVal !== 'all') {
            terrs = _unique(filteredBases.flatMap(b => b.territories.filter(t => t.ctl === newCtlVal).map(t => t.id)));
        } else {
            terrs = _unique(filteredBases.flatMap(b => b.territories.map(t => t.id)));
        }
        _populateSelect(terrSel, terrs, 'all');
    }

    // Atualizar _activeFilters com os valores atuais (após cascata)
    _activeFilters = {
        bdm: bdmSel.value,
        base: baseSel.value,
        ctl: ctlSel.value,
        territory: terrSel.value,
    };
}

/**
 * Renderiza a barra de filtros no container fornecido.
 * Cria quatro <select> (BDM, Base, CTL, Território) com opções populadas
 * a partir de _reportData e preserva os valores de _activeFilters.
 *
 * @param {HTMLElement} container
 */
function _renderFilterBar(container) {
    if (!_reportData) return;

    const bases = _reportData.bases || [];

    // Calcular opções iniciais (sem filtro aplicado)
    const bdmOptions = _unique(bases.map(b => b.bdm));
    const baseOptions = _unique(bases.map(b => b.code));
    const ctlOptions = _unique(bases.flatMap(b => b.territories.map(t => t.ctl)));
    const terrOptions = _unique(bases.flatMap(b => b.territories.map(t => t.id)));

    const filterDefs = [
        { id: 'md-filter-bdm',       label: 'BDM',        options: bdmOptions,  filterKey: 'bdm' },
        { id: 'md-filter-base',      label: 'Base',       options: baseOptions, filterKey: 'base' },
        { id: 'md-filter-ctl',       label: 'CTL',        options: ctlOptions,  filterKey: 'ctl' },
        { id: 'md-filter-territory', label: 'Território', options: terrOptions, filterKey: 'territory' },
    ];

    container.innerHTML = `<div class="md-filter-bar">${
        filterDefs.map(f => `
            <div class="md-filter-group">
                <label for="${f.id}">${f.label}</label>
                <select id="${f.id}">
                    <option value="all">Todos</option>
                    ${f.options.map(v => `<option value="${v}">${v}</option>`).join('')}
                </select>
            </div>
        `).join('')
    }</div>`;

    // Restaurar valores de _activeFilters
    for (const f of filterDefs) {
        const sel = document.getElementById(f.id);
        if (sel && _activeFilters[f.filterKey] && _activeFilters[f.filterKey] !== 'all') {
            sel.value = _activeFilters[f.filterKey];
        }
    }

    // Adicionar event listeners
    const bdmSel  = document.getElementById('md-filter-bdm');
    const baseSel = document.getElementById('md-filter-base');
    const ctlSel  = document.getElementById('md-filter-ctl');
    const terrSel = document.getElementById('md-filter-territory');

    bdmSel.addEventListener('change', () => {
        _applyFilterCascade('md-filter-bdm');
        render();
    });

    baseSel.addEventListener('change', () => {
        _applyFilterCascade('md-filter-base');
        render();
    });

    ctlSel.addEventListener('change', () => {
        _applyFilterCascade('md-filter-ctl');
        render();
    });

    terrSel.addEventListener('change', () => {
        _activeFilters.territory = terrSel.value;
        render();
    });
}

// ---------------------------------------------------------------------------
// KPI_Cards — cálculo e renderização
// ---------------------------------------------------------------------------

/**
 * Calcula os KPIs a partir das bases filtradas.
 * Função pura exportada para testes (Property 3).
 *
 * @param {Array} filteredBases - array de BaseData já filtrado
 * @returns {KPISummary}
 */
function _computeKPIs(filteredBases) {
    if (!filteredBases || filteredBases.length === 0) {
        return {
            totalBases: 0,
            totalTerritories: 0,
            totalDailyDemand: 0,
            totalIdealSlots: 0,
            totalOpenSlots: 0,
            totalActivePartners: 0,
            avgAttainment: 0,
            avgCoverage: 0,
        };
    }

    const totalBases = filteredBases.length;
    const totalTerritories = filteredBases.reduce((sum, b) => sum + (b.territories ? b.territories.length : 0), 0);
    const totalDailyDemand = filteredBases.reduce((sum, b) => sum + (b.dailyDemand || 0), 0);
    const totalIdealSlots = filteredBases.reduce((sum, b) => sum + (b.idealSlots || 0), 0);
    const totalOpenSlots = filteredBases.reduce((sum, b) => sum + (b.openSlots || 0), 0);
    const totalActivePartners = filteredBases.reduce((sum, b) => sum + ((b.partners && b.partners.active) || 0), 0);
    const avgAttainment = filteredBases.reduce((sum, b) => sum + (b.attainment || 0), 0) / totalBases;
    const avgCoverage = filteredBases.reduce((sum, b) => sum + (b.coverage || 0), 0) / totalBases;

    return {
        totalBases,
        totalTerritories,
        totalDailyDemand,
        totalIdealSlots,
        totalOpenSlots,
        totalActivePartners,
        avgAttainment,
        avgCoverage,
    };
}

export const computeKPIs = _computeKPIs;

// ---------------------------------------------------------------------------
// Territory_Table — ordenação e renderização
// ---------------------------------------------------------------------------

/**
 * Ordena um array de territórios por uma coluna e direção.
 * Função pura exportada para testes (Property 6).
 *
 * @param {Array} territories - array de objetos { ...TerritoryData, baseCode: string }
 * @param {string} column - chave de ordenação
 * @param {'asc'|'desc'} direction - direção
 * @returns {Array} novo array ordenado (não muta o original)
 */
export function sortTerritories(territories, column, direction) {
    if (!territories || !column) return territories ? [...territories] : [];
    return [...territories].sort((a, b) => {
        const va = a[column];
        const vb = b[column];
        let cmp;
        if (typeof va === 'string' && typeof vb === 'string') {
            cmp = va.localeCompare(vb);
        } else {
            cmp = (va ?? 0) - (vb ?? 0);
        }
        return direction === 'desc' ? -cmp : cmp;
    });
}

/**
 * Renderiza a tabela de detalhamento por território.
 *
 * @param {HTMLElement} container
 * @param {Array} filteredTerritories - array plano de { ...TerritoryData, baseCode: string }
 */
function _renderTerritoryTable(container, filteredTerritories) {
    if (!filteredTerritories || filteredTerritories.length === 0) {
        container.innerHTML = '<div class="md-message md-empty">Nenhum dado encontrado para os filtros selecionados</div>';
        return;
    }

    const columns = [
        { key: 'baseCode',    label: 'Base' },
        { key: 'ctl',         label: 'CTL' },
        { key: 'id',          label: 'Território' },
        { key: 'dailyDemand', label: 'Demanda Diária' },
        { key: 'totalSlots',  label: 'Vagas Totais' },
        { key: 'openSlots',   label: 'Vagas em Aberto' },
        { key: 'active',      label: 'Ativos' },
        { key: 'onboarding',  label: 'Onboarding' },
        { key: 'bg',          label: 'BG' },
        { key: 'prospects',   label: 'Prospects' },
        { key: 'inactive',    label: 'Inativos' },
        { key: 'attainment',  label: 'Attainment (%)' },
        { key: 'accuracy',    label: 'Acuracidade (%)' },
    ];

    const sorted = _sortState.column
        ? sortTerritories(filteredTerritories, _sortState.column, _sortState.direction)
        : filteredTerritories;

    const headerCells = columns.map(col => {
        let cls = '';
        if (_sortState.column === col.key) {
            cls = ` class="${_sortState.direction === 'asc' ? 'sort-asc' : 'sort-desc'}"`;
        }
        return `<th${cls} data-col="${col.key}" style="cursor:pointer">${col.label}</th>`;
    }).join('');

    const rows = sorted.map(t => {
        const attCls = getStatusClass(t.attainment, { green: 0.15, yellow: 0.05 });
        const accCls = getStatusClass(t.accuracy, { green: 0.70, yellow: 0.40 });
        return `<tr>
            <td>${t.baseCode ?? ''}</td>
            <td>${t.ctl ?? ''}</td>
            <td>${t.id ?? ''}</td>
            <td>${(t.dailyDemand ?? 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}</td>
            <td>${t.totalSlots ?? 0}</td>
            <td>${t.openSlots ?? 0}</td>
            <td>${t.active ?? 0}</td>
            <td>${t.onboarding ?? 0}</td>
            <td>${t.bg ?? 0}</td>
            <td>${t.prospects ?? 0}</td>
            <td>${t.inactive ?? 0}</td>
            <td class="${attCls}">${((t.attainment ?? 0) * 100).toFixed(1)}%</td>
            <td class="${accCls}">${((t.accuracy ?? 0) * 100).toFixed(1)}%</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
        <div class="md-table-wrapper">
            <table class="md-table">
                <thead><tr>${headerCells}</tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;

    // Adicionar event listeners para ordenação
    const ths = container.querySelectorAll('th[data-col]');
    ths.forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-col');
            if (_sortState.column === col) {
                _sortState.direction = _sortState.direction === 'asc' ? 'desc' : 'asc';
            } else {
                _sortState.column = col;
                _sortState.direction = 'asc';
            }
            render();
        });
    });
}

/**
 * Retorna a classe CSS de status baseada em thresholds.
 * Função pura exportada para testes (Properties 4 e 5).
 *
 * @param {number} value - valor decimal (0-1)
 * @param {{ green: number, yellow: number }} thresholds - green é o limiar superior
 * @returns {'status-green'|'status-yellow'|'status-red'}
 */
export function getStatusClass(value, thresholds) {
    if (value >= thresholds.green) return 'status-green';
    if (value >= thresholds.yellow) return 'status-yellow';
    return 'status-red';
}

/**
 * Renderiza os KPI cards no container fornecido.
 *
 * @param {HTMLElement} container
 * @param {KPISummary} kpis
 */
function _renderKPICards(container, kpis) {
    const attainmentClass = getStatusClass(kpis.avgAttainment, { green: 0.15, yellow: 0.05 });
    const coverageClass = getStatusClass(kpis.avgCoverage, { green: 0.25, yellow: 0.10 });

    const reportDate = _reportData && _reportData.generatedAt
        ? `<div class="md-report-date">Relatório gerado em: ${_reportData.generatedAt}</div>`
        : '';

    const cards = [
        { label: 'Total de Bases',          value: kpis.totalBases.toLocaleString('pt-BR'),                  cls: '' },
        { label: 'Total de Territórios',    value: kpis.totalTerritories.toLocaleString('pt-BR'),            cls: '' },
        { label: 'Demanda Diária (pacotes/dia)', value: kpis.totalDailyDemand.toLocaleString('pt-BR'),       cls: '' },
        { label: 'Vagas Ideais',            value: kpis.totalIdealSlots.toLocaleString('pt-BR'),             cls: '' },
        { label: 'Vagas em Aberto',         value: kpis.totalOpenSlots.toLocaleString('pt-BR'),              cls: '' },
        { label: 'Parceiros Ativos',        value: kpis.totalActivePartners.toLocaleString('pt-BR'),         cls: '' },
        { label: 'Attainment Médio (%)',    value: (kpis.avgAttainment * 100).toFixed(1) + '%',              cls: attainmentClass },
        { label: 'Cobertura Média (%)',     value: (kpis.avgCoverage * 100).toFixed(1) + '%',                cls: coverageClass },
    ];

    container.innerHTML = reportDate + `<div class="md-kpi-grid">${
        cards.map(c => `
            <div class="md-kpi-card">
                <div class="md-kpi-label">${c.label}</div>
                <div class="md-kpi-value ${c.cls}">${c.value}</div>
            </div>
        `).join('')
    }</div>`;
}

// ---------------------------------------------------------------------------
// Charts — gráficos Chart.js com fallback de tabela
// ---------------------------------------------------------------------------

/**
 * Calcula os dados dos gráficos a partir das bases filtradas e da base selecionada.
 * Função pura exportada para testes (Property 8).
 *
 * @param {Array} filteredBases - array de BaseData já filtrado
 * @param {string} selectedBase - código da base selecionada ou 'all'
 * @returns {{
 *   attainmentByBase: { labels: string[], data: number[] },
 *   partnersByBase: { labels: string[], datasets: Array },
 *   attainmentByTerritory: { labels: string[], data: number[] } | null
 * }}
 */
export function getChartDataForBase(filteredBases, selectedBase) {
    // Gráfico 1: attainment por Base, ordenado do maior para o menor
    const sortedByAttainment = [...filteredBases].sort((a, b) => b.attainment - a.attainment);
    const attainmentByBase = {
        labels: sortedByAttainment.map(b => b.code),
        data: sortedByAttainment.map(b => parseFloat((b.attainment * 100).toFixed(1))),
    };

    // Gráfico 2: composição de parceiros por Base
    const partnerLabels = filteredBases.map(b => b.code);
    const partnersByBase = {
        labels: partnerLabels,
        datasets: [
            {
                label: 'Ativos',
                data: filteredBases.map(b => (b.partners && b.partners.active) || 0),
                backgroundColor: '#27ae60',
            },
            {
                label: 'Onboarding',
                data: filteredBases.map(b => (b.partners && b.partners.onboarding) || 0),
                backgroundColor: '#f39c12',
            },
            {
                label: 'BG',
                data: filteredBases.map(b => (b.partners && b.partners.bgChecks) || 0),
                backgroundColor: '#e67e22',
            },
            {
                label: 'Prospects',
                data: filteredBases.map(b => (b.partners && b.partners.prospects) || 0),
                backgroundColor: '#9b59b6',
            },
            {
                label: 'Inativos',
                data: filteredBases.map(b => (b.partners && b.partners.inactive) || 0),
                backgroundColor: '#e74c3c',
            },
        ],
    };

    // Gráfico 3: attainment por Território (apenas quando uma base específica está selecionada)
    let attainmentByTerritory = null;
    if (selectedBase && selectedBase !== 'all') {
        const base = filteredBases.find(b => b.code === selectedBase);
        if (base && base.territories && base.territories.length > 0) {
            const territories = base.territories;
            attainmentByTerritory = {
                labels: territories.map(t => t.id),
                data: territories.map(t => parseFloat((t.attainment * 100).toFixed(1))),
            };
        }
    }

    return { attainmentByBase, partnersByBase, attainmentByTerritory };
}

/**
 * Renderiza tabela de fallback quando Chart.js não está disponível.
 * @param {HTMLElement} container
 * @param {Array} filteredBases
 * @param {string} selectedBase
 */
function _renderChartsFallback(container, filteredBases, selectedBase) {
    const chartData = getChartDataForBase(filteredBases, selectedBase);

    let html = '<div class="md-charts-grid">';

    // Tabela de attainment por base
    html += `
        <div class="md-chart-card">
            <h3>Attainment por Base (%)</h3>
            <table class="md-table">
                <thead><tr><th>Base</th><th>Attainment (%)</th></tr></thead>
                <tbody>
                    ${chartData.attainmentByBase.labels.map((label, i) =>
                        `<tr><td>${label}</td><td>${chartData.attainmentByBase.data[i]}%</td></tr>`
                    ).join('')}
                </tbody>
            </table>
        </div>`;

    // Tabela de composição de parceiros por base
    html += `
        <div class="md-chart-card">
            <h3>Composição de Parceiros por Base</h3>
            <table class="md-table">
                <thead><tr><th>Base</th><th>Ativos</th><th>Onboarding</th><th>BG</th><th>Prospects</th><th>Inativos</th></tr></thead>
                <tbody>
                    ${chartData.partnersByBase.labels.map((label, i) =>
                        `<tr>
                            <td>${label}</td>
                            <td>${chartData.partnersByBase.datasets[0].data[i]}</td>
                            <td>${chartData.partnersByBase.datasets[1].data[i]}</td>
                            <td>${chartData.partnersByBase.datasets[2].data[i]}</td>
                            <td>${chartData.partnersByBase.datasets[3].data[i]}</td>
                            <td>${chartData.partnersByBase.datasets[4].data[i]}</td>
                        </tr>`
                    ).join('')}
                </tbody>
            </table>
        </div>`;

    // Tabela de attainment por território (se base selecionada)
    if (chartData.attainmentByTerritory) {
        html += `
            <div class="md-chart-card">
                <h3>Attainment por Território — ${selectedBase} (%)</h3>
                <table class="md-table">
                    <thead><tr><th>Território</th><th>Attainment (%)</th></tr></thead>
                    <tbody>
                        ${chartData.attainmentByTerritory.labels.map((label, i) =>
                            `<tr><td>${label}</td><td>${chartData.attainmentByTerritory.data[i]}%</td></tr>`
                        ).join('')}
                    </tbody>
                </table>
            </div>`;
    }

    html += '</div>';
    container.innerHTML = html;
}

/**
 * Renderiza os gráficos Chart.js no container fornecido.
 * Destrói instâncias anteriores antes de criar novas.
 * Usa fallback de tabela quando Chart.js não está disponível.
 *
 * @param {HTMLElement} container
 * @param {Array} filteredBases
 * @param {string} selectedBase - código da base selecionada ou 'all'
 */
function _renderCharts(container, filteredBases, selectedBase) {
    if (!filteredBases || filteredBases.length === 0) {
        container.innerHTML = '';
        return;
    }

    // Fallback: Chart.js não disponível
    if (typeof Chart === 'undefined') {
        _renderChartsFallback(container, filteredBases, selectedBase);
        return;
    }

    // Destruir instâncias anteriores
    for (const key of Object.keys(_charts)) {
        if (_charts[key] && typeof _charts[key].destroy === 'function') {
            _charts[key].destroy();
        }
        delete _charts[key];
    }

    const chartData = getChartDataForBase(filteredBases, selectedBase);
    const hasTerritory = chartData.attainmentByTerritory !== null;

    // Montar HTML com canvas
    let html = '<div class="md-charts-grid">';
    html += `<div class="md-chart-card"><canvas id="md-chart-attainment-base"></canvas></div>`;
    html += `<div class="md-chart-card"><canvas id="md-chart-partners-base"></canvas></div>`;
    if (hasTerritory) {
        html += `<div class="md-chart-card"><canvas id="md-chart-attainment-territory"></canvas></div>`;
    }
    html += '</div>';
    container.innerHTML = html;

    // Gráfico 1: barras horizontais — attainment por Base
    const ctx1 = document.getElementById('md-chart-attainment-base');
    if (ctx1) {
        _charts['attainmentBase'] = new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: chartData.attainmentByBase.labels,
                datasets: [{
                    label: 'Attainment (%)',
                    data: chartData.attainmentByBase.data,
                    backgroundColor: '#3498db',
                }],
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.label}: ${ctx.parsed.x}%`,
                        },
                    },
                    legend: { display: false },
                    title: { display: true, text: 'Attainment por Base (%)' },
                },
            },
        });
    }

    // Gráfico 2: barras empilhadas — composição de parceiros por Base
    const ctx2 = document.getElementById('md-chart-partners-base');
    if (ctx2) {
        _charts['partnersBase'] = new Chart(ctx2, {
            type: 'bar',
            data: chartData.partnersByBase,
            options: {
                responsive: true,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}`,
                        },
                    },
                    title: { display: true, text: 'Composição de Parceiros por Base' },
                },
                scales: {
                    x: { stacked: true },
                    y: { stacked: true },
                },
            },
        });
    }

    // Gráfico 3: barras — attainment por Território (base específica selecionada)
    if (hasTerritory) {
        const ctx3 = document.getElementById('md-chart-attainment-territory');
        if (ctx3) {
            _charts['attainmentTerritory'] = new Chart(ctx3, {
                type: 'bar',
                data: {
                    labels: chartData.attainmentByTerritory.labels,
                    datasets: [{
                        label: 'Attainment (%)',
                        data: chartData.attainmentByTerritory.data,
                        backgroundColor: '#3498db',
                    }],
                },
                options: {
                    responsive: true,
                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: ctx => `${ctx.label}: ${ctx.parsed.y}%`,
                            },
                        },
                        legend: { display: false },
                        title: { display: true, text: `Attainment por Território — ${selectedBase} (%)` },
                    },
                },
            });
        }
    }
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/**
 * Inicializa o dashboard gerencial.
 * Chamado pelo main.js ao abrir o painel pela primeira vez.
 * Faz fetch do relatorio_executivo.json apenas uma vez.
 */
export async function init() {
    if (_initialized) return;
    _initialized = true;

    const root = document.getElementById('management-dashboard-root');
    if (!root) return;

    root.innerHTML = `<div class="md-spinner-wrapper"><div class="md-spinner"></div><span>Carregando relatório...</span></div>`;

    try {
        const response = await fetch(DATA_URLS.executiveReport);
        if (!response.ok) {
            throw new Error(`Não foi possível carregar o relatório (HTTP ${response.status})`);
        }
        _reportData = await response.json();
        render();
    } catch (e) {
        root.innerHTML = `<div class="md-message md-error">Erro ao carregar o relatório executivo: ${e.message}</div>`;
    }
}

// ---------------------------------------------------------------------------
// CEP Listing — listagem de CEPs por território
// ---------------------------------------------------------------------------

/**
 * Retorna um array de CEPs únicos para um território dado.
 * Os CEPs vêm diretamente do relatorio_executivo.json (campo `ceps` por território).
 * Função pura exportada para testes (Property 7).
 *
 * @param {object|null} reportData - objeto ReportData
 * @param {string} territoryId - id do território (ex: "DBH5_bucket-01")
 * @returns {string[]} array de CEPs únicos (sem duplicatas)
 */
export function getUniqueCeps(reportData, territoryId) {
    if (!reportData || !territoryId) return [];
    for (const base of (reportData.bases || [])) {
        for (const t of (base.territories || [])) {
            if (t.id === territoryId) {
                return [...new Set(t.ceps || [])];
            }
        }
    }
    return [];
}

/**
 * Renderiza a listagem de CEPs para o território selecionado.
 * Oculta a seção quando o filtro de Território é 'all'.
 * Os CEPs vêm do relatorio_executivo.json — sem fetch adicional.
 *
 * @param {HTMLElement} container
 * @param {string} selectedTerritory - id do território selecionado ou 'all'
 */
function _renderCepListing(container, selectedTerritory) {
    if (!selectedTerritory || selectedTerritory === 'all') {
        container.innerHTML = '';
        return;
    }

    const ceps = getUniqueCeps(_reportData, selectedTerritory);

    if (ceps.length === 0) {
        container.innerHTML = `<div class="md-cep-section"><p class="md-message md-empty">CEPs não disponíveis para este território</p></div>`;
        return;
    }

    const tagsHtml = ceps.map(cep => `<span class="md-cep-tag">${cep}</span>`).join('');

    container.innerHTML = `
        <div class="md-cep-section">
            <h4>CEPs do Território</h4>
            <div class="md-kpi-card" style="margin-bottom:8px">
                <div class="md-kpi-label">Total de CEPs</div>
                <div class="md-kpi-value">${ceps.length.toLocaleString('pt-BR')}</div>
            </div>
            <div class="md-cep-list">${tagsHtml}</div>
        </div>`;
}

// ---------------------------------------------------------------------------
// Parceiros Ativos por Bucket
// ---------------------------------------------------------------------------

/**
 * Retorna parceiros ativos agrupados por bucket_ade, usando bucket_ade como fonte.
 * Filtra pela delivery_station selecionada (ou todas se 'all').
 * @param {string} selectedStation
 * @returns {{ bucket: string, partners: {name:string, store_id:string, bucket_ade:string}[] }[]}
 */
function _getActivePartnersByBucket(selectedStation) {
    const all = state.allMarkersData || [];
    const active = all.filter(p =>
        p.status === 'Active' &&
        p.bucket_ade &&
        (selectedStation === 'all' || p.delivery_station === selectedStation)
    );

    const grouped = {};
    for (const p of active) {
        const key = p.bucket_ade;
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push({ name: p.name, store_id: p.store_id, bucket_ade: p.bucket_ade });
    }

    return Object.entries(grouped)
        .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
        .map(([bucket, partners]) => ({ bucket, partners }));
}

/**
 * Exporta os dados de parceiros ativos por bucket como arquivo CSV.
 * @param {{ bucket: string, partners: {name:string, store_id:string, bucket_ade:string}[] }[]} groups
 */
function _exportPartnersBucketCSV(groups) {
    const rows = [['name', 'store_id', 'bucket_ade']];
    for (const { partners } of groups) {
        for (const p of partners) {
            rows.push([`"${p.name}"`, p.store_id, p.bucket_ade]);
        }
    }
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'parceiros_ativos_por_bucket.csv';
    a.click();
    URL.revokeObjectURL(url);
}

/**
 * Renderiza a tabela de parceiros ativos por bucket.
 * @param {HTMLElement} container
 * @param {string} selectedStation
 */
function _renderPartnersByBucketTable(container, selectedStation) {
    const groups = _getActivePartnersByBucket(selectedStation);
    const total = groups.reduce((s, g) => s + g.partners.length, 0);

    if (total === 0) {
        container.innerHTML = '';
        return;
    }

    const rows = groups.flatMap(({ partners }) =>
        partners.map(p => `<tr>
            <td>${p.name}</td>
            <td>${p.store_id}</td>
            <td>${p.bucket_ade}</td>
        </tr>`)
    ).join('');

    container.innerHTML = `
        <div class="md-partners-bucket-section">
            <div class="md-section-header">
                <h3>Parceiros Ativos por Bucket (${total})</h3>
                <button class="md-export-btn" id="md-export-bucket-btn">⬇ Exportar CSV</button>
            </div>
            <div class="md-table-wrapper">
                <table class="md-table">
                    <thead>
                        <tr>
                            <th>Nome</th>
                            <th>Store ID</th>
                            <th>Bucket</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;

    document.getElementById('md-export-bucket-btn')?.addEventListener('click', () => {
        _exportPartnersBucketCSV(groups);
    });
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

/**
 * Re-renderiza todos os componentes com os filtros ativos.
 */
export function render() {
    const root = document.getElementById('management-dashboard-root');
    if (!root || !_reportData) return;

    const filteredBases = filterBases(_reportData, _activeFilters);

    // Render filter bar
    let filterContainer = root.querySelector('.md-filter-bar-wrapper');
    if (!filterContainer) {
        filterContainer = document.createElement('div');
        filterContainer.className = 'md-filter-bar-wrapper';
        root.innerHTML = '';
        root.appendChild(filterContainer);
    }
    _renderFilterBar(filterContainer);

    // Render KPI cards
    let kpiContainer = root.querySelector('.md-kpi-container');
    if (!kpiContainer) {
        kpiContainer = document.createElement('div');
        kpiContainer.className = 'md-kpi-container';
        root.appendChild(kpiContainer);
    }
    const kpis = _computeKPIs(filteredBases);
    _renderKPICards(kpiContainer, kpis);

    // Render charts
    let chartsContainer = root.querySelector('.md-charts-container');
    if (!chartsContainer) {
        chartsContainer = document.createElement('div');
        chartsContainer.className = 'md-charts-container';
        root.appendChild(chartsContainer);
    }
    _renderCharts(chartsContainer, filteredBases, _activeFilters.base);

    // Render territory table
    let tableContainer = root.querySelector('.md-territory-table-container');
    if (!tableContainer) {
        tableContainer = document.createElement('div');
        tableContainer.className = 'md-territory-table-container';
        root.appendChild(tableContainer);
    }
    const filteredTerritories = filteredBases.flatMap(b => b.territories.map(t => ({ ...t, baseCode: b.code })));
    _renderTerritoryTable(tableContainer, filteredTerritories);

    // Render CEP listing
    let cepContainer = root.querySelector('.md-cep-listing-container');
    if (!cepContainer) {
        cepContainer = document.createElement('div');
        cepContainer.className = 'md-cep-listing-container';
        root.appendChild(cepContainer);
    }
    _renderCepListing(cepContainer, _activeFilters.territory);

    // Render partners by bucket table
    let bucketContainer = root.querySelector('.md-partners-bucket-container');
    if (!bucketContainer) {
        bucketContainer = document.createElement('div');
        bucketContainer.className = 'md-partners-bucket-container';
        root.appendChild(bucketContainer);
    }
    _renderPartnersByBucketTable(bucketContainer, _activeFilters.base);
}
