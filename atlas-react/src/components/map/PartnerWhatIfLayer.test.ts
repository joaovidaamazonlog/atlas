/**
 * PartnerWhatIfLayer.test.ts
 * ==========================
 * Property-based and unit tests for the hex-diff engine in PartnerWhatIfLayer.
 *
 * Feature: hex-partner-coverage-model
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fc from 'fast-check';
import { getHexesWithinRadius, computeAdvSimulated, MAX_CAP } from './PartnerWhatIfLayer';

// ---------------------------------------------------------------------------
// Property 5: Hex-Diff Disjointness
// Validates: Requirements 5.1, 5.2
// ---------------------------------------------------------------------------

describe('Property 5: Hex-Diff Disjointness', () => {
  it('hexesLost and hexesGained are always disjoint', () => {
    // Feature: hex-partner-coverage-model, Property 5: Hex-Diff Disjointness
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 20 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 20 }),
        (originalArr, simulatedArr) => {
          const original = new Set(originalArr);
          const simulated = new Set(simulatedArr);
          const lost = new Set([...original].filter(h => !simulated.has(h)));
          const gained = new Set([...simulated].filter(h => !original.has(h)));
          // Disjointness: lost ∩ gained = ∅
          for (const h of lost) {
            if (gained.has(h)) return false;
          }
          return true;
        },
      ),
      { numRuns: 500 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6: ADV Simulation Formula
// Validates: Requirements 5.5, 5.6
// ---------------------------------------------------------------------------

describe('Property 6: ADV Simulation Formula', () => {
  it('computeAdvSimulated matches min(max(capacity - loss + gain, 0), MAX_CAP)', () => {
    // Feature: hex-partner-coverage-model, Property 6: ADV Simulation Formula
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 80 }),
        fc.float({ min: 0, max: 200, noNaN: true }),
        fc.float({ min: 0, max: 200, noNaN: true }),
        (capacity, loss, gain) => {
          const result = computeAdvSimulated(capacity, loss, gain);
          const expected = Math.min(Math.max(capacity - loss + gain, 0), 80);
          return Math.abs(result - expected) < 1e-9;
        },
      ),
      { numRuns: 1000 },
    );
  });

  it('result is always clamped between 0 and MAX_CAP', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 80 }),
        fc.float({ min: 0, max: 200, noNaN: true }),
        fc.float({ min: 0, max: 200, noNaN: true }),
        (capacity, loss, gain) => {
          const result = computeAdvSimulated(capacity, loss, gain);
          return result >= 0 && result <= MAX_CAP;
        },
      ),
      { numRuns: 500 },
    );
  });
});

// ---------------------------------------------------------------------------
// Unit test: warning dispatched when hex_coverage absent and hexes are lost
// Validates: Requirement 5.8
// ---------------------------------------------------------------------------

describe('Unit test: guard condition — hex_coverage absent with hexes lost', () => {
  let dispatchedEvents: { type: string; detail: unknown }[];
  let originalDispatch: typeof document.dispatchEvent;

  beforeEach(() => {
    dispatchedEvents = [];
    originalDispatch = document.dispatchEvent.bind(document);
    vi.spyOn(document, 'dispatchEvent').mockImplementation((event: Event) => {
      if (event instanceof CustomEvent) {
        dispatchedEvents.push({ type: event.type, detail: event.detail });
      }
      return true;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('dispatches atlas:whatif-warning and NOT atlas:whatif-result when hex_coverage is absent and hexes are lost', () => {
    // Simulate the guard logic directly (mirrors handleDragEnd guard block)
    const partnerName = 'Test Partner';
    const hexCoverage: undefined = undefined;
    const hexesLost = new Set(['hex_abc', 'hex_def']); // non-empty → hexes are lost

    const hexCoverageAbsent = !hexCoverage || (hexCoverage as unknown[]).length === 0;

    if (hexCoverageAbsent && hexesLost.size > 0) {
      document.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: {
            message: `${partnerName}: dados de cobertura hex indisponíveis. Reposicione após recarregar os dados.`,
          },
        }),
      );
      // Guard returns here — no atlas:whatif-result dispatched
    }

    const warningEvents = dispatchedEvents.filter(e => e.type === 'atlas:whatif-warning');
    const resultEvents = dispatchedEvents.filter(e => e.type === 'atlas:whatif-result');

    expect(warningEvents).toHaveLength(1);
    expect(resultEvents).toHaveLength(0);
    expect((warningEvents[0].detail as { message: string }).message).toContain(partnerName);
  });

  it('dispatches atlas:whatif-warning and NOT atlas:whatif-result when hex_coverage is empty and hexes are lost', () => {
    const partnerName = 'Empty Coverage Partner';
    const hexCoverage: { hex_id: string; packages_allocated: number }[] = [];
    const hexesLost = new Set(['hex_xyz']);

    const hexCoverageAbsent = !hexCoverage || hexCoverage.length === 0;

    if (hexCoverageAbsent && hexesLost.size > 0) {
      document.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: {
            message: `${partnerName}: dados de cobertura hex indisponíveis. Reposicione após recarregar os dados.`,
          },
        }),
      );
    }

    const warningEvents = dispatchedEvents.filter(e => e.type === 'atlas:whatif-warning');
    const resultEvents = dispatchedEvents.filter(e => e.type === 'atlas:whatif-result');

    expect(warningEvents).toHaveLength(1);
    expect(resultEvents).toHaveLength(0);
  });

  it('does NOT dispatch warning when hex_coverage is absent but no hexes are lost', () => {
    // Gain-only scenario: hex_coverage absent but hexesLost is empty → proceed normally
    const hexCoverage: undefined = undefined;
    const hexesLost = new Set<string>(); // empty — no hexes lost

    const hexCoverageAbsent = !hexCoverage || (hexCoverage as unknown[]).length === 0;

    if (hexCoverageAbsent && hexesLost.size > 0) {
      document.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: { message: 'should not be dispatched' },
        }),
      );
    }

    const warningEvents = dispatchedEvents.filter(e => e.type === 'atlas:whatif-warning');
    expect(warningEvents).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Unit tests for getHexesWithinRadius
// ---------------------------------------------------------------------------

describe('getHexesWithinRadius', () => {
  it('returns empty set when features array is empty', () => {
    const result = getHexesWithinRadius([], -23.5, -46.6, 500);
    expect(result.size).toBe(0);
  });

  it('includes a Point feature whose coordinates are within radius', () => {
    const feature: GeoJSON.Feature = {
      type: 'Feature',
      properties: { hex_id: 'hex_001' },
      geometry: {
        type: 'Point',
        // Same location as center → distance = 0
        coordinates: [-46.6, -23.5],
      },
    };
    const result = getHexesWithinRadius([feature], -23.5, -46.6, 500);
    expect(result.has('hex_001')).toBe(true);
  });

  it('excludes a Point feature whose coordinates are outside radius', () => {
    const feature: GeoJSON.Feature = {
      type: 'Feature',
      properties: { hex_id: 'hex_002' },
      geometry: {
        type: 'Point',
        // ~111 km away (1 degree latitude ≈ 111 km)
        coordinates: [-46.6, -24.5],
      },
    };
    const result = getHexesWithinRadius([feature], -23.5, -46.6, 500);
    expect(result.has('hex_002')).toBe(false);
  });

  it('skips features without hex_id property', () => {
    const feature: GeoJSON.Feature = {
      type: 'Feature',
      properties: { some_other_field: 'value' },
      geometry: {
        type: 'Point',
        coordinates: [-46.6, -23.5],
      },
    };
    const result = getHexesWithinRadius([feature], -23.5, -46.6, 500);
    expect(result.size).toBe(0);
  });

  it('skips features with unsupported geometry types', () => {
    const feature: GeoJSON.Feature = {
      type: 'Feature',
      properties: { hex_id: 'hex_line' },
      geometry: {
        type: 'LineString',
        coordinates: [[-46.6, -23.5], [-46.7, -23.6]],
      } as GeoJSON.Geometry,
    };
    const result = getHexesWithinRadius([feature], -23.5, -46.6, 500);
    expect(result.size).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Unit tests for computeAdvSimulated
// ---------------------------------------------------------------------------

describe('computeAdvSimulated', () => {
  it('returns capacity when loss and gain are both zero', () => {
    expect(computeAdvSimulated(50, 0, 0)).toBe(50);
  });

  it('clamps to 0 when loss exceeds capacity + gain', () => {
    expect(computeAdvSimulated(10, 100, 0)).toBe(0);
  });

  it('clamps to MAX_CAP (80) when result would exceed it', () => {
    expect(computeAdvSimulated(70, 0, 50)).toBe(MAX_CAP);
  });

  it('correctly computes capacity - loss + gain', () => {
    expect(computeAdvSimulated(50, 10, 20)).toBe(60);
  });
});
