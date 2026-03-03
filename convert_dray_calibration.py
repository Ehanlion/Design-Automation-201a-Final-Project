#!/usr/bin/env python3
"""Convert raw calibration output (dray_ECTC2.txt) into dictionary-ready text."""

import re
from pathlib import Path
from typing import List, Tuple


def parse_calibration_block(block: str) -> Tuple[str, List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Extract condition line and calibration tuples for GPU and HBM from a text block."""
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty calibration block encountered")

    condition_with_suffix = lines[0]
    colon_index = condition_with_suffix.find(":")
    if colon_index == -1:
        raise ValueError(f"Condition line missing ':' separator: {condition_with_suffix!r}")
    condition_line = condition_with_suffix[: colon_index + 1]

    gpu_entries: List[Tuple[str, str]] = []
    hbm_entries: List[Tuple[str, str]] = []
    entry_pattern = re.compile(r"calibrate_(GPU|HBM) :: ([^:]+) : \(([^)]+)\)")

    for line in lines[1:]:
        match = entry_pattern.search(line)
        if not match:
            continue
        target, setpoint, values = match.groups()
        if target.upper() == "GPU":
            gpu_entries.append((setpoint.strip(), values.strip()))
        else:
            hbm_entries.append((setpoint.strip(), values.strip()))

    if not gpu_entries and not hbm_entries:
        raise ValueError(f"No calibration entries found for block starting: {condition_line}")

    return condition_line, gpu_entries, hbm_entries


def format_condition_block(condition: str, entries: List[Tuple[str, str]]) -> List[str]:
    """Render a condition block without a calibrate header."""
    if not entries:
        return []

    output = [condition, '    temperature_dict["2p5D_1GPU"] = {']
    for index, (setpoint, values) in enumerate(entries):
        trailing = "," if index < len(entries) - 1 else ""
        output.append(f"        {setpoint} : ({values}){trailing}")
    output.append("    }")
    output.append("")
    return output


def convert(source: Path, destination: Path) -> None:
    raw_text = source.read_text()
    blocks = [block.strip() for block in raw_text.split("\n\n") if block.strip()]

    gpu_sections: List[List[str]] = []
    hbm_sections: List[List[str]] = []

    for block in blocks:
        condition, gpu_entries, hbm_entries = parse_calibration_block(block)
        gpu_block = format_condition_block(condition, gpu_entries)
        if gpu_block:
            gpu_sections.append(gpu_block)
        hbm_block = format_condition_block(condition, hbm_entries)
        if hbm_block:
            hbm_sections.append(hbm_block)

    output_lines: List[str] = []

    if gpu_sections:
        output_lines.append("calibrate_GPU")
        for block in gpu_sections:
            output_lines.extend(block)

    if hbm_sections:
        if output_lines and output_lines[-1] != "":
            output_lines.append("")
        output_lines.append("calibrate_HBM")
        for block in hbm_sections:
            output_lines.extend(block)

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    destination.write_text("\n".join(output_lines) + "\n")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    source_path = project_root / "dray_ECTC2.txt"
    destination_path = project_root / "dray_ECTC3.txt"

    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    convert(source_path, destination_path)
    print(f"Converted {source_path.name} → {destination_path.name}")
