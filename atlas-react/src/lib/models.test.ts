/**
 * models.test.ts
 * ==============
 * Unit tests for the Partner model, focusing on the `adv_opportunity` field mapping.
 *
 * **Validates: Requirements 4.3, 4.4**
 */

import { describe, it, expect } from 'vitest';
import { Partner } from './models';
import type { AdvOpportunity } from '../store/types';

const validAdvOpportunity: AdvOpportunity = {
  suggested_lat: -23.5505,
  suggested_lon: -46.6333,
  suggested_cap: 72,
  suggested_radius: 1200,
  estimated_adv_gain: 30,
  distance_from_current: 187.4,
};

describe('Partner — adv_opportunity field mapping', () => {
  it('maps adv_opportunity to null when raw JSON has adv_opportunity: null', () => {
    const partner = new Partner({ adv_opportunity: null } as any);
    expect(partner.adv_opportunity).toBeNull();
  });

  it('maps adv_opportunity to null when adv_opportunity is absent from raw JSON', () => {
    const partner = new Partner({});
    expect(partner.adv_opportunity).toBeNull();
  });

  it('maps adv_opportunity to the provided object when a valid object is given', () => {
    const partner = new Partner({ adv_opportunity: validAdvOpportunity } as any);
    expect(partner.adv_opportunity).toEqual(validAdvOpportunity);
  });
});
