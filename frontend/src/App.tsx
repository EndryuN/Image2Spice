import { useState, useEffect, useCallback } from "react";
import { Toolbar } from "./components/Toolbar";
import { Editor } from "./components/Editor";
import { AscPreview } from "./components/AscPreview";
import { PropertyPanel } from "./components/PropertyPanel";
import { ComponentPalette } from "./components/ComponentPalette";
import { ScreenshotPanel } from "./components/ScreenshotPanel";
import { GenerateWizard } from "./components/GenerateWizard";
import { StoppedScreen } from "./components/StoppedScreen";
import { useSchematic } from "./hooks/useSchematic";
import { useTheme } from "./hooks/useTheme";
import { fetchDictionary, redrawWires, apiShutdown } from "./lib/api";
import { generateAsc } from "./lib/ascGenerator";
import { parseAsc } from "./lib/ascParser";
import type { Dictionary, LlmProvider } from "./types/schematic";

function App() {
  const [stopped, setStopped] = useState(false);
  const [dictionary, setDictionary] = useState<Dictionary | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<"select" | "wire">("select");
  const [status, setStatus] = useState("Ready");
  const [validation, _setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [showPalette, setShowPalette] = useState(true);
  const [connectionData, setConnectionData] = useState<{
    connections: Array<{ from: { component: string; pin: string }; to: { component: string; pin: string } }>;
    grounds: Array<{ component: string; pin: string }>;
    labels: Array<{ component: string; pin: string; label: string }>;
  } | null>(null);
  const [llmProvider, setLlmProvider] = useState<LlmProvider>(() => {
    const saved = localStorage.getItem("llmProvider");
    if (saved) {
      try { return JSON.parse(saved); } catch { /* ignore */ }
    }
    return { provider: "openai", model: "gpt-4o", apiKey: "" };
  });

  // Persist provider settings (including API key) to localStorage
  useEffect(() => {
    localStorage.setItem("llmProvider", JSON.stringify(llmProvider));
  }, [llmProvider]);

  const { theme, toggleTheme } = useTheme();

  const {
    schematic,
    loadSchematic,
    clearSchematic,
    setSheet,
    moveComponent,
    updateComponent,
    addComponent,
    deleteComponent,
    addWire,
    deleteWire,
    deleteWires,
    clearAllWires,
    addFlag,
    deleteFlag,
    undo,
    redo,
    canUndo,
    canRedo,
  } = useSchematic();

  const ascText = generateAsc(schematic, dictionary);

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
    if (file.name.endsWith(".asc")) {
      // Import .asc file directly into editor
      file.text().then((text) => {
        const result = parseAsc(text, dictionary);
        if (result.errors.length > 0) {
          setStatus(`Imported with ${result.errors.length} warning(s): ${result.errors[0]}`);
        } else {
          setStatus(`Imported ${result.schematic.components.length} components, ${result.schematic.wires.length} wires, ${result.schematic.flags.length} flags.`);
        }
        loadSchematic(result.schematic);
      });
      return;
    }
    if (file.type === "image/svg+xml") {
      // Rasterize SVG to PNG for vision model compatibility
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth || 1024;
        canvas.height = img.naturalHeight || 768;
        const ctx = canvas.getContext("2d")!;
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0);
        canvas.toBlob((blob) => {
          URL.revokeObjectURL(url);
          if (blob) {
            const pngFile = new File([blob], file.name.replace(/\.svg$/i, ".png"), { type: "image/png" });
            setImageFile(pngFile);
            setImageUrl(URL.createObjectURL(pngFile));
            setStatus("SVG converted to PNG. Click Generate to analyze.");
          }
        }, "image/png");
      };
      img.src = url;
    } else {
      setImageFile(file);
      setImageUrl(URL.createObjectURL(file));
      setStatus("Image loaded. Click Generate to analyze.");
    }
  }, []);

  const handleGenerate = useCallback(() => {
    if (!imageFile) return;
    setWizardOpen(true);
  }, [imageFile]);

  const handleClear = useCallback(() => {
    clearSchematic();
    setImageFile(null);
    setImageUrl(null);
    setSelectedIds(new Set());
    setStatus("Cleared. Upload a new image or .asc file.");
  }, [clearSchematic]);

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

  const handleRedrawWires = useCallback(async () => {
    if (!connectionData || schematic.components.length === 0) return;
    setStatus("Redrawing wires...");
    try {
      const result = await redrawWires({
        components: schematic.components.map((c) => ({
          instanceName: c.instanceName,
          type: c.type,
          value: c.value,
          position: c.position,
          rotation: c.rotation,
        })),
        ...connectionData,
      });
      // Replace all wires and flags with the new ones
      const newWires = result.wires.map((w, i) => ({
        id: `rw-${i}`,
        from: { x: w.x1, y: w.y1 },
        to: { x: w.x2, y: w.y2 },
      }));
      const newFlags = result.flags.map((f, i) => ({
        id: `rf-${i}`,
        name: f.name,
        position: { x: f.x, y: f.y },
      }));
      loadSchematic({
        ...schematic,
        wires: newWires,
        flags: newFlags,
      });
      setStatus(`Redrawn: ${newWires.length} wires, ${newFlags.length} flags`);
    } catch (err) {
      setStatus(`Redraw failed: ${err instanceof Error ? err.message : err}`);
    }
  }, [connectionData, schematic, loadSchematic]);

  const handleExit = async () => {
    if (stopped) return;
    setStopped(true);
    try {
      await apiShutdown();
    } catch {
      // Backend may already be down
    }
  };

  if (stopped) {
    return <StoppedScreen />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg-panel)", color: "var(--color-text)" }}>
      <Toolbar
        onUpload={handleUpload}
        onGenerate={handleGenerate}
        onRedrawWires={handleRedrawWires}
        canRedraw={!!connectionData && schematic.components.length > 0}
        onExport={handleExport}
        onClear={handleClear}
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
        onExit={handleExit}
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
          selectedIds={selectedIds}
          onSelect={setSelectedIds}
          onMoveComponent={moveComponent}
          onAddWire={addWire}
          onSetSheet={setSheet}
          onToggleMode={() => setMode((m) => (m === "select" ? "wire" : "select"))}
          mode={mode}
          showGrid={showGrid}
        />

        {/* Right panel: property + preview + screenshot */}
        <div style={{ width: 300, display: "flex", flexDirection: "column", borderLeft: "1px solid var(--color-border)" }}>
          <div style={{ borderBottom: "1px solid var(--color-border)", minHeight: 120, maxHeight: "50%", overflow: "auto" }}>
            <PropertyPanel
              schematic={schematic}
              selectedIds={selectedIds}
              onUpdateComponent={updateComponent}
              onDeleteComponent={deleteComponent}
              onDeleteWire={deleteWire}
              onDeleteFlag={deleteFlag}
              onDeleteWires={deleteWires}
              onClearAllWires={clearAllWires}
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
          onLoadSchematic={loadSchematic}
          onConnectionData={setConnectionData}
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
