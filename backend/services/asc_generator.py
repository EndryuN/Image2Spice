from dataclasses import dataclass, field


@dataclass
class Component:
    type: str
    instance_name: str
    value: str
    x: int
    y: int
    rotation: str
    value2: str | None = None
    windows: list[str] = field(default_factory=list)


@dataclass
class Wire:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class Flag:
    name: str
    x: int
    y: int


@dataclass
class Text:
    content: str
    x: int
    y: int
    justify: str = "Left"
    font_size: int = 2


class SchematicIR:
    def __init__(self, sheet_width: int = 880, sheet_height: int = 680):
        self.sheet_width = sheet_width
        self.sheet_height = sheet_height
        self.components: list[Component] = []
        self.wires: list[Wire] = []
        self.flags: list[Flag] = []
        self.texts: list[Text] = []

    def add_component(
        self,
        comp_type: str,
        instance_name: str,
        value: str,
        x: int,
        y: int,
        rotation: str,
        value2: str | None = None,
    ):
        self.components.append(
            Component(comp_type, instance_name, value, x, y, rotation, value2)
        )

    def add_wire(self, x1: int, y1: int, x2: int, y2: int):
        self.wires.append(Wire(x1, y1, x2, y2))

    def add_flag(self, name: str, x: int, y: int):
        self.flags.append(Flag(name, x, y))

    def add_text(self, content: str, x: int, y: int):
        self.texts.append(Text(content, x, y))


def generate_asc(ir: SchematicIR) -> str:
    lines: list[str] = []

    lines.append("Version 4")
    lines.append(f"SHEET 1 {ir.sheet_width} {ir.sheet_height}")

    for comp in ir.components:
        lines.append(f"SYMBOL {comp.type} {comp.x} {comp.y} {comp.rotation}")
        for window in comp.windows:
            lines.append(window)
        lines.append(f"SYMATTR InstName {comp.instance_name}")
        lines.append(f"SYMATTR Value {comp.value}")
        if comp.value2 is not None:
            lines.append(f"SYMATTR Value2 {comp.value2}")

    for wire in ir.wires:
        lines.append(f"WIRE {wire.x1} {wire.y1} {wire.x2} {wire.y2}")

    for flag in ir.flags:
        lines.append(f"FLAG {flag.x} {flag.y} {flag.name}")

    for text in ir.texts:
        prefix = "!" if text.content.startswith(".") else ""
        lines.append(
            f"TEXT {text.x} {text.y} {text.justify} {text.font_size} {prefix}{text.content}"
        )

    lines.append("")
    return "\n".join(lines)
