import { useState } from "react";

interface ScreenshotPanelProps {
  imageUrl: string | null;
}

export function ScreenshotPanel({ imageUrl }: ScreenshotPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  if (!imageUrl) {
    return (
      <div style={{ padding: 12, color: "var(--color-text-muted)", fontSize: 12, textAlign: "center", borderTop: "1px solid var(--color-border)" }}>
        Upload an image to see it here
      </div>
    );
  }

  return (
    <>
      <div style={{ borderTop: "1px solid var(--color-border)", display: "flex", flexDirection: "column", height: expanded ? "50%" : 150, minHeight: 80 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "2px 8px", fontSize: 12, fontWeight: "bold", color: "var(--color-text)", borderBottom: "1px solid var(--color-border)", background: "var(--bg-panel)" }}>
          <span>Screenshot</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button onClick={() => setExpanded(e => !e)} style={{ fontSize: 10, padding: "1px 4px" }} title={expanded ? "Collapse" : "Expand"}>
              {expanded ? "▼" : "▲"}
            </button>
            <button onClick={() => setFullscreen(true)} style={{ fontSize: 10, padding: "1px 4px" }} title="Fullscreen">⛶</button>
          </div>
        </div>
        <div style={{ flex: 1, overflow: "auto", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <img src={imageUrl} alt="LTspice screenshot" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
        </div>
      </div>
      {fullscreen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "var(--bg-backdrop)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }} onClick={() => setFullscreen(false)}>
          <img src={imageUrl} alt="Fullscreen" style={{ maxWidth: "95vw", maxHeight: "95vh", objectFit: "contain" }} onClick={e => e.stopPropagation()} />
          <button onClick={() => setFullscreen(false)} style={{ position: "absolute", top: 16, right: 16, fontSize: 24, background: "var(--bg-panel)", color: "var(--color-text)", border: "none", borderRadius: 4, padding: "4px 12px", cursor: "pointer" }}>✕</button>
        </div>
      )}
    </>
  );
}
