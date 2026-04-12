import { useRef, useState, useCallback, useEffect, useMemo } from "react";
import type {
  Schematic,
  Component,
  Dictionary,
  Position,
} from "../types/schematic";
import { snapToGrid } from "../lib/gridSnap";

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

const PIN_SNAP_RADIUS = 20;

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
  const svgRef = useRef<SVGSVGElement>(null);
  const [viewBox, setViewBox] = useState({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
  const viewBoxRef = useRef({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
  const targetViewBoxRef = useRef({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
  const animRef = useRef<number | null>(null);
  const [dragging, setDragging] = useState<{
    id: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  // Wire drawing state machine: null → "first" → "second" → null
  const [wirePhase, setWirePhase] = useState<"first" | "second" | null>(null);
  const [wireStart, setWireStart] = useState<Position | null>(null);
  const [wireCorner, setWireCorner] = useState<Position | null>(null);
  const [cursorPos, setCursorPos] = useState<Position | null>(null);

  const [marquee, setMarquee] = useState<{ start: Position; end: Position } | null>(null);
  const marqueeRef = useRef<{ start: Position; end: Position } | null>(null);
  const [panning, setPanning] = useState<{
    startX: number;
    startY: number;
    startVX: number;
    startVY: number;
  } | null>(null);

  // ── Compute absolute pin positions for all components ──────────────
  const allPins = useMemo(() => {
    if (!dictionary) return [];
    const pins: { x: number; y: number; comp: string; pin: string }[] = [];
    for (const comp of schematic.components) {
      const dictComp = dictionary.components[comp.type];
      if (!dictComp) continue;
      const w = dictComp.symbol.width;
      const h = dictComp.symbol.height;
      // Bounds offset: convert LTspice pin coords to SVG coords
      // Bounds may be {minX,minY,...} or [minX,minY,maxX,maxY]
      const rawBounds = dictComp.geometry?.bounds;
      let bx = 0, by = 0;
      if (Array.isArray(rawBounds)) {
        bx = rawBounds[0] ?? 0;
        by = rawBounds[1] ?? 0;
      } else if (rawBounds) {
        bx = (rawBounds as { minX: number }).minX ?? 0;
        by = (rawBounds as { minY: number }).minY ?? 0;
      }
      for (const pin of dictComp.pins) {
        // Convert from LTspice coords to SVG coords
        let px = (pin.x ?? 0) - bx;
        let py = (pin.y ?? 0) - by;
        // Apply SVG rotation around center (cx, cy) — must match the
        // rotate(θ, cx, cy) transform used to render the component path
        const cx = w / 2;
        const cy = h / 2;
        switch (comp.rotation) {
          case "R90": {
            const newPx = cx - (py - cy);
            const newPy = cy + (px - cx);
            px = newPx; py = newPy; break;
          }
          case "R180": {
            px = 2 * cx - px;
            py = 2 * cy - py;
            break;
          }
          case "R270": {
            const newPx = cx + (py - cy);
            const newPy = cy - (px - cx);
            px = newPx; py = newPy; break;
          }
        }
        pins.push({
          x: comp.position.x + px,
          y: comp.position.y + py,
          comp: comp.instanceName,
          pin: pin.name,
        });
      }
    }
    return pins;
  }, [schematic.components, dictionary]);

  // ── Find nearest pin to a position ─────────────────────────────────
  const snapToPin = useCallback(
    (pos: Position): Position => {
      let best = pos;
      let bestDist = PIN_SNAP_RADIUS;
      for (const pin of allPins) {
        const dist = Math.abs(pin.x - pos.x) + Math.abs(pin.y - pos.y);
        if (dist < bestDist) {
          bestDist = dist;
          best = { x: pin.x, y: pin.y };
        }
      }
      return best;
    },
    [allPins]
  );

  // ── Snap position: try pin first, then grid ────────────────────────
  const snapPosition = useCallback(
    (pos: Position): Position => {
      const pinSnap = snapToPin(pos);
      if (pinSnap !== pos) return pinSnap;
      return { x: snapToGrid(pos.x), y: snapToGrid(pos.y) };
    },
    [snapToPin]
  );

  // ── Compute L-shape corner from start and cursor ───────────────────
  const computeCorner = useCallback(
    (start: Position, cursor: Position): Position => {
      // Auto-detect: if moved more horizontally, go horizontal first
      const dx = Math.abs(cursor.x - start.x);
      const dy = Math.abs(cursor.y - start.y);
      if (dx >= dy) {
        // Horizontal first → corner at (cursor.x, start.y)
        return { x: cursor.x, y: start.y };
      } else {
        // Vertical first → corner at (start.x, cursor.y)
        return { x: start.x, y: cursor.y };
      }
    },
    []
  );

  function getRotationTransform(rotation: string, width: number, height: number): string {
    const cx = width / 2;
    const cy = height / 2;
    switch (rotation) {
      case "R90": return `rotate(90, ${cx}, ${cy})`;
      case "R180": return `rotate(180, ${cx}, ${cy})`;
      case "R270": return `rotate(270, ${cx}, ${cy})`;
      case "M0": return `translate(${width}, 0) scale(-1, 1)`;
      case "M90": return `translate(${width}, 0) scale(-1, 1) rotate(90, ${cx}, ${cy})`;
      default: return "";
    }
  }

  const svgPoint = useCallback(
    (clientX: number, clientY: number): Position => {
      const svg = svgRef.current;
      if (!svg) return { x: 0, y: 0 };
      const rect = svg.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * viewBox.w + viewBox.x;
      const y = ((clientY - rect.top) / rect.height) * viewBox.h + viewBox.y;
      return { x: Math.round(x), y: Math.round(y) };
    },
    [viewBox]
  );

  const animateToTarget = useCallback(() => {
    if (animRef.current != null) return; // already running
    const step = () => {
      const v = viewBoxRef.current;
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
        const snapped = { x: t.x, y: t.y, w: t.w, h: t.h };
        viewBoxRef.current = snapped;
        setViewBox(snapped);
        return;
      }

      const next = { x: nx, y: ny, w: nw, h: nh };
      viewBoxRef.current = next;
      setViewBox(next);
      animRef.current = requestAnimationFrame(step);
    };
    animRef.current = requestAnimationFrame(step);
  }, []);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      // Middle-click: toggle Select / Wire
      if (e.button === 1) {
        e.preventDefault();
        onToggleMode();
        return;
      }
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
        const raw = svgPoint(e.clientX, e.clientY);
        const pos = snapPosition(raw);

        if (!wirePhase) {
          // Start drawing
          setWireStart(pos);
          setWirePhase("first");
          setCursorPos(pos);
        } else if (wirePhase === "first" && wireStart) {
          // Lock the corner, transition to second segment
          const corner = computeCorner(wireStart, pos);
          // Place first segment if it has length
          if (corner.x !== wireStart.x || corner.y !== wireStart.y) {
            onAddWire(wireStart, corner);
          }
          setWireCorner(corner);
          setWirePhase("second");
        } else if (wirePhase === "second" && wireCorner) {
          // Place second segment and finish
          const endPos = snapPosition(raw);
          if (endPos.x !== wireCorner.x || endPos.y !== wireCorner.y) {
            onAddWire(wireCorner, endPos);
          }
          // Reset
          setWireStart(null);
          setWireCorner(null);
          setWirePhase(null);
          setCursorPos(null);
        }
        return;
      }

      if (mode === "select" && e.button === 0) {
        // Start marquee selection — don't clear selection yet, wait for mouseUp
        const pos = svgPoint(e.clientX, e.clientY);
        const m = { start: pos, end: pos };
        setMarquee(m);
        marqueeRef.current = m;
      }
    },
    [mode, wirePhase, wireStart, wireCorner, svgPoint, snapPosition, computeCorner, onAddWire, onSelect, onToggleMode, viewBox]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
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
      if (dragging) {
        const pos = svgPoint(e.clientX, e.clientY);
        onMoveComponent(dragging.id, {
          x: snapToGrid(pos.x - dragging.offsetX),
          y: snapToGrid(pos.y - dragging.offsetY),
        });
        return;
      }
      if (marqueeRef.current) {
        const pos = svgPoint(e.clientX, e.clientY);
        const m = { start: marqueeRef.current.start, end: pos };
        setMarquee(m);
        marqueeRef.current = m;
        return;
      }
      // Update cursor position for wire preview and pin highlighting
      if (mode === "wire") {
        const raw = svgPoint(e.clientX, e.clientY);
        setCursorPos(snapPosition(raw));
      }
    },
    [panning, dragging, mode, svgPoint, snapPosition, onMoveComponent, viewBox, marquee]
  );

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    setPanning(null);
    const m = marqueeRef.current;
    if (m) {
      const x1 = Math.min(m.start.x, m.end.x);
      const y1 = Math.min(m.start.y, m.end.y);
      const x2 = Math.max(m.start.x, m.end.x);
      const y2 = Math.max(m.start.y, m.end.y);
      const dragDist = Math.abs(x2 - x1) + Math.abs(y2 - y1);

      if (dragDist > 10) {
        // Marquee drag — select all wires that intersect the rectangle
        const ids = new Set<string>();
        for (const wire of schematic.wires) {
          const wx1 = Math.min(wire.from.x, wire.to.x);
          const wy1 = Math.min(wire.from.y, wire.to.y);
          const wx2 = Math.max(wire.from.x, wire.to.x);
          const wy2 = Math.max(wire.from.y, wire.to.y);
          if (wx2 >= x1 && wx1 <= x2 && wy2 >= y1 && wy1 <= y2) {
            ids.add(wire.id);
          }
        }
        // Also select components inside the rectangle
        for (const comp of schematic.components) {
          if (comp.position.x >= x1 && comp.position.x <= x2 &&
              comp.position.y >= y1 && comp.position.y <= y2) {
            ids.add(comp.id);
          }
        }
        onSelect(ids);
      } else {
        // Just a click on empty space — deselect
        onSelect(new Set());
      }
      setMarquee(null);
      marqueeRef.current = null;
    }
  }, [schematic.wires, schematic.components, onSelect]);

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

  const zoomFit = useCallback(() => {
    targetViewBoxRef.current = {
      x: -20,
      y: -20,
      w: schematic.sheet.width + 40,
      h: schematic.sheet.height + 40,
    };
    animateToTarget();
  }, [schematic.sheet.width, schematic.sheet.height, animateToTarget]);

  const startDrag = useCallback(
    (compId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      if (mode === "wire") return; // Don't intercept clicks in wire mode
      onSelect(new Set([compId]));
      const comp = schematic.components.find((c) => c.id === compId);
      if (!comp) return;
      const pos = svgPoint(e.clientX, e.clientY);
      setDragging({
        id: compId,
        offsetX: pos.x - comp.position.x,
        offsetY: pos.y - comp.position.y,
      });
    },
    [mode, schematic.components, svgPoint, onSelect]
  );

  // Reset viewBox when sheet size changes (snap immediately, no animation)
  useEffect(() => {
    const next = { x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 };
    targetViewBoxRef.current = next;
    setViewBox(next);
  }, [schematic.sheet.width, schematic.sheet.height]);

  // Mirror viewBox state into viewBoxRef so the rAF loop can read it synchronously
  useEffect(() => {
    viewBoxRef.current = viewBox;
  }, [viewBox]);

  // Cancel any in-flight rAF animation on unmount
  useEffect(() => {
    return () => {
      if (animRef.current != null) {
        cancelAnimationFrame(animRef.current);
        animRef.current = null;
      }
    };
  }, []);

  // Keyboard: Escape cancels wire, Delete removes selected wire
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setWireStart(null);
        setWireCorner(null);
        setWirePhase(null);
        setCursorPos(null);
        setMarquee(null);
        onSelect(new Set());
      }
      // Delete/Backspace handled by parent via PropertyPanel
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSelect, selectedIds, schematic.wires]);

  // Reset wire state when switching away from wire mode
  useEffect(() => {
    if (mode !== "wire") {
      setWireStart(null);
      setWireCorner(null);
      setWirePhase(null);
      setCursorPos(null);
    }
  }, [mode]);

  // ── Wire preview lines ─────────────────────────────────────────────
  const wirePreviewLines = useMemo(() => {
    if (!wireStart || !cursorPos) return null;

    if (wirePhase === "first") {
      // L-shaped preview from start to cursor
      const corner = computeCorner(wireStart, cursorPos);
      return (
        <>
          <line
            x1={wireStart.x} y1={wireStart.y} x2={corner.x} y2={corner.y}
            stroke="var(--color-selection)" strokeWidth={2} strokeDasharray="4,4" pointerEvents="none"
          />
          <line
            x1={corner.x} y1={corner.y} x2={cursorPos.x} y2={cursorPos.y}
            stroke="var(--color-selection)" strokeWidth={2} strokeDasharray="4,4" pointerEvents="none"
          />
          <circle cx={corner.x} cy={corner.y} r={3} fill="var(--color-selection)" pointerEvents="none" />
        </>
      );
    }

    if (wirePhase === "second" && wireCorner) {
      // Straight line from corner to cursor
      return (
        <line
          x1={wireCorner.x} y1={wireCorner.y} x2={cursorPos.x} y2={cursorPos.y}
          stroke="var(--color-selection)" strokeWidth={2} strokeDasharray="4,4" pointerEvents="none"
        />
      );
    }

    return null;
  }, [wireStart, wireCorner, wirePhase, cursorPos, computeCorner]);

  // ── Nearest pin highlight ──────────────────────────────────────────
  const nearestPin = useMemo(() => {
    if (mode !== "wire" || !cursorPos) return null;
    let best: { x: number; y: number } | null = null;
    let bestDist = PIN_SNAP_RADIUS;
    for (const pin of allPins) {
      const dist = Math.abs(pin.x - cursorPos.x) + Math.abs(pin.y - cursorPos.y);
      if (dist < bestDist) {
        bestDist = dist;
        best = { x: pin.x, y: pin.y };
      }
    }
    return best;
  }, [mode, cursorPos, allPins]);

  const renderComponent = (comp: Component) => {
    const dictComp = dictionary?.components[comp.type];
    const isSelected = selectedIds.has(comp.id);
    const rotTransform = dictComp
      ? getRotationTransform(comp.rotation, dictComp.symbol.width, dictComp.symbol.height)
      : "";
    return (
      <g
        key={comp.id}
        transform={`translate(${comp.position.x}, ${comp.position.y})`}
        onMouseDown={(e) => startDrag(comp.id, e)}
        style={{ cursor: mode === "select" ? "grab" : "crosshair", pointerEvents: mode === "wire" ? "none" : "auto" }}
      >
        {/* Invisible hit area for easier selection */}
        <rect
          x={-10} y={-14}
          width={(dictComp?.symbol.width ?? 64) + 20}
          height={(dictComp?.symbol.height ?? 32) + 32}
          fill="transparent"
        />
        {isSelected && dictComp && (
          <rect
            x={-4} y={-4}
            width={dictComp.symbol.width + 8}
            height={dictComp.symbol.height + 8}
            fill="none" stroke="var(--color-selection)" strokeWidth={2} strokeDasharray="4,4"
          />
        )}
        <g transform={rotTransform}>
          {dictComp ? (
            <path d={dictComp.symbol.svgPath} fill="none" stroke="var(--color-component)" strokeWidth={2} />
          ) : (
            <rect width={64} height={32} fill="none" stroke="var(--color-component)" strokeWidth={2} />
          )}
        </g>
        {(() => {
          const w = dictComp?.symbol.width ?? 64;
          const h = dictComp?.symbol.height ?? 32;
          const isVert = comp.rotation === "R0" || comp.rotation === "R180";

          let nameX: number, nameY: number, valX: number, valY: number;
          let anchor: "start" | "middle";

          if (isVert) {
            anchor = "start";
            nameX = w + 4;
            nameY = h * 0.35;
            valX = w + 4;
            valY = h * 0.7;
          } else {
            const visTop = (h - w) / 2;
            const visBottom = (h + w) / 2;
            anchor = "middle";
            nameX = w / 2;
            nameY = visTop - 6;
            valX = w / 2;
            valY = visBottom + 14;
          }

          return (
            <>
              <text x={nameX} y={nameY} textAnchor={anchor} dominantBaseline="auto" fontSize={12} fill="var(--color-component)">
                {comp.instanceName}
              </text>
              <text x={valX} y={valY} textAnchor={anchor} dominantBaseline="auto" fontSize={10} fill="var(--color-component)">
                {comp.value}
              </text>
            </>
          );
        })()}
      </g>
    );
  };

  const zoomPercent = Math.round((schematic.sheet.width / viewBox.w) * 100);

  return (
    <div style={{ flex: 2, position: "relative", overflow: "hidden" }}>
      <svg
        ref={svgRef}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
        style={{ width: "100%", height: "100%", background: "var(--bg-editor-outside)", cursor: mode === "wire" ? "crosshair" : "default" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onContextMenu={(e) => e.preventDefault()}
      >
        <defs>
          <pattern id="grid" width={16} height={16} patternUnits="userSpaceOnUse">
            <circle cx={8} cy={8} r={1.5} fill="var(--color-grid)" />
          </pattern>
        </defs>
        {/* Sheet area */}
        <rect
          x={0} y={0}
          width={schematic.sheet.width} height={schematic.sheet.height}
          fill="var(--bg-editor)"
          stroke="var(--color-border)"
          strokeWidth={2}
        />
        {showGrid && (
          <rect
            x={0} y={0}
            width={schematic.sheet.width} height={schematic.sheet.height}
            fill="url(#grid)"
          />
        )}

        {/* Pin highlights in wire mode */}
        {mode === "wire" && allPins.map((pin, i) => (
          <circle
            key={`pin-${i}`}
            cx={pin.x} cy={pin.y} r={4}
            fill="none"
            stroke="var(--color-accent, #1976d2)"
            strokeWidth={1.5}
            opacity={0.6}
            pointerEvents="none"
          />
        ))}

        {/* Nearest pin glow */}
        {nearestPin && (
          <circle
            cx={nearestPin.x} cy={nearestPin.y} r={7}
            fill="var(--color-accent, #1976d2)"
            opacity={0.3}
            pointerEvents="none"
          />
        )}

        {/* Wires */}
        {schematic.wires.map((wire) => {
          const isWireSelected = selectedIds.has(wire.id);
          return (
            <g key={wire.id}>
              {/* Invisible wide hit area for easier clicking */}
              <line
                x1={wire.from.x} y1={wire.from.y} x2={wire.to.x} y2={wire.to.y}
                stroke="transparent"
                strokeWidth={12}
                onClick={(e) => {
                  e.stopPropagation();
                  if (e.shiftKey) {
                    const next = new Set(selectedIds);
                    if (next.has(wire.id)) next.delete(wire.id);
                    else next.add(wire.id);
                    onSelect(next);
                  } else {
                    onSelect(new Set([wire.id]));
                  }
                }}
                style={{ cursor: "pointer" }}
              />
              {/* Visible wire */}
              <line
                x1={wire.from.x} y1={wire.from.y} x2={wire.to.x} y2={wire.to.y}
                stroke={isWireSelected ? "var(--color-selection)" : "var(--color-component)"}
                strokeWidth={isWireSelected ? 3 : 2}
                pointerEvents="none"
              />
            </g>
          );
        })}

        {/* Marquee selection rectangle */}
        {marquee && (
          <rect
            x={Math.min(marquee.start.x, marquee.end.x)}
            y={Math.min(marquee.start.y, marquee.end.y)}
            width={Math.abs(marquee.end.x - marquee.start.x)}
            height={Math.abs(marquee.end.y - marquee.start.y)}
            fill="var(--color-selection)"
            fillOpacity={0.1}
            stroke="var(--color-selection)"
            strokeWidth={1}
            strokeDasharray="4,4"
            pointerEvents="none"
          />
        )}

        {/* Wire preview */}
        {wirePreviewLines}

        {/* Cursor dot in wire mode */}
        {mode === "wire" && cursorPos && (
          <circle
            cx={cursorPos.x} cy={cursorPos.y} r={3}
            fill="var(--color-selection)"
            pointerEvents="none"
          />
        )}

        {schematic.components.map(renderComponent)}
        {schematic.flags.map((flag) => {
          const isFlagSelected = selectedIds.has(flag.id);
          return (
          <g key={flag.id} transform={`translate(${flag.position.x}, ${flag.position.y})`}
            onClick={(e) => { e.stopPropagation(); onSelect(new Set([flag.id])); }}
            style={{ cursor: "pointer" }}
          >
            {/* Hit area */}
            <rect x={-15} y={-15} width={30} height={30} fill="transparent" />
            {isFlagSelected && (
              <rect x={-12} y={-12} width={24} height={24} fill="none" stroke="var(--color-selection)" strokeWidth={1} strokeDasharray="3,3" />
            )}
            {flag.name === "0" ? (
              <>
                <line x1={0} y1={0} x2={0} y2={10} stroke={isFlagSelected ? "var(--color-selection)" : "var(--color-component)"} strokeWidth={2} />
                <line x1={-10} y1={10} x2={10} y2={10} stroke={isFlagSelected ? "var(--color-selection)" : "var(--color-component)"} strokeWidth={2} />
                <line x1={-6} y1={14} x2={6} y2={14} stroke={isFlagSelected ? "var(--color-selection)" : "var(--color-component)"} strokeWidth={2} />
                <line x1={-2} y1={18} x2={2} y2={18} stroke={isFlagSelected ? "var(--color-selection)" : "var(--color-component)"} strokeWidth={2} />
              </>
            ) : (
              <>
                <line x1={0} y1={0} x2={0} y2={-5} stroke={isFlagSelected ? "var(--color-selection)" : "var(--color-component)"} strokeWidth={1} />
                <text x={2} y={-8} fontSize={11} fill={isFlagSelected ? "var(--color-selection)" : "var(--color-component)"}>{flag.name}</text>
              </>
            )}
          </g>
          );
        })}
        {schematic.text.map((t) => (
          <text key={t.id} x={t.position.x} y={t.position.y} fontSize={11} fill="var(--color-text)">
            {t.content}
          </text>
        ))}
      </svg>

      {/* Bottom bar overlay */}
      <div
        style={{
          position: "absolute",
          bottom: 8,
          left: 8,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        {/* Zoom controls */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            background: "var(--bg-panel)",
            border: "1px solid var(--color-border)",
            borderRadius: 6,
            padding: "2px 4px",
            boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
          }}
        >
          <button onClick={() => zoomBy(1.25)} style={zoomBtnStyle} title="Zoom out">-</button>
          <button onClick={zoomFit} style={{ ...zoomBtnStyle, minWidth: 44, fontSize: 11 }} title="Fit to sheet">
            {zoomPercent}%
          </button>
          <button onClick={() => zoomBy(0.8)} style={zoomBtnStyle} title="Zoom in">+</button>
        </div>

        {/* Canvas size */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            background: "var(--bg-panel)",
            border: "1px solid var(--color-border)",
            borderRadius: 6,
            padding: "2px 6px",
            boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
            fontSize: 11,
            color: "var(--color-text)",
          }}
        >
          <span style={{ color: "var(--color-text-muted)" }}>Sheet</span>
          <input
            type="number"
            value={schematic.sheet.width}
            min={64}
            max={9999}
            onChange={(e) => {
              const v = Math.max(64, Math.min(9999, Number(e.target.value) || 64));
              onSetSheet(v, schematic.sheet.height);
            }}
            style={sheetInputStyle}
            title="Sheet width"
          />
          <span style={{ color: "var(--color-text-muted)" }}>x</span>
          <input
            type="number"
            value={schematic.sheet.height}
            min={64}
            max={9999}
            onChange={(e) => {
              const v = Math.max(64, Math.min(9999, Number(e.target.value) || 64));
              onSetSheet(schematic.sheet.width, v);
            }}
            style={sheetInputStyle}
            title="Sheet height"
          />
        </div>
      </div>
    </div>
  );
}

const zoomBtnStyle: React.CSSProperties = {
  padding: "2px 8px",
  border: "1px solid var(--color-border)",
  borderRadius: 4,
  background: "var(--bg-canvas, var(--bg-panel))",
  color: "var(--color-text)",
  cursor: "pointer",
  fontSize: 14,
  fontWeight: "bold",
  lineHeight: 1,
};

const sheetInputStyle: React.CSSProperties = {
  width: 52,
  padding: "1px 4px",
  border: "1px solid var(--color-border)",
  borderRadius: 3,
  background: "var(--bg-canvas, var(--bg-panel))",
  color: "var(--color-text)",
  fontSize: 11,
  textAlign: "center",
};
