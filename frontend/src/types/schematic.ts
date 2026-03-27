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
  symbol: {
    width: number;
    height: number;
    svgPath: string;
  };
  pins: { name: string; position: [number, number]; direction: string }[];
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
