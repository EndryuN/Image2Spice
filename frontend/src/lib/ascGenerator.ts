import type { Schematic } from "../types/schematic";

export function generateAsc(schematic: Schematic): string {
  const lines: string[] = [];
  lines.push("Version 4");
  lines.push(`SHEET 1 ${schematic.sheet.width} ${schematic.sheet.height}`);

  for (const comp of schematic.components) {
    lines.push(`SYMBOL ${comp.type} ${comp.position.x} ${comp.position.y} ${comp.rotation}`);
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
