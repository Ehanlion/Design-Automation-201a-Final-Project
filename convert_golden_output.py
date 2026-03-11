#!/usr/bin/env python3
"""
Convert solutions/golden_output.txt into *_results.txt-compatible format.

Input line format:
  Mean temperature of <name> chiplet is <avg> and its maximum temperature is <peak>

Output format:
  # tuple format: (peak_temperature_C, average_temperature_C, thermal_resistance_x, thermal_resistance_y, thermal_resistance_z)
  results = {
      "<name>": (<peak>, <avg>, 0.0, 0.0, 0.0),
      ...
  }
"""

import argparse
import pathlib
import re
import sys
from typing import List, Tuple

LINE_RE = re.compile(
    r"^Mean temperature of (?P<name>.+?) chiplet is (?P<avg>[-+0-9.eE]+) "
    r"and its maximum temperature is (?P<peak>[-+0-9.eE]+)\s*$"
)


def parse_golden(path: pathlib.Path) -> List[Tuple[str, float, float]]:
    entries: List[Tuple[str, float, float]] = []
    with path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("Mean temperature of entire system is "):
                continue
            match = LINE_RE.match(line)
            if not match:
                raise ValueError(f"Unrecognized golden_output line: {line}")
            name = match.group("name")
            avg = float(match.group("avg"))
            peak = float(match.group("peak"))
            entries.append((name, peak, avg))
    return entries


def write_results_txt(path: pathlib.Path, entries: List[Tuple[str, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(
            "# tuple format: (peak_temperature_C, average_temperature_C, "
            "thermal_resistance_x, thermal_resistance_y, thermal_resistance_z)\n"
        )
        f.write("# NOTE: golden output does not include thermal resistance values.\n")
        f.write("#       rx/ry/rz are set to 0.0 for schema compatibility only.\n")
        f.write("results = {\n")
        for name, peak, avg in entries:
            f.write(
                f'    "{name}": ({peak:.6f}, {avg:.6f}, 0.000000, 0.000000, 0.000000),\n'
            )
        f.write("}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="solutions/golden_output.txt",
        help="Path to source golden output text file.",
    )
    parser.add_argument(
        "--output",
        default="solutions/golden_output_results.txt",
        help="Path to converted output file.",
    )
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Golden input file not found: {input_path}", file=sys.stderr)
        return 1

    entries = parse_golden(input_path)
    if not entries:
        print(f"ERROR: No chiplet temperature rows parsed from: {input_path}", file=sys.stderr)
        return 1

    write_results_txt(output_path, entries)
    print(f"Wrote converted golden results: {output_path} ({len(entries)} boxes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
