import { useState, useCallback } from "react";
import type { Dictionary, WizardComponent } from "../types/schematic";
import {
  wizardIdentify,
  wizardDirectives,
  wizardLayout,
  wizardWires,
} from "../lib/api";

interface GenerateWizardProps {
  imageFile: File;
  dictionary: Dictionary | null;
  onAddComponent: (
    type: string,
    name: string,
    value: string,
    pos: { x: number; y: number },
    value2?: string
  ) => void;
  onAddWire: (from: { x: number; y: number }, to: { x: number; y: number }) => void;
  onAddFlag: (name: string, pos: { x: number; y: number }) => void;
  onAddText: (content: string, pos: { x: number; y: number }) => void;
  onClose: () => void;
}

type Step = 1 | 2 | 3 | 4 | 5 | 6; // 6 = done

export function GenerateWizard({
  imageFile,
  dictionary,
  onAddComponent,
  onAddWire,
  onAddFlag,
  onAddText,
  onClose,
}: GenerateWizardProps) {
  const [step, setStep] = useState<Step>(1);
  const [minimized, setMinimized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1: canvas
  const [canvasWidth, setCanvasWidth] = useState(880);
  const [canvasHeight, setCanvasHeight] = useState(680);

  // Step 2: components
  const [components, setComponents] = useState<WizardComponent[]>([]);

  // Step 3: directives
  const [directives, setDirectives] = useState<string[]>([]);

  // Step 4: positions
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});

  // Summary
  const [wireCount, setWireCount] = useState(0);
  const [flagCount, setFlagCount] = useState(0);

  const componentTypes = dictionary ? Object.keys(dictionary.components) : [];

  // ── Step transitions ────────────────────────────────────────────────────────

  const goStep1to2 = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await wizardIdentify(imageFile);
      setComponents(
        result.components.map((c) => ({ ...c, confirmed: false }))
      );
      setStep(2);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [imageFile]);

  const goStep2to3 = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await wizardDirectives(imageFile);
      setDirectives(result.directives);
      setStep(3);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [imageFile]);

  const goStep3to4 = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const confirmed = components.filter((c) => c.confirmed !== false);
      const result = await wizardLayout(imageFile, confirmed);
      setPositions(result.positions);

      // Place confirmed components in the editor
      confirmed.forEach((comp) => {
        const pos = result.positions[comp.instanceName] ?? { x: 400, y: 300 };
        onAddComponent(comp.type, comp.instanceName, comp.value, pos, comp.value2);
      });

      // Add directives as text
      directives.forEach((d, i) => {
        onAddText(d, { x: 50, y: 50 + i * 32 });
      });

      setStep(4);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [imageFile, components, directives, onAddComponent, onAddText]);

  const goStep4to5 = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const confirmed = components.filter((c) => c.confirmed !== false);
      const result = await wizardWires(imageFile, confirmed, positions);

      result.wires.forEach((w) => {
        onAddWire({ x: w.x1, y: w.y1 }, { x: w.x2, y: w.y2 });
      });
      result.flags.forEach((f) => {
        onAddFlag(f.name, { x: f.x, y: f.y });
      });

      setWireCount(result.wires.length);
      setFlagCount(result.flags.length);
      setStep(5);

      // Immediately mark as done
      setStep(6);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [imageFile, components, positions, onAddWire, onAddFlag]);

  // ── Component row helpers ───────────────────────────────────────────────────

  const updateComp = (idx: number, updates: Partial<WizardComponent>) => {
    setComponents((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, ...updates } : c))
    );
  };

  const deleteComp = (idx: number) => {
    setComponents((prev) => prev.filter((_, i) => i !== idx));
  };

  const confirmComp = (idx: number) => {
    updateComp(idx, { confirmed: true });
  };

  const addMissingComp = () => {
    setComponents((prev) => [
      ...prev,
      { type: componentTypes[0] ?? "res", instanceName: `R${prev.length + 1}`, value: "1k", confirmed: false },
    ]);
  };

  // ── Directives helpers ──────────────────────────────────────────────────────

  const updateDirective = (idx: number, val: string) => {
    setDirectives((prev) => prev.map((d, i) => (i === idx ? val : d)));
  };

  const deleteDirective = (idx: number) => {
    setDirectives((prev) => prev.filter((_, i) => i !== idx));
  };

  const addDirective = () => {
    setDirectives((prev) => [...prev, ".tran 1m"]);
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  if (minimized) {
    return (
      <div
        style={{
          position: "fixed",
          bottom: 24,
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 2000,
          background: "var(--bg-panel)",
          border: "1px solid var(--color-border)",
          borderRadius: 24,
          padding: "8px 20px",
          display: "flex",
          alignItems: "center",
          gap: 12,
          boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
          cursor: "default",
        }}
      >
        <span style={{ fontSize: 13, color: "var(--color-text)" }}>
          Generate Wizard — Step {step} of 5
        </span>
        <button
          onClick={() => setMinimized(false)}
          style={{
            padding: "2px 10px",
            borderRadius: 12,
            border: "1px solid var(--color-border)",
            background: "var(--bg-canvas)",
            color: "var(--color-text)",
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          Show
        </button>
        <button
          onClick={onClose}
          style={{
            padding: "2px 8px",
            borderRadius: 12,
            border: "1px solid var(--color-border)",
            background: "var(--bg-canvas)",
            color: "var(--color-text)",
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          ✕
        </button>
      </div>
    );
  }

  const stepLabels = ["Canvas", "Identify", "Directives", "Layout", "Wires"];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1500,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(0,0,0,0.45)",
      }}
      onClick={(e) => {
        // Close if clicking the backdrop itself
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "var(--bg-panel)",
          color: "var(--color-text)",
          border: "1px solid var(--color-border)",
          borderRadius: 8,
          width: 620,
          maxWidth: "95vw",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "10px 16px",
            borderBottom: "1px solid var(--color-border)",
            gap: 8,
          }}
        >
          <strong style={{ flex: 1, fontSize: 15 }}>Generate from Image</strong>
          <button
            onClick={() => setMinimized(true)}
            title="Minimize"
            style={{
              background: "none",
              border: "1px solid var(--color-border)",
              borderRadius: 4,
              padding: "2px 8px",
              cursor: "pointer",
              color: "var(--color-text)",
              fontSize: 12,
            }}
          >
            —
          </button>
          <button
            onClick={onClose}
            title="Close"
            style={{
              background: "none",
              border: "1px solid var(--color-border)",
              borderRadius: 4,
              padding: "2px 8px",
              cursor: "pointer",
              color: "var(--color-text)",
              fontSize: 12,
            }}
          >
            ✕
          </button>
        </div>

        {/* Step indicator */}
        {step <= 5 && (
          <div
            style={{
              display: "flex",
              padding: "8px 16px",
              gap: 4,
              borderBottom: "1px solid var(--color-border)",
              background: "var(--bg-canvas)",
            }}
          >
            {stepLabels.map((label, i) => {
              const s = (i + 1) as Step;
              const active = s === step;
              const done = s < step;
              return (
                <div
                  key={label}
                  style={{
                    flex: 1,
                    textAlign: "center",
                    fontSize: 11,
                    padding: "4px 2px",
                    borderRadius: 4,
                    background: done
                      ? "var(--color-success, #4caf50)"
                      : active
                      ? "var(--color-accent, #1976d2)"
                      : "var(--bg-panel)",
                    color: active || done ? "#fff" : "var(--color-text-muted)",
                    fontWeight: active ? "bold" : "normal",
                    border: "1px solid var(--color-border)",
                  }}
                >
                  {done ? "✓ " : ""}{label}
                </div>
              );
            })}
          </div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
          {error && (
            <div
              style={{
                marginBottom: 12,
                padding: "8px 12px",
                background: "var(--color-error-bg, #ffebee)",
                color: "var(--color-error, #c62828)",
                border: "1px solid var(--color-error, #c62828)",
                borderRadius: 4,
                fontSize: 13,
              }}
            >
              {error}
            </div>
          )}

          {/* ── Step 1: Canvas ── */}
          {step === 1 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Set the canvas size for the generated schematic.
              </p>
              <div style={{ display: "flex", gap: 16, alignItems: "flex-end" }}>
                <label style={{ fontSize: 13 }}>
                  Width (px)
                  <br />
                  <input
                    type="number"
                    value={canvasWidth}
                    onChange={(e) => setCanvasWidth(Number(e.target.value))}
                    style={{
                      marginTop: 4,
                      padding: "4px 8px",
                      border: "1px solid var(--color-border)",
                      borderRadius: 4,
                      background: "var(--bg-canvas)",
                      color: "var(--color-text)",
                      width: 100,
                    }}
                  />
                </label>
                <label style={{ fontSize: 13 }}>
                  Height (px)
                  <br />
                  <input
                    type="number"
                    value={canvasHeight}
                    onChange={(e) => setCanvasHeight(Number(e.target.value))}
                    style={{
                      marginTop: 4,
                      padding: "4px 8px",
                      border: "1px solid var(--color-border)",
                      borderRadius: 4,
                      background: "var(--bg-canvas)",
                      color: "var(--color-text)",
                      width: 100,
                    }}
                  />
                </label>
              </div>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>
                Image: <em>{imageFile.name}</em> — Next step will identify components.
              </p>
            </div>
          )}

          {/* ── Step 2: Identify Components ── */}
          {step === 2 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Review identified components. Edit type, name, or value, then confirm each row.
              </p>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: "var(--bg-canvas)" }}>
                      <th style={thStyle}>Type</th>
                      <th style={thStyle}>Name</th>
                      <th style={thStyle}>Value</th>
                      <th style={thStyle}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {components.map((comp, idx) => (
                      <tr
                        key={idx}
                        style={{
                          background: comp.confirmed
                            ? "var(--color-success-bg, #e8f5e9)"
                            : "transparent",
                        }}
                      >
                        <td style={tdStyle}>
                          <select
                            value={comp.type}
                            onChange={(e) => updateComp(idx, { type: e.target.value })}
                            style={{
                              padding: "2px 4px",
                              border: "1px solid var(--color-border)",
                              borderRadius: 3,
                              background: "var(--bg-canvas)",
                              color: "var(--color-text)",
                              fontSize: 12,
                              maxWidth: 120,
                            }}
                          >
                            {componentTypes.map((t) => (
                              <option key={t} value={t}>
                                {dictionary?.components[t]?.displayName ?? t}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td style={tdStyle}>
                          <input
                            value={comp.instanceName}
                            onChange={(e) => updateComp(idx, { instanceName: e.target.value })}
                            style={inputStyle}
                          />
                        </td>
                        <td style={tdStyle}>
                          <input
                            value={comp.value}
                            onChange={(e) => updateComp(idx, { value: e.target.value })}
                            style={inputStyle}
                          />
                        </td>
                        <td style={{ ...tdStyle, display: "flex", gap: 4 }}>
                          <button
                            onClick={() => confirmComp(idx)}
                            title="Confirm"
                            style={{
                              padding: "2px 6px",
                              background: comp.confirmed
                                ? "var(--color-success, #4caf50)"
                                : "var(--bg-panel)",
                              border: "1px solid var(--color-border)",
                              borderRadius: 3,
                              cursor: "pointer",
                              color: comp.confirmed ? "#fff" : "var(--color-text)",
                            }}
                          >
                            ✓
                          </button>
                          <button
                            onClick={() => deleteComp(idx)}
                            title="Delete"
                            style={{
                              padding: "2px 6px",
                              background: "var(--bg-panel)",
                              border: "1px solid var(--color-border)",
                              borderRadius: 3,
                              cursor: "pointer",
                              color: "var(--color-error, #c62828)",
                            }}
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button
                onClick={addMissingComp}
                style={{
                  marginTop: 8,
                  padding: "4px 12px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                + Add Missing
              </button>
            </div>
          )}

          {/* ── Step 3: Directives ── */}
          {step === 3 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Edit simulation directives. These will be added as text to the schematic.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {directives.map((d, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <input
                      value={d}
                      onChange={(e) => updateDirective(idx, e.target.value)}
                      style={{
                        flex: 1,
                        padding: "4px 8px",
                        border: "1px solid var(--color-border)",
                        borderRadius: 4,
                        background: "var(--bg-canvas)",
                        color: "var(--color-text)",
                        fontSize: 13,
                        fontFamily: "monospace",
                      }}
                    />
                    <button
                      onClick={() => deleteDirective(idx)}
                      style={{
                        padding: "4px 8px",
                        border: "1px solid var(--color-border)",
                        borderRadius: 4,
                        background: "var(--bg-panel)",
                        color: "var(--color-error, #c62828)",
                        cursor: "pointer",
                      }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
                {directives.length === 0 && (
                  <p style={{ fontSize: 12, color: "var(--color-text-muted)", margin: 0 }}>
                    No directives detected.
                  </p>
                )}
              </div>
              <button
                onClick={addDirective}
                style={{
                  marginTop: 8,
                  padding: "4px 12px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                + Add Directive
              </button>
            </div>
          )}

          {/* ── Step 4: Layout ── */}
          {step === 4 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>
                Components have been placed in the editor. You can minimize this modal to drag
                components to their final positions.
              </p>
              <div
                style={{
                  padding: 12,
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  fontSize: 12,
                }}
              >
                <strong>{components.filter((c) => c.confirmed !== false).length}</strong>{" "}
                components placed in editor.
              </div>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>
                Click <em>Minimize</em> (—) to interact with the canvas, then come back to continue.
              </p>
            </div>
          )}

          {/* ── Step 5: Wires (processing) ── */}
          {step === 5 && (
            <div style={{ textAlign: "center", padding: 24 }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>⚙️</div>
              <p style={{ fontSize: 13, margin: 0 }}>Tracing wires...</p>
            </div>
          )}

          {/* ── Done ── */}
          {step === 6 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 15, fontWeight: "bold" }}>
                Generation complete!
              </p>
              <ul style={{ fontSize: 13, lineHeight: 1.7 }}>
                <li>
                  <strong>{components.filter((c) => c.confirmed !== false).length}</strong>{" "}
                  components placed
                </li>
                <li>
                  <strong>{wireCount}</strong> wires traced
                </li>
                <li>
                  <strong>{flagCount}</strong> flags added
                </li>
                <li>
                  <strong>{directives.length}</strong> directives added
                </li>
              </ul>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                Review the schematic in the editor. Use Undo if you need to roll back.
              </p>
            </div>
          )}
        </div>

        {/* Footer / navigation */}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            padding: "10px 16px",
            borderTop: "1px solid var(--color-border)",
          }}
        >
          {step === 6 ? (
            <button
              onClick={onClose}
              style={primaryBtnStyle}
            >
              Close
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                style={secondaryBtnStyle}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (step === 1) goStep1to2();
                  else if (step === 2) goStep2to3();
                  else if (step === 3) goStep3to4();
                  else if (step === 4) goStep4to5();
                }}
                disabled={loading}
                style={primaryBtnStyle}
              >
                {loading ? "Loading..." : step === 4 ? "Trace Wires" : "Next →"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Shared inline styles ─────────────────────────────────────────────────────

const thStyle: React.CSSProperties = {
  padding: "4px 8px",
  borderBottom: "1px solid var(--color-border)",
  textAlign: "left",
  fontWeight: "bold",
};

const tdStyle: React.CSSProperties = {
  padding: "4px 6px",
  borderBottom: "1px solid var(--color-border)",
};

const inputStyle: React.CSSProperties = {
  padding: "2px 6px",
  border: "1px solid var(--color-border)",
  borderRadius: 3,
  background: "var(--bg-canvas)",
  color: "var(--color-text)",
  fontSize: 12,
  width: "100%",
  boxSizing: "border-box",
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "6px 18px",
  background: "var(--color-accent, #1976d2)",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
  fontWeight: "bold",
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: "6px 14px",
  background: "var(--bg-canvas)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 13,
};
