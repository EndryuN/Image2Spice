import type { Schematic, Dictionary } from "../types/schematic";

export function generateAsc(schematic: Schematic, dictionary?: Dictionary | null): string {
  const lines: string[] = [];
  lines.push("Version 4");
  lines.push(`SHEET 1 ${schematic.sheet.width} ${schematic.sheet.height}`);

  for (const comp of schematic.components) {
    // Convert SVG position to LTspice origin for .asc export
    const dictComp = dictionary?.components[comp.type];
    const rawBounds = dictComp?.geometry?.bounds;
    let bx = 0, by = 0;
    if (Array.isArray(rawBounds)) {
      bx = rawBounds[0] ?? 0;
      by = rawBounds[1] ?? 0;
    } else if (rawBounds) {
      bx = (rawBounds as { minX: number }).minX ?? 0;
      by = (rawBounds as { minY: number }).minY ?? 0;
    }
    const ltX = comp.position.x - bx;
    const ltY = comp.position.y - by;
    lines.push(`SYMBOL ${comp.type} ${ltX} ${ltY} ${comp.rotation}`);
    // Add WINDOW lines for text label positioning
    const wins = dictComp?.windows as
      | { index: number; x: number; y: number; justification?: string; fontSize?: number }[]
      | undefined;
    if (wins) {
      for (const win of wins) {
        lines.push(`WINDOW ${win.index} ${win.x} ${win.y} ${win.justification ?? "Left"} ${win.fontSize ?? 2}`);
      }
    }
    lines.push(`SYMATTR InstName ${comp.instanceName}`);
    lines.push(`SYMATTR Value ${comp.value}`);
    if (comp.value2) {
      lines.push(`SYMATTR Value2 ${comp.value2}`);
    }
  }

  for (const wire of schematic.wires) {
    lines.push(`WIRE ${wire.from.x} ${wire.from.y} ${wire.to.x} ${wire.to.y}`);
  }

  for (const flag of schematic.flags) {
    lines.push(`FLAG ${flag.position.x} ${flag.position.y} ${flag.name}`);
  }

  for (const text of schematic.text) {
    const prefix = text.content.startsWith(".") ? "!" : "";
    lines.push(`TEXT ${text.position.x} ${text.position.y} Left 2 ${prefix}${text.content}`);
  }

  return lines.join("\n") + "\n";
}
