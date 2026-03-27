interface AscPreviewProps {
  ascText: string;
  validation: { valid: boolean; errors: string[] } | null;
}

export function AscPreview({ ascText, validation }: AscPreviewProps) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", borderLeft: "1px solid #ccc" }}>
      <div style={{ padding: "4px 8px", borderBottom: "1px solid #ccc", fontSize: 12, fontWeight: "bold", display: "flex", justifyContent: "space-between" }}>
        <span>.asc Preview</span>
        {validation && (
          <span style={{ color: validation.valid ? "green" : "red" }}>
            {validation.valid ? "Valid" : `${validation.errors.length} error(s)`}
          </span>
        )}
      </div>
      {validation && !validation.valid && (
        <div style={{ padding: 8, background: "#fff0f0", fontSize: 11, color: "red", borderBottom: "1px solid #fcc" }}>
          {validation.errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
      <pre style={{ flex: 1, margin: 0, padding: 8, overflow: "auto", fontSize: 11, fontFamily: "monospace", background: "#fafafa", whiteSpace: "pre-wrap" }}>
        {ascText || "No .asc content yet. Upload an image and click Generate."}
      </pre>
    </div>
  );
}
