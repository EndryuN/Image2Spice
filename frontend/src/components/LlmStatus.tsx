import { useState, useRef, useEffect } from "react";
import type { LlmProvider } from "../types/schematic";

interface LlmStatusProps {
  provider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
}

export function LlmStatus({ provider, onProviderChange }: LlmStatusProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const label =
    provider.provider === "local"
      ? `Local: ${provider.model}`
      : `OpenRouter: ${provider.model.split("/").pop()}`;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: "4px 10px",
          border: "1px solid var(--color-border)",
          borderRadius: 12,
          background: provider.provider === "openrouter" ? "var(--color-accent, #1976d2)" : "var(--bg-canvas)",
          color: provider.provider === "openrouter" ? "#fff" : "var(--color-text)",
          cursor: "pointer",
          fontSize: 11,
          whiteSpace: "nowrap",
        }}
      >
        {label} ▾
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: 4,
            padding: 12,
            background: "var(--bg-panel)",
            border: "1px solid var(--color-border)",
            borderRadius: 6,
            boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
            zIndex: 3000,
            width: 280,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            fontSize: 12,
          }}
        >
          <div>
            <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>Provider</div>
            <label style={{ marginRight: 16, cursor: "pointer", color: "var(--color-text)" }}>
              <input
                type="radio"
                name="provider"
                checked={provider.provider === "local"}
                onChange={() =>
                  onProviderChange({ provider: "local", model: "qwen3-vl:8b" })
                }
              />{" "}
              Local (Ollama)
            </label>
            <label style={{ cursor: "pointer", color: "var(--color-text)" }}>
              <input
                type="radio"
                name="provider"
                checked={provider.provider === "openrouter"}
                onChange={() =>
                  onProviderChange({
                    provider: "openrouter",
                    model: "qwen/qwen3.6-plus:free",
                    apiKey: provider.apiKey ?? "",
                  })
                }
              />{" "}
              OpenRouter
            </label>
          </div>

          <div>
            <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>Model</div>
            <input
              value={provider.model}
              onChange={(e) =>
                onProviderChange({ ...provider, model: e.target.value })
              }
              style={{
                width: "100%",
                padding: "4px 8px",
                border: "1px solid var(--color-border)",
                borderRadius: 4,
                background: "var(--bg-canvas)",
                color: "var(--color-text)",
                fontSize: 12,
                boxSizing: "border-box",
              }}
            />
          </div>

          {provider.provider === "openrouter" && (
            <div>
              <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>API Key</div>
              <input
                type="password"
                value={provider.apiKey ?? ""}
                onChange={(e) =>
                  onProviderChange({ ...provider, apiKey: e.target.value })
                }
                placeholder="sk-or-..."
                style={{
                  width: "100%",
                  padding: "4px 8px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  fontSize: 12,
                  boxSizing: "border-box",
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
