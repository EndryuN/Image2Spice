# No-Overlap Wiring — Design

**Status:** Proposed
**Date:** 2026-04-15
**Scope:** Prevent collinear wire overlap in both the interactive editor and the backend-generated schematics. Upgrade the VLM wiring pipeline to use the already-built `route_with_paths` router.

---

## Motivation

Today, two wires can occupy the same line in two situations:

1. **Interactive drawing** (`Editor.tsx`): the user can draw a wire directly on top of an existing one. The code detects `click-hits-wire` on the third click of an L-shape (lines 276-290) but does not detect the *candidate segment* overlapping along its length.
2. **Backend generation** (`wire_router.py`): `_deduplicate_wires` removes only exact duplicates, not collinear overlaps. Independent L-routes for adjacent nets frequently stack on a shared column/row. The result is a visually messy, electrically redundant schematic.

A second latent issue: the `/api/wizard/wires` endpoint calls the legacy pairwise router (`compute_wires`) and ignores the VLM-aware router (`route_with_paths`) that already exists in the codebase. The VLM sees the original image and knows where buses actually run — but it's only asked for pin pairs.

## Overlap definition (used by both phases)

Two wires overlap iff they are **collinear and share a common segment**. This covers:

- Exact duplicates.
- One segment fully contains another.
- Partial overlap that extends either end.

Perpendicular crossings are **allowed**. In LTspice, crossings without a junction dot are legitimate non-connecting intersections.

**Abutting segments (endpoint-to-endpoint on the same line) are treated differently in each phase:**

- **Phase 1 (interactive):** abutting is **allowed** — the user is deliberately extending a line or creating a T-junction. Strict inequality (`<`) on intervals.
- **Phase 2 (backend merge):** abutting is **merged** — the final `.asc` should emit one clean segment instead of two, since the two are electrically indistinguishable from one longer wire. Inclusive inequality (`<=`) on intervals.

This is a principled split, not an inconsistency: interactive intent respects the user's drawing action; deterministic cleanup normalizes what the LLM produced.

## Architecture

```
┌───────────────────────────────┐       ┌───────────────────────────────┐
│  FRONTEND (Phase 1)           │       │  BACKEND (Phase 2)            │
│                               │       │                               │
│  Editor.tsx                   │       │  /api/wizard/wires            │
│   ├─ ghost preview ──red──┐   │       │   ├─ describe_wires (VLM) ──┐ │
│   └─ commit click ────────┤   │       │   │   wire_paths + buses    │ │
│                           ▼   │       │   ▼                         │ │
│             wireOverlap.ts    │       │   build CircuitGraph          │
│        isCollinearOverlap()   │       │   route_with_paths(...)       │
│                               │       │     └─ _merge_collinear_wires │
└───────────────────────────────┘       └───────────────────────────────┘
```

Frontend and backend each own their overlap logic. They don't share code (different languages), but they share the *definition*, written out in one place per side.

---

## Phase 1 — Interactive wire mode

### Files touched

- `frontend/src/lib/wireOverlap.ts` *(new)*
- `frontend/src/components/Editor.tsx`

### `wireOverlap.ts` (new helper)

Pure module with one exported function:

```ts
export function isCollinearOverlap(
  candidate: { from: Position; to: Position },
  existing: Array<{ from: Position; to: Position }>
): boolean;
```

Implementation:

1. Classify `candidate` as horizontal (`from.y === to.y`), vertical (`from.x === to.x`), or degenerate (zero length → return `false`; the existing zero-length guard in Editor.tsx already skips these, but the helper defends itself).
2. For each `existing` wire of the same orientation on the same axis (same shared coord), compute 1D interval overlap: `max(a.lo, b.lo) < min(a.hi, b.hi)` (strict — touching-at-a-point is not overlap) OR `max(a.lo, b.lo) <= min(a.hi, b.hi)` if we want abutting to count as overlap.

**Decision:** use strict inequality (`<`). Abutting endpoint-to-endpoint is not an overlap in the interactive sense — it's a normal T-junction in the making. The merge pass in Phase 2 handles abutting on the backend separately.

Returns `true` if any existing wire shares positive overlap with the candidate.

### Editor.tsx changes

**Ghost preview (lines 578-611, `wirePreviewLines`).** The current preview emits 1 or 2 dashed segments. For each segment, call `isCollinearOverlap(segment, schematic.wires)`. If `true`, render that segment with `stroke="var(--color-error)"` and `strokeWidth={2}`; otherwise leave as-is. Only the overlapping leg turns red — not the whole L — so the user sees exactly which leg is the problem.

**Click rejection.**

- **Click 2 (wirePhase === "first", line 266-274):** before calling `onAddWire(wireStart, corner)`, check `isCollinearOverlap({from: wireStart, to: corner}, schematic.wires)`. If true: reset state (`setWireStart(null)`, `setWireCorner(null)`, `setWirePhase(null)`, `setCursorPos(null)`) and return. Nothing is committed.

- **Click 3 (wirePhase === "second", line 275-301):** the existing "click on existing wire" hit-test at lines 276-290 stays as-is. Add a new check *after* that: before calling `onAddWire(wireCorner, endPos)` at line 295, check `isCollinearOverlap({from: wireCorner, to: endPos}, schematic.wires)`. If true: reset state and return. **Do not roll back segment 1.** This matches the existing abort pattern at 285-290.

No other Editor.tsx changes. No undo-stack manipulation. No new theme variables (`--color-error` already exists in `theme.css:16` and `:39`).

### Out of scope for Phase 1

- Retroactive cleanup of existing `schematic.wires` (e.g., on import).
- Validation pass on schematics loaded from the backend (the backend will already be overlap-free after Phase 2).
- Drag-to-move of existing wires (doesn't exist today; not being added).

---

## Phase 2a — Backend: deterministic merge backstop

### Files touched

- `backend/services/wire_router.py`
- `backend/tests/test_wire_router.py` *(extended)*
- `backend/tests/test_wire_overlap.py` *(new)*

### New function: `_merge_collinear_wires`

Replaces `_deduplicate_wires` (line 290). Same signature, stronger semantics.

Algorithm:

1. Normalize every wire so endpoints are ordered (`x1 <= x2`, and if `x1 == x2` then `y1 <= y2`). Matches existing normalization at line 297.
2. Partition into three buckets: horizontal (`y1 == y2`), vertical (`x1 == x2`), and diagonal. Diagonals should not appear (router only emits Manhattan), but if one does, pass it through untouched.
3. **For horizontal bucket:** group by shared `y`. Within each group, sort by `x1`. Sweep: merge wire `B` into wire `A` if `B.x1 <= A.x2`, extending `A.x2 = max(A.x2, B.x2)`. Emit maximal non-overlapping segments.
4. **For vertical bucket:** same algorithm swapping x/y.
5. Concatenate all buckets → return.

This handles exact duplicates, containment, partial overlap, AND abutting segments (since the sweep uses `<=`). Result: one maximal segment per run of collinear overlapping+abutting pieces. Electrically identical; visually clean.

**Call sites** (no other change): already called at `wire_router.py:287`, `:463`, `:524`, `:586`. All three routers (`route_with_paths`, `route_connections`, `route_nets`) and `_route_net_with_direct_wires` get the fix for free.

### `_COLLINEAR_THRESHOLD`

Declared at line 14, used nowhere. Leave it alone — removing it is out of scope.

---

## Phase 2b — Backend: VLM-assisted routing

### Files touched

- `backend/prompts/wires_system.txt`
- `backend/services/vision.py` (specifically `describe_wires`)
- `backend/api/wizard_routes.py` (handler for `/api/wizard/wires`)

### Prompt upgrade (`wires_system.txt`)

Extend the required JSON output to include `wire_paths` and `buses`, using the vocabulary `route_with_paths` already consumes:

```json
{
  "connections": [...],     // unchanged
  "grounds": [...],         // unchanged
  "labels": [...],          // unchanged
  "wire_paths": [
    {"from_pin": "R1.A", "to_pin": "Q1.C", "path": "L_horizontal_first"}
  ],
  "buses": [
    {"orientation": "horizontal", "y_pct": 40, "connects": ["R1.B", "R2.B", "C1.A"]}
  ]
}
```

Allowed `path` values: `L_horizontal_first`, `L_vertical_first`, `direct_horizontal`, `direct_vertical`. Allowed `orientation` values: `horizontal`, `vertical`.

Prompt text must:

- Instruct the model to describe what it **sees** in the image, not invent routing.
- Explicitly allow empty `wire_paths` and `buses` arrays when the image is simple or ambiguous — `route_with_paths` falls back to plain L-routing in that case.
- Prefer `buses` when multiple pins share a visible bus line in the image; prefer per-connection `wire_paths` otherwise.

### `describe_wires` in `vision.py`

Parse the new fields from the VLM JSON. Graceful fallback: missing `wire_paths` → `[]`; missing `buses` → `[]`. The existing `_extract_json` handling remains unchanged.

### `/api/wizard/wires` handler (`wizard_routes.py:123-204`)

**This is the biggest change.** Currently builds a raw `comp_map` dict at line 184-193 and calls `compute_wires(...)` at line 195. Switch to `route_with_paths`, which requires a `CircuitGraph`.

New flow (replace lines 184-195):

1. Build a `CircuitGraph` from `dictionary`. Pattern already used at `wizard_routes.py:302-305` and `schematic_builder.py:94-120` — reuse the idiom (do not refactor those).
2. For each component in `components`, add a node to the graph with `type`, `instanceName`, and — if present in `positions` — `position` and `rotation`. This is the only state `route_with_paths` needs from the graph: it calls `_get_pin_abs(graph, name, pin)` which only looks at `graph.components`. Connections, grounds, and labels are passed as separate arguments and do not need to be written to the graph.
3. Call:
   ```python
   wire_result = route_with_paths(
       graph,
       wire_paths=wire_desc.get("wire_paths", []),
       buses=wire_desc.get("buses", []),
       connections=wire_desc.get("connections", []),
       grounds=wire_desc.get("grounds", []),
       labels=wire_desc.get("labels", []),
   )
   ```
4. Response shape unchanged: `{wire_descriptions, wires, flags}` where `wires` is already serialized from `wire_result.wires`.

**Backward compat:** when the VLM returns old-format JSON (no `wire_paths`/`buses`), the handler passes `[]` to those params. `route_with_paths` then routes via its step 3 (line 414) — plain L-routing per connection, identical in behavior to the current `compute_wires` path. No regression risk.

**Legacy `compute_wires` stays** in `wire_router.py` — it's still referenced elsewhere (`/api/refine`, etc.) and removing it is out of scope.

### Pin normalization

Existing normalization at `wizard_routes.py:165-182` handles `connections`/`grounds`/`labels`. `wire_paths` and `buses` use `"Component.Pin"` strings. `route_with_paths` routes these through `_resolve_pin` (`wire_router.py:57-67`), which already handles case-insensitive matching and alias normalization via `normalize_pin`. No explicit normalization pass is required for the new fields.

---

## Testing

### Backend

**New:** `backend/tests/test_wire_overlap.py` — unit tests for `_merge_collinear_wires`:

- Exact duplicate → 1 wire out.
- Containment (A contains B) → 1 wire out equal to A.
- Partial overlap extending both ends → 1 wire spanning the union.
- Abutting (A ends where B starts) → 1 merged wire.
- Perpendicular crossing → 2 wires out, unchanged.
- Collinear but disjoint (gap between) → 2 wires out.
- Mixed horizontal + vertical + perpendicular → correct per-bucket handling.

**Extended:** `backend/tests/test_wire_router.py`:

- Given a net whose L-routes would overlap, `route_nets` / `route_connections` final `WireResult.wires` contains no collinear duplicates.
- Given VLM-provided `wire_paths`, `route_with_paths` honors the `path` type.
- Given VLM-provided `buses`, `route_with_paths` emits one bus + stubs.
- Given empty `wire_paths` and `buses`, `route_with_paths` falls back to per-connection L-routing (regression guard for the wizard migration).

### Frontend

No automated test harness. Manual verification checklist:

- Draw a wire segment directly onto an existing wire. Ghost leg turns red. Click does nothing (resets drawing state).
- Draw an L-shape where leg-2 would overlap an existing wire. Leg-1 ghost is normal; leg-2 ghost is red. Click 3 cancels without committing leg-2. Leg-1 stays committed.
- Draw perpendicular wires that cross — ghost stays normal, commit succeeds.
- `npm run build` succeeds.

---

## Risks

- **VLM regression on prompt upgrade.** The existing prompt works; adding new required fields could confuse the model. Mitigation: tell the model both fields are optional (empty arrays allowed), and `route_with_paths` already falls back to plain L-routing in that case.
- **`CircuitGraph` construction bug in handler.** The handler currently uses raw dicts; migrating to `CircuitGraph` means any mismatch between `positions_json` shape and what `CircuitGraph` expects will surface as routing failures. Mitigation: reuse the existing pattern from `wizard_routes.py:302-305`, and add a regression test calling `/api/wizard/wires` with `wire_paths=[]` and `buses=[]` asserting parity with pre-change output on a fixture.
- **Merge-on-abut changes visual output.** Existing schematics that happened to have abutting (but not overlapping) segments will now render as single segments. This is electrically identical and visually cleaner, so acceptable — but it is a user-visible diff on regenerate.

## Out of scope

- Retroactive pass over imported / existing frontend schematics.
- Overlap detection for grounds / flags (they're flags, not wires).
- Changes to `/api/refine` or the legacy `compute_wires`.
- Removing the unused `_COLLINEAR_THRESHOLD` constant.
- Frontend drag-to-move wires (doesn't exist).
- Prompt changes for `identify`, `directives`, or `layout` steps.

---

## Summary of file changes

| File | Change |
|------|--------|
| `frontend/src/lib/wireOverlap.ts` | **new**: `isCollinearOverlap()` helper |
| `frontend/src/components/Editor.tsx` | overlap check at commit points + red ghost rendering |
| `backend/services/wire_router.py` | replace `_deduplicate_wires` with `_merge_collinear_wires` |
| `backend/prompts/wires_system.txt` | add `wire_paths` + `buses` to required output |
| `backend/services/vision.py` | parse `wire_paths` + `buses` in `describe_wires` |
| `backend/api/wizard_routes.py` | `/api/wizard/wires` builds `CircuitGraph` + calls `route_with_paths` |
| `backend/tests/test_wire_overlap.py` | **new**: merge function unit tests |
| `backend/tests/test_wire_router.py` | extended: overlap-free output + VLM path cases |
