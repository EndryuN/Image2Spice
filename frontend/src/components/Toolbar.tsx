import { useRef } from "react";
import { LlmStatus } from "./LlmStatus";
import type { LlmProvider } from "../types/schematic";

interface ToolbarProps {
  onUpload: (file: File) => void;
  onGenerate: () => void;
  onExport: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  generating: boolean;
  imageLoaded: boolean;
  showGrid: boolean;
  onToggleGrid: () => void;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  llmProvider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
}

export function Toolbar({
  onUpload,
  onGenerate,
  onExport,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  generating,
  imageLoaded,
  showGrid,
  onToggleGrid,
  theme,
  onToggleTheme,
  llmProvider,
  onProviderChange,
}: ToolbarProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: 8,
        borderBottom: "1px solid var(--color-border)",
        alignItems: "center",
        background: "var(--bg-panel)",
      }}
    >
      <strong>image2spice</strong>
      <div style={{ width: 1, height: 24, background: "var(--color-border)" }} />
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
        }}
      />
      <button onClick={() => fileRef.current?.click()}>Upload Image</button>
      <button onClick={onGenerate} disabled={!imageLoaded || generating}>
        {generating ? "Generating..." : "Generate"}
      </button>
      <button onClick={onExport}>Export .asc</button>
      <div style={{ width: 1, height: 24, background: "var(--color-border)" }} />
      <button onClick={onUndo} disabled={!canUndo}>Undo</button>
      <button onClick={onRedo} disabled={!canRedo}>Redo</button>
      <div style={{ width: 1, height: 24, background: "var(--color-border)" }} />
      <button onClick={onToggleGrid} title="Toggle Grid">
        {showGrid ? "Grid On" : "Grid Off"}
      </button>
      <button onClick={onToggleTheme} title="Toggle Theme">
        {theme === "light" ? "Dark" : "Light"}
      </button>
      <div style={{ flex: 1 }} />
      <LlmStatus provider={llmProvider} onProviderChange={onProviderChange} />
    </div>
  );
}
