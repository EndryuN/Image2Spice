# Canvas Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace middle-click pan with right-click pan, add middle-click Select/Wire toggle, and make wheel zoom cursor-anchored and smooth via rAF easing.

**Architecture:** All runtime logic lives in `frontend/src/components/Editor.tsx`. The animation uses a ref-based target viewBox (`targetViewBoxRef`) plus a rAF loop that lerps the rendered `viewBox` toward the target by 20% per frame. Every zoom path (wheel, +/- buttons, Fit, sheet reset) writes the target and kicks the loop; every pan path writes both the rendered box and the target ref in lockstep so the animation never fights a drag. `App.tsx` gets a one-line prop addition to expose `setMode` to the editor.

**Tech Stack:** React 19, TypeScript 5.9, native SVG. No new dependencies.

**Testing note:** Per `CLAUDE.md`, the frontend has no test suite. Verification is `npm run build` (TypeScript + Vite compilation) plus manual in-browser testing. Each task ends with a build check; the final task is a manual test pass.

---

## File Structure

**Modified files:**
- `frontend/src/components/Editor.tsx` — input handling, zoom/pan state, animation loop
- `frontend/src/App.tsx` — pass `onToggleMode` prop to `Editor`

**No new files.**

---

## Task 1: Right-click pan + suppress context menu

Replace the existing middle-click pan (`button === 1`) with right-click pan (`button === 2`) and stop the browser context menu from appearing on the canvas.

**Files:**
- Modify: `frontend/src/components/Editor.tsx:183-239` (handleMouseDown — replace the button-1 branch)
- Modify: `frontend/src/components/Editor.tsx:514-521` (the `<svg>` element — add `onContextMenu`)

- [ ] **Step 1: Replace the middle-click pan branch with right-click pan**

In `handleMouseDown`, change the existing pan branch from `e.button === 1` to `e.button === 2`. The body is unchanged.

```tsx
const handleMouseDown = useCallback(
  (e: React.MouseEvent) => {
    // Right-click pan
    if (e.button === 2) {
      setPanning({
        startX: e.clientX,
        startY: e.clientY,
        startVX: viewBox.x,
        startVY: viewBox.y,
      });
      e.preventDefault();
      return;
    }

    if (mode === "wire" && e.button === 0) {
      // ... unchanged
```

Leave the rest of `handleMouseDown` alone.

- [ ] **Step 2: Suppress the browser context menu on the SVG**

Add `onContextMenu={(e) => e.preventDefault()}` to the `<svg>` element:

```tsx
<svg
  ref={svgRef}
  viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
  style={{ width: "100%", height: "100%", background: "var(--bg-editor-outside)", cursor: mode === "wire" ? "crosshair" : "default" }}
  onMouseDown={handleMouseDown}
  onMouseMove={handleMouseMove}
  onMouseUp={handleMouseUp}
  onContextMenu={(e) => e.preventDefault()}
>
```

- [ ] **Step 3: Build check**

Run from `frontend/`:
```bash
npm run build
```
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 4: Manual smoke test**

Start `npm run dev`, open http://localhost:5173, upload any image or drop a component. Right-click-drag on the canvas — view should pan. No browser context menu should appear. Middle-click should do nothing yet (we're removing it before we add the toggle).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat(editor): right-click drag to pan, suppress context menu"
```

---

## Task 2: Middle-click toggles Select/Wire mode

Add an `onToggleMode` prop to `Editor` and call it on middle-click. Wire it up from `App.tsx`.

**Files:**
- Modify: `frontend/src/components/Editor.tsx:10-20` (EditorProps interface)
- Modify: `frontend/src/components/Editor.tsx:24-34` (function parameters)
- Modify: `frontend/src/components/Editor.tsx:183-239` (handleMouseDown — add button-1 branch)
- Modify: `frontend/src/App.tsx:258-268` (Editor invocation)

- [ ] **Step 1: Add `onToggleMode` to `EditorProps`**

```tsx
interface EditorProps {
  schematic: Schematic;
  dictionary: Dictionary | null;
  selectedIds: Set<string>;
  onSelect: (ids: Set<string>) => void;
  onMoveComponent: (id: string, pos: Position) => void;
  onAddWire: (from: Position, to: Position) => void;
  onSetSheet: (width: number, height: number) => void;
  onToggleMode: () => void;
  mode: "select" | "wire";
  showGrid: boolean;
}
```

- [ ] **Step 2: Destructure `onToggleMode` in the component function**

```tsx
export function Editor({
  schematic,
  dictionary,
  selectedIds,
  onSelect,
  onMoveComponent,
  onAddWire,
  onSetSheet,
  onToggleMode,
  mode,
  showGrid,
}: EditorProps) {
```

- [ ] **Step 3: Handle middle-click in `handleMouseDown`**

At the top of `handleMouseDown`, above the `button === 2` branch, add:

```tsx
// Middle-click: toggle Select / Wire
if (e.button === 1) {
  e.preventDefault();
  onToggleMode();
  return;
}
```

Also add `onToggleMode` to the `useCallback` dependency array:

```tsx
[mode, wirePhase, wireStart, wireCorner, svgPoint, snapPosition, computeCorner, onAddWire, onSelect, onToggleMode, viewBox]
```

- [ ] **Step 4: Wire up `onToggleMode` in `App.tsx`**

At `App.tsx:258`:

```tsx
<Editor
  schematic={schematic}
  dictionary={dictionary}
  selectedIds={selectedIds}
  onSelect={setSelectedIds}
  onMoveComponent={moveComponent}
  onAddWire={addWire}
  onSetSheet={setSheet}
  onToggleMode={() => setMode((m) => (m === "select" ? "wire" : "select"))}
  mode={mode}
  showGrid={showGrid}
/>
```

- [ ] **Step 5: Build check**

```bash
npm run build
```
Expected: build succeeds.

- [ ] **Step 6: Manual smoke test**

In the running dev server: middle-click on the canvas. The toolbar Select/Wire buttons should flip. Middle-clicking again flips back. Middle-clicking during a half-drawn wire should cancel the wire (the existing effect at `Editor.tsx:377` handles this).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Editor.tsx frontend/src/App.tsx
git commit -m "feat(editor): middle-click toggles Select/Wire mode"
```

---

## Task 3: Smooth zoom infrastructure (target ref + rAF loop)

Introduce `targetViewBoxRef` and a rAF-driven lerp loop. This task does not yet change user behavior — it prepares the plumbing and routes the existing `+`/`-`/Fit buttons and sheet-reset effect through the new path, so they ease instead of snap.

**Files:**
- Modify: `frontend/src/components/Editor.tsx` (add refs, animation helpers, update zoomBy/zoomFit, update sheet-reset effect, update pan handler)

- [ ] **Step 1: Add target ref and animation ref**

Just below the existing `viewBox` state (Editor.tsx:36), add:

```tsx
const targetViewBoxRef = useRef({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
const animRef = useRef<number | null>(null);
```

- [ ] **Step 2: Add the animation loop helper**

Add this inside the component body, above `handleMouseDown`:

```tsx
const animateToTarget = useCallback(() => {
  if (animRef.current != null) return; // already running
  const step = () => {
    setViewBox((v) => {
      const t = targetViewBoxRef.current;
      const nx = v.x + (t.x - v.x) * 0.2;
      const ny = v.y + (t.y - v.y) * 0.2;
      const nw = v.w + (t.w - v.w) * 0.2;
      const nh = v.h + (t.h - v.h) * 0.2;
      const done =
        Math.abs(nw - t.w) < 0.01 &&
        Math.abs(nh - t.h) < 0.01 &&
        Math.abs(nx - t.x) < 0.01 &&
        Math.abs(ny - t.y) < 0.01;
      if (done) {
        animRef.current = null;
        return { x: t.x, y: t.y, w: t.w, h: t.h };
      }
      animRef.current = requestAnimationFrame(step);
      return { x: nx, y: ny, w: nw, h: nh };
    });
  };
  animRef.current = requestAnimationFrame(step);
}, []);
```

- [ ] **Step 3: Cancel rAF on unmount**

Add a cleanup effect near the other `useEffect`s (after the sheet-reset effect around Editor.tsx:358):

```tsx
useEffect(() => {
  return () => {
    if (animRef.current != null) {
      cancelAnimationFrame(animRef.current);
      animRef.current = null;
    }
  };
}, []);
```

- [ ] **Step 4: Route `zoomBy` through the target + animation**

Replace the existing `zoomBy` (Editor.tsx:320-331) with:

```tsx
const zoomBy = useCallback(
  (factor: number) => {
    const t = targetViewBoxRef.current;
    const cx = t.x + t.w / 2;
    const cy = t.y + t.h / 2;
    const maxW = schematic.sheet.width * 20;
    const minW = 64;
    const newW = Math.max(minW, Math.min(maxW, t.w * factor));
    const newH = t.h * (newW / t.w);
    targetViewBoxRef.current = {
      x: cx - newW / 2,
      y: cy - newH / 2,
      w: newW,
      h: newH,
    };
    animateToTarget();
  },
  [schematic.sheet.width, animateToTarget]
);
```

- [ ] **Step 5: Route `zoomFit` through the target + animation**

Replace the existing `zoomFit` (Editor.tsx:333-335) with:

```tsx
const zoomFit = useCallback(() => {
  targetViewBoxRef.current = {
    x: -20,
    y: -20,
    w: schematic.sheet.width + 40,
    h: schematic.sheet.height + 40,
  };
  animateToTarget();
}, [schematic.sheet.width, schematic.sheet.height, animateToTarget]);
```

- [ ] **Step 6: Make the sheet-reset effect write both ref and state**

Replace the sheet-reset `useEffect` at Editor.tsx:355-357:

```tsx
useEffect(() => {
  const next = { x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 };
  targetViewBoxRef.current = next;
  setViewBox(next);
}, [schematic.sheet.width, schematic.sheet.height]);
```

(Sheet-size changes reset instantly — no ease — because the user changed the canvas dimensions and expects the view to match immediately.)

- [ ] **Step 7: Keep the target ref in sync during panning**

In `handleMouseMove`, inside the existing `if (panning)` branch (Editor.tsx:243-255), update the target ref alongside the state write:

```tsx
if (panning) {
  const svg = svgRef.current;
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const dx = ((e.clientX - panning.startX) / rect.width) * viewBox.w;
  const dy = ((e.clientY - panning.startY) / rect.height) * viewBox.h;
  const nx = panning.startVX - dx;
  const ny = panning.startVY - dy;
  targetViewBoxRef.current = { ...targetViewBoxRef.current, x: nx, y: ny };
  setViewBox((v) => ({ ...v, x: nx, y: ny }));
  return;
}
```

- [ ] **Step 8: Build check**

```bash
npm run build
```
Expected: build succeeds.

- [ ] **Step 9: Manual smoke test**

In the dev server: click the `+` and `-` zoom buttons. View should ease in/out instead of snapping. Click Fit (the percentage button) — same easing. Change the sheet width/height inputs — view should snap (no ease) to the new fit. Right-click-drag to pan — should feel instant, no rubber-banding.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat(editor): rAF-driven smooth zoom for buttons and fit"
```

---

## Task 4: Cursor-anchored wheel zoom

Attach a native wheel listener to the SVG via `useEffect` (so `preventDefault` works even with passive defaults), compute the cursor-anchored target, and kick the animation loop.

**Files:**
- Modify: `frontend/src/components/Editor.tsx` (add wheel `useEffect`)

- [ ] **Step 1: Add the wheel handler effect**

Add this `useEffect` near the other effects (after the rAF cleanup from Task 3). It reads from `svgRef`, `targetViewBoxRef`, `schematic.sheet.width`, and `animateToTarget`.

```tsx
useEffect(() => {
  const svg = svgRef.current;
  if (!svg) return;

  const handleWheel = (e: WheelEvent) => {
    e.preventDefault();
    const rect = svg.getBoundingClientRect();
    const t = targetViewBoxRef.current;

    // Cursor position in SVG user coords (using target, not rendered)
    const fracX = (e.clientX - rect.left) / rect.width;
    const fracY = (e.clientY - rect.top) / rect.height;
    const mx = fracX * t.w + t.x;
    const my = fracY * t.h + t.y;

    // Exponential factor — works for both wheel and trackpad
    const factor = Math.exp(e.deltaY * 0.0015);
    const maxW = schematic.sheet.width * 20;
    const minW = 64;
    const newW = Math.max(minW, Math.min(maxW, t.w * factor));
    const newH = t.h * (newW / t.w);

    // Keep the cursor point fixed
    const newX = mx - fracX * newW;
    const newY = my - fracY * newH;

    targetViewBoxRef.current = { x: newX, y: newY, w: newW, h: newH };
    animateToTarget();
  };

  svg.addEventListener("wheel", handleWheel, { passive: false });
  return () => svg.removeEventListener("wheel", handleWheel);
}, [schematic.sheet.width, animateToTarget]);
```

- [ ] **Step 2: Build check**

```bash
npm run build
```
Expected: build succeeds.

- [ ] **Step 3: Manual smoke test — mouse wheel**

In the dev server, place the cursor over a specific component on the canvas. Scroll the wheel up — that component should grow larger while staying under the cursor (not drift to the center). Scroll down — it should shrink in place. Zoom should ease smoothly, not snap.

- [ ] **Step 4: Manual smoke test — trackpad (if available)**

On a trackpad, two-finger scroll should zoom smoothly. Pinch gesture (which the browser sends as a wheel event with `ctrlKey`) should also zoom — the handler ignores `ctrlKey` so it works automatically.

- [ ] **Step 5: Manual smoke test — interaction with pan**

Zoom in deep with the wheel, then right-click-drag to pan. The pan should start from wherever you currently are (no snap-back). Zoom again after panning — the cursor-anchoring should still land correctly, because Task 3 Step 7 keeps `targetViewBoxRef` in sync during pan.

- [ ] **Step 6: Manual smoke test — page scroll suppression**

Scroll the wheel while hovering the canvas. The page behind the canvas must NOT scroll (`preventDefault` is working).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Editor.tsx
git commit -m "feat(editor): cursor-anchored smooth wheel zoom"
```

---

## Task 5: Final verification pass

- [ ] **Step 1: Full build**

```bash
cd frontend && npm run build
```
Expected: success.

- [ ] **Step 2: Lint**

```bash
npm run lint
```
Expected: no new warnings from our changes. (Pre-existing warnings in unrelated files are OK.)

- [ ] **Step 3: Manual checklist**

Run through every interaction once more in one session:
- [ ] Right-click-drag pans
- [ ] Browser context menu never appears over the canvas
- [ ] Middle-click toggles Select ↔ Wire (toolbar updates)
- [ ] Middle-click mid-wire cancels the half-drawn wire
- [ ] Wheel zooms cursor-anchored, smoothly
- [ ] `+`/`-` buttons ease smoothly
- [ ] Fit button eases smoothly
- [ ] Sheet-size change snaps instantly (no ease)
- [ ] Pan after wheel zoom does not snap back
- [ ] Left-click drag still creates marquee selection
- [ ] Left-click on a component still drags it in Select mode
- [ ] Wire mode still draws L-shaped wires on left-click

- [ ] **Step 4: No additional commit needed** — verification only.

---

## Out of Scope

Per the spec: keyboard shortcuts for pan/zoom, momentum/inertia on pan, zoom-to-selection, and touch/pointer gesture support beyond trackpad wheel events.
