/**
 * deliveriesSlice.ts
 * ==================
 * Helpers e state defaults para a feature de análise de canal
 * (IHS vs DSP) — artefatos gerados pela Fase 6 do pipeline backend.
 *
 * Por que as actions não ficam aqui
 * ---------------------------------
 * O store principal (`store/index.ts`) usa `create(set, get)` com todas as
 * actions inline — sem `StateCreator` composto. Manter a consistência
 * com os outros slices (filters, prospect, etc.) facilita leitura e
 * evita que este slice seja o único "diferente".
 *
 * Este arquivo concentra o que pode ser reutilizado:
 *  - Tipos do state.
 *  - Default initial state.
 *  - Fetchers puros usados pelas actions do store.
 *  - Utilitário de descompactação de jsonl.gz com fallback.
 *
 * Estratégia de carregamento
 * --------------------------
 * - `summary` (deliveries_summary.json): eager-load. Pequeno (~0.5–2 MB),
 *   alimenta KPIs, tabela de parceiros e aba Insights.
 *
 * - `byHex` (deliveries_by_hex.json): lazy. Médio (3–15 MB). Só é baixado
 *   quando o usuário abre a aba de Análise Manual ou ativa o layer de
 *   share DSP.
 *
 * - `detailByDs` (detalhes .jsonl.gz por DS): lazy por DS. Chamado quando
 *   o usuário expande o drill-down de um parceiro. Cacheado por `ds_code`.
 */

import { DATA_URLS } from '../lib/config';
import type {
  DeliverySummary,
  DeliveriesByHex,
  PackageDelivery,
} from './types';

// ---------------------------------------------------------------------------
// STATE
// ---------------------------------------------------------------------------

export interface DeliveriesState {
  summary: DeliverySummary | null;
  byHex: DeliveriesByHex | null;
  detailByDs: Record<string, PackageDelivery[]>;
  isLoadingSummary: boolean;
  isLoadingByHex: boolean;
  loadingDetailDs: string | null;
  errorSummary: string | null;
  errorByHex: string | null;
  errorDetail: string | null;
}

export const DEFAULT_DELIVERIES_STATE: DeliveriesState = {
  summary: null,
  byHex: null,
  detailByDs: {},
  isLoadingSummary: false,
  isLoadingByHex: false,
  loadingDetailDs: null,
  errorSummary: null,
  errorByHex: null,
  errorDetail: null,
};

// ---------------------------------------------------------------------------
// FETCHERS
// ---------------------------------------------------------------------------

export async function fetchDeliveriesSummary(): Promise<DeliverySummary> {
  const res = await fetch(DATA_URLS.deliveriesSummary);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as DeliverySummary;
}

export async function fetchDeliveriesByHex(): Promise<DeliveriesByHex> {
  const res = await fetch(DATA_URLS.deliveriesByHex);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as DeliveriesByHex;
}

/**
 * Lê um `.jsonl.gz` por DS. Se o servidor configura `Content-Encoding: gzip`,
 * o browser já descomprime; caso contrário, tenta `DecompressionStream`
 * (Chromium/Firefox/Safari modernos). Se ambos falharem, devolve o texto
 * cru assumindo que o servidor está enviando sem compressão real.
 */
export async function fetchDeliveryDetailForDS(
  dsCode: string,
): Promise<PackageDelivery[]> {
  const url = `${DATA_URLS.deliveriesDetailBase}/${encodeURIComponent(dsCode)}.jsonl.gz`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  let text: string;
  const contentEncoding = res.headers.get('content-encoding');

  if (contentEncoding?.includes('gzip')) {
    // Browser já descomprimiu.
    text = await res.text();
  } else if (typeof (window as unknown as { DecompressionStream?: unknown }).DecompressionStream !== 'undefined') {
    try {
      const DS = (window as unknown as {
        DecompressionStream: new (format: string) => ReadableWritablePair<Uint8Array, Uint8Array>;
      }).DecompressionStream;
      const stream = (res.body as ReadableStream<Uint8Array>).pipeThrough(
        new DS('gzip'),
      );
      text = await new Response(stream).text();
    } catch {
      text = await res.text();
    }
  } else {
    text = await res.text();
  }

  const lines = text.split('\n').filter((l) => l.trim().length > 0);
  return lines.map((l) => JSON.parse(l) as PackageDelivery);
}
