interface AscPreviewProps {
  ascText: string;
  validation: { valid: boolean; errors: string[] } | null;
}

export function AscPreview({ ascText, validation }: AscPreviewProps) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", borderLeft: "1px solid var(--color-border)" }}>
      <div style={{ padding: "4px 8px", borderBottom: "1px solid var(--color-border)", fontSize: 12, fontWeight: "bold", display: "flex", justifyContent: "space-between", color: "var(--color-text)" }}>
        <span>.asc Preview</span>
        {validation && (
          <span style={{ color: validation.valid ? "var(--color-success)" : "var(--color-error)" }}>
            {validation.valid ? "Valid" : `${validation.errors.length} error(s)`}
          </span>
        )}
      </div>
      {validation && !validation.valid && (
        <div style={{ padding: 8, background: "var(--color-error-bg, rgba(200,0,0,0.1))", fontSize: 11, color: "var(--color-error)", borderBottom: "1px solid var(--color-error)" }}>
          {validation.errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
      <pre style={{ flex: 1, margin: 0, padding: 8, overflow: "auto", fontSize: 11, fontFamily: "monospace", background: "var(--color-preview-bg)", color: "var(--color-text)", whiteSpace: "pre-wrap" }}>
        {ascText || "No .asc content yet. Upload an image and click Generate."}
      </pre>
    </div>
  );
}
