import type { Component, Schematic } from "../types/schematic";

interface PropertyPanelProps {
  schematic: Schematic;
  selectedIds: Set<string>;
  onUpdateComponent: (id: string, updates: Partial<Component>) => void;
  onDeleteComponent: (id: string) => void;
  onDeleteWire: (id: string) => void;
  onDeleteFlag: (id: string) => void;
  onDeleteWires: (ids: string[]) => void;
  onRotateWires: (ids: string[], degrees?: number) => void;
  onClearAllWires: () => void;
}

export function PropertyPanel({
  schematic,
  selectedIds,
  onUpdateComponent,
  onDeleteComponent,
  onDeleteWire,
  onDeleteFlag,
  onDeleteWires,
  onRotateWires,
  onClearAllWires,
}: PropertyPanelProps) {
  if (selectedIds.size === 0) {
    return (
      <div style={{ padding: 12, color: "var(--color-text-muted)", fontSize: 13 }}>
        Select a component to edit its properties
        {schematic.wires.length > 0 && (
          <button
            onClick={onClearAllWires}
            style={{
              display: "block",
              marginTop: 12,
              padding: "4px 10px",
              border: "1px solid var(--color-error, #c62828)",
              borderRadius: 4,
              background: "transparent",
              color: "var(--color-error, #c62828)",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Clear All Wires ({schematic.wires.length})
          </button>
        )}
      </div>
    );
  }

  // Multi-wire selection
  const selectedWires = schematic.wires.filter((w) => selectedIds.has(w.id));
  const selectedComps = schematic.components.filter((c) => selectedIds.has(c.id));
  const selectedFlags = schematic.flags.filter((f) => selectedIds.has(f.id));

  if (selectedWires.length > 1 || (selectedWires.length >= 1 && selectedComps.length === 0 && selectedFlags.length === 0)) {
    if (selectedWires.length > 1) {
      return (
        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <h4 style={{ margin: 0, color: "var(--color-text)" }}>{selectedWires.length} Wires Selected</h4>
          <div style={{ fontSize: 12, color: "var(--color-text-muted)", maxHeight: 120, overflow: "auto" }}>
            {selectedWires.map((w) => (
              <div key={w.id} style={{ marginBottom: 2 }}>
                ({w.from.x},{w.from.y}) - ({w.to.x},{w.to.y})
              </div>
            ))}
          </div>
          <button
            onClick={() => onRotateWires(selectedWires.map((w) => w.id))}
            style={{ padding: "4px 10px", border: "1px solid var(--color-border)", borderRadius: 4, background: "transparent", color: "var(--color-text)", cursor: "pointer", fontSize: 12 }}
          >
            Rotate 45°
          </button>
          <button
            onClick={() => onDeleteWires(selectedWires.map((w) => w.id))}
            style={{ color: "var(--color-error, red)", marginTop: 4, padding: "4px 10px", border: "1px solid var(--color-error, red)", borderRadius: 4, background: "transparent", cursor: "pointer", fontSize: 12 }}
          >
            Delete {selectedWires.length} Wires
          </button>
        </div>
      );
    }
    // Single wire
    const wire = selectedWires[0];
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0, color: "var(--color-text)" }}>Wire</h4>
        <span style={{ fontSize: 12, color: "var(--color-text)" }}>({wire.from.x}, {wire.from.y}) to ({wire.to.x}, {wire.to.y})</span>
        <button
          onClick={() => onRotateWires([wire.id])}
          style={{ padding: "4px 10px", border: "1px solid var(--color-border)", borderRadius: 4, background: "transparent", color: "var(--color-text)", cursor: "pointer", fontSize: 12 }}
        >
          Rotate 45°
        </button>
        <button
          onClick={() => onDeleteWire(wire.id)}
          style={{ color: "var(--color-error, red)", marginTop: 4, padding: "4px 10px", border: "1px solid var(--color-error, red)", borderRadius: 4, background: "transparent", cursor: "pointer", fontSize: 12 }}
        >
          Delete Wire
        </button>
      </div>
    );
  }

  // Single component
  if (selectedComps.length === 1) {
    const comp = selectedComps[0];
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0, color: "var(--color-text)" }}>Component: {comp.type}</h4>
        <label style={{ fontSize: 12, color: "var(--color-text)" }}>
          Instance Name
          <input value={comp.instanceName} onChange={(e) => onUpdateComponent(comp.id, { instanceName: e.target.value })} style={inputStyle} />
        </label>
        <label style={{ fontSize: 12, color: "var(--color-text)" }}>
          Value
          <input value={comp.value} onChange={(e) => onUpdateComponent(comp.id, { value: e.target.value })} style={inputStyle} />
        </label>
        {comp.value2 !== undefined && (
          <label style={{ fontSize: 12, color: "var(--color-text)" }}>
            Value2
            <input value={comp.value2 ?? ""} onChange={(e) => onUpdateComponent(comp.id, { value2: e.target.value })} style={inputStyle} />
          </label>
        )}
        <label style={{ fontSize: 12, color: "var(--color-text)" }}>
          Rotation
          <select value={comp.rotation} onChange={(e) => onUpdateComponent(comp.id, { rotation: e.target.value })} style={inputStyle}>
            {["R0", "R90", "R180", "R270", "M0", "M90"].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: 12, color: "var(--color-text-muted)" }}>X: {comp.position.x}, Y: {comp.position.y}</label>
        <button
          onClick={() => onDeleteComponent(comp.id)}
          style={{ color: "var(--color-error, red)", marginTop: 4, padding: "4px 10px", border: "1px solid var(--color-error, red)", borderRadius: 4, background: "transparent", cursor: "pointer", fontSize: 12 }}
        >
          Delete Component
        </button>
      </div>
    );
  }

  // Single flag
  if (selectedFlags.length === 1) {
    const flag = selectedFlags[0];
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0, color: "var(--color-text)" }}>Flag: {flag.name}</h4>
        <button
          onClick={() => onDeleteFlag(flag.id)}
          style={{ color: "var(--color-error, red)", marginTop: 4, padding: "4px 10px", border: "1px solid var(--color-error, red)", borderRadius: 4, background: "transparent", cursor: "pointer", fontSize: 12 }}
        >
          Delete Flag
        </button>
      </div>
    );
  }

  // Mixed selection
  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <h4 style={{ margin: 0, color: "var(--color-text)" }}>
        {selectedIds.size} items selected
      </h4>
      <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
        {selectedComps.length > 0 && <div>{selectedComps.length} component(s)</div>}
        {selectedWires.length > 0 && <div>{selectedWires.length} wire(s)</div>}
        {selectedFlags.length > 0 && <div>{selectedFlags.length} flag(s)</div>}
      </div>
      {selectedWires.length > 0 && (
        <button
          onClick={() => onDeleteWires(selectedWires.map((w) => w.id))}
          style={{ color: "var(--color-error, red)", marginTop: 4, padding: "4px 10px", border: "1px solid var(--color-error, red)", borderRadius: 4, background: "transparent", cursor: "pointer", fontSize: 12 }}
        >
          Delete {selectedWires.length} Wire(s)
        </button>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  marginTop: 2,
  padding: "3px 6px",
  border: "1px solid var(--color-border)",
  borderRadius: 3,
  background: "var(--bg-canvas)",
  color: "var(--color-text)",
  fontSize: 12,
};
