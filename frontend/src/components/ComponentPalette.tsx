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
    return <div style={{ padding: 8, color: "var(--color-text-muted)", fontSize: 12 }}>Loading dictionary...</div>;
  }

  const categories = new Map<string, string[]>();
  for (const [id, comp] of Object.entries(dictionary.components)) {
    const cat = comp.category;
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(id);
  }

  return (
    <div style={{ width: 160, borderRight: "1px solid var(--color-border)", overflow: "auto", fontSize: 12, background: "var(--bg-panel)", color: "var(--color-text)" }}>
      <div style={{ padding: 8, borderBottom: "1px solid var(--color-border)" }}>
        <strong>Tools</strong>
        <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
          <button onClick={() => onModeChange("select")} style={{ flex: 1, fontWeight: mode === "select" ? "bold" : "normal", background: mode === "select" ? "var(--color-accent, #1976d2)" : "var(--bg-canvas)", color: mode === "select" ? "#fff" : "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 3 }}>Select</button>
          <button onClick={() => onModeChange("wire")} style={{ flex: 1, fontWeight: mode === "wire" ? "bold" : "normal", background: mode === "wire" ? "var(--color-accent, #1976d2)" : "var(--bg-canvas)", color: mode === "wire" ? "#fff" : "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 3 }}>Wire</button>
        </div>
        <button onClick={onAddFlag} style={{ width: "100%", marginTop: 4, background: "var(--bg-canvas)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 3, padding: "2px 4px", cursor: "pointer" }}>+ Flag</button>
      </div>
      {[...categories.entries()].map(([cat, ids]) => (
        <div key={cat} style={{ padding: 8, borderBottom: "1px solid var(--color-border)" }}>
          <strong style={{ textTransform: "capitalize" }}>{cat}</strong>
          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 4 }}>
            {ids.map((id) => (
              <button key={id} onClick={() => onAddComponent(id)} style={{ textAlign: "left", padding: "2px 4px", background: "var(--bg-canvas)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 3, cursor: "pointer" }}>
                {dictionary.components[id].displayName}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
