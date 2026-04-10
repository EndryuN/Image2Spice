import { useState, useRef, useEffect, useCallback } from "react";
import type { LlmProvider } from "../types/schematic";
import { checkLlmHealth, fetchEnvKeys } from "../lib/api";

interface LlmStatusProps {
  provider: LlmProvider;
  onProviderChange: (provider: LlmProvider) => void;
}

export function LlmStatus({ provider, onProviderChange }: LlmStatusProps) {
  const [open, setOpen] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [envKeys, setEnvKeys] = useState<Record<string, boolean>>({});

  // Load which providers have .env keys on mount
  useEffect(() => {
    fetchEnvKeys().then(setEnvKeys);
  }, []);
  const ref = useRef<HTMLDivElement>(null);

  const checkHealth = useCallback(() => {
    // For non-local providers, don't auto-check — require explicit Connect
    if (provider.provider !== "local") return;
    setOnline(null);
    checkLlmHealth(provider.provider).then(setOnline);
  }, [provider.provider]);

  const connectOpenRouter = useCallback(() => {
    if (!provider.apiKey && !envKeys[provider.provider]) return;
    setOnline(null);
    // If no frontend key but .env has one, call without key (backend uses .env)
    checkLlmHealth(provider.provider, provider.apiKey || undefined).then(setOnline);
  }, [provider.provider, provider.apiKey, envKeys]);

  // Auto-check for local only; reset status when switching providers
  useEffect(() => {
    setOnline(null);
    if (provider.provider === "local") {
      checkHealth();
      const interval = setInterval(checkHealth, 30000);
      return () => clearInterval(interval);
    }
  }, [provider.provider, checkHealth]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const providerLabels: Record<string, string> = {
    local: "Local",
    openrouter: "OpenRouter",
    openai: "OpenAI",
    claude: "Claude",
  };
  const shortModel = provider.model.includes("/") ? provider.model.split("/").pop() : provider.model;
  const label = `${providerLabels[provider.provider] ?? provider.provider}: ${shortModel}`;

  const dotColor =
    online === null ? "var(--color-text-muted, #888)" : online ? "#4caf50" : "#f44336";

  const needsKey = provider.provider !== "local";
  const statusText =
    needsKey && online === null && !provider.apiKey
      ? "Enter API key"
      : needsKey && online === null
      ? "Click Connect"
      : online === null
      ? "checking..."
      : online
      ? "connected"
      : "offline";

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          padding: "4px 10px",
          border: "1px solid var(--color-border)",
          borderRadius: 12,
          background: provider.provider !== "local" ? "var(--color-accent, #1976d2)" : "var(--bg-canvas)",
          color: provider.provider !== "local" ? "#fff" : "var(--color-text)",
          cursor: "pointer",
          fontSize: 11,
          whiteSpace: "nowrap",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: dotColor,
            display: "inline-block",
            flexShrink: 0,
          }}
        />
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
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
              Status: {statusText}
            </span>
            {provider.provider === "local" && (
              <button
                onClick={checkHealth}
                style={{
                  padding: "2px 8px",
                  border: "1px solid var(--color-border)",
                  borderRadius: 4,
                  background: "var(--bg-canvas)",
                  color: "var(--color-text)",
                  cursor: "pointer",
                  fontSize: 11,
                }}
              >
                Refresh
              </button>
            )}
          </div>

          <div>
            <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>Provider</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
              <label style={{ cursor: "pointer", color: "var(--color-text)" }}>
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
                      model: "google/gemma-4-31b-it:free",
                      apiKey: provider.apiKey ?? "",
                    })
                  }
                />{" "}
                OpenRouter
              </label>
              <label style={{ cursor: "pointer", color: "var(--color-text)" }}>
                <input
                  type="radio"
                  name="provider"
                  checked={provider.provider === "openai"}
                  onChange={() =>
                    onProviderChange({
                      provider: "openai",
                      model: "gpt-4o",
                      apiKey: provider.apiKey ?? "",
                    })
                  }
                />{" "}
                OpenAI
              </label>
              <label style={{ cursor: "pointer", color: "var(--color-text)" }}>
                <input
                  type="radio"
                  name="provider"
                  checked={provider.provider === "claude"}
                  onChange={() =>
                    onProviderChange({
                      provider: "claude",
                      model: "claude-sonnet-4-20250514",
                      apiKey: provider.apiKey ?? "",
                    })
                  }
                />{" "}
                Claude
              </label>
            </div>
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

          {provider.provider !== "local" && (
            <>
              <div>
                <div style={{ marginBottom: 4, fontWeight: "bold", color: "var(--color-text)" }}>
                  API Key
                  {envKeys[provider.provider] && !provider.apiKey && (
                    <span style={{ fontWeight: "normal", fontSize: 10, color: "var(--color-accent, #1976d2)", marginLeft: 8 }}>
                      loaded from server .env
                    </span>
                  )}
                </div>
                <input
                  type="password"
                  value={provider.apiKey ?? ""}
                  onChange={(e) => {
                    setOnline(null);
                    onProviderChange({ ...provider, apiKey: e.target.value });
                  }}
                  placeholder={
                    envKeys[provider.provider] ? "Using server .env key" :
                    provider.provider === "openrouter" ? "sk-or-..." :
                    provider.provider === "openai" ? "sk-..." :
                    provider.provider === "claude" ? "sk-ant-..." : "API key"
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
              <button
                onClick={connectOpenRouter}
                disabled={!provider.apiKey && !envKeys[provider.provider]}
                style={{
                  padding: "6px 12px",
                  border: "none",
                  borderRadius: 4,
                  background: (provider.apiKey || envKeys[provider.provider])
                    ? "var(--color-accent, #1976d2)"
                    : "var(--color-border)",
                  color: (provider.apiKey || envKeys[provider.provider]) ? "#fff" : "var(--color-text-muted)",
                  cursor: (provider.apiKey || envKeys[provider.provider]) ? "pointer" : "default",
                  fontSize: 12,
                  fontWeight: "bold",
                }}
              >
                Connect
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
