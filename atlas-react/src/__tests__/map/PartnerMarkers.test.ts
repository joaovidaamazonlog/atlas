/**
 * PartnerMarkers.test.ts
 * ======================
 * Teste de regressão da Task 7: a `key` usada em cada `<CircleMarker>`
 * deve ser APENAS `partner.salesforce_id`, sem concatenação com
 * `i18n.language`. Isso garante que a troca de idioma atualiza o
 * conteúdo do popup (via re-render) sem desmontar/recriar os markers.
 *
 * Validação via análise estática do código-fonte: inspecionamos o
 * arquivo `PartnerMarkers.tsx` e confirmamos que não há padrões
 * `${partner.salesforce_id}-${i18n.language}` ou equivalentes.
 *
 * Essa abordagem evita depender de jsdom + Leaflet (que exigiria
 * mocks extensos) e testa exatamente o que queremos: a invariante
 * estrutural do key estável.
 *
 * Referências: Requirements 5.1, 5.2, 5.3, 6.5
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SOURCE_PATH = resolve(
  __dirname,
  '../../components/map/PartnerMarkers.tsx',
);

describe('PartnerMarkers — key estável (Stable_Marker_Key)', () => {
  const src = readFileSync(SOURCE_PATH, 'utf-8');

  it('não concatena i18n.language na key do Fragment', () => {
    // Padrões de regressão que queremos evitar:
    const badPatterns = [
      /\$\{partner\.salesforce_id\}-\$\{i18n\.language\}/,
      /key=\{`[^`]*\$\{i18n\.language\}[^`]*`\}/,
      /key=\{[^}]*i18n\.language[^}]*\}/,
    ];
    for (const pattern of badPatterns) {
      expect(src).not.toMatch(pattern);
    }
  });

  it('usa partner.salesforce_id como key do Fragment', () => {
    expect(src).toMatch(/key=\{partner\.salesforce_id\}/);
  });

  it('ainda chama useTranslation() para disparar re-render na troca de idioma', () => {
    // Necessário para que getPartnerPopupHtml seja recomputado
    expect(src).toMatch(/useTranslation\(\)/);
  });

  it('popupHtml é recomputado em cada render (sem memoização por idioma)', () => {
    // A regeneração do popup depende do re-render disparado por useTranslation,
    // não de um useMemo com i18n.language nas deps.
    expect(src).not.toMatch(/useMemo\(\s*\([^)]*\)\s*=>\s*getPartnerPopupHtml[^}]*i18n\.language/);
  });

  it('markerRefs usa apenas salesforce_id (não composto com idioma)', () => {
    // Invariante: o ref de cada marker é indexado por um ID estável, para
    // que listeners externos (OpenPartnerPopupListener) funcionem após
    // trocas de idioma.
    expect(src).toMatch(/markerRefs\.current\.set\(partner\.salesforce_id/);
    expect(src).toMatch(/markerRefs\.current\.delete\(partner\.salesforce_id/);
  });
});
