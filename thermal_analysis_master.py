from __future__ import annotations

import contextlib
import math
import os
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

from thermal_analysis_gui import (
    GPU_FLOPs_throttled,
    GPU_throttling,
    HBM_throttled_performance,
    step,
)


@dataclass(frozen=True)
class IterationKey:
    system_name: str
    htc: int
    tim_cond: int
    infill_cond: int
    hbm_power: float
    gpu_power: float
    gpu_flops_power: float
    is_first_iteration: bool
    start_power: float


@dataclass
class IterationOutcome:
    key: IterationKey
    runtime_seconds: Optional[float]
    gpu_time_frac_idle: Optional[float]
    gpu_power_next: float
    hbm_power_next: float
    gpu_flops_power_next: float
    gpu_peak_temperature_current: float
    hbm_peak_temperature_current: float
    gpu_peak_temperature_next: float
    hbm_peak_temperature_next: float
    error: Optional[str]
    temp_config_path: Optional[Path]
    exp_dir: Optional[Path]


@dataclass(frozen=True)
class ExperimentRequest:
    system_name: str
    htc: int
    tim_cond: int = 1
    infill_cond: int = 237
    hbm_power: float = 5.0
    start_power: float = 540.0
    num_layers: int = 32
    power_step: float = 20.0
    min_power_fraction: float = 0.2


@dataclass
class ExperimentResult:
    request: ExperimentRequest
    runtime_seconds: Optional[float]
    gpu_peak_temperature: Optional[float]
    hbm_peak_temperature: Optional[float]
    gpu_time_frac_idle: Optional[float]
    iterations_executed: int
    final_gpu_power: float
    final_hbm_power: float
    reti_index: int
    error: Optional[str]

    def as_tuple(self) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        return (
            self.runtime_seconds,
            self.gpu_peak_temperature,
            self.hbm_peak_temperature,
            self.gpu_time_frac_idle,
        )


class ThermalAnalysisMaster:
    """Runs thermal experiments while preserving the GUI's original semantics."""

    GPU_SAFE_TEMPERATURE = 95.0
    GPU_IDLE_POWER = 42.0
    BASE_FREQUENCY_HZ = 1.41e9
    HBM_LATENCY_BASE = 100e-9

    def __init__(self, max_workers: Optional[int] = None) -> None:
        worker_count = max_workers or min(8, os.cpu_count() or 1)
        self._executor = ThreadPoolExecutor(max_workers=worker_count)
        self._iteration_cache: Dict[IterationKey, IterationOutcome] = {}
        self._inflight: Dict[IterationKey, Future[IterationOutcome]] = {}
        self._cache_lock = threading.Lock()

        self._repo_root = Path(__file__).resolve().parent
        self._configs_root = (
            self._repo_root
            / "DeepFlow_llm_dev"
            / "configs"
            / "hardware-config"
        )
        self._model_config_path = (
            self._repo_root
            / "DeepFlow_llm_dev"
            / "configs"
            / "model-config"
            / "LLM_thermal.yaml"
        )
        self._output_root = self._repo_root / "output_master"
        self._output_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def __enter__(self) -> "ThermalAnalysisMaster":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_experiment(self, request: ExperimentRequest) -> ExperimentResult:
        max_iterations = self._compute_max_iterations(
            request.start_power,
            request.power_step,
            request.min_power_fraction,
        )

        gpu_power = request.start_power
        hbm_power = request.hbm_power
        gpu_flops_power = request.start_power

        current_gpu_temp, current_hbm_temp = step(
            system_name=request.system_name,
            GPU_power=gpu_power,
            HBM_power=hbm_power,
            HTC=request.htc,
            TIM_cond=request.tim_cond,
            infill_cond=request.infill_cond,
        )

        runtimes: List[Optional[float]] = []
        gpu_time_frac_idle_list: List[Optional[float]] = []
        gpu_peak_temperature_list: List[float] = [current_gpu_temp]
        hbm_peak_temperature_list: List[float] = [current_hbm_temp]
        gpu_power_list: List[float] = [gpu_power]
        hbm_power_list: List[float] = [hbm_power]

        old_gpu_temp = -10.0
        old_hbm_temp = -10.0
        old_old_gpu_temp = -20.0
        old_old_hbm_temp = -20.0

        iterations = 0
        reti = -1
        error: Optional[str] = None

        while (
            abs(old_hbm_temp - current_hbm_temp) > 0.1
            or current_gpu_temp > self.GPU_SAFE_TEMPERATURE
        ):
            key = self._make_iteration_key(
                request=request,
                hbm_power=hbm_power,
                gpu_power=gpu_power,
                gpu_flops_power=gpu_flops_power,
                is_first=(iterations == 0),
            )

            outcome = self._get_or_compute_iteration(key, request.num_layers)

            if outcome.error:
                error = outcome.error
                break

            runtimes.append(outcome.runtime_seconds)
            gpu_time_frac_idle_list.append(outcome.gpu_time_frac_idle)

            old_old_gpu_temp = old_gpu_temp
            old_old_hbm_temp = old_hbm_temp
            old_gpu_temp = current_gpu_temp
            old_hbm_temp = current_hbm_temp

            gpu_power = outcome.gpu_power_next
            hbm_power = outcome.hbm_power_next
            gpu_flops_power = outcome.gpu_flops_power_next
            current_gpu_temp = outcome.gpu_peak_temperature_next
            current_hbm_temp = outcome.hbm_peak_temperature_next

            gpu_peak_temperature_list.append(current_gpu_temp)
            hbm_peak_temperature_list.append(current_hbm_temp)
            gpu_power_list.append(gpu_power)
            hbm_power_list.append(hbm_power)

            iterations += 1
            if iterations >= max_iterations:
                break
            if current_gpu_temp == old_old_gpu_temp:
                if len(runtimes) > 1:
                    last = runtimes[-1]
                    prev = runtimes[-2]
                    if (
                        last is not None
                        and prev is not None
                        and last < prev
                    ):
                        reti = -2
                break

        runtime_final = runtimes[reti] if runtimes else None
        gpu_time_frac_idle_final = (
            gpu_time_frac_idle_list[reti] if gpu_time_frac_idle_list else None
        )
        gpu_peak_temperature_final = (
            gpu_peak_temperature_list[reti]
            if gpu_peak_temperature_list
            else None
        )
        hbm_peak_temperature_final = (
            hbm_peak_temperature_list[reti]
            if hbm_peak_temperature_list
            else None
        )
        final_gpu_power = gpu_power_list[reti] if gpu_power_list else gpu_power
        final_hbm_power = hbm_power_list[reti] if hbm_power_list else hbm_power

        return ExperimentResult(
            request=request,
            runtime_seconds=runtime_final,
            gpu_peak_temperature=gpu_peak_temperature_final,
            hbm_peak_temperature=hbm_peak_temperature_final,
            gpu_time_frac_idle=gpu_time_frac_idle_final,
            iterations_executed=iterations,
            final_gpu_power=final_gpu_power,
            final_hbm_power=final_hbm_power,
            reti_index=reti,
            error=error,
        )

    def run_experiments(
        self, requests: Sequence[ExperimentRequest], max_parallel: Optional[int] = None
    ) -> List[ExperimentResult]:
        if not requests:
            return []

        parallelism = max_parallel or min(
            len(requests), self._executor._max_workers  # type: ignore[attr-defined]
        )
        results: List[Optional[ExperimentResult]] = [None] * len(requests)
        with ThreadPoolExecutor(max_workers=parallelism) as pool:
            future_to_index = {
                pool.submit(self.run_experiment, request): idx
                for idx, request in enumerate(requests)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                results[idx] = future.result()
        return [result for result in results if result is not None]

    # ------------------------------------------------------------------
    # Iteration execution & caching
    # ------------------------------------------------------------------
    def _get_or_compute_iteration(
        self, key: IterationKey, num_layers: int
    ) -> IterationOutcome:
        with self._cache_lock:
            if key in self._iteration_cache:
                return self._iteration_cache[key]
            if key in self._inflight:
                future = self._inflight[key]
            else:
                future = self._executor.submit(
                    self._compute_iteration,
                    key,
                    num_layers,
                )
                self._inflight[key] = future
        outcome = future.result()
        with self._cache_lock:
            self._iteration_cache[key] = outcome
            self._inflight.pop(key, None)
        return outcome

    def _compute_iteration(
        self, key: IterationKey, num_layers: int
    ) -> IterationOutcome:
        base_config_path, hbm_bandwidth_reference = self._resolve_config(
            key.system_name
        )
        current_gpu_temp, current_hbm_temp = step(
            system_name=key.system_name,
            GPU_power=key.gpu_power,
            HBM_power=key.hbm_power,
            HTC=key.htc,
            TIM_cond=key.tim_cond,
            infill_cond=key.infill_cond,
        )

        nominal_frequency, gpu_flops_power_next, register_bandwidth, l1_bandwidth, l2_bandwidth = (
            GPU_FLOPs_throttled(
                GPU_peak_temperature=current_gpu_temp,
                GPU_safe_temperature=self.GPU_SAFE_TEMPERATURE,
                GPU_peak_power=key.gpu_flops_power,
                GPU_average_power=key.gpu_power,
            )
        )

        if key.is_first_iteration:
            nominal_frequency = self.BASE_FREQUENCY_HZ
            gpu_flops_power_next = key.start_power

        hbm_bandwidth, hbm_latency, hbm_power_next = HBM_throttled_performance(
            bandwidth=hbm_bandwidth_reference,
            latency=self.HBM_LATENCY_BASE,
            HBM_peak_temperature=current_hbm_temp,
        )

        nominal_frequency_ghz = nominal_frequency / 1e9
        hbm_latency_ns = hbm_latency * 1e9

        config_data = self._load_config(base_config_path)
        self._update_config_scalars(
            config_data,
            nominal_frequency_ghz=nominal_frequency_ghz,
            hbm_bandwidth_gbps=math.ceil(hbm_bandwidth),
            hbm_latency_ns=hbm_latency_ns,
            l2_bandwidth_gbps=math.ceil(l2_bandwidth),
            l1_bandwidth_gbps=math.ceil(l1_bandwidth),
            register_bandwidth_gbps=math.ceil(register_bandwidth),
        )

        temp_config_path = self._write_temp_config(config_data)
        exp_dir = self._output_root / (
            f"{key.system_name}_htc{key.htc}_gp{int(round(key.gpu_power))}_"
            f"{abs(hash(key)) & 0xFFFF:04x}"
        )
        exp_dir.mkdir(parents=True, exist_ok=True)

        runtime_seconds: Optional[float] = None
        gpu_time_frac_idle: Optional[float] = None
        error: Optional[str] = None

        try:
            with contextlib.redirect_stdout(None):
                from DeepFlow_llm_dev.run_perf import run_LLM

                runtime_seconds, gpu_time_frac_idle = run_LLM(
                    mode="LLM",
                    exp_hw_config_path=str(temp_config_path),
                    exp_model_config_path=str(self._model_config_path),
                    exp_dir=str(exp_dir),
                )
        except Exception as exc:  # pylint: disable=broad-except
            error = str(exc)
        else:
            if runtime_seconds is not None:
                runtime_seconds = float(runtime_seconds)
            if gpu_time_frac_idle is not None:
                gpu_time_frac_idle = float(gpu_time_frac_idle) * num_layers

        if gpu_time_frac_idle is not None:
            gpu_power_next = GPU_throttling(
                GPU_power=gpu_flops_power_next,
                GPU_time_frac_idle=gpu_time_frac_idle,
                GPU_idle_power=self.GPU_IDLE_POWER,
            )
        else:
            gpu_power_next = key.gpu_power

        gpu_peak_temperature_next, hbm_peak_temperature_next = step(
            system_name=key.system_name,
            GPU_power=gpu_power_next,
            HBM_power=hbm_power_next,
            HTC=key.htc,
            TIM_cond=key.tim_cond,
            infill_cond=key.infill_cond,
        )

        return IterationOutcome(
            key=key,
            runtime_seconds=runtime_seconds,
            gpu_time_frac_idle=gpu_time_frac_idle,
            gpu_power_next=gpu_power_next,
            hbm_power_next=hbm_power_next,
            gpu_flops_power_next=gpu_flops_power_next,
            gpu_peak_temperature_current=current_gpu_temp,
            hbm_peak_temperature_current=current_hbm_temp,
            gpu_peak_temperature_next=gpu_peak_temperature_next,
            hbm_peak_temperature_next=hbm_peak_temperature_next,
            error=error,
            temp_config_path=temp_config_path,
            exp_dir=exp_dir,
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_max_iterations(
        start_power: float, power_step: float, min_fraction: float
    ) -> int:
        min_power = start_power * max(min_fraction, 0.0)
        if power_step <= 0:
            return 100
        count = int(math.ceil((start_power - min_power) / power_step)) + 1
        return max(count, 1)

    def _make_iteration_key(
        self,
        request: ExperimentRequest,
        hbm_power: float,
        gpu_power: float,
        gpu_flops_power: float,
        is_first: bool,
    ) -> IterationKey:
        return IterationKey(
            system_name=request.system_name,
            htc=request.htc,
            tim_cond=request.tim_cond,
            infill_cond=request.infill_cond,
            hbm_power=self._quantize(hbm_power),
            gpu_power=self._quantize(gpu_power),
            gpu_flops_power=self._quantize(gpu_flops_power),
            is_first_iteration=is_first,
            start_power=self._quantize(request.start_power),
        )

    def _resolve_config(self, system_name: str) -> Tuple[Path, float]:
        if system_name in {"2p5D_1GPU", "2p5D_waferscale"}:
            filename = "testing_thermal_A100_2p5D.yaml"
            hbm_ref = 1986.0
        elif system_name == "3D_waferscale":
            filename = "testing_thermal_A100.yaml"
            hbm_ref = 7944.0
        elif system_name == "3D_1GPU":
            filename = "testing_thermal_A100_3D_1GPU_ECTC.yaml"
            hbm_ref = 7944.0
        else:
            raise ValueError(f"Unsupported system_name '{system_name}'.")

        config_path = self._configs_root / filename
        if not config_path.exists():
            raise FileNotFoundError(config_path)
        return config_path, hbm_ref

    @staticmethod
    def _load_config(path: Path) -> Dict[str, object]:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    @staticmethod
    def _write_temp_config(data: Dict[str, object]) -> Path:
        fd, temp_path = tempfile.mkstemp(suffix=".yaml", prefix="thermal_iter_")
        os.close(fd)
        with open(temp_path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False)
        return Path(temp_path)

    @staticmethod
    def _update_config_scalars(
        config_data: Dict[str, object],
        nominal_frequency_ghz: float,
        hbm_bandwidth_gbps: int,
        hbm_latency_ns: float,
        l2_bandwidth_gbps: int,
        l1_bandwidth_gbps: int,
        register_bandwidth_gbps: int,
    ) -> None:
        tech_param = config_data.setdefault("tech_param", {})
        core = tech_param.setdefault("core", {})
        dram = tech_param.setdefault("DRAM", {})
        sram_l2 = tech_param.setdefault("SRAM-L2", {})
        sram_l1 = tech_param.setdefault("SRAM-L1", {})
        sram_r = tech_param.setdefault("SRAM-R", {})

        rounded_frequency_ghz = float(f"{nominal_frequency_ghz:.2f}")
        core["operating_frequency"] = rounded_frequency_ghz * 1e9

        dram["bandwidth"] = float(hbm_bandwidth_gbps)
        dram["latency"] = float(f"{hbm_latency_ns:.1f}") * 1e-9

        sram_l2["bandwidth"] = float(l2_bandwidth_gbps)
        sram_l1["bandwidth"] = float(l1_bandwidth_gbps)
        sram_r["bandwidth"] = float(register_bandwidth_gbps)

    @staticmethod
    def _quantize(value: float, digits: int = 6) -> float:
        return round(float(value), digits)


__all__ = [
    "IterationKey",
    "IterationOutcome",
    "ExperimentRequest",
    "ExperimentResult",
    "ThermalAnalysisMaster",
]
