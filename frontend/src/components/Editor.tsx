import { useRef, useState, useCallback, useEffect } from "react";
import type {
  Schematic,
  Component,
  Dictionary,
  Position,
} from "../types/schematic";

interface EditorProps {
  schematic: Schematic;
  dictionary: Dictionary | null;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveComponent: (id: string, pos: Position) => void;
  onAddWire: (from: Position, to: Position) => void;
  mode: "select" | "wire";
  showGrid: boolean;
}

export function Editor({
  schematic,
  dictionary,
  selectedId,
  onSelect,
  onMoveComponent,
  onAddWire,
  mode,
  showGrid,
}: EditorProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [viewBox, setViewBox] = useState({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
  const [dragging, setDragging] = useState<{
    id: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);
  const [wireStart, setWireStart] = useState<Position | null>(null);
  const [wirePreview, setWirePreview] = useState<Position | null>(null);
  const [panning, setPanning] = useState<{
    startX: number;
    startY: number;
    startVX: number;
    startVY: number;
  } | null>(null);

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

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (e.button === 1) {
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
        const pos = svgPoint(e.clientX, e.clientY);
        if (!wireStart) {
          setWireStart(pos);
          setWirePreview(pos);
        } else {
          onAddWire(wireStart, pos);
          setWireStart(null);
          setWirePreview(null);
        }
        return;
      }
      if (mode === "select" && e.button === 0) {
        onSelect(null);
      }
    },
    [mode, wireStart, svgPoint, onAddWire, onSelect, viewBox]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (panning) {
        const svg = svgRef.current;
        if (!svg) return;
        const rect = svg.getBoundingClientRect();
        const dx = ((e.clientX - panning.startX) / rect.width) * viewBox.w;
        const dy = ((e.clientY - panning.startY) / rect.height) * viewBox.h;
        setViewBox((v) => ({
          ...v,
          x: panning.startVX - dx,
          y: panning.startVY - dy,
        }));
        return;
      }
      if (dragging) {
        const pos = svgPoint(e.clientX, e.clientY);
        onMoveComponent(dragging.id, {
          x: pos.x - dragging.offsetX,
          y: pos.y - dragging.offsetY,
        });
        return;
      }
      if (wireStart) {
        setWirePreview(svgPoint(e.clientX, e.clientY));
      }
    },
    [panning, dragging, wireStart, svgPoint, onMoveComponent, viewBox]
  );

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    setPanning(null);
  }, []);

  const zoomBy = useCallback(
    (factor: number) => {
      setViewBox((v) => {
        const cx = v.x + v.w / 2;
        const cy = v.y + v.h / 2;
        const newW = v.w * factor;
        const newH = v.h * factor;
        return { x: cx - newW / 2, y: cy - newH / 2, w: newW, h: newH };
      });
    },
    []
  );

  const zoomFit = useCallback(() => {
    setViewBox({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
  }, [schematic.sheet.width, schematic.sheet.height]);

  const startDrag = useCallback(
    (compId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      onSelect(compId);
      if (mode !== "select") return;
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

  // Reset viewBox when sheet size changes
  useEffect(() => {
    setViewBox({ x: -20, y: -20, w: schematic.sheet.width + 40, h: schematic.sheet.height + 40 });
  }, [schematic.sheet.width, schematic.sheet.height]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setWireStart(null);
        setWirePreview(null);
        onSelect(null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSelect]);

  const renderComponent = (comp: Component) => {
    const dictComp = dictionary?.components[comp.type];
    const isSelected = comp.id === selectedId;
    const rotTransform = dictComp
      ? getRotationTransform(comp.rotation, dictComp.symbol.width, dictComp.symbol.height)
      : "";
    return (
      <g
        key={comp.id}
        transform={`translate(${comp.position.x}, ${comp.position.y})`}
        onMouseDown={(e) => startDrag(comp.id, e)}
        style={{ cursor: mode === "select" ? "grab" : "default" }}
      >
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
          {dictComp?.pins.map((pin) => (
            pin.position ? (
              <circle key={pin.name} cx={pin.position[0]} cy={pin.position[1]} r={3} fill="var(--color-component)" />
            ) : null
          ))}
        </g>
        <text x={dictComp ? dictComp.symbol.width / 2 : 32} y={-8} textAnchor="middle" fontSize={12} fill="var(--color-component)">
          {comp.instanceName}
        </text>
        <text x={dictComp ? dictComp.symbol.width / 2 : 32} y={(dictComp?.symbol.height ?? 32) + 14} textAnchor="middle" fontSize={10} fill="var(--color-component)">
          {comp.value}
        </text>
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
      >
        <defs>
          <pattern id="grid" width={16} height={16} patternUnits="userSpaceOnUse">
            <circle cx={0} cy={0} r={0.5} fill="var(--color-grid)" />
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
        {schematic.wires.map((wire) => (
          <line
            key={wire.id}
            x1={wire.from.x} y1={wire.from.y} x2={wire.to.x} y2={wire.to.y}
            stroke="var(--color-component)" strokeWidth={2}
            onClick={(e) => { e.stopPropagation(); onSelect(wire.id); }}
            style={{ cursor: "pointer" }}
          />
        ))}
        {wireStart && wirePreview && (
          <line
            x1={wireStart.x} y1={wireStart.y} x2={wirePreview.x} y2={wirePreview.y}
            stroke="var(--color-selection)" strokeWidth={1} strokeDasharray="4,4" pointerEvents="none"
          />
        )}
        {schematic.components.map(renderComponent)}
        {schematic.flags.map((flag) => (
          <g key={flag.id} transform={`translate(${flag.position.x}, ${flag.position.y})`}>
            {flag.name === "0" ? (
              <>
                <line x1={0} y1={0} x2={0} y2={10} stroke="var(--color-component)" strokeWidth={2} />
                <line x1={-10} y1={10} x2={10} y2={10} stroke="var(--color-component)" strokeWidth={2} />
                <line x1={-6} y1={14} x2={6} y2={14} stroke="var(--color-component)" strokeWidth={2} />
                <line x1={-2} y1={18} x2={2} y2={18} stroke="var(--color-component)" strokeWidth={2} />
              </>
            ) : (
              <>
                <line x1={0} y1={0} x2={0} y2={-5} stroke="var(--color-component)" strokeWidth={1} />
                <text x={2} y={-8} fontSize={11} fill="var(--color-component)">{flag.name}</text>
              </>
            )}
          </g>
        ))}
        {schematic.text.map((t) => (
          <text key={t.id} x={t.position.x} y={t.position.y} fontSize={11} fill="var(--color-text)">
            {t.content}
          </text>
        ))}
      </svg>

      {/* Zoom controls overlay */}
      <div
        style={{
          position: "absolute",
          bottom: 8,
          left: 8,
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
