/**
 * Property-Based Tests for useGeolocation hook
 *
 * Feature: prospect-ux-redesign, Property 15: Marcador reflete posição atual
 * Validates: Requirements 7.4
 */

import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { useGeolocation } from './useGeolocation';

// ---------------------------------------------------------------------------
// Mock setup
// ---------------------------------------------------------------------------

let watchCallback: ((pos: GeolocationPosition) => void) | null = null;

const mockGeolocation = {
  watchPosition: vi.fn((success: (pos: GeolocationPosition) => void) => {
    watchCallback = success;
    return 1; // watchId
  }),
  clearWatch: vi.fn(),
};

Object.defineProperty(navigator, 'geolocation', {
  value: mockGeolocation,
  writable: true,
});

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function makePosition(lat: number, lon: number): GeolocationPosition {
  return {
    coords: {
      latitude: lat,
      longitude: lon,
      accuracy: 10,
      altitude: null,
      altitudeAccuracy: null,
      heading: null,
      speed: null,
    },
    timestamp: Date.now(),
  } as GeolocationPosition;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useGeolocation', () => {
  beforeEach(() => {
    watchCallback = null;
    mockGeolocation.watchPosition.mockClear();
    mockGeolocation.clearWatch.mockClear();
  });

  /**
   * **Property 15: Marcador reflete posição atual**
   *
   * For any sequence of GPS positions [p1, p2, ..., pn] emitted by the mock
   * watchPosition, the hook must always expose the most recent position pn.
   *
   * Validates: Requirements 7.4
   */
  it('P15 — position always reflects the most recent GPS emission', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.tuple(
            fc.float({ min: -90, max: 90, noNaN: true }),
            fc.float({ min: -180, max: 180, noNaN: true }),
          ),
          { minLength: 1, maxLength: 10 },
        ),
        (coords) => {
          watchCallback = null;

          const { result, unmount } = renderHook(() => useGeolocation());

          // Start tracking so watchPosition is registered
          act(() => {
            result.current.startTracking();
          });

          // Emit each position in sequence and verify the hook reflects the latest
          for (const [lat, lon] of coords) {
            act(() => {
              watchCallback!(makePosition(lat, lon));
            });
          }

          // After all emissions, position must equal the last emitted pair
          const [lastLat, lastLon] = coords[coords.length - 1];
          expect(result.current.position).toEqual([lastLat, lastLon]);

          unmount();
        },
      ),
      { numRuns: 50 },
    );
  });
});
