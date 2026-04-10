import { useState, useCallback, useEffect, useRef } from "react";
import type { Dictionary, LlmProvider, Schematic } from "../types/schematic";
import { wizardGenerateAsc } from "../lib/api";
import { parseAsc } from "../lib/ascParser";

interface ConnectionData {
  connections: Array<{ from: { component: string; pin: string }; to: { component: string; pin: string } }>;
  grounds: Array<{ component: string; pin: string }>;
  labels: Array<{ component: string; pin: string; label: string }>;
}

interface GenerateWizardProps {
  imageFile: File;
  dictionary: Dictionary | null;
  onSetSheet: (width: number, height: number) => void;
  onLoadSchematic: (s: Schematic) => void;
  onConnectionData?: (data: ConnectionData) => void;
  onClose: () => void;
  llmProvider: LlmProvider;
}

type Step = 1 | 2 | 3; // 1=canvas, 2=generating, 3=done

export function GenerateWizard({
  imageFile,
  dictionary,
  onSetSheet,
  onLoadSchematic,
  onConnectionData,
  onClose,
  llmProvider,
}: GenerateWizardProps) {
  const [step, setStep] = useState<Step>(1);
  const [minimized, setMinimized] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [canvasWidth, setCanvasWidth] = useState(880);
  const [canvasHeight, setCanvasHeight] = useState(680);
  const [ascText, setAscText] = useState("");
  const [stats, setStats] = useState<{ components: number; wires: number; flags: number } | null>(null);

  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (loading) {
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((e) => e + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  useEffect(() => () => { abortRef.current?.abort(); }, []);

  // Auto-detect canvas size from image
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const minDim = 800;
      const scaleX = img.naturalWidth < minDim ? minDim / img.naturalWidth : 1;
      const scaleY = img.naturalHeight < minDim ? minDim / img.naturalHeight : 1;
      const scale = Math.max(scaleX, scaleY, 1);
      setCanvasWidth(Math.round(img.naturalWidth * scale));
      setCanvasHeight(Math.round(img.naturalHeight * scale));
    };
    img.src = URL.createObjectURL(imageFile);
    return () => URL.revokeObjectURL(img.src);
  }, [imageFile]);

  const doGenerate = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);
    setError(null);
    setStep(2);
    onSetSheet(canvasWidth, canvasHeight);

    try {
      const result = await wizardGenerateAsc(imageFile, llmProvider, { width: canvasWidth, height: canvasHeight }, ac.signal) as {
        asc: string;
        connections?: Array<{ from: { component: string; pin: string }; to: { component: string; pin: string } }>;
        grounds?: Array<{ component: string; pin: string }>;
        labels?: Array<{ component: string; pin: string; label: string }>;
      };
      setAscText(result.asc);
      // Save connection data for redraw-wires
      if (onConnectionData && result.connections) {
        onConnectionData({
          connections: result.connections,
          grounds: result.grounds ?? [],
          labels: result.labels ?? [],
        });
      }
      const parsed = parseAsc(result.asc, dictionary);
      const s = parsed.schematic;

      // Scale output to fill canvas if VLM used smaller coordinates
      if (s.components.length > 0 || s.wires.length > 0) {
        let maxX = 0, maxY = 0;
        for (const c of s.components) { maxX = Math.max(maxX, c.position.x + 64); maxY = Math.max(maxY, c.position.y + 96); }
        for (const w of s.wires) { maxX = Math.max(maxX, w.from.x, w.to.x); maxY = Math.max(maxY, w.from.y, w.to.y); }
        for (const f of s.flags) { maxX = Math.max(maxX, f.position.x); maxY = Math.max(maxY, f.position.y); }

        if (maxX > 0 && maxY > 0) {
          const scaleX = maxX < canvasWidth * 0.8 ? (canvasWidth * 0.85) / maxX : 1;
          const scaleY = maxY < canvasHeight * 0.8 ? (canvasHeight * 0.85) / maxY : 1;
          const scale = Math.min(scaleX, scaleY);
          if (scale > 1.1) {
            const snap = (v: number) => Math.round((v * scale) / 16) * 16;
            for (const c of s.components) { c.position.x = snap(c.position.x); c.position.y = snap(c.position.y); }
            for (const w of s.wires) { w.from.x = snap(w.from.x); w.from.y = snap(w.from.y); w.to.x = snap(w.to.x); w.to.y = snap(w.to.y); }
            for (const f of s.flags) { f.position.x = snap(f.position.x); f.position.y = snap(f.position.y); }
            for (const t of s.text) { t.position.x = snap(t.position.x); t.position.y = snap(t.position.y); }
          }
        }
        s.sheet = { width: canvasWidth, height: canvasHeight };
      }

      onLoadSchematic(s);
      setStats({ components: s.components.length, wires: s.wires.length, flags: s.flags.length });
      if (parsed.errors.length > 0) setError(`Parsed with ${parsed.errors.length} warning(s): ${parsed.errors[0]}`);
      setStep(3);
    } catch (e: unknown) {
      if ((e as Error).name === "AbortError") return;
      setError(e instanceof Error ? e.message : String(e));
      setStep(1);
    } finally {
      setLoading(false);
    }
  }, [imageFile, llmProvider, canvasWidth, canvasHeight, onSetSheet, onLoadSchematic]);

  if (minimized) {
    return (
      <div style={{ position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", zIndex: 2000, background: "var(--bg-panel)", border: "1px solid var(--color-border)", borderRadius: 24, padding: "8px 20px", display: "flex", alignItems: "center", gap: 12, boxShadow: "0 4px 16px rgba(0,0,0,0.25)" }}>
        <span style={{ fontSize: 13, color: "var(--color-text)" }}>Generating... {elapsed}s</span>
        <button onClick={() => setMinimized(false)} style={minBtnStyle}>Show</button>
        <button onClick={onClose} style={minBtnStyle}>✕</button>
      </div>
    );
  }

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1500, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.45)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: "var(--bg-panel)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 8, width: 500, maxWidth: "95vw", maxHeight: "90vh", display: "flex", flexDirection: "column", boxShadow: "0 8px 32px rgba(0,0,0,0.35)" }}
        onClick={(e) => e.stopPropagation()}>

        <div style={{ display: "flex", alignItems: "center", padding: "10px 16px", borderBottom: "1px solid var(--color-border)", gap: 8 }}>
          <strong style={{ flex: 1, fontSize: 15 }}>Generate from Image</strong>
          {step === 2 && <button onClick={() => setMinimized(true)} style={headerBtnStyle}>—</button>}
          <button onClick={onClose} style={headerBtnStyle}>✕</button>
        </div>

        <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
          {error && (
            <div style={{ marginBottom: 12, padding: "8px 12px", background: "var(--color-error-bg, #ffebee)", color: "var(--color-error, #c62828)", border: "1px solid var(--color-error, #c62828)", borderRadius: 4, fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ flex: 1 }}>{error}</span>
              <button onClick={() => { setError(null); doGenerate(); }} style={{ padding: "2px 10px", border: "1px solid var(--color-error)", borderRadius: 4, background: "transparent", color: "var(--color-error)", cursor: "pointer", fontSize: 12 }}>Retry</button>
            </div>
          )}

          {step === 1 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 13 }}>Set canvas size, then click Generate.</p>
              <div style={{ display: "flex", gap: 16, alignItems: "flex-end" }}>
                <label style={{ fontSize: 13 }}>Width<br />
                  <input type="number" value={canvasWidth} onChange={(e) => setCanvasWidth(Number(e.target.value))} style={inputStyle} />
                </label>
                <label style={{ fontSize: 13 }}>Height<br />
                  <input type="number" value={canvasHeight} onChange={(e) => setCanvasHeight(Number(e.target.value))} style={inputStyle} />
                </label>
              </div>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>Image: <em>{imageFile.name}</em></p>
            </div>
          )}

          {step === 2 && (
            <div style={{ textAlign: "center", padding: 24 }}>
              <p style={{ fontSize: 15, fontWeight: "bold", margin: "0 0 8px 0" }}>Generating schematic...</p>
              <p style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                {elapsed < 10 ? "Sending image to model..." : elapsed < 30 ? "Analyzing circuit..." : elapsed < 60 ? "Generating .asc..." : "Still working — complex circuits take longer"}
              </p>
              <p style={{ fontSize: 24, fontWeight: "bold", color: "var(--color-accent, #1976d2)", marginTop: 12 }}>{elapsed}s</p>
            </div>
          )}

          {step === 3 && (
            <div>
              <p style={{ marginTop: 0, fontSize: 15, fontWeight: "bold" }}>Generation complete!</p>
              {stats && (
                <ul style={{ fontSize: 13, lineHeight: 1.7 }}>
                  <li><strong>{stats.components}</strong> components</li>
                  <li><strong>{stats.wires}</strong> wires</li>
                  <li><strong>{stats.flags}</strong> flags</li>
                </ul>
              )}
              <details style={{ fontSize: 12, marginTop: 8 }}>
                <summary style={{ cursor: "pointer", color: "var(--color-text-muted)" }}>Show raw .asc</summary>
                <pre style={{ marginTop: 8, padding: 8, background: "var(--color-preview-bg)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 4, fontSize: 11, maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap" }}>{ascText}</pre>
              </details>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 8 }}>Review in the editor. Use Undo to roll back.</p>
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "10px 16px", borderTop: "1px solid var(--color-border)" }}>
          {step === 3 ? (
            <button onClick={onClose} style={primaryBtnStyle}>Close</button>
          ) : (
            <>
              <button onClick={onClose} style={secondaryBtnStyle} disabled={loading}>Cancel</button>
              {step === 1 && <button onClick={doGenerate} style={primaryBtnStyle}>Generate</button>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const headerBtnStyle: React.CSSProperties = { background: "none", border: "1px solid var(--color-border)", borderRadius: 4, padding: "2px 8px", cursor: "pointer", color: "var(--color-text)", fontSize: 12 };
const minBtnStyle: React.CSSProperties = { padding: "2px 10px", borderRadius: 12, border: "1px solid var(--color-border)", background: "var(--bg-canvas)", color: "var(--color-text)", cursor: "pointer", fontSize: 12 };
const primaryBtnStyle: React.CSSProperties = { padding: "6px 18px", background: "var(--color-accent, #1976d2)", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer", fontSize: 13, fontWeight: "bold" };
const secondaryBtnStyle: React.CSSProperties = { padding: "6px 14px", background: "var(--bg-canvas)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: 4, cursor: "pointer", fontSize: 13 };
const inputStyle: React.CSSProperties = { marginTop: 4, padding: "4px 8px", border: "1px solid var(--color-border)", borderRadius: 4, background: "var(--bg-canvas)", color: "var(--color-text)", width: 100 };
