"""Rebuild dictionary/components.json from LTspice .asy files."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from services.asy_parser import build_dictionary_from_asy

def main():
    ltspice_sym = Path(os.environ.get(
        "LTSPICE_SYM_DIR",
        os.path.expandvars(r"%LOCALAPPDATA%\LTspice\lib\sym")
    ))

    if not ltspice_sym.exists():
        print(f"LTspice sym directory not found: {ltspice_sym}")
        print("Set LTSPICE_SYM_DIR environment variable to override.")
        sys.exit(1)

    print(f"Parsing .asy files from: {ltspice_sym}")
    dictionary = build_dictionary_from_asy(ltspice_sym)

    out_path = Path(__file__).parent.parent.parent / "dictionary" / "components.json"
    out_path.write_text(json.dumps({"components": dictionary}, indent=2), encoding="utf-8")
    print(f"Wrote {len(dictionary)} components to {out_path}")

if __name__ == "__main__":
    main()
