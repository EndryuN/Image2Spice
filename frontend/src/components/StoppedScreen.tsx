export function StoppedScreen() {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg-editor-outside)",
        color: "var(--color-text)",
        fontFamily: "system-ui, sans-serif",
        gap: 16,
      }}
    >
      <h1 style={{ margin: 0, fontSize: 32 }}>image2spice has stopped</h1>
      <p style={{ margin: 0, opacity: 0.7 }}>You can close this tab.</p>
    </div>
  );
}
