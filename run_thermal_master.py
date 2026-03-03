from __future__ import annotations

import argparse
import json
from typing import List

from thermal_analysis_master import (
    ExperimentRequest,
    ThermalAnalysisMaster,
)


DEFAULT_START_POWER = 540.0
DEFAULT_POWER_STEP = 20.0
DEFAULT_MIN_POWER_FRACTION = 0.2
DEFAULT_HBM_POWER = 5.0
DEFAULT_NUM_LAYERS = 32


def parse_htc_list(raw: str) -> List[int]:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token))
    if not values:
        raise argparse.ArgumentTypeError("Provide at least one HTC value, e.g. '7,10,20'.")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Thermal analysis runner that mirrors the GUI's iteration semantics."
    )
    parser.add_argument(
        "--system-name",
        default="3D_1GPU",
        choices=["2p5D_1GPU", "2p5D_waferscale", "3D_waferscale", "3D_1GPU"],
        help="Hardware configuration to evaluate.",
    )
    parser.add_argument(
        "--htc",
        type=parse_htc_list,
        default=parse_htc_list("7,10,20"),
        help="Comma-separated HTC values to evaluate (kW/(m^2*K)).",
    )
    parser.add_argument(
        "--start-power",
        type=float,
        default=DEFAULT_START_POWER,
        help="Starting GPU power in watts.",
    )
    parser.add_argument(
        "--power-step",
        type=float,
        default=DEFAULT_POWER_STEP,
        help="Power decrement per iteration in watts.",
    )
    parser.add_argument(
        "--min-power-fraction",
        type=float,
        default=DEFAULT_MIN_POWER_FRACTION,
        help="Minimum power as a fraction of the start power (0-1].",
    )
    parser.add_argument(
        "--tim-cond",
        type=int,
        default=1,
        help="TIM conductivity selector (matches existing configs).",
    )
    parser.add_argument(
        "--infill-cond",
        type=int,
        default=237,
        help="Infill conductivity selector (matches existing configs).",
    )
    parser.add_argument(
        "--hbm-power",
        type=float,
        default=DEFAULT_HBM_POWER,
        help="HBM power value used for all iterations (watts).",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=DEFAULT_NUM_LAYERS,
        help="Number of model layers used to scale idle fraction outputs.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Optional thread pool size override.",
    )

    args = parser.parse_args()

    htc_values = args.htc
    requests = [
        ExperimentRequest(
            system_name=args.system_name,
            htc=htc,
            tim_cond=args.tim_cond,
            infill_cond=args.infill_cond,
            hbm_power=args.hbm_power,
            start_power=args.start_power,
            num_layers=args.num_layers,
            power_step=args.power_step,
            min_power_fraction=args.min_power_fraction,
        )
        for htc in htc_values
    ]

    with ThermalAnalysisMaster(max_workers=args.max_workers) as master:
        print("Running thermal experiments...")
        results = master.run_experiments(requests)

    for result in results:
        if result.error:
            print(
                json.dumps(
                    {
                        "htc": result.request.htc,
                        "error": result.error,
                    },
                    indent=2,
                )
            )
            continue

        report = {
            "htc": result.request.htc,
            "gpu_power_final": result.final_gpu_power,
            "hbm_power_final": result.final_hbm_power,
            "runtime_seconds": result.runtime_seconds,
            "gpu_peak_temperature": result.gpu_peak_temperature,
            "hbm_peak_temperature": result.hbm_peak_temperature,
            "gpu_time_frac_idle": result.gpu_time_frac_idle,
            "iterations_executed": result.iterations_executed,
            "reti_index": result.reti_index,
        }
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
