#!/usr/bin/env python3
"""
Visualize thermal simulation results from YAML output files.

Generates bar charts of peak/average temperatures per component and a
comparison chart across configurations.

Usage:
  python3 visualize_results.py --results_dir out_therm
"""

import argparse
import pathlib
import sys

import yaml

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


CONFIG_LABELS = {
    "ECTC_3D_1GPU_8high_120125_higherHTC": "Config 1: 3D GPU-on-top",
    "ECTC_3D_1GPU_8high_110325_higherHTC": "Config 2: 3D GPU-bottom",
    "ECTC_2p5D_1GPU_8high_110325_higherHTC": "Config 3: 2.5D",
}


def load_results(path):
    with path.open() as f:
        return yaml.safe_load(f) or {}


def classify_box(name):
    parts = name.split(".")
    last = parts[-1].lower()
    if "gpu" in last:
        return "GPU"
    if last.startswith("hbm"):
        depth = sum(1 for p in parts if p.lower().startswith("hbm_l"))
        if depth > 0:
            return None
        return last.upper()
    if "dummy" in last.lower():
        return last
    if last == "substrate":
        return "Substrate"
    if name == parts[0] and "power_source" in last:
        return "Power_Source"
    return None


def plot_config_temperatures(data, project_name, out_dir):
    if not HAS_MPL:
        return

    labels, peaks, avgs = [], [], []
    for box_name, vals in data.items():
        cat = classify_box(box_name)
        if cat is None:
            continue
        peak, avg = vals[0], vals[1]
        labels.append(cat)
        peaks.append(peak)
        avgs.append(avg)

    if not labels:
        return

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 0.6), 6))
    x = range(len(labels))
    w = 0.35
    ax.bar([i - w / 2 for i in x], peaks, w, label="Peak T (°C)", color="#e74c3c", alpha=0.85)
    ax.bar([i + w / 2 for i in x], avgs, w, label="Avg T (°C)", color="#3498db", alpha=0.85)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Temperature (°C)")
    label = CONFIG_LABELS.get(project_name, project_name)
    ax.set_title(f"Temperature Distribution — {label}")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    ax.axhline(y=45, color="green", linestyle="--", alpha=0.5, label="Ambient (45°C)")

    fig.tight_layout()
    out_path = out_dir / f"{project_name}_temp_chart.png"
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_comparison(all_data, out_dir):
    if not HAS_MPL or len(all_data) < 2:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    configs = []
    gpu_peaks = []
    hbm_peaks = []
    for project, data in all_data.items():
        label = CONFIG_LABELS.get(project, project)
        configs.append(label)
        gpu_p = max((v[0] for k, v in data.items() if "gpu" in k.split(".")[-1].lower()), default=0)
        hbm_p = max((v[0] for k, v in data.items() if k.split(".")[-1].lower().startswith("hbm")), default=0)
        gpu_peaks.append(gpu_p)
        hbm_peaks.append(hbm_p)

    colors_gpu = ["#e74c3c", "#c0392b", "#a93226"]
    colors_hbm = ["#3498db", "#2980b9", "#2471a3"]

    ax = axes[0]
    bars = ax.barh(configs, gpu_peaks, color=colors_gpu[:len(configs)], alpha=0.85)
    ax.set_xlabel("Peak Temperature (°C)")
    ax.set_title("GPU Peak Temperature")
    ax.axvline(x=45, color="green", linestyle="--", alpha=0.5)
    for bar, val in zip(bars, gpu_peaks):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}°C", va="center", fontsize=9)

    ax = axes[1]
    bars = ax.barh(configs, hbm_peaks, color=colors_hbm[:len(configs)], alpha=0.85)
    ax.set_xlabel("Peak Temperature (°C)")
    ax.set_title("HBM Peak Temperature")
    ax.axvline(x=45, color="green", linestyle="--", alpha=0.5)
    for bar, val in zip(bars, hbm_peaks):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}°C", va="center", fontsize=9)

    fig.suptitle("Cross-Configuration Temperature Comparison", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = out_dir / "temperature_comparison.png"
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize thermal simulation results.")
    parser.add_argument("--results_dir", default="out_therm", help="Directory with *_results.yaml files.")
    args = parser.parse_args()

    if not HAS_MPL:
        print("matplotlib not available — skipping visualization.")
        sys.exit(0)

    results_dir = pathlib.Path(args.results_dir)
    files = sorted(results_dir.glob("*_results.yaml"))

    if not files:
        print(f"No result files found in {results_dir}")
        sys.exit(1)

    all_data = {}
    for f in files:
        project = f.stem.replace("_results", "")
        data = load_results(f)
        all_data[project] = data
        print(f"Plotting: {project}")
        plot_config_temperatures(data, project, results_dir)

    plot_comparison(all_data, results_dir)
    print("\nVisualization complete.")


if __name__ == "__main__":
    main()
