import type { Dictionary, WizardComponent, WizardWireResult, LlmProvider } from "../types/schematic";

const BASE_URL = "http://localhost:8000/api";

export async function checkLlmHealth(provider: string): Promise<boolean> {
  try {
    const resp = await fetch(`${BASE_URL}/llm-status?provider=${provider}`);
    if (!resp.ok) return false;
    const data = await resp.json();
    return data.online === true;
  } catch {
    return false;
  }
}

export async function fetchDictionary(): Promise<Dictionary> {
  const resp = await fetch(`${BASE_URL}/dictionary`);
  if (!resp.ok) throw new Error(`Dictionary fetch failed: ${resp.status}`);
  return resp.json();
}

export async function wizardIdentify(file: File, providerConfig?: LlmProvider): Promise<{ components: WizardComponent[] }> {
  const formData = new FormData();
  formData.append("file", file);
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/identify`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Identify failed: ${resp.status}`);
  }
  return resp.json();
}

export async function wizardDirectives(file: File, providerConfig?: LlmProvider): Promise<{ directives: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/directives`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Directives failed: ${resp.status}`);
  }
  return resp.json();
}

export async function wizardLayout(
  file: File,
  components: WizardComponent[],
  providerConfig?: LlmProvider,
): Promise<{ positions: Record<string, { x: number; y: number }> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/layout`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Layout failed: ${resp.status}`);
  }
  return resp.json();
}

export async function wizardWires(
  file: File,
  components: WizardComponent[],
  positions: Record<string, { x: number; y: number }>,
  providerConfig?: LlmProvider,
): Promise<WizardWireResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  formData.append("positions_json", JSON.stringify(positions));
  if (providerConfig) formData.append("provider_json", JSON.stringify(providerConfig));
  const resp = await fetch(`${BASE_URL}/wizard/wires`, { method: "POST", body: formData });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail?.error ?? body?.detail ?? `Wires failed: ${resp.status}`);
  }
  return resp.json();
}

export async function refineIR(
  ir: object
): Promise<{ asc: string; validation: { valid: boolean; errors: string[] } }> {
  const resp = await fetch(`${BASE_URL}/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ir }),
  });
  if (!resp.ok) throw new Error(`Refine failed: ${resp.status}`);
  return resp.json();
}

export async function validateAsc(
  asc: string
): Promise<{ valid: boolean; errors: string[] }> {
  const resp = await fetch(`${BASE_URL}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asc }),
  });
  if (!resp.ok) throw new Error(`Validate failed: ${resp.status}`);
  return resp.json();
}
