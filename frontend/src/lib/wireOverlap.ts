import type { Position } from "../types/schematic";

interface Segment {
  from: Position;
  to: Position;
}

/**
 * Returns true if `candidate` is collinear with any wire in `existing`
 * AND shares a positive-length sub-segment with it.
 *
 * Abutting endpoint-to-endpoint is NOT considered overlap (strict inequality)
 * — it is a valid T-junction or line extension by the user.  Perpendicular
 * crossings are never overlap.
 */
export function isCollinearOverlap(
  candidate: Segment,
  existing: readonly Segment[],
): boolean {
  const aHoriz = candidate.from.y === candidate.to.y;
  const aVert = candidate.from.x === candidate.to.x;
  if (aHoriz && aVert) return false; // zero-length candidate — let caller handle

  for (const w of existing) {
    const bHoriz = w.from.y === w.to.y;
    const bVert = w.from.x === w.to.x;

    if (aHoriz && bHoriz && candidate.from.y === w.from.y) {
      const aLo = Math.min(candidate.from.x, candidate.to.x);
      const aHi = Math.max(candidate.from.x, candidate.to.x);
      const bLo = Math.min(w.from.x, w.to.x);
      const bHi = Math.max(w.from.x, w.to.x);
      if (Math.max(aLo, bLo) < Math.min(aHi, bHi)) return true;
    } else if (aVert && bVert && candidate.from.x === w.from.x) {
      const aLo = Math.min(candidate.from.y, candidate.to.y);
      const aHi = Math.max(candidate.from.y, candidate.to.y);
      const bLo = Math.min(w.from.y, w.to.y);
      const bHi = Math.max(w.from.y, w.to.y);
      if (Math.max(aLo, bLo) < Math.min(aHi, bHi)) return true;
    }
    // horizontal vs vertical → never collinear, skip
  }
  return false;
}
