import type { Component, Schematic } from "../types/schematic";

interface PropertyPanelProps {
  schematic: Schematic;
  selectedId: string | null;
  onUpdateComponent: (id: string, updates: Partial<Component>) => void;
  onDeleteComponent: (id: string) => void;
  onDeleteWire: (id: string) => void;
  onDeleteFlag: (id: string) => void;
}

export function PropertyPanel({
  schematic,
  selectedId,
  onUpdateComponent,
  onDeleteComponent,
  onDeleteWire,
  onDeleteFlag,
}: PropertyPanelProps) {
  if (!selectedId) {
    return (
      <div style={{ padding: 12, color: "#999", fontSize: 13 }}>
        Select a component to edit its properties
      </div>
    );
  }

  const comp = schematic.components.find((c) => c.id === selectedId);
  if (comp) {
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0 }}>Component: {comp.type}</h4>
        <label style={{ fontSize: 12 }}>
          Instance Name
          <input value={comp.instanceName} onChange={(e) => onUpdateComponent(comp.id, { instanceName: e.target.value })} style={{ width: "100%", marginTop: 2 }} />
        </label>
        <label style={{ fontSize: 12 }}>
          Value
          <input value={comp.value} onChange={(e) => onUpdateComponent(comp.id, { value: e.target.value })} style={{ width: "100%", marginTop: 2 }} />
        </label>
        {comp.value2 !== undefined && (
          <label style={{ fontSize: 12 }}>
            Value2
            <input value={comp.value2 ?? ""} onChange={(e) => onUpdateComponent(comp.id, { value2: e.target.value })} style={{ width: "100%", marginTop: 2 }} />
          </label>
        )}
        <label style={{ fontSize: 12 }}>
          Rotation
          <select value={comp.rotation} onChange={(e) => onUpdateComponent(comp.id, { rotation: e.target.value })} style={{ width: "100%", marginTop: 2 }}>
            {["R0", "R90", "R180", "R270", "M0", "M90"].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: 12 }}>X: {comp.position.x}, Y: {comp.position.y}</label>
        <button onClick={() => onDeleteComponent(comp.id)} style={{ color: "red", marginTop: 8 }}>Delete Component</button>
      </div>
    );
  }

  const wire = schematic.wires.find((w) => w.id === selectedId);
  if (wire) {
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0 }}>Wire</h4>
        <span style={{ fontSize: 12 }}>({wire.from.x}, {wire.from.y}) to ({wire.to.x}, {wire.to.y})</span>
        <button onClick={() => onDeleteWire(wire.id)} style={{ color: "red", marginTop: 8 }}>Delete Wire</button>
      </div>
    );
  }

  const flag = schematic.flags.find((f) => f.id === selectedId);
  if (flag) {
    return (
      <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        <h4 style={{ margin: 0 }}>Flag: {flag.name}</h4>
        <button onClick={() => onDeleteFlag(flag.id)} style={{ color: "red", marginTop: 8 }}>Delete Flag</button>
      </div>
    );
  }

  return <div style={{ padding: 12, color: "#999" }}>Unknown selection</div>;
}
