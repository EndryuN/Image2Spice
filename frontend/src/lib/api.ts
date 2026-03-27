import type { Dictionary, GenerateResponse } from "../types/schematic";

const BASE_URL = "http://localhost:8000/api";

export async function fetchDictionary(): Promise<Dictionary> {
  const resp = await fetch(`${BASE_URL}/dictionary`);
  if (!resp.ok) throw new Error(`Dictionary fetch failed: ${resp.status}`);
  return resp.json();
}

export async function generateFromImage(file: File): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const resp = await fetch(`${BASE_URL}/generate`, {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) throw new Error(`Generate failed: ${resp.status}`);
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
