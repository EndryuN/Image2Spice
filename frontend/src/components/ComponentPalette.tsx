import type { Dictionary } from "../types/schematic";

interface ComponentPaletteProps {
  dictionary: Dictionary | null;
  onAddComponent: (type: string) => void;
  mode: "select" | "wire";
  onModeChange: (mode: "select" | "wire") => void;
  onAddFlag: () => void;
}

export function ComponentPalette({
  dictionary,
  onAddComponent,
  mode,
  onModeChange,
  onAddFlag,
}: ComponentPaletteProps) {
  if (!dictionary) {
    return <div style={{ padding: 8, color: "#999", fontSize: 12 }}>Loading dictionary...</div>;
  }

  const categories = new Map<string, string[]>();
  for (const [id, comp] of Object.entries(dictionary.components)) {
    const cat = comp.category;
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(id);
  }

  return (
    <div style={{ width: 160, borderRight: "1px solid #ccc", overflow: "auto", fontSize: 12, background: "#fafafa" }}>
      <div style={{ padding: 8, borderBottom: "1px solid #eee" }}>
        <strong>Tools</strong>
        <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
          <button onClick={() => onModeChange("select")} style={{ flex: 1, fontWeight: mode === "select" ? "bold" : "normal", background: mode === "select" ? "#ddd" : "#fff" }}>Select</button>
          <button onClick={() => onModeChange("wire")} style={{ flex: 1, fontWeight: mode === "wire" ? "bold" : "normal", background: mode === "wire" ? "#ddd" : "#fff" }}>Wire</button>
        </div>
        <button onClick={onAddFlag} style={{ width: "100%", marginTop: 4 }}>+ Flag</button>
      </div>
      {[...categories.entries()].map(([cat, ids]) => (
        <div key={cat} style={{ padding: 8, borderBottom: "1px solid #eee" }}>
          <strong style={{ textTransform: "capitalize" }}>{cat}</strong>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
            {ids.map((id) => (
              <button key={id} onClick={() => onAddComponent(id)} style={{ textAlign: "left", padding: "2px 4px" }}>
                {dictionary.components[id].displayName}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
