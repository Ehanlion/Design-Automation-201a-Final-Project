#!/usr/bin/env python3
"""
Compare out_therm/*_results.txt files against a golden *_results.txt reference.

Only files with the same number of boxes as the golden reference are evaluated.
"""

import argparse
import ast
import csv
import pathlib
import re
import sys
from typing import Dict, List, Tuple

RESULTS_RE = re.compile(r"results\s*=\s*(\{.*\})\s*$", re.DOTALL)
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR


def _resolve_existing_path(path_str: str) -> pathlib.Path:
    p = pathlib.Path(path_str)
    if p.is_absolute():
        return p
    cwd_candidate = (pathlib.Path.cwd() / p).resolve()
    if cwd_candidate.exists():
        return cwd_candidate
    project_candidate = (PROJECT_DIR / p).resolve()
    if project_candidate.exists():
        return project_candidate
    return project_candidate


def _resolve_output_path(path_str: str) -> pathlib.Path:
    p = pathlib.Path(path_str)
    if p.is_absolute():
        return p
    if p.parent == pathlib.Path("."):
        return (pathlib.Path.cwd() / p).resolve()
    return (PROJECT_DIR / p).resolve()


def _population_variance(values: List[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) * (v - mean) for v in values) / len(values)


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

    peak_mae = sum(err for _, err in peak_errs) / len(peak_errs)
    avg_mae = sum(err for _, err in avg_errs) / len(avg_errs)

    peak_var_g = _population_variance(golden_peaks)
    peak_var_o = _population_variance(result_peaks)
    avg_var_g = _population_variance(golden_avgs)
    avg_var_o = _population_variance(result_avgs)

    return {
        "matched_boxes": len(common),
        "missing_boxes": len(missing),
        "extra_boxes": len(extra),
        "peak_mae_C": peak_mae,
        "avg_mae_C": avg_mae,
        "peak_var_golden_C2": peak_var_g,
        "peak_var_result_C2": peak_var_o,
        "avg_var_golden_C2": avg_var_g,
        "avg_var_result_C2": avg_var_o,
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
                f"peak_mae={row['peak_mae_C']:.6f} C, "
                f"avg_mae={row['avg_mae_C']:.6f} C, "
                f"peak_variance_match={row['peak_var_match_pct']:.2f}% | 100.00% ideal, "
                f"avg_variance_match={row['avg_var_match_pct']:.2f}% | 100.00% ideal"
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
        "avg_mae_C",
        "peak_var_golden_C2",
        "peak_var_result_C2",
        "peak_var_match_pct",
        "avg_var_golden_C2",
        "avg_var_result_C2",
        "avg_var_match_pct",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _format_value_with_ideal(actual: str, ideal: str) -> str:
    return f"{actual} | {ideal} ideal"


def _metric_definitions_txt() -> List[str]:
    return [
        "Metric definitions:",
        "- matched_boxes: number of boxes shared after normalization; ideal = golden_box_count/golden_box_count",
        "- peak_mean_absolute_error_c: mean_i(|result_peak_i - golden_peak_i|); ideal = 0.000000 C",
        "- average_mean_absolute_error_c: mean_i(|result_avg_i - golden_avg_i|); ideal = 0.000000 C",
        "- peak_variance_match_percent: 100 * min(var(result_peak)/var(golden_peak), var(golden_peak)/var(result_peak)); ideal = 100.00%",
        "- average_variance_match_percent: 100 * min(var(result_avg)/var(golden_avg), var(golden_avg)/var(result_avg)); ideal = 100.00%",
        "- *_variance_values_c2: raw variance values in C^2 used by the variance-match formula",
    ]


def write_summary_txt(
    golden_count: int, compared_rows: List[dict], skipped_rows: List[dict], out_path: pathlib.Path
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        f.write("# Golden comparison summary\n")
        f.write("# One compared case per section. One metric per line.\n")
        f.write("# Focused on grading-relevant correctness metrics only.\n\n")
        for line in _metric_definitions_txt():
            f.write(f"{line}\n")
        f.write("\n")
        f.write(f"golden_box_count: {golden_count}\n")
        f.write(f"compared_case_count: {len(compared_rows)}\n")
        f.write(f"skipped_case_count: {len(skipped_rows)}\n\n")

        for idx, row in enumerate(compared_rows, start=1):
            matched_actual = f"{row['matched_boxes']}/{golden_count}"
            matched_ideal = f"{golden_count}/{golden_count}"
            peak_mae_actual = f"{row['peak_mae_C']:.6f} C"
            avg_mae_actual = f"{row['avg_mae_C']:.6f} C"
            peak_var_match_actual = f"{row['peak_var_match_pct']:.2f}%"
            avg_var_match_actual = f"{row['avg_var_match_pct']:.2f}%"
            f.write(f"Case {idx}: {row['file_name']}\n")
            f.write(
                "matched_boxes: "
                f"{_format_value_with_ideal(matched_actual, matched_ideal)}\n"
            )
            f.write(
                "peak_mean_absolute_error_c: "
                f"{_format_value_with_ideal(peak_mae_actual, '0.000000 C')}\n"
            )
            f.write(
                "average_mean_absolute_error_c: "
                f"{_format_value_with_ideal(avg_mae_actual, '0.000000 C')}\n"
            )
            f.write(
                "peak_variance_match_percent: "
                f"{_format_value_with_ideal(peak_var_match_actual, '100.00%')}\n"
            )
            f.write(
                "peak_variance_values_c2: "
                f"result={row['peak_var_result_C2']:.6f}, golden={row['peak_var_golden_C2']:.6f}\n"
            )
            f.write(
                "average_variance_match_percent: "
                f"{_format_value_with_ideal(avg_var_match_actual, '100.00%')}\n"
            )
            f.write(
                "average_variance_values_c2: "
                f"result={row['avg_var_result_C2']:.6f}, golden={row['avg_var_golden_C2']:.6f}\n\n"
            )

        if skipped_rows:
            f.write("Skipped files note:\n")
            f.write("Skipped files are excluded from compared metrics.\n")
            f.write("Skipped files:\n")
            for row in skipped_rows:
                f.write(f"- {row['file_name']}: {row['reason']}\n")


def write_summary_md(
    golden_count: int, compared_rows: List[dict], skipped_rows: List[dict], out_path: pathlib.Path
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        f.write("# Golden Comparison Summary\n\n")
        f.write("Focused on the grading-relevant correctness metrics only: distance from golden and variance match.\n\n")
        f.write("## Metric Definitions\n\n")
        f.write("| Metric | Calculation | Ideal |\n")
        f.write("| --- | --- | --- |\n")
        f.write("| Matched boxes | Shared box names after normalization | ")
        f.write(f"`{golden_count}/{golden_count}` |\n")
        f.write("| Peak MAE (C) | `mean_i(abs(result_peak_i - golden_peak_i))` | `0.000000` |\n")
        f.write("| Average MAE (C) | `mean_i(abs(result_avg_i - golden_avg_i))` | `0.000000` |\n")
        f.write("| Peak variance match (%) | `100 * min(var(result_peak)/var(golden_peak), var(golden_peak)/var(result_peak))` | `100.00%` |\n")
        f.write("| Average variance match (%) | `100 * min(var(result_avg)/var(golden_avg), var(golden_avg)/var(result_avg))` | `100.00%` |\n")
        f.write("\n")
        f.write("## Overview\n\n")
        f.write(f"- Golden box count: `{golden_count}`\n")
        f.write(f"- Compared case count: `{len(compared_rows)}`\n")
        f.write(f"- Skipped case count: `{len(skipped_rows)}`\n\n")

        if compared_rows:
            f.write("## Compared Cases\n\n")
            for idx, row in enumerate(compared_rows, start=1):
                f.write(f"### Case {idx}: `{row['file_name']}`\n\n")
                f.write("| Metric | Result | Ideal | Notes |\n")
                f.write("| --- | --- | --- | --- |\n")
                f.write(
                    f"| Matched boxes | `{row['matched_boxes']}/{golden_count}` | `{golden_count}/{golden_count}` | Same box count and normalized box names matched |\n"
                )
                f.write(
                    f"| Peak MAE (C) | `{row['peak_mae_C']:.6f}` | `0.000000` | Lower is better |\n"
                )
                f.write(
                    f"| Average MAE (C) | `{row['avg_mae_C']:.6f}` | `0.000000` | Lower is better |\n"
                )
                f.write(
                    f"| Peak variance match (%) | `{row['peak_var_match_pct']:.2f}%` | `100.00%` | `var(result_peak)={row['peak_var_result_C2']:.6f}`, `var(golden_peak)={row['peak_var_golden_C2']:.6f}` |\n"
                )
                f.write(
                    f"| Average variance match (%) | `{row['avg_var_match_pct']:.2f}%` | `100.00%` | `var(result_avg)={row['avg_var_result_C2']:.6f}`, `var(golden_avg)={row['avg_var_golden_C2']:.6f}` |\n\n"
                )
        else:
            f.write("## Compared Cases\n\n")
            f.write("No result files matched the golden box count.\n\n")

        if skipped_rows:
            f.write("## Skipped Files\n\n")
            f.write("These files were excluded from the compared metrics.\n\n")
            for row in skipped_rows:
                f.write(f"- `{row['file_name']}`: {row['reason']}\n")


def _ensure_golden_results_file(golden_path: pathlib.Path) -> pathlib.Path:
    """
    Ensure golden *_results.txt exists.

    If missing and the corresponding golden_output.txt exists, auto-convert it.
    """
    if golden_path.exists():
        return golden_path

    candidate_source = golden_path.with_name("golden_output.txt")
    if not candidate_source.exists():
        return golden_path

    try:
        from convert_golden_output import parse_golden, write_results_txt

        entries = parse_golden(candidate_source)
        if entries:
            write_results_txt(golden_path, entries)
            print(
                "Golden results file not found; generated automatically: "
                f"{candidate_source} -> {golden_path}"
            )
    except Exception as exc:
        print(
            f"WARNING: Failed to auto-generate golden results from {candidate_source}: {exc}",
            file=sys.stderr,
        )
    return golden_path


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
    parser.add_argument(
        "--summary_txt",
        default="out_therm/golden_comparison_summary.txt",
        help="Human-readable one-line-per-result summary output path.",
    )
    parser.add_argument(
        "--summary_md",
        default="out_therm/golden_comparison_summary.md",
        help="Formatted Markdown summary output path.",
    )
    args = parser.parse_args()

    golden_path = _resolve_existing_path(args.golden)
    results_dir = _resolve_existing_path(args.results_dir)
    csv_path = _resolve_output_path(args.csv)
    summary_txt_path = _resolve_output_path(args.summary_txt)
    summary_md_path = _resolve_output_path(args.summary_md)

    golden_path = _ensure_golden_results_file(golden_path)

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
    write_summary_txt(golden_count, compared_rows, skipped_rows, summary_txt_path)
    write_summary_md(golden_count, compared_rows, skipped_rows, summary_md_path)
    if compared_rows:
        print("")
        print(f"Wrote comparison CSV: {csv_path}")
    print(f"Wrote comparison summary TXT: {summary_txt_path}")
    print(f"Wrote comparison summary MD: {summary_md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
