#!/usr/bin/env python3
"""
Compare out_therm/*_results.txt files against a golden *_results.txt reference.

Only files with the same number of boxes as the golden reference are evaluated.
"""

import argparse
import ast
import csv
import math
import pathlib
import re
import sys
from typing import Dict, List, Tuple

RESULTS_RE = re.compile(r"results\s*=\s*(\{.*\})\s*$", re.DOTALL)


def _population_variance(values: List[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) * (v - mean) for v in values) / len(values)


def _ratio_pct(num: float, den: float) -> float:
    # User-requested format: num/den * 100, with 100 meaning equal.
    if den <= 0.0:
        if num <= 0.0:
            return 100.0
        return float("inf")
    return 100.0 * num / den


def _ratio_match_pct(num: float, den: float) -> float:
    # Symmetric bounded similarity: 100 is perfect, 0 is worst.
    if num <= 0.0 and den <= 0.0:
        return 100.0
    if num <= 0.0 or den <= 0.0:
        return 0.0
    r = num / den
    if r <= 0.0:
        return 0.0
    return 100.0 * min(r, 1.0 / r)


def _error_score_pct(err: float, ref_scale: float) -> float:
    # 100 is perfect (0 error). Ref scale uses golden standard deviation.
    ref = max(ref_scale, 1e-12)
    return 100.0 / (1.0 + (err / ref))


def load_results_txt(path: pathlib.Path) -> Dict[str, Tuple[float, float]]:
    text = path.read_text()
    match = RESULTS_RE.search(text)
    if not match:
        raise ValueError(f"Could not find 'results = {{...}}' in {path}")

    parsed = ast.literal_eval(match.group(1))
    if not isinstance(parsed, dict):
        raise ValueError(f"Parsed results are not a dictionary in {path}")

    out: Dict[str, Tuple[float, float]] = {}
    for name, values in parsed.items():
        if not isinstance(name, str):
            continue
        try:
            peak = float(values[0])
            avg = float(values[1])
        except (IndexError, TypeError, ValueError):
            continue
        out[name] = (peak, avg)
    return out


def normalize_name(name: str) -> str:
    # Some outputs insert ".set_primary" as an internal hierarchy marker.
    return name.replace(".set_primary", "")


def normalize_results(data: Dict[str, Tuple[float, float]], source: pathlib.Path) -> Dict[str, Tuple[float, float]]:
    normalized: Dict[str, Tuple[float, float]] = {}
    for name, vals in data.items():
        key = normalize_name(name)
        if key in normalized:
            raise ValueError(
                f"Duplicate normalized box name '{key}' found in {source}. "
                "Cannot compare safely."
            )
        normalized[key] = vals
    return normalized


def summarize_deltas(golden: Dict[str, Tuple[float, float]], result: Dict[str, Tuple[float, float]]) -> dict:
    golden_names = set(golden)
    result_names = set(result)
    common = sorted(golden_names & result_names)
    missing = sorted(golden_names - result_names)
    extra = sorted(result_names - golden_names)

    if not common:
        return {
            "matched_boxes": 0,
            "missing_boxes": len(missing),
            "extra_boxes": len(extra),
        }

    peak_errs: List[Tuple[str, float]] = []
    avg_errs: List[Tuple[str, float]] = []
    golden_peaks: List[float] = []
    golden_avgs: List[float] = []
    result_peaks: List[float] = []
    result_avgs: List[float] = []
    for name in common:
        g_peak, g_avg = golden[name]
        r_peak, r_avg = result[name]
        peak_errs.append((name, abs(r_peak - g_peak)))
        avg_errs.append((name, abs(r_avg - g_avg)))
        golden_peaks.append(g_peak)
        golden_avgs.append(g_avg)
        result_peaks.append(r_peak)
        result_avgs.append(r_avg)

    peak_max_box, peak_max_abs = max(peak_errs, key=lambda p: p[1])
    avg_max_box, avg_max_abs = max(avg_errs, key=lambda p: p[1])

    peak_mae = sum(err for _, err in peak_errs) / len(peak_errs)
    avg_mae = sum(err for _, err in avg_errs) / len(avg_errs)

    peak_rmse = math.sqrt(sum(err * err for _, err in peak_errs) / len(peak_errs))
    avg_rmse = math.sqrt(sum(err * err for _, err in avg_errs) / len(avg_errs))

    peak_var_g = _population_variance(golden_peaks)
    peak_var_o = _population_variance(result_peaks)
    avg_var_g = _population_variance(golden_avgs)
    avg_var_o = _population_variance(result_avgs)

    peak_std_g = math.sqrt(peak_var_g)
    avg_std_g = math.sqrt(avg_var_g)

    return {
        "matched_boxes": len(common),
        "missing_boxes": len(missing),
        "extra_boxes": len(extra),
        "peak_mae_C": peak_mae,
        "peak_rmse_C": peak_rmse,
        "peak_max_abs_C": peak_max_abs,
        "peak_max_box": peak_max_box,
        "avg_mae_C": avg_mae,
        "avg_rmse_C": avg_rmse,
        "avg_max_abs_C": avg_max_abs,
        "avg_max_box": avg_max_box,
        # Percentage metrics (100 = perfect)
        "peak_mae_pct": _error_score_pct(peak_mae, peak_std_g),
        "peak_rmse_pct": _error_score_pct(peak_rmse, peak_std_g),
        "peak_max_abs_pct": _error_score_pct(peak_max_abs, peak_std_g),
        "avg_mae_pct": _error_score_pct(avg_mae, avg_std_g),
        "avg_rmse_pct": _error_score_pct(avg_rmse, avg_std_g),
        "avg_max_abs_pct": _error_score_pct(avg_max_abs, avg_std_g),
        # Requested variance percentage: var(golden)/var(ours) * 100
        "peak_var_golden_over_ours_pct": _ratio_pct(peak_var_g, peak_var_o),
        "avg_var_golden_over_ours_pct": _ratio_pct(avg_var_g, avg_var_o),
        # Symmetric bounded variance match percentage
        "peak_var_match_pct": _ratio_match_pct(peak_var_g, peak_var_o),
        "avg_var_match_pct": _ratio_match_pct(avg_var_g, avg_var_o),
    }


def print_results(golden_count: int, compared_rows: List[dict], skipped_rows: List[dict]) -> None:
    print(f"Golden boxes: {golden_count}")
    print("")

    if compared_rows:
        print("Compared files (same box count):")
        for row in compared_rows:
            print(
                f"- {row['file_name']}: "
                f"matched={row['matched_boxes']}, "
                f"peak_mae={row['peak_mae_pct']:.2f}% ({row['peak_mae_C']:.6f} C), "
                f"peak_max={row['peak_max_abs_pct']:.2f}% ({row['peak_max_abs_C']:.6f} C, {row['peak_max_box']}), "
                f"avg_mae={row['avg_mae_pct']:.2f}% ({row['avg_mae_C']:.6f} C), "
                f"avg_max={row['avg_max_abs_pct']:.2f}% ({row['avg_max_abs_C']:.6f} C, {row['avg_max_box']}), "
                f"var_pct[g/o] peak={row['peak_var_golden_over_ours_pct']:.2f}% avg={row['avg_var_golden_over_ours_pct']:.2f}%"
            )
    else:
        print("No result files matched the golden box count.")

    if skipped_rows:
        print("")
        print("Skipped files:")
        for row in skipped_rows:
            print(f"- {row['file_name']}: {row['reason']}")


def write_csv(rows: List[dict], out_path: pathlib.Path) -> None:
    if not rows:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_name",
        "file_path",
        "golden_boxes",
        "result_boxes",
        "matched_boxes",
        "missing_boxes",
        "extra_boxes",
        "peak_mae_C",
        "peak_rmse_C",
        "peak_max_abs_C",
        "peak_max_box",
        "avg_mae_C",
        "avg_rmse_C",
        "avg_max_abs_C",
        "avg_max_box",
        "peak_mae_pct",
        "peak_rmse_pct",
        "peak_max_abs_pct",
        "avg_mae_pct",
        "avg_rmse_pct",
        "avg_max_abs_pct",
        "peak_var_golden_over_ours_pct",
        "avg_var_golden_over_ours_pct",
        "peak_var_match_pct",
        "avg_var_match_pct",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        default="solutions/golden_output_results.txt",
        help="Golden results file in *_results.txt dictionary format.",
    )
    parser.add_argument(
        "--results_dir",
        default="out_therm",
        help="Directory containing *_results.txt files to compare.",
    )
    parser.add_argument(
        "--csv",
        default="out_therm/golden_comparison.csv",
        help="Optional CSV output path for comparison rows.",
    )
    args = parser.parse_args()

    golden_path = pathlib.Path(args.golden)
    results_dir = pathlib.Path(args.results_dir)
    csv_path = pathlib.Path(args.csv)

    if not golden_path.exists():
        print(f"ERROR: Golden file not found: {golden_path}", file=sys.stderr)
        return 1
    if not results_dir.exists():
        print(f"ERROR: Results directory not found: {results_dir}", file=sys.stderr)
        return 1

    golden = load_results_txt(golden_path)
    golden = normalize_results(golden, golden_path)
    golden_count = len(golden)
    if golden_count == 0:
        print(f"ERROR: Parsed zero boxes from golden file: {golden_path}", file=sys.stderr)
        return 1

    compared_rows: List[dict] = []
    skipped_rows: List[dict] = []

    for result_path in sorted(results_dir.glob("*_results.txt")):
        result = load_results_txt(result_path)
        result = normalize_results(result, result_path)
        result_count = len(result)
        if result_count != golden_count:
            skipped_rows.append(
                {
                    "file_name": result_path.name,
                    "file_path": str(result_path),
                    "box_count": result_count,
                    "reason": f"boxes={result_count} (expected {golden_count})",
                }
            )
            continue

        common_count = len(set(golden) & set(result))
        if common_count != golden_count:
            skipped_rows.append(
                {
                    "file_name": result_path.name,
                    "file_path": str(result_path),
                    "box_count": result_count,
                    "reason": (
                        f"box names differ after normalization "
                        f"(common={common_count}, expected={golden_count})"
                    ),
                }
            )
            continue

        metrics = summarize_deltas(golden, result)
        row = {
            "file_name": result_path.name,
            "file_path": str(result_path),
            "golden_boxes": golden_count,
            "result_boxes": result_count,
            **metrics,
        }
        compared_rows.append(row)

    print_results(golden_count, compared_rows, skipped_rows)
    write_csv(compared_rows, csv_path)
    if compared_rows:
        print("")
        print(f"Wrote comparison CSV: {csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
