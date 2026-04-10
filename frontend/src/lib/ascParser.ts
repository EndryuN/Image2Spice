import type { Schematic, Component, Wire, Flag, TextDirective, Dictionary } from "../types/schematic";

let nextId = 10000;
function genId(): string {
  return `imp-${nextId++}`;
}

export interface AscParseResult {
  schematic: Schematic;
  errors: string[];
}

export function parseAsc(text: string, dictionary?: Dictionary | null): AscParseResult {
  const lines = text.split(/\r?\n/);
  const errors: string[] = [];

  let sheetWidth = 880;
  let sheetHeight = 680;
  const components: Component[] = [];
  const wires: Wire[] = [];
  const flags: Flag[] = [];
  const texts: TextDirective[] = [];

  // State for building current component
  let current: Partial<Component> | null = null;

  function flushComponent() {
    if (current && current.type && current.instanceName) {
      components.push({
        id: genId(),
        type: current.type,
        instanceName: current.instanceName,
        value: current.value ?? "",
        position: current.position ?? { x: 0, y: 0 },
        rotation: current.rotation ?? "R0",
        value2: current.value2,
      });
    }
    current = null;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    if (line.startsWith("Version")) {
      continue;
    }

    if (line.startsWith("SHEET")) {
      const parts = line.split(/\s+/);
      if (parts.length >= 4) {
        sheetWidth = parseInt(parts[2], 10) || 880;
        sheetHeight = parseInt(parts[3], 10) || 680;
      }
      continue;
    }

    if (line.startsWith("SYMBOL")) {
      flushComponent();
      const parts = line.split(/\s+/);
      if (parts.length >= 5) {
        const compType = parts[1];
        let sx = parseInt(parts[2], 10);
        let sy = parseInt(parts[3], 10);
        if (!isNaN(sx) && !isNaN(sy)) {
          // Convert LTspice origin to SVG top-left using bounds offset
          if (dictionary) {
            const dictComp = dictionary.components[compType];
            const rawBounds = dictComp?.geometry?.bounds;
            if (Array.isArray(rawBounds)) {
              sx = sx + (rawBounds[0] ?? 0);
              sy = sy + (rawBounds[1] ?? 0);
            } else if (rawBounds) {
              sx = sx + ((rawBounds as { minX: number }).minX ?? 0);
              sy = sy + ((rawBounds as { minY: number }).minY ?? 0);
            }
          }
          current = {
            type: compType,
            position: { x: sx, y: sy },
            rotation: parts[4],
          };
        }
      }
      continue;
    }

    if (line.startsWith("SYMATTR")) {
      if (!current) {
        errors.push(`Line ${i + 1}: SYMATTR without preceding SYMBOL`);
        continue;
      }
      const match = line.match(/^SYMATTR\s+(\S+)\s+(.*)/);
      if (match) {
        const [, attr, value] = match;
        if (attr === "InstName") current.instanceName = value;
        else if (attr === "Value") current.value = value;
        else if (attr === "Value2") current.value2 = value;
      }
      continue;
    }

    if (line.startsWith("WINDOW")) {
      // Skip WINDOW lines — they define label positioning, not needed for import
      continue;
    }

    if (line.startsWith("WIRE")) {
      flushComponent();
      const parts = line.split(/\s+/);
      if (parts.length >= 5) {
        const x1 = parseInt(parts[1], 10);
        const y1 = parseInt(parts[2], 10);
        const x2 = parseInt(parts[3], 10);
        const y2 = parseInt(parts[4], 10);
        if (!isNaN(x1) && !isNaN(y1) && !isNaN(x2) && !isNaN(y2)) {
          wires.push({ id: genId(), from: { x: x1, y: y1 }, to: { x: x2, y: y2 } });
        }
      }
      // Skip malformed/empty WIRE lines silently
      continue;
    }

    if (line.startsWith("FLAG")) {
      flushComponent();
      const parts = line.split(/\s+/);
      if (parts.length >= 4) {
        flags.push({
          id: genId(),
          position: { x: parseInt(parts[1], 10), y: parseInt(parts[2], 10) },
          name: parts.slice(3).join(" "),
        });
      }
      continue;
    }

    if (line.startsWith("TEXT")) {
      flushComponent();
      // TEXT x y justify fontSize content
      const match = line.match(/^TEXT\s+(-?\d+)\s+(-?\d+)\s+\S+\s+\d+\s+(!?)(.*)$/);
      if (match) {
        const content = match[3] === "!" ? match[4] : match[4];
        // Restore the "." prefix for SPICE directives
        const finalContent = match[3] === "!" ? match[4] : match[4];
        texts.push({
          id: genId(),
          position: { x: parseInt(match[1], 10), y: parseInt(match[2], 10) },
          content: finalContent,
        });
      }
      continue;
    }
  }

  // Flush last component
  flushComponent();

  return {
    schematic: {
      sheet: { width: sheetWidth, height: sheetHeight },
      components,
      wires,
      flags,
      text: texts,
    },
    errors,
  };
}
