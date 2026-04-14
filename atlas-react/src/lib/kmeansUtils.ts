import type { ProspectCompany, ProspectCluster } from '../store/types';

/**
 * Returns a stable key for a prospect company.
 * Uses google_maps_link when available and not 'N/A', otherwise falls back to "nome|endereco".
 */
export function getLeadKey(company: ProspectCompany): string {
  if (company.google_maps_link && company.google_maps_link !== 'N/A') {
    return company.google_maps_link;
  }
  return `${company.nome}|${company.endereco}`;
}

/** Squared Euclidean distance between two lat/lon points. */
function sqDist(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number }
): number {
  const dlat = a.lat - b.lat;
  const dlon = a.lon - b.lon;
  return dlat * dlat + dlon * dlon;
}

/**
 * K-means++ initialisation.
 * Returns k centroid objects sampled from validPoints.
 */
function kmeansppInit(
  validPoints: { lat: number; lon: number }[],
  k: number
): { lat: number; lon: number }[] {
  const n = validPoints.length;
  const centroids: { lat: number; lon: number }[] = [];

  // Pick first centroid uniformly at random
  const firstIdx = Math.floor(Math.random() * n);
  centroids.push({ ...validPoints[firstIdx] });

  for (let c = 1; c < k; c++) {
    // Compute squared distance from each point to its nearest centroid
    const distances = validPoints.map((p) => {
      let minD = Infinity;
      for (const centroid of centroids) {
        const d = sqDist(p, centroid);
        if (d < minD) minD = d;
      }
      return minD;
    });

    // Sample proportionally to distances
    const total = distances.reduce((s, d) => s + d, 0);
    let rand = Math.random() * total;
    let chosen = n - 1;
    for (let i = 0; i < n; i++) {
      rand -= distances[i];
      if (rand <= 0) {
        chosen = i;
        break;
      }
    }
    centroids.push({ ...validPoints[chosen] });
  }

  return centroids;
}

/**
 * Clusters prospect companies using K-means with K-means++ initialisation.
 *
 * @param companies - Full list of ProspectCompany (may include entries without coordinates).
 * @param k         - Desired number of clusters (default 4).
 * @returns         - Array of ProspectCluster sorted by priority (1 = highest).
 */
export function kmeansCluster(
  companies: ProspectCompany[],
  k: number = 4
): ProspectCluster[] {
  // Step 1: collect valid companies (with coordinates) and remember their original indices
  const validEntries: { point: { lat: number; lon: number }; originalIdx: number }[] = [];
  for (let i = 0; i < companies.length; i++) {
    const c = companies[i];
    if (c.lat != null && c.lon != null) {
      validEntries.push({ point: { lat: c.lat, lon: c.lon }, originalIdx: i });
    }
  }

  const n = validEntries.length;

  // Step 3: empty case
  if (n === 0) return [];

  // Step 2: clamp k
  const effectiveK = Math.min(k, n);

  const validPoints = validEntries.map((e) => e.point);

  // Step 4: K-means++ initialisation
  let centroids = kmeansppInit(validPoints, effectiveK);

  // Step 5: iterate until convergence
  let assignments = new Array<number>(n).fill(0);
  const MAX_ITER = 100;
  const DELTA_THRESHOLD = 1e-6;

  for (let iter = 0; iter < MAX_ITER; iter++) {
    // Assign each point to nearest centroid
    const newAssignments = validPoints.map((p) => {
      let bestIdx = 0;
      let bestDist = Infinity;
      for (let c = 0; c < effectiveK; c++) {
        const d = sqDist(p, centroids[c]);
        if (d < bestDist) {
          bestDist = d;
          bestIdx = c;
        }
      }
      return bestIdx;
    });

    // Recompute centroids
    const sums = Array.from({ length: effectiveK }, () => ({ lat: 0, lon: 0, count: 0 }));
    for (let i = 0; i < n; i++) {
      const ci = newAssignments[i];
      sums[ci].lat += validPoints[i].lat;
      sums[ci].lon += validPoints[i].lon;
      sums[ci].count += 1;
    }

    const newCentroids = sums.map((s, ci) =>
      s.count > 0
        ? { lat: s.lat / s.count, lon: s.lon / s.count }
        : centroids[ci] // keep old centroid if cluster is empty
    );

    // Check convergence
    let maxDelta = 0;
    for (let c = 0; c < effectiveK; c++) {
      maxDelta = Math.max(maxDelta, sqDist(centroids[c], newCentroids[c]));
    }

    assignments = newAssignments;
    centroids = newCentroids;

    if (maxDelta < DELTA_THRESHOLD) break;
  }

  // Step 6: build cluster objects
  const clusterData: {
    centroid: { lat: number; lon: number };
    count: number;
    match_count: number;
    company_indices: number[];
  }[] = Array.from({ length: effectiveK }, (_, ci) => ({
    centroid: centroids[ci],
    count: 0,
    match_count: 0,
    company_indices: [],
  }));

  for (let i = 0; i < n; i++) {
    const ci = assignments[i];
    const originalIdx = validEntries[i].originalIdx;
    clusterData[ci].count += 1;
    clusterData[ci].company_indices.push(originalIdx);
    if (companies[originalIdx].isMatch === true) {
      clusterData[ci].match_count += 1;
    }
  }

  // Step 7: sort by (count + match_count) descending, assign priority (1-based)
  clusterData.sort((a, b) => b.count + b.match_count - (a.count + a.match_count));

  // Step 8: assign priority and intensity
  return clusterData.map((cd, idx) => {
    const priority = idx + 1;
    const intensity =
      priority === 1 ? 1.0 : 1.0 - (priority - 1) / effectiveK;
    return {
      centroid: cd.centroid,
      count: cd.count,
      match_count: cd.match_count,
      priority,
      intensity,
      company_indices: cd.company_indices,
    };
  });
}
