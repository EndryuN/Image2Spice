import { useCallback } from "react";
import type {
  Schematic,
  Component,
  Wire,
  Flag,
  Position,
  GenerateResponse,
} from "../types/schematic";
import { useHistory } from "./useHistory";
import { snapToGrid } from "../lib/gridSnap";

let nextId = 1;
function genId(): string {
  return `item-${nextId++}`;
}

const EMPTY_SCHEMATIC: Schematic = {
  sheet: { width: 880, height: 680 },
  components: [],
  wires: [],
  flags: [],
  text: [],
};

export function useSchematic() {
  const { state: schematic, set, undo, redo, canUndo, canRedo } =
    useHistory<Schematic>(structuredClone(EMPTY_SCHEMATIC));

  const loadFromGenerateResponse = useCallback(
    (resp: GenerateResponse) => {
      const s: Schematic = {
        sheet: resp.ir.sheet,
        components: resp.ir.components.map((c) => ({
          id: genId(),
          type: c.type,
          instanceName: c.instanceName,
          value: c.value,
          position: c.position,
          rotation: c.rotation,
          value2: c.value2,
        })),
        wires: resp.ir.wires.map((w) => ({
          id: genId(),
          from: w.from,
          to: w.to,
        })),
        flags: resp.ir.flags.map((f) => ({
          id: genId(),
          name: f.name,
          position: f.position,
        })),
        text: resp.ir.text.map((t) => ({
          id: genId(),
          content: t.content,
          position: t.position,
        })),
      };
      set(s);
    },
    [set]
  );

  const loadSchematic = useCallback(
    (s: Schematic) => {
      set(s);
    },
    [set]
  );

  const clearSchematic = useCallback(() => {
    set(structuredClone(EMPTY_SCHEMATIC));
  }, [set]);

  const setSheet = useCallback(
    (width: number, height: number) => {
      set({ ...schematic, sheet: { width, height } });
    },
    [schematic, set]
  );

  const moveComponent = useCallback(
    (id: string, pos: Position) => {
      const snapped = { x: snapToGrid(pos.x), y: snapToGrid(pos.y) };
      set({
        ...schematic,
        components: schematic.components.map((c) =>
          c.id === id ? { ...c, position: snapped } : c
        ),
      });
    },
    [schematic, set]
  );

  const updateComponent = useCallback(
    (id: string, updates: Partial<Component>) => {
      set({
        ...schematic,
        components: schematic.components.map((c) =>
          c.id === id ? { ...c, ...updates } : c
        ),
      });
    },
    [schematic, set]
  );

  const addComponent = useCallback(
    (type: string, instanceName: string, value: string, pos: Position) => {
      const snapped = { x: snapToGrid(pos.x), y: snapToGrid(pos.y) };
      const comp: Component = {
        id: genId(),
        type,
        instanceName,
        value,
        position: snapped,
        rotation: "R0",
      };
      set({ ...schematic, components: [...schematic.components, comp] });
    },
    [schematic, set]
  );

  const addComponentsBatch = useCallback(
    (comps: { type: string; instanceName: string; value: string; pos: Position; value2?: string; rotation?: string }[]) => {
      const newComps = comps.map((c) => ({
        id: genId(),
        type: c.type,
        instanceName: c.instanceName,
        value: c.value,
        position: { x: snapToGrid(c.pos.x), y: snapToGrid(c.pos.y) },
        rotation: c.rotation ?? "R0",
        value2: c.value2,
      }));
      set({ ...schematic, components: [...schematic.components, ...newComps] });
    },
    [schematic, set]
  );

  const addWiresBatch = useCallback(
    (wires: { from: Position; to: Position }[]) => {
      const newWires = wires.map((w) => ({
        id: genId(),
        from: { x: snapToGrid(w.from.x), y: snapToGrid(w.from.y) },
        to: { x: snapToGrid(w.to.x), y: snapToGrid(w.to.y) },
      }));
      set({ ...schematic, wires: [...schematic.wires, ...newWires] });
    },
    [schematic, set]
  );

  const addFlagsBatch = useCallback(
    (flags: { name: string; pos: Position }[]) => {
      const newFlags = flags.map((f) => ({
        id: genId(),
        name: f.name,
        position: { x: snapToGrid(f.pos.x), y: snapToGrid(f.pos.y) },
      }));
      set({ ...schematic, flags: [...schematic.flags, ...newFlags] });
    },
    [schematic, set]
  );

  const addWiresAndFlagsBatch = useCallback(
    (wires: { from: Position; to: Position }[], flags: { name: string; pos: Position }[]) => {
      const newWires = wires.map((w) => ({
        id: genId(),
        from: { x: snapToGrid(w.from.x), y: snapToGrid(w.from.y) },
        to: { x: snapToGrid(w.to.x), y: snapToGrid(w.to.y) },
      }));
      const newFlags = flags.map((f) => ({
        id: genId(),
        name: f.name,
        position: { x: snapToGrid(f.pos.x), y: snapToGrid(f.pos.y) },
      }));
      set({
        ...schematic,
        wires: [...schematic.wires, ...newWires],
        flags: [...schematic.flags, ...newFlags],
      });
    },
    [schematic, set]
  );

  const deleteComponent = useCallback(
    (id: string) => {
      set({
        ...schematic,
        components: schematic.components.filter((c) => c.id !== id),
      });
    },
    [schematic, set]
  );

  const addWire = useCallback(
    (from: Position, to: Position) => {
      const wire: Wire = {
        id: genId(),
        from: { x: snapToGrid(from.x), y: snapToGrid(from.y) },
        to: { x: snapToGrid(to.x), y: snapToGrid(to.y) },
      };
      set({ ...schematic, wires: [...schematic.wires, wire] });
    },
    [schematic, set]
  );

  const deleteWire = useCallback(
    (id: string) => {
      set({
        ...schematic,
        wires: schematic.wires.filter((w) => w.id !== id),
      });
    },
    [schematic, set]
  );

  const deleteWires = useCallback(
    (ids: string[]) => {
      const idSet = new Set(ids);
      set({
        ...schematic,
        wires: schematic.wires.filter((w) => !idSet.has(w.id)),
      });
    },
    [schematic, set]
  );

  const clearAllWires = useCallback(() => {
    set({
      ...schematic,
      wires: [],
      flags: [],
    });
  }, [schematic, set]);

  const addFlag = useCallback(
    (name: string, pos: Position) => {
      const flag: Flag = {
        id: genId(),
        name,
        position: { x: snapToGrid(pos.x), y: snapToGrid(pos.y) },
      };
      set({ ...schematic, flags: [...schematic.flags, flag] });
    },
    [schematic, set]
  );

  const deleteFlag = useCallback(
    (id: string) => {
      set({
        ...schematic,
        flags: schematic.flags.filter((f) => f.id !== id),
      });
    },
    [schematic, set]
  );

  const toIR = useCallback(() => {
    return {
      sheet: schematic.sheet,
      components: schematic.components.map((c) => ({
        type: c.type,
        instanceName: c.instanceName,
        value: c.value,
        position: c.position,
        rotation: c.rotation,
        value2: c.value2,
      })),
      wires: schematic.wires.map((w) => ({ from: w.from, to: w.to })),
      flags: schematic.flags.map((f) => ({
        name: f.name,
        position: f.position,
      })),
      text: schematic.text.map((t) => ({
        content: t.content,
        position: t.position,
      })),
    };
  }, [schematic]);

  return {
    schematic,
    loadSchematic,
    clearSchematic,
    setSheet,
    loadFromGenerateResponse,
    moveComponent,
    updateComponent,
    addComponent,
    addComponentsBatch,
    deleteComponent,
    addWire,
    addWiresBatch,
    deleteWire,
    deleteWires,
    clearAllWires,
    addFlag,
    addFlagsBatch,
    addWiresAndFlagsBatch,
    deleteFlag,
    toIR,
    undo,
    redo,
    canUndo,
    canRedo,
  };
}

