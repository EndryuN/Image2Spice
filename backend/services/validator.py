from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_asc(content: str) -> ValidationResult:
    result = ValidationResult()
    lines = content.strip().split("\n")

    if not lines or not lines[0].startswith("Version 4"):
        result.valid = False
        result.errors.append("File must start with 'Version 4'")

    has_sheet = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("SHEET "):
            has_sheet = True
            _validate_sheet(line, result)

        elif line.startswith("SYMBOL "):
            _validate_symbol_block(lines, i, result)

        elif line.startswith("WIRE "):
            _validate_wire(line, result)

        elif line.startswith("FLAG "):
            _validate_flag(line, result)

        i += 1

    if not has_sheet:
        result.valid = False
        result.errors.append("File must contain a SHEET line")

    return result


def _validate_sheet(line: str, result: ValidationResult):
    parts = line.split()
    if len(parts) != 4:
        result.valid = False
        result.errors.append(f"Invalid SHEET line: {line}")


def _validate_symbol_block(lines: list[str], symbol_idx: int, result: ValidationResult):
    parts = lines[symbol_idx].strip().split()
    if len(parts) != 5:
        result.valid = False
        result.errors.append(f"Invalid SYMBOL line: {lines[symbol_idx].strip()}")
        return

    rotation = parts[4]
    valid_rotations = {"R0", "R90", "R180", "R270", "M0", "M90", "M180", "M270"}
    if rotation not in valid_rotations:
        result.valid = False
        result.errors.append(f"Invalid rotation '{rotation}' in: {lines[symbol_idx].strip()}")

    has_instname = False
    j = symbol_idx + 1
    while j < len(lines):
        next_line = lines[j].strip()
        if next_line.startswith("SYMATTR InstName"):
            has_instname = True
            break
        elif next_line.startswith("SYMATTR ") or next_line.startswith("WINDOW "):
            j += 1
            continue
        else:
            break
        j += 1

    if not has_instname:
        result.valid = False
        result.errors.append(
            f"SYMBOL at line {symbol_idx + 1} missing SYMATTR InstName"
        )


def _validate_wire(line: str, result: ValidationResult):
    parts = line.split()
    if len(parts) != 5:
        result.valid = False
        result.errors.append(f"WIRE must have 4 integer coordinates: {line}")
        return

    for coord_str in parts[1:]:
        try:
            val = float(coord_str)
            if val != int(val):
                result.valid = False
                result.errors.append(
                    f"WIRE coordinates must be integers, got '{coord_str}': {line}"
                )
        except ValueError:
            result.valid = False
            result.errors.append(
                f"WIRE coordinate '{coord_str}' is not a number: {line}"
            )


def _validate_flag(line: str, result: ValidationResult):
    parts = line.split()
    if len(parts) < 4:
        result.valid = False
        result.errors.append(f"Invalid FLAG line: {line}")
