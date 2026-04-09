import { useState, useEffect, useCallback } from "react";
import { Toolbar } from "./components/Toolbar";
import { Editor } from "./components/Editor";
import { AscPreview } from "./components/AscPreview";
import { PropertyPanel } from "./components/PropertyPanel";
import { ComponentPalette } from "./components/ComponentPalette";
import { ScreenshotPanel } from "./components/ScreenshotPanel";
import { GenerateWizard } from "./components/GenerateWizard";
import { useSchematic } from "./hooks/useSchematic";
import { useTheme } from "./hooks/useTheme";
import { fetchDictionary } from "./lib/api";
import { generateAsc } from "./lib/ascGenerator";
import type { Dictionary, LlmProvider } from "./types/schematic";

function App() {
  const [dictionary, setDictionary] = useState<Dictionary | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<"select" | "wire">("select");
  const [status, setStatus] = useState("Ready");
  const [validation, _setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [showPalette, setShowPalette] = useState(true);
  const [llmProvider, setLlmProvider] = useState<LlmProvider>({ provider: "local", model: "qwen3-vl:8b" });

  const { theme, toggleTheme } = useTheme();

  const {
    schematic,
    setSheet,
    moveComponent,
    updateComponent,
    addComponent,
    addComponentsBatch,
    deleteComponent,
    addWire,
    addWiresBatch,
    deleteWire,
    addFlag,
    addFlagsBatch,
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

  const handleGenerate = useCallback(() => {
    if (!imageFile) return;
    setWizardOpen(true);
  }, [imageFile]);

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
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg-panel)", color: "var(--color-text)" }}>
      <Toolbar
        onUpload={handleUpload}
        onGenerate={handleGenerate}
        onExport={handleExport}
        onUndo={undo}
        onRedo={redo}
        canUndo={canUndo}
        canRedo={canRedo}
        generating={false}
        imageLoaded={!!imageFile}
        showGrid={showGrid}
        onToggleGrid={() => setShowGrid((g) => !g)}
        theme={theme}
        onToggleTheme={toggleTheme}
        llmProvider={llmProvider}
        onProviderChange={setLlmProvider}
      />
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Collapsible palette */}
        <div style={{ display: "flex" }}>
          <button
            onClick={() => setShowPalette((p) => !p)}
            style={{
              writingMode: "vertical-rl",
              padding: "8px 2px",
              background: "var(--bg-panel)",
              border: "none",
              borderRight: "1px solid var(--color-border)",
              cursor: "pointer",
              color: "var(--color-text)",
              fontSize: 12,
            }}
          >
            {showPalette ? "◀" : "▶"}
          </button>
          {showPalette && (
            <ComponentPalette
              dictionary={dictionary}
              onAddComponent={handleAddComponent}
              mode={mode}
              onModeChange={setMode}
              onAddFlag={handleAddFlag}
            />
          )}
        </div>

        {/* Center: Editor takes all remaining space */}
        <Editor
          schematic={schematic}
          dictionary={dictionary}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onMoveComponent={moveComponent}
          onAddWire={addWire}
          mode={mode}
          showGrid={showGrid}
        />

        {/* Right panel: property + preview + screenshot */}
        <div style={{ width: 280, display: "flex", flexDirection: "column", borderLeft: "1px solid var(--color-border)" }}>
          <div style={{ borderBottom: "1px solid var(--color-border)", maxHeight: "30%", overflow: "auto" }}>
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
          <ScreenshotPanel imageUrl={imageUrl} onUpload={handleUpload} />
        </div>
      </div>

      <footer
        style={{
          padding: "4px 8px",
          borderTop: "1px solid var(--color-border)",
          fontSize: 12,
          background: "var(--bg-panel)",
          color: "var(--color-text)",
        }}
      >
        {status}
      </footer>

      {/* Wizard modal */}
      {wizardOpen && imageFile && (
        <GenerateWizard
          imageFile={imageFile}
          dictionary={dictionary}
          llmProvider={llmProvider}
          onSetSheet={setSheet}
          onAddComponentsBatch={addComponentsBatch}
          onAddWiresBatch={addWiresBatch}
          onAddFlagsBatch={addFlagsBatch}
          onClose={() => {
            setWizardOpen(false);
            setStatus("Wizard closed.");
          }}
        />
      )}
    </div>
  );
}

export default App;
