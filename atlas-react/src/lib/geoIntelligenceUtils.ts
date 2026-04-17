/**
 * geoIntelligenceUtils.ts
 * =======================
 * Utilitários de apresentação para o módulo de Geointeligência.
 */

export type { RegionType } from '../store/geoIntelligenceSlice';
import type { RegionType } from '../store/geoIntelligenceSlice';

// ---------------------------------------------------------------------------
// ESCALA DE CORES (frio → quente)
// ---------------------------------------------------------------------------

/**
 * Converte um `potential_score` em [0, 100] para uma cor hex no gradiente
 * frio (azul) → neutro (amarelo) → quente (vermelho).
 *
 * Implementação via interpolação linear em dois segmentos:
 *   [0, 50]  → azul  (#2166ac) → amarelo (#ffffbf)
 *   [50, 100] → amarelo (#ffffbf) → vermelho (#d73027)
 */
export function potentialScoreToColor(score: number): string {
  // Clamp para garantir que score está em [0, 100]
  const s = Math.max(0, Math.min(100, score));

  // Cores âncora: frio, meio, quente
  const cold = { r: 0x21, g: 0x66, b: 0xac };   // #2166ac
  const mid  = { r: 0xff, g: 0xff, b: 0xbf };   // #ffffbf
  const hot  = { r: 0xd7, g: 0x30, b: 0x27 };   // #d73027

  let r: number, g: number, b: number;

  if (s <= 50) {
    const t = s / 50;
    r = Math.round(cold.r + t * (mid.r - cold.r));
    g = Math.round(cold.g + t * (mid.g - cold.g));
    b = Math.round(cold.b + t * (mid.b - cold.b));
  } else {
    const t = (s - 50) / 50;
    r = Math.round(mid.r + t * (hot.r - mid.r));
    g = Math.round(mid.g + t * (hot.g - mid.g));
    b = Math.round(mid.b + t * (hot.b - mid.b));
  }

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function toHex(n: number): string {
  return Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
}

// ---------------------------------------------------------------------------
// LABELS EM PORTUGUÊS
// ---------------------------------------------------------------------------

const REGION_TYPE_LABELS: Record<RegionType, string> = {
  favela_comunidade:        'Favela / Comunidade',
  residencial_baixa_renda:  'Residencial Baixa Renda',
  residencial_media_renda:  'Residencial Média Renda',
  residencial_alta_renda:   'Residencial Alta Renda',
  comercial:                'Comercial',
  industrial:               'Industrial',
  rural:                    'Rural',
  alto_padrao:              'Alto Padrão',
};

/**
 * Retorna o label em português para um `RegionType`.
 */
export function regionTypeLabel(type: RegionType): string {
  return REGION_TYPE_LABELS[type] ?? type;
}

// ---------------------------------------------------------------------------
// FORMATAÇÃO DE GAP
// ---------------------------------------------------------------------------

/**
 * Formata um valor de `gap` com sinal explícito e uma casa decimal.
 * Exemplos: `+12.5`, `-3.2`, `+0.0`
 */
export function formatGap(gap: number): string {
  const fixed = Math.abs(gap).toFixed(1);
  return gap >= 0 ? `+${fixed}` : `-${fixed}`;
}
