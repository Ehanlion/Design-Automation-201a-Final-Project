#!/usr/bin/env python3
"""
Summarize thermal simulation outputs.

Usage:
  python3 summarize_results.py \
      --results_dir out_therm \
      --csv out_therm/summary.csv \
      --md out_therm/summary.md

Parses all *_results.yaml files in results_dir, extracts peak/avg temps per
box, and emits a text table plus optional CSV/Markdown summaries.
"""

import argparse
import csv
import pathlib
from typing import Dict, Iterable, Tuple

import yaml


def is_gpu(name: str) -> bool:
    token = name.split(".")[-1].lower()
    return "gpu" in token


def is_hbm(name: str) -> bool:
    token = name.split(".")[-1].lower()
    return "hbm" in token


def load_results(path: pathlib.Path) -> Dict[str, Tuple[float, float, float, float, float]]:
    # Result files store tuples using the !!python/tuple tag; use FullLoader to permit them.
    loader = getattr(yaml, "FullLoader", yaml.Loader)
    with path.open() as f:
        data = yaml.load(f, Loader=loader) or {}
    return data


def summarize_file(path: pathlib.Path) -> Dict[str, float]:
    data = load_results(path)
    project = path.stem.replace("_results", "")

    peaks = []
    gpu_peaks = []
    hbm_peaks = []
    hottest_box = None
    hottest_peak = float("-inf")

    for box_name, values in data.items():
        try:
            peak, avg, *_ = values
        except Exception:
            # Skip malformed entries
            continue
        peaks.append(peak)
        if peak > hottest_peak:
            hottest_peak = peak
            hottest_box = box_name
        if is_gpu(box_name):
            gpu_peaks.append(peak)
        if is_hbm(box_name):
            hbm_peaks.append(peak)

    def safe_max(vals: Iterable[float]) -> float:
        return max(vals) if vals else float("nan")

    summary = {
        "project": project,
        "hottest_box": hottest_box or "N/A",
        "hottest_peak_C": hottest_peak if peaks else float("nan"),
        "overall_avg_peak_C": sum(peaks) / len(peaks) if peaks else float("nan"),
        "gpu_peak_C": safe_max(gpu_peaks),
        "hbm_peak_C": safe_max(hbm_peaks),
        "num_boxes": len(peaks),
    }
    return summary


def write_csv(rows, path: pathlib.Path):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_md(rows, path: pathlib.Path):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys())
    with path.open("w") as f:
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("|" + "|".join([" --- "] * len(headers)) + "|\n")
        for row in rows:
            f.write("| " + " | ".join(f"{row[h]}" for h in headers) + " |\n")


def print_table(rows):
    if not rows:
        print("No result files found.")
        return
    headers = ["project", "hottest_peak_C", "hottest_box", "gpu_peak_C", "hbm_peak_C", "num_boxes"]
    col_widths = {h: max(len(h), max(len(f"{row[h]}") for row in rows)) for h in headers}
    def fmt(row):
        return "  ".join(f"{row[h]:>{col_widths[h]}}" for h in headers)
    print(fmt({h: h for h in headers}))
    print("-" * (sum(col_widths.values()) + 2 * (len(headers) - 1)))
    for row in rows:
        print(fmt(row))


def main():
    parser = argparse.ArgumentParser(description="Summarize thermal result YAMLs.")
    parser.add_argument("--results_dir", default="out_therm", help="Directory containing *_results.yaml files.")
    parser.add_argument("--csv", default=None, help="Optional path to write CSV summary.")
    parser.add_argument("--md", default=None, help="Optional path to write Markdown summary.")
    args = parser.parse_args()

    results_dir = pathlib.Path(args.results_dir)
    files = sorted(results_dir.glob("*_results.yaml"))
    rows = [summarize_file(p) for p in files]

    print_table(rows)

    if args.csv:
        write_csv(rows, pathlib.Path(args.csv))
    if args.md:
        write_md(rows, pathlib.Path(args.md))


if __name__ == "__main__":
    main()
