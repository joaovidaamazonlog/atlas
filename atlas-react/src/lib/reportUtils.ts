/**
 * reportUtils.ts
 * ==============
 * Pure functions ported from management-dashboard.js.
 * No side effects, no DOM access, no fetch — only data transformations.
 */

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface TerritoryData {
  id: string;
  ctl: string;
  dailyDemand: number;
  totalSlots: number;
  openSlots: number;
  active: number;
  onboarding: number;
  bg: number;
  prospects: number;
  inactive: number;
  attainment: number;   // decimal 0-1
  accuracy: number;     // decimal 0-1
}

export interface BaseData {
  code: string;
  bdm: string;
  numTerritories: number;
  dailyDemand: number;
  idealSlots: number;
  matchedSlots: number;
  openSlots: number;
  coverage: number;     // decimal 0-1
  partners: {
    active: number;
    onboarding: number;
    bgChecks: number;
    prospects: number;
    inactive: number;
  };
  attainment: number;   // decimal 0-1
  territories: TerritoryData[];
}

export interface ReportData {
  generatedAt: string | null;
  bases: BaseData[];
}

export interface DashboardFilters {
  bdm: string;
  base: string;
  ctl: string;
  territory: string;
}

export interface KPISummary {
  totalBases: number;
  totalTerritories: number;
  totalDailyDemand: number;
  totalIdealSlots: number;
  totalOpenSlots: number;
  totalActivePartners: number;
  avgAttainment: number;
  avgCoverage: number;
}

export interface TerritoryRow extends TerritoryData {
  baseCode: string;
}

export interface ChartData {
  attainmentByBase: { labels: string[]; data: number[] };
  partnersByBase: {
    labels: string[];
    datasets: Array<{ label: string; data: number[]; backgroundColor: string }>;
  };
  attainmentByTerritory: { labels: string[]; data: number[] } | null;
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/**
 * Converts a percentage string (e.g. "3.8%") to decimal (0.038).
 * Falls back to 0. Never throws.
 */
function _pct(str: string): number {
  return (parseFloat((str || '').replace(',', '.')) || 0) / 100;
}

/**
 * Converts a numeric string (e.g. "18,396.0") to number.
 * Removes thousand separators before parsing. Falls back to 0. Never throws.
 */
function _num(str: string): number {
  return parseFloat((str || '').replace(/,/g, '')) || 0;
}

// ---------------------------------------------------------------------------
// parse
// ---------------------------------------------------------------------------

/**
 * Parses the content of RELATORIO_EXECUTIVO.txt and returns a ReportData object.
 * Pure function — no fetch, receives string and returns object.
 * Never throws; returns { generatedAt: null, bases: [] } for invalid input.
 */
export function parse(text: string): ReportData {
  if (!text || typeof text !== 'string') {
    return { generatedAt: null, bases: [] };
  }

  const headerMatch = text.match(/Gerado em:\s*(.+)/);
  const generatedAt = headerMatch ? headerMatch[1].trim() : null;

  const bases: BaseData[] = [];

  const basePattern = /BASE:\s*(\S+)\s*\|\s*BDM:\s*(.+?)\n([\s\S]*?)(?=\nBASE:\s|\s*$)/g;
  let baseMatch: RegExpExecArray | null;

  while ((baseMatch = basePattern.exec(text)) !== null) {
    const code = baseMatch[1].trim();
    const bdm = baseMatch[2].trim();
    const baseBody = baseMatch[3];

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

    const territories: TerritoryData[] = [];
    const terrPattern = /(\S+_bucket-\d+)\s*\(([^)]+)\)\s*\n([\s\S]*?)(?=\n\s+\S+_bucket-|\n\nBASE:|\n================|$)/g;
    let terrMatch: RegExpExecArray | null;

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
        ctl,
        dailyDemand: _num(tDemandMatch ? tDemandMatch[1] : '0'),
        totalSlots: tSlotsMatch ? _num(tSlotsMatch[1]) : 0,
        openSlots: tSlotsMatch ? _num(tSlotsMatch[2]) : 0,
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

// ---------------------------------------------------------------------------
// serialize
// ---------------------------------------------------------------------------

/**
 * Serializes a ReportData object back to the report text format.
 * Required for round-trip testing (Property 1).
 */
export function serialize(data: ReportData): string {
  if (!data || !Array.isArray(data.bases)) {
    return '';
  }

  const lines: string[] = [];
  lines.push('RELATORIO EXECUTIVO DE OTIMIZACAO');
  lines.push(`Gerado em: ${data.generatedAt || ''}`);
  lines.push('='.repeat(80));

  for (const base of data.bases) {
    lines.push('');
    lines.push(`BASE: ${base.code} | BDM: ${base.bdm}`);
    lines.push('-'.repeat(80));

    const coveragePct = ((base.coverage || 0) * 100).toFixed(1);
    const attainmentPct = ((base.attainment || 0) * 100).toFixed(1);
    const p = base.partners || { active: 0, onboarding: 0, bgChecks: 0, prospects: 0, inactive: 0 };

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
// filterBases
// ---------------------------------------------------------------------------

/**
 * Returns filtered bases according to active filters.
 * Pure exported function — required for property tests (Property 2).
 */
export function filterBases(reportData: ReportData | null, filters: DashboardFilters): BaseData[] {
  if (!reportData || !Array.isArray(reportData.bases)) return [];

  let bases = reportData.bases;

  if (filters.bdm && filters.bdm !== 'all') {
    bases = bases.filter(b => b.bdm === filters.bdm);
  }

  if (filters.base && filters.base !== 'all') {
    bases = bases.filter(b => b.code === filters.base);
  }

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

  if ((filters.ctl && filters.ctl !== 'all') || (filters.territory && filters.territory !== 'all')) {
    bases = bases.filter(b => b.territories.length > 0);
  }

  return bases;
}

// ---------------------------------------------------------------------------
// computeKPIs
// ---------------------------------------------------------------------------

/**
 * Computes KPIs from filtered bases.
 * Pure exported function — required for property tests (Property 3).
 * Returns zeroed KPIs for empty array without division by zero.
 */
export function computeKPIs(filteredBases: BaseData[]): KPISummary {
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

// ---------------------------------------------------------------------------
// sortTerritories
// ---------------------------------------------------------------------------

/**
 * Sorts a territory array by a column and direction.
 * Pure exported function — does not mutate the original array.
 */
export function sortTerritories(
  territories: TerritoryRow[],
  column: string,
  direction: 'asc' | 'desc',
): TerritoryRow[] {
  if (!territories || !column) return territories ? [...territories] : [];
  return [...territories].sort((a, b) => {
    const va = (a as unknown as Record<string, unknown>)[column];
    const vb = (b as unknown as Record<string, unknown>)[column];
    let cmp: number;
    if (typeof va === 'string' && typeof vb === 'string') {
      cmp = va.localeCompare(vb);
    } else {
      cmp = ((va as number) ?? 0) - ((vb as number) ?? 0);
    }
    return direction === 'desc' ? -cmp : cmp;
  });
}

// ---------------------------------------------------------------------------
// getStatusClass
// ---------------------------------------------------------------------------

/**
 * Returns the CSS status class based on thresholds.
 * Pure exported function — required for property tests (Properties 4 and 5).
 *
 * @param value - decimal value (0-1)
 * @param thresholds - green is the upper threshold
 */
export function getStatusClass(
  value: number,
  thresholds: { green: number; yellow: number },
): 'status-green' | 'status-yellow' | 'status-red' {
  if (value >= thresholds.green) return 'status-green';
  if (value >= thresholds.yellow) return 'status-yellow';
  return 'status-red';
}

// ---------------------------------------------------------------------------
// getChartDataForBase
// ---------------------------------------------------------------------------

/**
 * Computes chart data from filtered bases and the selected base.
 * Pure exported function — required for property tests (Property 8).
 */
export function getChartDataForBase(filteredBases: BaseData[], selectedBase: string): ChartData {
  // Chart 1: attainment by Base, sorted descending
  const sortedByAttainment = [...filteredBases].sort((a, b) => b.attainment - a.attainment);
  const attainmentByBase = {
    labels: sortedByAttainment.map(b => b.code),
    data: sortedByAttainment.map(b => parseFloat((b.attainment * 100).toFixed(1))),
  };

  // Chart 2: partner composition by Base
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

  // Chart 3: attainment by Territory (only when a specific base is selected)
  let attainmentByTerritory: { labels: string[]; data: number[] } | null = null;
  if (selectedBase && selectedBase !== 'all') {
    const base = filteredBases.find(b => b.code === selectedBase);
    if (base && base.territories && base.territories.length > 0) {
      attainmentByTerritory = {
        labels: base.territories.map(t => t.id),
        data: base.territories.map(t => parseFloat((t.attainment * 100).toFixed(1))),
      };
    }
  }

  return { attainmentByBase, partnersByBase, attainmentByTerritory };
}
