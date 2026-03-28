export interface Position {
  x: number;
  y: number;
}

export interface Component {
  id: string;
  type: string;
  instanceName: string;
  value: string;
  position: Position;
  rotation: string;
  value2?: string;
}

export interface Wire {
  id: string;
  from: Position;
  to: Position;
}

export interface Flag {
  id: string;
  name: string;
  position: Position;
}

export interface TextDirective {
  id: string;
  content: string;
  position: Position;
}

export interface Schematic {
  sheet: { width: number; height: number };
  components: Component[];
  wires: Wire[];
  flags: Flag[];
  text: TextDirective[];
}

export interface DictionaryComponent {
  id: string;
  category: string;
  displayName: string;
  asySource?: string;
  prefix?: string;
  description?: string;
  geometry?: {
    lines: { x1: number; y1: number; x2: number; y2: number }[];
    circles: { x1: number; y1: number; x2: number; y2: number }[];
    arcs: any[];
    bounds: { minX: number; minY: number; maxX: number; maxY: number };
  };
  pins: { name: string; x?: number; y?: number; position?: [number, number]; direction?: string; spiceOrder?: number }[];
  windows?: any[];
  symbol: {
    width: number;
    height: number;
    svgPath: string;
  };
  ascSyntax: {
    symbolName: string;
    attributes: string[];
  };
  rotations: string[];
}

export interface Dictionary {
  components: Record<string, DictionaryComponent>;
  directives: {
    directives: Record<string, { syntax: string; description: string }>;
    valueFormats?: Record<string, string>;
  };
}

export interface GenerateResponse {
  ir: {
    sheet: { width: number; height: number };
    components: Array<{
      type: string;
      instanceName: string;
      value: string;
      position: Position;
      rotation: string;
      value2?: string;
    }>;
    wires: Array<{ from: Position; to: Position }>;
    flags: Array<{ name: string; position: Position }>;
    text: Array<{ content: string; position: Position }>;
  };
  asc: string;
  validation: { valid: boolean; errors: string[] };
}

export interface WizardComponent {
  type: string;
  instanceName: string;
  value: string;
  value2?: string;
  confirmed?: boolean;
}

export interface WizardLayoutItem {
  instanceName: string;
  region: string;
  nearby: { name: string; direction: string }[];
}

export interface WizardWireResult {
  wires: { x1: number; y1: number; x2: number; y2: number }[];
  flags: { name: string; x: number; y: number }[];
}
