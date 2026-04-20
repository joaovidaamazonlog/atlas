/**
 * store.property.test.ts
 * ======================
 * Property-based tests for the Zustand store slices.
 *
 * Feature: partner-cap-optimization
 */

import { describe, it, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { useStore } from './index';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Pure toggle logic — mirrors the store's toggleHexSelection reducer */
function applyToggleSequence(
  hexes: Array<{ hexId: string; demandDaily: number; demandResidual: number }>,
): { selectedHexIds: string[]; totalDemandDaily: number; totalDemandResidual: number } {
  let selectedHexIds: string[] = [];
  let totalDemandDaily = 0;
  let totalDemandResidual = 0;

  for (const { hexId, demandDaily, demandResidual } of hexes) {
    const isSelected = selectedHexIds.includes(hexId);
    if (isSelected) {
      selectedHexIds = selectedHexIds.filter((id) => id !== hexId);
      totalDemandDaily -= demandDaily;
      totalDemandResidual -= demandResidual;
    } else {
      selectedHexIds = [...selectedHexIds, hexId];
      totalDemandDaily += demandDaily;
      totalDemandResidual += demandResidual;
    }
  }

  return { selectedHexIds, totalDemandDaily, totalDemandResidual };
}

// ---------------------------------------------------------------------------
// Reset store before each test
// ---------------------------------------------------------------------------

beforeEach(() => {
  useStore.setState({
    hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 },
  });
});

// ---------------------------------------------------------------------------
// Property 10: Hex selection accumulation
// // Feature: partner-cap-optimization, Property 10: Hex selection accumulation
// Validates: Requirements 9.2
// ---------------------------------------------------------------------------

describe('Property 10: Hex selection accumulation', () => {
  it(
    'totalDemandDaily and totalDemandResidual equal sums of selected hexes after any click sequence',
    () => {
      const hexClickArb = fc.array(
        fc.record({
          hexId: fc.string(),
          demandDaily: fc.float({ min: 0, max: 100, noNaN: true }),
          demandResidual: fc.float({ min: 0, max: 100, noNaN: true }),
        }),
      );

      fc.assert(
        fc.property(hexClickArb, (hexClicks) => {
          // Reset store state for each run
          useStore.setState({
            hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 },
          });

          // Apply toggles via the actual store action
          for (const { hexId, demandDaily, demandResidual } of hexClicks) {
            useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);
          }

          const { selectedHexIds, totalDemandDaily, totalDemandResidual } =
            useStore.getState().hexSelectionState;

          // Compute expected sums: for each currently-selected hex, find the LAST
          // occurrence in the click sequence (the one that added it) and sum its values.
          // We use the pure helper to derive the ground truth.
          const expected = applyToggleSequence(hexClicks);

          // Verify selected hex IDs match
          const sameIds =
            selectedHexIds.length === expected.selectedHexIds.length &&
            expected.selectedHexIds.every((id) => selectedHexIds.includes(id));

          // Verify accumulated totals match (allow tiny floating-point epsilon)
          const epsilon = 1e-4;
          const dailyOk = Math.abs(totalDemandDaily - expected.totalDemandDaily) < epsilon;
          const residualOk =
            Math.abs(totalDemandResidual - expected.totalDemandResidual) < epsilon;

          return sameIds && dailyOk && residualOk;
        }),
        { numRuns: 100 },
      );
    },
  );

  it('totalDemandDaily equals sum of demandDaily for all currently-selected hexes', () => {
    const hexClickArb = fc.array(
      fc.record({
        hexId: fc.string(),
        demandDaily: fc.float({ min: 0, max: 100, noNaN: true }),
        demandResidual: fc.float({ min: 0, max: 100, noNaN: true }),
      }),
    );

    fc.assert(
      fc.property(hexClickArb, (hexClicks) => {
        useStore.setState({
          hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 },
        });

        for (const { hexId, demandDaily, demandResidual } of hexClicks) {
          useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);
        }

        const { totalDemandDaily } = useStore.getState().hexSelectionState;

        // Use the pure helper as ground truth for expected totalDemandDaily
        const expected = applyToggleSequence(hexClicks);

        return Math.abs(totalDemandDaily - expected.totalDemandDaily) < 1e-4;
      }),
      { numRuns: 100 },
    );
  });

  it('totalDemandResidual equals sum of demandResidual for all currently-selected hexes', () => {
    const hexClickArb = fc.array(
      fc.record({
        hexId: fc.string(),
        demandDaily: fc.float({ min: 0, max: 100, noNaN: true }),
        demandResidual: fc.float({ min: 0, max: 100, noNaN: true }),
      }),
    );

    fc.assert(
      fc.property(hexClickArb, (hexClicks) => {
        useStore.setState({
          hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 },
        });

        for (const { hexId, demandDaily, demandResidual } of hexClicks) {
          useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);
        }

        const { totalDemandResidual } = useStore.getState().hexSelectionState;

        // Use the pure helper as ground truth for expected totalDemandResidual
        const expected = applyToggleSequence(hexClicks);

        return Math.abs(totalDemandResidual - expected.totalDemandResidual) < 1e-4;
      }),
      { numRuns: 100 },
    );
  });

  it('duplicate hexId in sequence toggles off (second click removes the hex)', () => {
    fc.assert(
      fc.property(
        fc.record({
          hexId: fc.string(),
          demandDaily: fc.float({ min: 0, max: 100, noNaN: true }),
          demandResidual: fc.float({ min: 0, max: 100, noNaN: true }),
        }),
        ({ hexId, demandDaily, demandResidual }) => {
          useStore.setState({
            hexSelectionState: {
              selectedHexIds: [],
              totalDemandDaily: 0,
              totalDemandResidual: 0,
            },
          });

          // Click once — should be selected
          useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);
          const afterFirst = useStore.getState().hexSelectionState;

          // Click again — should be deselected
          useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);
          const afterSecond = useStore.getState().hexSelectionState;

          return (
            afterFirst.selectedHexIds.includes(hexId) &&
            !afterSecond.selectedHexIds.includes(hexId) &&
            Math.abs(afterSecond.totalDemandDaily) < 1e-4 &&
            Math.abs(afterSecond.totalDemandResidual) < 1e-4
          );
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 11: Hex selection toggle idempotence
// Feature: partner-cap-optimization, Property 11: Hex selection toggle idempotence
// Validates: Requirements 9.4
// ---------------------------------------------------------------------------

describe('Property 11: Hex selection toggle idempotence', () => {
  it(
    'toggling a selected hex removes it and reduces sums by exactly that hex\'s values',
    () => {
      const hexArb = fc.record({
        hexId: fc.string(),
        demandDaily: fc.float({ min: 0, max: 1000, noNaN: true }),
        demandResidual: fc.float({ min: 0, max: 1000, noNaN: true }),
      });

      const uniqueHexesArb = fc
        .array(hexArb, { minLength: 1 })
        .filter((hexes) => {
          const ids = hexes.map((h) => h.hexId);
          return new Set(ids).size === ids.length;
        });

      fc.assert(
        fc.property(uniqueHexesArb, (hexes) => {
          // Reset store for each run
          useStore.setState({
            hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 },
          });

          // Step 1: add all hexes to the selection (click each once)
          for (const { hexId, demandDaily, demandResidual } of hexes) {
            useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);
          }

          // Step 2: for each hex, toggle it off and verify the invariants
          for (const { hexId, demandDaily, demandResidual } of hexes) {
            const before = useStore.getState().hexSelectionState;

            // Hex must be selected before we toggle it off
            if (!before.selectedHexIds.includes(hexId)) return false;

            useStore.getState().toggleHexSelection(hexId, demandDaily, demandResidual);

            const after = useStore.getState().hexSelectionState;

            // Hex must be removed from selectedHexIds
            if (after.selectedHexIds.includes(hexId)) return false;

            // totalDemandDaily must decrease by exactly demandDaily
            const epsilon = 1e-4;
            if (Math.abs(after.totalDemandDaily - (before.totalDemandDaily - demandDaily)) > epsilon) return false;

            // totalDemandResidual must decrease by exactly demandResidual
            if (Math.abs(after.totalDemandResidual - (before.totalDemandResidual - demandResidual)) > epsilon) return false;
          }

          return true;
        }),
        { numRuns: 100 },
      );
    },
  );
});
