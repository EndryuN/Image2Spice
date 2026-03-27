import { useState, useEffect, useCallback } from "react";
import { Toolbar } from "./components/Toolbar";
import { ImagePanel } from "./components/ImagePanel";
import { Editor } from "./components/Editor";
import { AscPreview } from "./components/AscPreview";
import { PropertyPanel } from "./components/PropertyPanel";
import { ComponentPalette } from "./components/ComponentPalette";
import { useSchematic } from "./hooks/useSchematic";
import { fetchDictionary, generateFromImage } from "./lib/api";
import { generateAsc } from "./lib/ascGenerator";
import type { Dictionary } from "./types/schematic";

function App() {
  const [dictionary, setDictionary] = useState<Dictionary | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [generating, setGenerating] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<"select" | "wire">("select");
  const [status, setStatus] = useState("Ready");
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null);

  const {
    schematic,
    loadFromGenerateResponse,
    moveComponent,
    updateComponent,
    addComponent,
    deleteComponent,
    addWire,
    deleteWire,
    addFlag,
    deleteFlag,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useSchematic();

  const ascText = generateAsc(schematic);

  useEffect(() => {
    fetchDictionary()
      .then(setDictionary)
      .catch((err) => setStatus(`Error loading dictionary: ${err.message}`));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "z") { e.preventDefault(); undo(); }
      else if (e.ctrlKey && e.key === "y") { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [undo, redo]);

  const handleUpload = useCallback((file: File) => {
    setImageFile(file);
    setImageUrl(URL.createObjectURL(file));
    setStatus("Image loaded. Click Generate to analyze.");
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!imageFile) return;
    setGenerating(true);
    setStatus("Analyzing image with vision model...");
    try {
      const resp = await generateFromImage(imageFile);
      loadFromGenerateResponse(resp);
      setValidation(resp.validation);
      setStatus(
        resp.validation.valid
          ? "Generation complete. Review and adjust in the editor."
          : `Generated with ${resp.validation.errors.length} validation error(s).`
      );
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setStatus(`Generation failed: ${message}`);
    } finally {
      setGenerating(false);
    }
  }, [imageFile, loadFromGenerateResponse]);

  const handleExport = useCallback(() => {
    const blob = new Blob([ascText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "schematic.asc";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Exported schematic.asc");
  }, [ascText]);

  const handleAddComponent = useCallback(
    (type: string) => {
      const name = `${type.charAt(0).toUpperCase()}${schematic.components.filter((c) => c.type === type).length + 1}`;
      addComponent(type, name, "1k", { x: 400, y: 300 });
    },
    [addComponent, schematic.components]
  );

  const handleAddFlag = useCallback(() => {
    const name = prompt("Flag name (use '0' for ground):");
    if (name) addFlag(name, { x: 400, y: 300 });
  }, [addFlag]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <Toolbar
        onUpload={handleUpload}
        onGenerate={handleGenerate}
        onExport={handleExport}
        onUndo={undo}
        onRedo={redo}
        canUndo={canUndo}
        canRedo={canRedo}
        generating={generating}
        imageLoaded={!!imageFile}
      />
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <ComponentPalette
          dictionary={dictionary}
          onAddComponent={handleAddComponent}
          mode={mode}
          onModeChange={setMode}
          onAddFlag={handleAddFlag}
        />
        <ImagePanel imageUrl={imageUrl} />
        <Editor
          schematic={schematic}
          dictionary={dictionary}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveComponent={moveComponent}
          onAddWire={addWire}
          mode={mode}
        />
        <div style={{ width: 280, display: "flex", flexDirection: "column", borderLeft: "1px solid #ccc" }}>
          <div style={{ borderBottom: "1px solid #ccc", maxHeight: "50%", overflow: "auto" }}>
            <PropertyPanel
              schematic={schematic}
              selectedId={selectedId}
              onUpdateComponent={updateComponent}
              onDeleteComponent={deleteComponent}
              onDeleteWire={deleteWire}
              onDeleteFlag={deleteFlag}
            />
          </div>
          <AscPreview ascText={ascText} validation={validation} />
        </div>
      </div>
      <footer style={{ padding: "4px 8px", borderTop: "1px solid #ccc", fontSize: 12, background: "#f5f5f5" }}>
        {status}
      </footer>
    </div>
  );
}

export default App;
