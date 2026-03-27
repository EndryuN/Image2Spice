import { useRef } from "react";

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
}: ToolbarProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: 8,
        borderBottom: "1px solid #ccc",
        alignItems: "center",
        background: "#f5f5f5",
      }}
    >
      <strong>image2asc</strong>
      <div style={{ width: 1, height: 24, background: "#ccc" }} />
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
      <div style={{ width: 1, height: 24, background: "#ccc" }} />
      <button onClick={onUndo} disabled={!canUndo}>Undo</button>
      <button onClick={onRedo} disabled={!canRedo}>Redo</button>
    </div>
  );
}
