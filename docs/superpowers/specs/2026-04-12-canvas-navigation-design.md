# Canvas Navigation — Pan, Mode Toggle, Smooth Wheel Zoom

**Date:** 2026-04-12
**Scope:** `frontend/src/components/Editor.tsx`, `frontend/src/App.tsx`

## Goal

Make the schematic canvas feel like a modern CAD tool: right-click to pan, middle-click to flip between Select/Wire, and smooth cursor-anchored wheel zoom.

## Input map

| Input | Action |
|---|---|
| Right mouse button drag | Pan the view |
| Middle mouse button click | Toggle mode Select ↔ Wire |
| Mouse wheel / trackpad scroll | Zoom at cursor (smooth) |
| Left mouse button | Unchanged (select / wire / marquee) |
| Browser context menu | Suppressed on the canvas |

This replaces the current middle-click pan. No keyboard shortcut changes.

## Implementation

### 1. Right-click pan

In `handleMouseDown`, handle `e.button === 2` identically to the current `button === 1` branch: record `startX/startY/startVX/startVY` in `panning` state and `preventDefault()`. Remove the old `button === 1` pan branch.

Add `onContextMenu={(e) => e.preventDefault()}` on the `<svg>` element so right-click-drag isn't interrupted by the browser menu.

### 2. Middle-click mode toggle

Add prop to `Editor`:

```ts
onToggleMode: () => void;
```

In `handleMouseDown`, when `e.button === 1`, call `onToggleMode()` and return (no pan). In `App.tsx`, pass `onToggleMode={() => setMode(m => m === "select" ? "wire" : "select")}`.

The existing `useEffect` at Editor.tsx:377 already clears wire state on mode change, so flipping mid-wire cancels cleanly.

### 3. Smooth cursor-anchored wheel zoom

**State additions:**
```ts
const [targetViewBox, setTargetViewBox] = useState(viewBox);
const animRef = useRef<number | null>(null);
```

**Wheel handler** (attached via `useEffect` + `addEventListener('wheel', handler, { passive: false })` so `preventDefault` works):

1. `e.preventDefault()` to stop page scroll.
2. Compute cursor SVG point from `targetViewBox` (not the rendered one — we stack zooms against the target).
3. `factor = Math.exp(e.deltaY * 0.0015)` (positive deltaY = zoom out).
4. Scale width/height by factor; shift x/y so the cursor point stays fixed.
5. Clamp zoom: min width 64, max width `sheet.width * 20`.
6. `setTargetViewBox(next)` and kick the animation loop if not running.

**Animation loop** (rAF):

```ts
const step = () => {
  setViewBox(v => {
    const t = targetViewBox;
    const nx = v.x + (t.x - v.x) * 0.2;
    const ny = v.y + (t.y - v.y) * 0.2;
    const nw = v.w + (t.w - v.w) * 0.2;
    const nh = v.h + (t.h - v.h) * 0.2;
    const done = Math.abs(nw - t.w) < 0.01 && Math.abs(nh - t.h) < 0.01;
    if (done) { animRef.current = null; return t; }
    animRef.current = requestAnimationFrame(step);
    return { x: nx, y: ny, w: nw, h: nh };
  });
};
```

**Also route the `+`/`-`/`Fit` buttons and sheet-size reset through `setTargetViewBox`** so every zoom path eases consistently.

**Pan stays direct** — panning writes `viewBox` and `targetViewBox` together so the animation doesn't fight the drag.

### 4. Cleanup

Cancel any pending rAF on unmount.

## Edge cases

- **Mid-wire mode flip:** handled by existing effect; wire state resets.
- **Middle-click during pan/drag:** `handleMouseDown` early-returns on button 2 before reaching the button 1 branch, so they can't interleave.
- **Trackpad pinch:** Chrome/Safari emit wheel events with `ctrlKey=true` for pinch — same handler works, since we only read `deltaY`.
- **Passive-wheel warning:** resolved by native `addEventListener` with `{ passive: false }`.

## Out of scope

- Keyboard panning/zoom shortcuts.
- Momentum/inertia on pan.
- Zoom-to-selection.
- Touch/gesture support beyond trackpad wheel events.
