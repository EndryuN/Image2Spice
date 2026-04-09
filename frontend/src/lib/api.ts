import type { Dictionary, WizardComponent, WizardWireResult } from "../types/schematic";

const BASE_URL = "http://localhost:8000/api";

export async function fetchDictionary(): Promise<Dictionary> {
  const resp = await fetch(`${BASE_URL}/dictionary`);
  if (!resp.ok) throw new Error(`Dictionary fetch failed: ${resp.status}`);
  return resp.json();
}

export async function wizardIdentify(file: File): Promise<{ components: WizardComponent[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/wizard/identify`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Identify failed: ${resp.status}`);
  return resp.json();
}

export async function wizardDirectives(file: File): Promise<{ directives: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/wizard/directives`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Directives failed: ${resp.status}`);
  return resp.json();
}

export async function wizardLayout(
  file: File,
  components: WizardComponent[]
): Promise<{ positions: Record<string, { x: number; y: number }> }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  const resp = await fetch(`${BASE_URL}/wizard/layout`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Layout failed: ${resp.status}`);
  return resp.json();
}

export async function wizardWires(
  file: File,
  components: WizardComponent[],
  positions: Record<string, { x: number; y: number }>
): Promise<WizardWireResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("components_json", JSON.stringify(components));
  formData.append("positions_json", JSON.stringify(positions));
  const resp = await fetch(`${BASE_URL}/wizard/wires`, { method: "POST", body: formData });
  if (!resp.ok) throw new Error(`Wires failed: ${resp.status}`);
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
