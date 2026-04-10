import { useState, useCallback } from "react";

interface ScreenshotPanelProps {
  imageUrl: string | null;
  onUpload?: (file: File) => void;
}

export function ScreenshotPanel({ imageUrl, onUpload }: ScreenshotPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [dragging, setDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.type.startsWith("image/") && onUpload) {
        onUpload(file);
      }
    },
    [onUpload],
  );

  const dropZoneStyle: React.CSSProperties = dragging
    ? { outline: "2px dashed var(--color-accent, #1976d2)", outlineOffset: -2, background: "var(--bg-canvas)" }
    : {};

  if (!imageUrl) {
    return (
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          padding: 24,
          color: "var(--color-text-muted)",
          fontSize: 12,
          textAlign: "center",
          borderTop: "1px solid var(--color-border)",
          cursor: onUpload ? "pointer" : "default",
          ...dropZoneStyle,
        }}
      >
        {dragging ? "Drop image here" : "Drag & drop an image here, or click Upload Image"}
      </div>
    );
  }

  return (
    <>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        style={{
          borderTop: "1px solid var(--color-border)",
          display: "flex",
          flexDirection: "column",
          height: expanded ? "50%" : 150,
          minHeight: 80,
          ...dropZoneStyle,
        }}
      >
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
          {dragging ? (
            <span style={{ color: "var(--color-accent, #1976d2)", fontSize: 13 }}>Drop to replace image</span>
          ) : (
            <img src={imageUrl} alt="LTspice screenshot" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
          )}
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
