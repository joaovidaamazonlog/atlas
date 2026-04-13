/**
 * colorUtils.ts
 * =============
 * Utilitários de cor para marcadores do mapa.
 * Migrado de frontend/js/modules/map-manager.js para TypeScript.
 */

import { COLOR_PALETTES } from './config';
import type { Partner, StyleConfig } from '../store/types';

// ---------------------------------------------------------------------------
// TIPOS
// ---------------------------------------------------------------------------

export type ColorMap = Record<string, string>;

export interface MarkerStyle {
  fillColor: string;
  color: string;
  weight: number;
  fillOpacity: number;
}

// ---------------------------------------------------------------------------
// FUNÇÕES PÚBLICAS
// ---------------------------------------------------------------------------

/**
 * Gera um mapa {valor → cor} para um campo dos dados.
 * Migrado de `generateColorMap` em map-manager.js.
 *
 * @param data     - Array de parceiros
 * @param field    - Campo do Partner a usar como chave
 * @param isBorder - Se true, usa paleta de borda; caso contrário, paleta de preenchimento
 */
export function generateColorMap(
  data: Partner[],
  field: keyof Partner,
  isBorder = false,
): ColorMap {
  const palette = isBorder ? COLOR_PALETTES.border : COLOR_PALETTES.fill;
  const uniqueKeys = [
    ...new Set(data.map((item) => String(item[field] ?? 'N/A'))),
  ].sort();
  const colorMap: ColorMap = {};
  uniqueKeys.forEach((val, idx) => {
    colorMap[val] = palette[idx % palette.length];
  });
  return colorMap;
}

/**
 * Retorna o estilo de um circleMarker para um parceiro específico.
 *
 * @param partner       - Parceiro a estilizar
 * @param primaryField  - Campo para cor de borda
 * @param secondaryField - Campo para cor de preenchimento (se diferente do primário)
 * @param colorMaps     - Objeto com os mapas de cor pré-calculados
 */
export function getMarkerStyle(
  partner: Partner,
  primaryField: keyof Partner,
  secondaryField: keyof Partner,
  colorMaps: { border: ColorMap; fill: ColorMap },
): MarkerStyle {
  const borderKey = String(partner[primaryField] ?? 'N/A');
  const borderColor = colorMaps.border[borderKey] ?? COLOR_PALETTES.border[0];

  let fillColor = '#fff';
  if (secondaryField !== primaryField) {
    const fillKey = String(partner[secondaryField] ?? 'N/A');
    fillColor = colorMaps.fill[fillKey] ?? '#808080';
  }

  return {
    fillColor,
    color: borderColor,
    weight: 3,
    fillOpacity: 0.9,
  };
}

/**
 * Gera os dois mapas de cor (borda e preenchimento) a partir de uma StyleConfig.
 *
 * @param data        - Array de parceiros
 * @param styleConfig - Configuração de estilização
 */
export function buildColorMaps(
  data: Partner[],
  styleConfig: Pick<StyleConfig, 'primaryField' | 'secondaryField'>,
): { border: ColorMap; fill: ColorMap } {
  const primary = styleConfig.primaryField as keyof Partner;
  const secondary = styleConfig.secondaryField as keyof Partner;

  const border = generateColorMap(data, primary, true);
  const fill =
    secondary !== primary ? generateColorMap(data, secondary, false) : {};

  return { border, fill };
}
