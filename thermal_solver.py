"""
3D Thermal Solver for EE201A Final Project.

Two solver approaches are available, tried in order:

  1. Voxel thermal RC network (PRIMARY for final-project runs)
     - Builds a non-uniform 3D voxel mesh aligned to package boundaries.
     - Assigns anisotropic per-voxel conductivities from the layer stackup.
     - Deposits GPU/HBM power on the center z-plane of each powered die/tier.
     - Exports the full meshed RC netlist to out_therm/thermal_netlist.sp.
     - Solves the RC netlist with the project-local ngspice binary first.
     - Falls back to scipy sparse CG (or numpy SOR) only if ngspice fails.

  2. PySpice box-level resistor network (LEGACY / non-voxel path)
     - Builds a coarse one-node-per-box SPICE network using the PySpice API.
     - Attempts ngspice operating-point simulation via PySpice/local netlist.
     - Falls back to a direct matrix solve from the same box-level topology.

POWER ASSUMPTION — 270 W GPU (NOT 400 W):
  The project PDF states 400 W for the GPU. However, the Piazza course forum
  clarified (Winter 2026) that the XML configs carry 270 W as core_power and
  that is the correct value to use:
    "Please use the 270 W values as in therm.py for now."
  The constant GPU_TOTAL_POWER_W below reflects this and is used ONLY in the
  legacy fallback path when no explicit box powers are found in the input.

SIMULATION TIMING:
  The simulation (this entire module) is intentionally excluded from the
  project figure-of-merit runtime. The caller (therm.py) measures placement
  and sizing time separately and reports "Total runtime (excluding
  SPICE/simulation)". This is per the project spec: timing should reflect
  the algorithmic complexity of mesh generation and placement, not the linear
  algebra solve.
"""

import math
import os
import time
import numpy as np
from pathlib import Path

try:
    from scipy import sparse
    from scipy.sparse.linalg import spsolve, cg
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# PySpice support is kept for the legacy box-level network path.
# Final-project runs use the voxel RC netlist + local ngspice path first.
HAS_PYSPICE = False
try:
    from PySpice.Spice.Netlist import Circuit as _PySpiceCircuit
    HAS_PYSPICE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Material conductivities (W/(m·K))
# ---------------------------------------------------------------------------

CONDUCTIVITY = {
    "Air":                    0.025,
    "FR-4":                   0.1,
    "Cu-Foil":              400.0,
    "Si":                   105.0,
    "Aluminium":            205.0,
    "TIM001":               100.0,
    "Glass":                  1.36,
    "TIM":                  100.0,
    "TIM0p5":                 5.0,
    "SnPb 67/37":            36.0,
    "Epoxy, Silver filled":   1.6,
    "EpAg":                   1.6,
    "EpAg_filled":            1.6,
    "Infill_material":       19.0,
    "Polymer1":             675.0,
    "SiO2":                   1.1,
    "AlN":                  237.0,
    "Epoxy":                  0.3,
}

AMBIENT_TEMP_C = 45.0

# GPU fallback power — 270 W per Piazza course-staff clarification.
# The project PDF says 400 W, but the correct value is 270 W (from the XML
# configs; confirmed on Piazza: "Please use the 270 W values as in therm.py").
# This constant is ONLY used when no explicit box.power values are found.
GPU_TOTAL_POWER_W = 270.0   # was 400.0 in starter code; corrected to 270 W
HBM_STACK_POWER_W = 5.0
H_BOTTOM = 10.0             # bottom convection coefficient W/(m²·K)

# Default paths for exported SPICE netlists
NETLIST_EXPORT_PATH = os.path.join("out_therm", "thermal_netlist.sp")
BOX_NETLIST_EXPORT_PATH = os.path.join("out_therm", "thermal_box_netlist.sp")


# Most recent solve metadata for concise run summaries in therm.py.
_LAST_SOLVE_SUMMARY = {
    "solver_mode": "unknown",
    "solver_backend": "unknown",
    "voxel_shape": None,
    "voxel_count": 0,
    "used_ngspice": False,
}

_REDUNDANT_REPORT_FILES = (
    "summary.csv",
    "summary.md",
    "golden_comparison.csv",
    "golden_comparison.md",
    "golden_comparison_summary.md",
)


def _reset_last_solve_summary():
    _LAST_SOLVE_SUMMARY.update(
        {
            "solver_mode": "unknown",
            "solver_backend": "unknown",
            "voxel_shape": None,
            "voxel_count": 0,
            "used_ngspice": False,
        }
    )


def _update_last_solve_summary(**kwargs):
    _LAST_SOLVE_SUMMARY.update(kwargs)


def get_last_solve_summary():
    """Return metadata from the most recent solve_thermal() call."""
    return dict(_LAST_SOLVE_SUMMARY)


def _purge_redundant_reports(out_dir="out_therm"):
    """Best-effort cleanup of redundant aggregate report artifacts."""
    try:
        base = Path(out_dir)
    except Exception:
        return
    for name in _REDUNDANT_REPORT_FILES:
        p = base / name
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def _env_flag(name, default=False):
    val = os.environ.get(name)
    if val is None:
        return default
    return str(val).strip().lower() not in {"0", "false", "no", "off"}


def _env_float(name, default):
    val = os.environ.get(name)
    if val is None:
        return float(default)
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(default)


# Final Project v4: GPU/HBM power should be deposited at the center z-plane
# of each powered die/tier. This requires voxel-level resolution.
FORCE_VOXEL_SOLVER_DEFAULT = _env_flag("EE201A_FORCE_VOXEL", default=True)
USE_CENTER_Z_PLANE_POWER_DEFAULT = _env_flag(
    "EE201A_CENTER_PLANE_POWER", default=True
)

# Default voxel grid controls (override via env when needed).
GRID_MAX_XY_MM = _env_float("EE201A_GRID_MAX_XY_MM", 2.0)
GRID_MAX_Z_MM = _env_float("EE201A_GRID_MAX_Z_MM", 0.3)
GRID_MIN_MM = _env_float("EE201A_GRID_MIN_MM", 0.001)
NGSPICE_TIMEOUT_S = _env_float("EE201A_NGSPICE_TIMEOUT_S", 600.0)
NGSPICE_PRINT_CHUNK = 64


def _estimate_convective_hc(heatsink_obj, hc_raw):
    """
    Estimate an effective top convection coefficient from heatsink metadata.

    For water-cooled setups we derive h from forced-convection correlations
    and treat the XML HTC as an upper bound when provided.

    This avoids directly using a nominal HTC in cases where fluid velocity is
    not specified and keeps the boundary model tied to geometry + flow regime.
    """
    hs = heatsink_obj or {}
    cooled_by = str(hs.get("cooled_by", "") or "").strip().lower()
    if cooled_by != "water":
        return hc_raw if (hc_raw is not None and hc_raw > 0) else 0.0

    # Parse flow speed from XML; empty string means unspecified.
    v = None
    fs = hs.get("fluid_speed", None)
    if fs not in (None, ""):
        try:
            v = float(fs)
        except (TypeError, ValueError):
            v = None
    if v is None or v <= 0:
        v = 1.0

    try:
        dx_m = float(hs.get("base_dx", 0.0)) / 1000.0
        dy_m = float(hs.get("base_dy", 0.0)) / 1000.0
        L = max(min(dx_m, dy_m), 1e-4)
    except (TypeError, ValueError):
        L = 0.02

    # Water properties near 45 C.
    rho = 990.0      # kg/m^3
    mu = 0.0006      # Pa·s
    kf = 0.63        # W/(m·K)
    pr = 4.0

    Re = max(rho * v * L / mu, 1.0)
    if Re < 5e5:
        # Laminar average Nu for constant heat flux over a flat plate.
        Nu = 0.680 * (Re ** 0.5) * (pr ** (1.0 / 3.0))
    else:
        Nu = (0.037 * (Re ** 0.8) - 871.0) * (pr ** (1.0 / 3.0))
    h_corr = max(Nu * kf / L, 1.0)

    if hc_raw is None or hc_raw <= 0:
        return h_corr
    return min(hc_raw, h_corr)

# Project-local ngspice installation (from setup/install_local_ngspice.sh).
PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_NGSPICE_PREFIX = PROJECT_ROOT / "third_party" / "ngspice" / "install"
LOCAL_NGSPICE_BIN = LOCAL_NGSPICE_PREFIX / "bin" / "ngspice"


# ============================================================================
# Material helpers (shared by both solver paths)
# ============================================================================

def _get_k(mat_str):
    """Thermal conductivity for a simple or composite material string."""
    if mat_str in CONDUCTIVITY:
        return CONDUCTIVITY[mat_str]
    if "," in mat_str and ":" in mat_str:
        k_s, r_s = 0.0, 0.0
        for part in mat_str.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            m, fs = part.rsplit(":", 1)
            try:
                f = float(fs)
            except ValueError:
                continue
            if f > 1.0:
                f /= 100.0
            k_s += f * CONDUCTIVITY.get(m.strip(), 1.0)
            r_s += f
        if r_s > 0:
            return k_s / r_s
    return CONDUCTIVITY.get("Si", 1.0)


def _build_layer_map(layers):
    """Map layer name → (thickness_mm, material_string, effective_k)."""
    lm = {}
    if not layers:
        return lm
    for la in layers:
        lm[la.get_name()] = (la.get_thickness(), la.get_material(), _get_k(la.get_material()))
    return lm


def _parse_stackup(box, lm):
    """Parse box stackup into list of (thickness_mm, k) tuples, bottom-up."""
    su = getattr(box, "stackup", None)
    if not su:
        return [(max(box.height, 1e-6), _get_k("Si"))]

    first = su.split(",", 1)[0]
    if first.count(":") >= 2:
        p = first.split(":")
        m1 = p[1].strip()
        try:
            r1 = float(p[2])
        except (IndexError, ValueError):
            r1 = 50.0
        try:
            rhs = su.split(",", 1)[1]
        except IndexError:
            return [(max(box.height, 1e-6), _get_k(m1))]
        if ":" in rhs:
            m2, r2s = rhs.rsplit(":", 1)
            try:
                r2 = float(r2s)
            except ValueError:
                r2 = 100 - r1
        else:
            m2, r2 = rhs.strip(), 100 - r1
        if r1 > 1:
            r1 /= 100.0
        if r2 > 1:
            r2 /= 100.0
        tot = r1 + r2
        k_eff = (r1 * _get_k(m1) + r2 * _get_k(m2.strip())) / tot if tot > 0 else _get_k("Si")
        return [(max(box.height, 1e-6), k_eff)]

    result = []
    for entry in su.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 2:
            continue
        try:
            cnt = float(parts[0]) if parts[0] else 1.0
        except ValueError:
            cnt = 1.0
        ln = parts[1]
        if ln in lm:
            t_mm, _, k = lm[ln]
            result.insert(0, (cnt * t_mm, k))
        else:
            result.insert(0, (cnt * 0.1, _get_k(ln)))
    return result if result else [(max(box.height, 1e-6), _get_k("Si"))]


def _box_eff_k(box, lm):
    """Volume-weighted average conductivity for the whole box."""
    layers = _parse_stackup(box, lm)
    tw = sum(t for t, _ in layers)
    if tw <= 0:
        return _get_k("Si")
    return sum(t * k for t, k in layers) / tw


def _retrieve_conductivity(box, voxel_z_lo, voxel_z_hi, lm):
    """Compute effective k for a specific z-slice through the box stackup."""
    layers = _parse_stackup(box, lm)
    if not layers:
        return _get_k("Si")

    voxel_dz = voxel_z_hi - voxel_z_lo
    if voxel_dz <= 0:
        return _get_k("Si")

    current_z = box.start_z
    k_acc = 0.0
    for t_mm, k in layers:
        layer_lo = current_z
        layer_hi = current_z + t_mm
        current_z = layer_hi
        ov_lo = max(layer_lo, voxel_z_lo)
        ov_hi = min(layer_hi, voxel_z_hi)
        if ov_lo < ov_hi:
            k_acc += (ov_hi - ov_lo) / voxel_dz * k

    return k_acc if k_acc > 0 else _get_k("Si")


def _retrieve_conductivity_aniso(box, voxel_z_lo, voxel_z_hi, lm):
    """
    Compute anisotropic effective conductivity for a z-slice.

    Returns
    -------
    (k_xy, k_z)
      k_xy: in-plane conductivity (arithmetic mix, parallel path)
      k_z : through-plane conductivity (harmonic mix, series path)
    """
    layers = _parse_stackup(box, lm)
    if not layers:
        k0 = _get_k("Si")
        return k0, k0

    voxel_dz = voxel_z_hi - voxel_z_lo
    if voxel_dz <= 0:
        k0 = _get_k("Si")
        return k0, k0

    current_z = box.start_z
    frac_sum = 0.0
    kxy_num = 0.0
    kz_denom = 0.0
    for t_mm, k in layers:
        layer_lo = current_z
        layer_hi = current_z + t_mm
        current_z = layer_hi
        ov_lo = max(layer_lo, voxel_z_lo)
        ov_hi = min(layer_hi, voxel_z_hi)
        if ov_lo < ov_hi and k > 0:
            frac = (ov_hi - ov_lo) / voxel_dz
            frac_sum += frac
            kxy_num += frac * k
            kz_denom += frac / k

    if frac_sum <= 0:
        k0 = _get_k("Si")
        return k0, k0

    k_xy = kxy_num / frac_sum
    k_z = frac_sum / kz_denom if kz_denom > 0 else k_xy
    return k_xy, k_z


# ============================================================================
# Box-level analytical resistances (used by both solver paths)
# ============================================================================

def _box_R(box, lm):
    eps = 1e-12
    layers = _parse_stackup(box, lm)
    w = max(box.width, eps) / 1e3
    l = max(box.length, eps) / 1e3
    a = w * l

    layers_m = [(max(t, eps) / 1e3, k) for t, k in layers]
    Rz = sum(t / (k + eps) for t, k in layers_m) / (a + eps)
    tt = sum(t for t, _ in layers_m)
    kp = sum(t * k for t, k in layers_m) / (tt + eps)
    Rx = w / (kp * tt * l + eps)
    Ry = l / (kp * tt * w + eps)
    return Rx, Ry, Rz


# ============================================================================
# PySpice Box-Level Thermal Solver (LEGACY / NON-VOXEL PATH)
# ============================================================================
#
# Thermal-to-electrical analogy:
#   Temperature rise above ambient  ↔  Voltage (V)
#   Power injection                 ↔  Current source (A)
#   Thermal resistance (K/W)        ↔  Electrical resistance (Ω)
#   Ambient boundary (T_amb)        ↔  Ground (0 V)
#
# Each physical box becomes one SPICE node. Adjacent boxes (touching in Z,
# with overlapping x-y footprints) are connected by a resistor whose value
# equals the sum of the two half-cell thermal resistances:
#
#   R_interface = h1/(2·k1·A) + h2/(2·k2·A)     [K/W = Ω in analogy]
#
# where h1/h2 are box heights, k1/k2 are effective conductivities, and A is
# the contact area (x-y overlap). Top-exposed boxes get a convective resistor
# to ground: R_conv = 1/(hc·A_top). Powered boxes receive current sources.
#
# The netlist is exported to NETLIST_EXPORT_PATH so the TA can inspect it.
# ============================================================================

def _contact_area_xy_mm2(b1, b2):
    """
    Return the x-y overlap area between two boxes in mm².

    Used to compute the thermal conductance between vertically adjacent boxes.
    """
    ox = min(b1.end_x, b2.end_x) - max(b1.start_x, b2.start_x)
    oy = min(b1.end_y, b2.end_y) - max(b1.start_y, b2.start_y)
    if ox <= 1e-6 or oy <= 1e-6:
        return 0.0
    return ox * oy


def _build_box_network_data(all_boxes, layers, hc_top):
    """
    Build box-level thermal conductance network from the list of all boxes.

    Each box is a thermal node. Adjacent boxes (sharing a z-face with non-zero
    x-y overlap) are connected by half-cell interface resistors. Top-exposed
    boxes get a convective conductance to ambient (ground). Powered boxes
    contribute to the power injection vector.

    Returns
    -------
    node_map : dict {box.name → int index}
    G_pairs  : list of (i, j, G_W_per_K) — conductances between node pairs
    P_vec    : numpy array of shape (N,) — power injection per node [W]
    G_conv   : numpy array of shape (N,) — convective conductance to ambient
    lm       : layer map (reused for analytical R calculation)
    """
    lm = _build_layer_map(layers)
    N = len(all_boxes)
    node_map = {b.name: i for i, b in enumerate(all_boxes)}

    tol_z = 1e-3  # mm — tolerance for z-interface detection
    eps = 1e-15

    G_pairs = []
    # Build z-adjacency conductances between all box pairs
    for i, b1 in enumerate(all_boxes):
        for j, b2 in enumerate(all_boxes):
            if j <= i:
                continue
            # Determine which box is on top and which on bottom
            if abs(b1.end_z - b2.start_z) < tol_z:
                b_bot, b_top = b1, b2
            elif abs(b2.end_z - b1.start_z) < tol_z:
                b_bot, b_top = b2, b1
            else:
                continue

            A_mm2 = _contact_area_xy_mm2(b_bot, b_top)
            if A_mm2 < 1e-6:
                continue

            A_m2 = A_mm2 / 1e6   # mm² → m²
            k1 = _box_eff_k(b_bot, lm)
            k2 = _box_eff_k(b_top, lm)
            h1_m = max(b_bot.height, eps) / 1000.0   # mm → m
            h2_m = max(b_top.height, eps) / 1000.0

            # Half-cell resistance for each box; series combination = interface R
            R_half1 = h1_m / (2.0 * max(k1, eps) * max(A_m2, eps))
            R_half2 = h2_m / (2.0 * max(k2, eps) * max(A_m2, eps))
            R_iface = R_half1 + R_half2
            if R_iface > 0:
                G_pairs.append((i, j, 1.0 / R_iface))

    # Power injection: use explicit box.power; fallback to legacy constants
    P_vec = np.zeros(N)
    has_explicit_power = False
    for i, box in enumerate(all_boxes):
        try:
            pwr = float(getattr(box, "power", 0.0) or 0.0)
        except (TypeError, ValueError):
            pwr = 0.0
        if pwr > 0:
            P_vec[i] = pwr
            has_explicit_power = True

    if not has_explicit_power:
        # Fallback: distribute GPU_TOTAL_POWER_W (270 W per Piazza) and
        # HBM_STACK_POWER_W among GPU and HBM leaf boxes respectively.
        gpu_b, hbm_leaf = [], []
        for i, box in enumerate(all_boxes):
            cp = getattr(box, "chiplet_parent", None)
            if cp is None:
                continue
            ct = cp.get_chiplet_type()
            if ct == "GPU":
                gpu_b.append(i)
            elif ct.startswith("HBM") and len(cp.get_child_chiplets()) == 0:
                hbm_leaf.append(i)
        n_stacks = max(1, len(hbm_leaf) // 8 if len(hbm_leaf) > 8 else 1)
        gpu_per = GPU_TOTAL_POWER_W / max(len(gpu_b), 1)
        hbm_per = (HBM_STACK_POWER_W * n_stacks) / max(len(hbm_leaf), 1) if hbm_leaf else 0.0
        for i in gpu_b:
            P_vec[i] = gpu_per
        for i in hbm_leaf:
            P_vec[i] = hbm_per

    # Convective boundary: top-exposed boxes get G_conv = hc_top * A_top
    G_conv = np.zeros(N)
    max_z = max(b.end_z for b in all_boxes)
    min_z = min(b.start_z for b in all_boxes)
    for i, box in enumerate(all_boxes):
        if abs(box.end_z - max_z) < tol_z:
            A_top_m2 = (box.width * box.length) / 1e6
            G_conv[i] += hc_top * A_top_m2
        if abs(box.start_z - min_z) < tol_z:
            A_bot_m2 = (box.width * box.length) / 1e6
            G_conv[i] += H_BOTTOM * A_bot_m2

    return node_map, G_pairs, P_vec, G_conv, lm


def _build_pyspice_circuit(all_boxes, node_map, G_pairs, P_vec, G_conv):
    """
    Construct a PySpice Circuit object representing the box-level thermal
    resistor network.

    Thermal analogy:
      - Node voltage  = temperature rise above ambient [°C = Ω·A]
      - Resistors     = thermal resistances [K/W]
      - Current srcs  = power injections [W → A]
      - Convective R  = 1/G_conv from node to ground (ambient = 0 V)

    The circuit is suitable for ngspice operating-point (.op) analysis.
    Node voltages returned by ngspice give temperature rise; add AMBIENT_TEMP_C
    for absolute temperature.

    Returns None if HAS_PYSPICE is False.
    """
    if not HAS_PYSPICE:
        return None

    return _build_resistor_network_circuit(
        "ThermalResistorNetwork",
        len(node_map),
        G_pairs,
        P_vec,
        G_conv,
    )


def _network_node_name(index):
    return f"nd{int(index)}"


def _build_resistor_network_circuit(title, node_count, G_pairs, P_vec, G_ground):
    """Build a generic thermal RC PySpice circuit from conductance data."""
    if not HAS_PYSPICE:
        return None

    circuit = _PySpiceCircuit(title)
    for idx, (i, j, G) in enumerate(G_pairs):
        if G <= 0:
            continue
        circuit.R(
            f"Rint{idx}",
            _network_node_name(i),
            _network_node_name(j),
            1.0 / G,
        )

    for i in range(node_count):
        G = float(G_ground[i])
        if G > 0:
            circuit.R(f"Rconv{i}", _network_node_name(i), circuit.gnd, 1.0 / G)

    for i in range(node_count):
        P = float(P_vec[i])
        if P > 0:
            circuit.I(f"Ipwr{i}", circuit.gnd, _network_node_name(i), P)

    return circuit


def _export_pyspice_netlist(circuit, path=NETLIST_EXPORT_PATH):
    """
    Export the PySpice circuit to a SPICE netlist file.

    This provides the "dump out netlist" path required by the project spec
    (per Piazza: "use Pyspice either as an API call or by dumping out netlist").
    """
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(str(circuit))
        print(f"  PySpice netlist exported -> {path}")
    except Exception as e:
        print(f"  Warning: could not export netlist: {e}")


def _export_resistor_network_netlist(title, node_count, G_pairs, P_vec, G_ground,
                                     path=NETLIST_EXPORT_PATH):
    """
    Export a generic resistor-network SPICE netlist.

    This path is used by the voxel mesh so the meshed RC network is solved
    directly by the local ngspice binary.
    """
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(f"* {title}\n")
            f.write(".option klu\n")
            for idx, (i, j, G) in enumerate(G_pairs):
                if G <= 0:
                    continue
                f.write(
                    f"RINT{idx} {_network_node_name(i)} {_network_node_name(j)} "
                    f"{1.0 / G:.12e}\n"
                )
            for i in range(node_count):
                G = float(G_ground[i])
                if G > 0:
                    f.write(
                        f"RAMB{i} {_network_node_name(i)} 0 {1.0 / G:.12e}\n"
                    )
            for i in range(node_count):
                P = float(P_vec[i])
                if P > 0:
                    f.write(
                        f"IPWR{i} 0 {_network_node_name(i)} DC {P:.12e}\n"
                    )
            f.write(".end\n")
        print(f"  RC netlist exported -> {path}")
    except Exception as e:
        print(f"  Warning: could not export netlist: {e}")


def _find_ngspice_binary():
    """
    Locate the ngspice binary, preferring project-local installation.

    Returns the path to the ngspice binary, or None if not found.
    """
    import shutil
    import subprocess

    env_override = os.environ.get("EE201A_NGSPICE_BIN")
    candidates = []
    if env_override:
        candidates.append(env_override)

    candidates.extend([
        str(LOCAL_NGSPICE_BIN),
        "ngspice",
        "/usr/bin/ngspice",
        "/usr/local/bin/ngspice",
        "/opt/local/bin/ngspice",
        "/usr/share/ngspice/bin/ngspice",
        os.path.expanduser("~/.local/bin/ngspice"),
    ])

    for cand in candidates:
        if shutil.which(cand) or os.path.isfile(cand):
            try:
                resolved = shutil.which(cand) or cand
                subprocess.run(
                    [resolved, "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5,
                )
                return resolved
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
    return None


def _find_local_ngspice_library():
    """
    Locate libngspice.so within the project-local installation, if available.
    """
    for lib_subdir in ("lib", "lib64"):
        lib_dir = LOCAL_NGSPICE_PREFIX / lib_subdir
        if not lib_dir.is_dir():
            continue
        exact = lib_dir / "libngspice.so"
        if exact.is_file():
            return str(exact)
        for candidate in sorted(lib_dir.glob("libngspice.so*")):
            if candidate.is_file():
                return str(candidate)
    return None


def _configure_ngspice_environment(ngspice_bin):
    """
    Configure environment variables so PySpice uses the local ngspice install.
    """
    if not ngspice_bin:
        return

    bin_dir = str(Path(ngspice_bin).resolve().parent)
    old_path = os.environ.get("PATH", "")
    path_parts = old_path.split(os.pathsep) if old_path else []
    if bin_dir not in path_parts:
        os.environ["PATH"] = bin_dir + (os.pathsep + old_path if old_path else "")

    lib_path = _find_local_ngspice_library()
    if lib_path:
        os.environ["NGSPICE_LIBRARY_PATH"] = lib_path
        lib_dir = str(Path(lib_path).resolve().parent)
        old_ld_path = os.environ.get("LD_LIBRARY_PATH", "")
        ld_parts = old_ld_path.split(os.pathsep) if old_ld_path else []
        if lib_dir not in ld_parts:
            os.environ["LD_LIBRARY_PATH"] = (
                lib_dir + (os.pathsep + old_ld_path if old_ld_path else "")
            )


def _solve_ngspice_subprocess(netlist_path, node_names, ngspice_bin=None):
    """
    PRIMARY ngspice path — call the local ngspice binary directly via subprocess.

    Solver order (per project requirement):
      1. Local ngspice binary  ← this function
      2. PySpice API          ← _solve_pyspice_ngspice
      3. Custom RC matrix     ← _solve_box_network_matrix

    Reads the already-exported RC netlist, appends a .control block that runs
    .op and prints all node voltages, then launches ngspice in batch mode.
    Parses stdout for lines like "v(nd0) = 5.50000e+01".

    Returns dict {node_name: float voltage} on success, None on failure.
    """
    import shutil
    import subprocess
    import tempfile
    import re

    ngspice_bin = ngspice_bin or _find_ngspice_binary()
    if ngspice_bin is None:
        print("  [ngspice-local] binary not found in PATH or common locations.")
        return None

    tmp_dir = None
    tmp_path = None
    try:
        with open(netlist_path, "r") as f:
            base_netlist = f.read()

        # Remove any existing .end so we can append our .control block
        base_no_end = re.sub(r"(?im)^\s*\.end\s*$", "", base_netlist).rstrip()

        node_names = list(node_names)
        tmp_dir = tempfile.mkdtemp(prefix="thermal_ngspice_")
        out_specs = []
        wrdata_lines = []
        for chunk_id, start in enumerate(range(0, len(node_names), NGSPICE_PRINT_CHUNK)):
            chunk_nodes = node_names[start:start + NGSPICE_PRINT_CHUNK]
            chunk_path = os.path.join(tmp_dir, f"voltages_{chunk_id:04d}.dat")
            vectors = " ".join(f"v({name})" for name in chunk_nodes)
            wrdata_lines.append(f"wrdata {chunk_path} {vectors}\n")
            out_specs.append((chunk_nodes, chunk_path))

        control_block = (
            "\n.option klu\n"
            "\n.control\n"
            "set filetype=ascii\n"
            "op\n"
            + "".join(wrdata_lines)
            + ".endc\n.end\n"
        )
        full_netlist = base_no_end + control_block

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sp", delete=False, prefix="thermal_ngspice_"
        ) as tmp:
            tmp.write(full_netlist)
            tmp_path = tmp.name

        result = subprocess.run(
            [ngspice_bin, "-b", tmp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=NGSPICE_TIMEOUT_S,
        )

        combined = result.stdout + result.stderr
        voltages = {}

        for chunk_nodes, chunk_path in out_specs:
            if not os.path.exists(chunk_path):
                continue
            try:
                with open(chunk_path, "r") as f:
                    raw = f.read().strip()
            except OSError:
                continue
            if not raw:
                continue
            cols = raw.split()
            values = cols[1::2]
            if len(values) != len(chunk_nodes):
                continue
            for node_name, value in zip(chunk_nodes, values):
                try:
                    voltages[node_name] = float(value)
                except ValueError:
                    pass

        if not voltages:
            # Fallback parser for smaller runs or unexpected wrdata failures.
            v_pattern = re.compile(
                r"v\((nd\d+)\)\s*=\s*([-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)"
            )
            for line in combined.splitlines():
                m = v_pattern.search(line)
                if m:
                    voltages[m.group(1)] = float(m.group(2))
        if voltages:
            print(
                f"  [ngspice-local] Parsed {len(voltages)}/{len(node_names)} node voltages."
            )
            return voltages
        else:
            print(
                "  [ngspice-local] ngspice ran but produced no parseable node voltages."
            )
            if result.returncode != 0:
                print(f"  [ngspice-local] exit code {result.returncode}")
            return None

    except subprocess.TimeoutExpired:
        print(f"  [ngspice-local] ngspice timed out after {NGSPICE_TIMEOUT_S:.0f} s.")
        return None
    except Exception as e:
        print(f"  [ngspice-local] Failed: {type(e).__name__}: {e}")
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _solve_pyspice_ngspice(circuit, ngspice_bin=None):
    """
    Attempt to solve the PySpice circuit via ngspice (operating-point).

    Returns a dict {node_name: voltage} on success, None on failure.
    """
    try:
        sim_kwargs = dict(
            temperature=25,
            nominal_temperature=25,
            simulator="ngspice-subprocess",
        )
        if ngspice_bin:
            sim_kwargs["spice_command"] = ngspice_bin
        simulator = circuit.simulator(**sim_kwargs)
        analysis = simulator.operating_point()
        result = {}
        for node in analysis.nodes:
            result[str(node)] = float(analysis[node])
        return result
    except Exception as e:
        print(f"  ngspice simulation unavailable ({type(e).__name__}: {e}). "
              f"Using matrix solve from PySpice circuit elements.")
        return None


def _solve_box_network_matrix(N, G_pairs, P_vec, G_conv):
    """
    Directly assemble and solve the conductance matrix for the box-level
    thermal network.

    This is called when ngspice is unavailable. The same network topology
    that was used to build the PySpice circuit (G_pairs, P_vec, G_conv) is
    used here — the physics is identical, only the solver backend differs.

    Uses scipy sparse CG if available, else numpy dense solve.
    """
    # Ensure there is at least one convective path to ambient so the matrix
    # is non-singular. If no convection was detected, add a small leakage.
    total_Gconv = G_conv.sum()
    if total_Gconv < 1e-12:
        G_conv = G_conv + 1e-6  # small regularisation

    b = np.zeros(N)

    if HAS_SCIPY:
        rows, cols, vals = [], [], []
        diag = np.zeros(N)

        for (i, j, G) in G_pairs:
            rows.extend([i, j])
            cols.extend([j, i])
            vals.extend([-G, -G])
            diag[i] += G
            diag[j] += G

        for i in range(N):
            if G_conv[i] > 0:
                diag[i] += G_conv[i]
                b[i] += G_conv[i] * AMBIENT_TEMP_C

        for i in range(N):
            if P_vec[i] > 0:
                b[i] += P_vec[i]

        rows.extend(range(N))
        cols.extend(range(N))
        vals.extend(diag.tolist())

        A = sparse.csr_matrix(
            (np.array(vals), (np.array(rows, dtype=np.int64),
                              np.array(cols, dtype=np.int64))),
            shape=(N, N),
        )
        T_vec = spsolve(A, b)
    else:
        A = np.zeros((N, N))
        for (i, j, G) in G_pairs:
            A[i, j] -= G
            A[j, i] -= G
            A[i, i] += G
            A[j, j] += G
        for i in range(N):
            if G_conv[i] > 0:
                A[i, i] += G_conv[i]
                b[i] += G_conv[i] * AMBIENT_TEMP_C
        for i in range(N):
            if P_vec[i] > 0:
                b[i] += P_vec[i]
        T_vec = np.linalg.solve(A, b)

    return T_vec


def solve_thermal_pyspice(boxes, bonding_boxes, tim_boxes, heatsink_obj, layers,
                           hc_top, netlist_path=BOX_NETLIST_EXPORT_PATH):
    """
    Box-level thermal solve using PySpice for circuit construction.

    Builds a SPICE thermal circuit via PySpice's API (one node per box),
    exports the netlist, attempts ngspice simulation, and falls back to
    direct matrix solve from the same circuit topology when ngspice is
    not available.

    Returns
    -------
    dict : {box.name: (peak_T, avg_T, R_x, R_y, R_z)}
    """
    all_boxes = list(boxes)
    if bonding_boxes:
        all_boxes.extend(bonding_boxes)
    if tim_boxes:
        all_boxes.extend(tim_boxes)

    N = len(all_boxes)
    if N == 0:
        return {}

    node_map, G_pairs, P_vec, G_conv, lm = _build_box_network_data(
        all_boxes, layers, hc_top
    )
    print(f"  [PySpice] Box network: {N} nodes, {len(G_pairs)} interface conductances")

    # Build PySpice circuit (API-based network construction) and export netlist.
    # The netlist export is required for the local-ngspice subprocess path as
    # well as for the "dump out netlist" project requirement.
    circuit = None
    T_vec = None

    if HAS_PYSPICE:
        circuit = _build_pyspice_circuit(all_boxes, node_map, G_pairs, P_vec, G_conv)
        _export_pyspice_netlist(circuit, path=netlist_path)

    # -----------------------------------------------------------------------
    # SOLVER PRIORITY ORDER (per course requirement and Piazza guidance):
    #   1. Local ngspice subprocess  — call ngspice binary directly with the
    #      exported netlist; most direct use of the local SPICE installation.
    #   2. PySpice API               — circuit.simulator().operating_point();
    #      still uses local ngspice but via PySpice's subprocess wrapper.
    #   3. Custom RC lin-alg solver  — assemble conductance matrix from the
    #      same network topology and solve with scipy sparse CG / numpy.
    # -----------------------------------------------------------------------

    ngspice_result = None
    solver_backend = "box-matrix-fallback"
    ngspice_bin = _find_ngspice_binary()
    _configure_ngspice_environment(ngspice_bin)

    # -- Step 1: Local ngspice subprocess (PRIMARY) --------------------------
    if HAS_PYSPICE and os.path.exists(netlist_path):
        print("  [Solver 1/3] Attempting local ngspice subprocess ...")
        ngspice_result = _solve_ngspice_subprocess(
            netlist_path,
            [_network_node_name(i) for i in range(N)],
            ngspice_bin=ngspice_bin,
        )
        if ngspice_result is not None:
            solver_backend = "box-ngspice-local"

    # -- Step 2: PySpice API (ngspice via PySpice interface) -----------------
    if ngspice_result is None and HAS_PYSPICE and circuit is not None:
        print("  [Solver 2/3] Attempting PySpice API (ngspice via PySpice) ...")
        ngspice_result = _solve_pyspice_ngspice(circuit, ngspice_bin=ngspice_bin)
        if ngspice_result is not None:
            solver_backend = "box-ngspice-pyspice"

    # Populate T_vec from whichever ngspice path succeeded
    if ngspice_result is not None:
        T_vec = np.full(N, AMBIENT_TEMP_C)
        for i in range(N):
            node_name = f"nd{i}"
            if node_name in ngspice_result:
                # Node voltage = temperature rise above ambient
                T_vec[i] = ngspice_result[node_name] + AMBIENT_TEMP_C
        print("  ngspice simulation succeeded.")

    # -- Step 3: Custom RC lin-alg solver (final fallback) -------------------
    if T_vec is None:
        print("  [Solver 3/3] Solving via custom RC linear-algebra solver "
              "(direct conductance-matrix assembly) ...")
        T_vec = _solve_box_network_matrix(N, G_pairs, P_vec, G_conv)
        solver_backend = "box-matrix-fallback"

    # Extract results for the primary boxes only (not bonding/TIM auxiliaries)
    results = {}
    for box in boxes:
        idx = node_map.get(box.name)
        if idx is None or idx >= len(T_vec):
            T_node = AMBIENT_TEMP_C
        else:
            T_node = float(T_vec[idx])
        Rx, Ry, Rz = _box_R(box, lm)
        # Box-level network: single temperature per node → peak == average
        results[box.name] = (T_node, T_node, Rx, Ry, Rz)

    _update_last_solve_summary(
        solver_mode="box-level",
        solver_backend=solver_backend,
        voxel_shape=None,
        voxel_count=0,
        used_ngspice=solver_backend.startswith("box-ngspice"),
    )
    return results


# ============================================================================
# 3D Voxel Grid Helpers (FALLBACK PATH — used if PySpice import fails)
# ============================================================================

def _subdivide(edges, max_s, min_s):
    out = [edges[0]]
    for i in range(len(edges) - 1):
        span = edges[i + 1] - edges[i]
        if span > max_s:
            n = max(2, int(math.ceil(span / max_s)))
            for j in range(1, n):
                out.append(edges[i] + j * span / n)
        out.append(edges[i + 1])
    merged = [out[0]]
    for v in out[1:]:
        if v - merged[-1] >= min_s:
            merged.append(v)
    if abs(merged[-1] - edges[-1]) > 1e-9:
        if merged[-1] < edges[-1]:
            merged.append(edges[-1])
        else:
            merged[-1] = edges[-1]
    return np.array(merged)


def build_grid(all_boxes, hs_obj, max_xy=2.0, max_z=0.3, min_s=0.001):
    xs, ys, zs = set(), set(), set()
    for b in all_boxes:
        xs.update([round(b.start_x, 6), round(b.end_x, 6)])
        ys.update([round(b.start_y, 6), round(b.end_y, 6)])
        zs.update([round(b.start_z, 6), round(b.end_z, 6)])
    hs = hs_obj or {}
    if hs:
        hx, hdx = float(hs.get("x", 0)), float(hs.get("base_dx", 0))
        hy, hdy = float(hs.get("y", 0)), float(hs.get("base_dy", 0))
        hz, hdz = float(hs.get("z", 0)), float(hs.get("base_dz", 0))
        xs.update([round(hx, 6), round(hx + hdx, 6)])
        ys.update([round(hy, 6), round(hy + hdy, 6)])
        zs.update([round(hz, 6), round(hz + hdz, 6)])
    return (
        _subdivide(sorted(xs), max_xy, min_s),
        _subdivide(sorted(ys), max_xy, min_s),
        _subdivide(sorted(zs), max_z, min_s * 0.2),
    )


def _cr(edges, lo, hi, eps=0.0005):
    i0 = max(0, int(np.searchsorted(edges, lo - eps)))
    i1 = min(len(edges) - 1, int(np.searchsorted(edges, hi - eps)))
    return i0, i1


def assign_materials(all_boxes, xe, ye, ze, layers, hs_obj, infill_k=19.0):
    nx, ny, nz = len(xe) - 1, len(ye) - 1, len(ze) - 1
    kx = np.full((nx, ny, nz), CONDUCTIVITY["Air"])
    ky = np.full((nx, ny, nz), CONDUCTIVITY["Air"])
    kz = np.full((nx, ny, nz), CONDUCTIVITY["Air"])
    lm = _build_layer_map(layers)

    excluded = {"interposer", "substrate", "PCB", "Power_Source"}
    chiplet_boxes = []
    for b in all_boxes:
        cp = getattr(b, "chiplet_parent", None)
        if cp and cp.get_chiplet_type() not in excluded:
            chiplet_boxes.append(b)

    if chiplet_boxes:
        chip_z_bot = min(b.start_z for b in chiplet_boxes)
        chip_z_top = max(b.end_z for b in chiplet_boxes)
    else:
        chip_z_bot = min(b.start_z for b in all_boxes)
        chip_z_top = max(b.end_z for b in all_boxes)

    chip_x_lo = min(b.start_x for b in chiplet_boxes) if chiplet_boxes else xe[0]
    chip_x_hi = max(b.end_x for b in chiplet_boxes) if chiplet_boxes else xe[-1]
    chip_y_lo = min(b.start_y for b in chiplet_boxes) if chiplet_boxes else ye[0]
    chip_y_hi = max(b.end_y for b in chiplet_boxes) if chiplet_boxes else ye[-1]

    ci0, ci1 = _cr(xe, chip_x_lo, chip_x_hi)
    cj0, cj1 = _cr(ye, chip_y_lo, chip_y_hi)
    for kk in range(nz):
        zc = (ze[kk] + ze[kk + 1]) / 2.0
        if chip_z_bot - 0.01 <= zc <= chip_z_top + 0.01:
            kx[ci0:ci1, cj0:cj1, kk] = infill_k
            ky[ci0:ci1, cj0:cj1, kk] = infill_k
            kz[ci0:ci1, cj0:cj1, kk] = infill_k

    for box in sorted(all_boxes, key=lambda b: b.width * b.length * b.height, reverse=True):
        i0, i1 = _cr(xe, box.start_x, box.end_x)
        j0, j1 = _cr(ye, box.start_y, box.end_y)
        k0, k1 = _cr(ze, box.start_z, box.end_z)
        if i0 >= i1 or j0 >= j1 or k0 >= k1:
            continue
        for kk in range(k0, k1):
            vz_lo = ze[kk]
            vz_hi = ze[kk + 1]
            kxy_v, kz_v = _retrieve_conductivity_aniso(box, vz_lo, vz_hi, lm)
            kx[i0:i1, j0:j1, kk] = kxy_v
            ky[i0:i1, j0:j1, kk] = kxy_v
            kz[i0:i1, j0:j1, kk] = kz_v

    hs = hs_obj or {}
    if hs:
        hx, hdx = float(hs.get("x", 0)), float(hs.get("base_dx", 0))
        hy, hdy = float(hs.get("y", 0)), float(hs.get("base_dy", 0))
        hz, hdz = float(hs.get("z", 0)), float(hs.get("base_dz", 0))
        hk = _get_k(hs.get("material", "Cu-Foil"))
        i0, i1 = _cr(xe, hx, hx + hdx)
        j0, j1 = _cr(ye, hy, hy + hdy)
        k0, k1 = _cr(ze, hz, hz + hdz)
        if k0 < k1:
            kx[i0:i1, j0:j1, k0:k1] = hk
            ky[i0:i1, j0:j1, k0:k1] = hk
            kz[i0:i1, j0:j1, k0:k1] = hk
    return kx, ky, kz


def _uses_center_plane_power(chiplet_type):
    return chiplet_type == "GPU" or chiplet_type.startswith("HBM")


def assign_power(boxes, xe, ye, ze, use_center_plane_power=USE_CENTER_Z_PLANE_POWER_DEFAULT):
    """
    Map chiplet power onto the voxel grid.

    Uses explicit box.power values (270 W for GPU per Piazza clarification).
    Falls back to legacy constants (GPU_TOTAL_POWER_W = 270 W, not 400 W)
    only when no box carries a positive power value.
    """
    nx, ny, nz = len(xe) - 1, len(ye) - 1, len(ze) - 1
    q = np.zeros((nx, ny, nz))

    powered_boxes = []
    for box in boxes:
        cp = getattr(box, "chiplet_parent", None)
        if cp is not None and cp.get_chiplet_type() == "Power_Source":
            # Final Project v4 sets Power_Source power to 0 W.
            continue
        try:
            pwr = float(getattr(box, "power", 0.0) or 0.0)
        except (TypeError, ValueError):
            pwr = 0.0
        if pwr > 0:
            powered_boxes.append((box, pwr))

    # Fallback: distribute constants when no explicit power found.
    # GPU_TOTAL_POWER_W = 270 W (per Piazza; NOT 400 W from lab PDF).
    if not powered_boxes:
        gpu_b, hbm_leaf = [], []
        for box in boxes:
            cp = getattr(box, "chiplet_parent", None)
            if cp is None:
                continue
            ct = cp.get_chiplet_type()
            kids = len(cp.get_child_chiplets()) > 0
            if ct == "GPU":
                gpu_b.append(box)
            elif ct.startswith("HBM") and not kids:
                hbm_leaf.append(box)

        n_stacks = sum(
            1 for b in boxes
            if getattr(b, "chiplet_parent", None)
            and b.chiplet_parent.get_chiplet_type() == "HBM"
        )
        n_stacks = max(n_stacks, 1)
        if n_stacks <= 1 and len(hbm_leaf) > 8:
            n_stacks = max(1, len(hbm_leaf) // 8)

        gpu_per = GPU_TOTAL_POWER_W / max(len(gpu_b), 1)
        total_hbm = HBM_STACK_POWER_W * n_stacks
        hbm_per = total_hbm / max(len(hbm_leaf), 1) if hbm_leaf else 0.0
        powered_boxes = [(b, gpu_per) for b in gpu_b] + [(b, hbm_per) for b in hbm_leaf]

    for box, pwr in powered_boxes:
        if pwr <= 0:
            continue
        i0, i1 = _cr(xe, box.start_x, box.end_x)
        j0, j1 = _cr(ye, box.start_y, box.end_y)
        k0, k1 = _cr(ze, box.start_z, box.end_z)
        if i0 >= i1 or j0 >= j1 or k0 >= k1:
            continue
        dxc = xe[i0 + 1:i1 + 1] - xe[i0:i1]
        dyc = ye[j0 + 1:j1 + 1] - ye[j0:j1]

        cp = getattr(box, "chiplet_parent", None)
        chiplet_type = cp.get_chiplet_type() if cp is not None else ""
        use_center_plane = use_center_plane_power and _uses_center_plane_power(chiplet_type)

        if use_center_plane:
            mid_z = 0.5 * (box.start_z + box.end_z)
            low = ze[k0:k1]
            high = ze[k0 + 1:k1 + 1]
            # Pick the z-slice(s) that intersect the center plane; if the
            # center lies exactly on a grid boundary, both adjacent slices are used.
            local_sel = np.where((low <= mid_z + 1e-12) & (high >= mid_z - 1e-12))[0]
            if local_sel.size == 0:
                centers = 0.5 * (low + high)
                local_sel = np.array([int(np.argmin(np.abs(centers - mid_z)))], dtype=int)
            k_sel = k0 + local_sel

            area_cells_mm2 = np.outer(dxc, dyc)
            area_total_mm2 = float(area_cells_mm2.sum())
            dz_sel_mm = ze[k_sel + 1] - ze[k_sel]
            tv = area_total_mm2 * float(np.sum(dz_sel_mm))
            if tv > 0:
                q_add = pwr / tv
                for kk in k_sel:
                    q[i0:i1, j0:j1, kk] += q_add
            continue

        dzc = ze[k0 + 1:k1 + 1] - ze[k0:k1]
        vol = np.einsum("i,j,k->ijk", dxc, dyc, dzc)
        tv = vol.sum()
        if tv > 0:
            q[i0:i1, j0:j1, k0:k1] += pwr / tv

    return q


# ============================================================================
# Voxel-level system assembly and solvers
# ============================================================================

def _build_system(kg, qg, xe, ye, ze, hc_top):
    """Build sparse conductance matrix A and RHS vector b."""
    if isinstance(kg, tuple):
        kxg, kyg, kzg = kg
    else:
        kxg = kyg = kzg = kg
    nx, ny, nz = kxg.shape
    N = nx * ny * nz
    eps = 1e-15

    dx = (xe[1:] - xe[:-1]) / 1000.0
    dy = (ye[1:] - ye[:-1]) / 1000.0
    dz = (ze[1:] - ze[:-1]) / 1000.0
    ksx = np.maximum(kxg, eps)
    ksy = np.maximum(kyg, eps)
    ksz = np.maximum(kzg, eps)

    Ax = dy[None, :, None] * dz[None, None, :]
    Gx = 1.0 / np.maximum(
        dx[:nx-1, None, None] / (2 * ksx[:nx-1] * Ax)
        + dx[1:, None, None] / (2 * ksx[1:] * Ax), eps)
    Ay = dx[:, None, None] * dz[None, None, :]
    Gy = 1.0 / np.maximum(
        dy[None, :ny-1, None] / (2 * ksy[:, :ny-1] * Ay)
        + dy[None, 1:, None] / (2 * ksy[:, 1:] * Ay), eps)
    Az = dx[:, None, None] * dy[None, :, None]
    Gz = 1.0 / np.maximum(
        dz[None, None, :nz-1] / (2 * ksz[:, :, :nz-1] * Az)
        + dz[None, None, 1:] / (2 * ksz[:, :, 1:] * Az), eps)

    ci = (np.arange(nx)[:, None, None] * (ny * nz)
          + np.arange(ny)[None, :, None] * nz
          + np.arange(nz)[None, None, :])

    lx = ci[:nx-1].ravel(); rx = ci[1:].ravel(); gx = Gx.ravel()
    ly = ci[:,:ny-1].ravel(); ry = ci[:,1:].ravel(); gy = Gy.ravel()
    lz = ci[:,:,:nz-1].ravel(); rz = ci[:,:,1:].ravel(); gz = Gz.ravel()

    diag = np.zeros((nx, ny, nz))
    diag[1:] += Gx; diag[:nx-1] += Gx
    diag[:,1:] += Gy; diag[:,:ny-1] += Gy
    diag[:,:,1:] += Gz; diag[:,:,:nz-1] += Gz

    cvol = np.einsum("i,j,k->ijk", dx * 1e3, dy * 1e3, dz * 1e3)
    rhs = qg * cvol

    Af = dx[:, None] * dy[None, :]
    Gt = 1.0 / np.maximum(
        dz[-1] / (2 * ksz[:, :, -1] * Af) + 1.0 / (hc_top * Af + eps),
        eps,
    )
    diag[:,:,-1] += Gt
    rhs[:,:,-1] += Gt * AMBIENT_TEMP_C

    Gb = 1.0 / np.maximum(
        dz[0] / (2 * ksz[:, :, 0] * Af) + 1.0 / (H_BOTTOM * Af + eps),
        eps,
    )
    diag[:,:,0] += Gb
    rhs[:,:,0] += Gb * AMBIENT_TEMP_C

    rows = np.concatenate([lx, rx, ly, ry, lz, rz, ci.ravel()])
    cols = np.concatenate([rx, lx, ry, ly, rz, lz, ci.ravel()])
    vals = np.concatenate([-gx, -gx, -gy, -gy, -gz, -gz, diag.ravel()])

    A = sparse.csr_matrix(
        (vals, (rows.astype(np.int64), cols.astype(np.int64))), shape=(N, N))
    return A, rhs.ravel(), diag.ravel()


def _build_voxel_network_data(kg, qg, xe, ye, ze, hc_top):
    """
    Build the voxel thermal RC network in resistor-network form.

    Returns
    -------
    tuple
        (shape, G_pairs, P_vec, G_ground)
    """
    if isinstance(kg, tuple):
        kxg, kyg, kzg = kg
    else:
        kxg = kyg = kzg = kg
    nx, ny, nz = kxg.shape
    N = nx * ny * nz
    eps = 1e-15

    dx = (xe[1:] - xe[:-1]) / 1000.0
    dy = (ye[1:] - ye[:-1]) / 1000.0
    dz = (ze[1:] - ze[:-1]) / 1000.0
    ksx = np.maximum(kxg, eps)
    ksy = np.maximum(kyg, eps)
    ksz = np.maximum(kzg, eps)

    Ax = dy[None, :, None] * dz[None, None, :]
    Gx = 1.0 / np.maximum(
        dx[:nx-1, None, None] / (2 * ksx[:nx-1] * Ax)
        + dx[1:, None, None] / (2 * ksx[1:] * Ax),
        eps,
    )
    Ay = dx[:, None, None] * dz[None, None, :]
    Gy = 1.0 / np.maximum(
        dy[None, :ny-1, None] / (2 * ksy[:, :ny-1] * Ay)
        + dy[None, 1:, None] / (2 * ksy[:, 1:] * Ay),
        eps,
    )
    Az = dx[:, None, None] * dy[None, :, None]
    Gz = 1.0 / np.maximum(
        dz[None, None, :nz-1] / (2 * ksz[:, :, :nz-1] * Az)
        + dz[None, None, 1:] / (2 * ksz[:, :, 1:] * Az),
        eps,
    )

    ci = (
        np.arange(nx)[:, None, None] * (ny * nz)
        + np.arange(ny)[None, :, None] * nz
        + np.arange(nz)[None, None, :]
    )

    G_pairs = []
    for left, right, gvals in (
        (ci[:nx-1], ci[1:], Gx),
        (ci[:, :ny-1], ci[:, 1:], Gy),
        (ci[:, :, :nz-1], ci[:, :, 1:], Gz),
    ):
        G_pairs.extend(
            zip(
                left.ravel().astype(np.int64),
                right.ravel().astype(np.int64),
                gvals.ravel(),
            )
        )

    cell_vol_mm3 = np.einsum(
        "i,j,k->ijk",
        dx * 1e3,
        dy * 1e3,
        dz * 1e3,
    )
    P_vec = (qg * cell_vol_mm3).ravel()

    Af = dx[:, None] * dy[None, :]
    G_top = 1.0 / np.maximum(
        dz[-1] / (2 * ksz[:, :, -1] * Af) + 1.0 / (hc_top * Af + eps),
        eps,
    )
    G_bottom = 1.0 / np.maximum(
        dz[0] / (2 * ksz[:, :, 0] * Af) + 1.0 / (H_BOTTOM * Af + eps),
        eps,
    )

    G_ground = np.zeros(N)
    G_ground[ci[:, :, -1].ravel()] += G_top.ravel()
    G_ground[ci[:, :, 0].ravel()] += G_bottom.ravel()

    return (nx, ny, nz), G_pairs, P_vec, G_ground


def _solve_voxel_ngspice(kg, qg, xe, ye, ze, hc_top,
                         netlist_path=NETLIST_EXPORT_PATH):
    """
    Solve the meshed voxel RC network with the local ngspice binary.

    Returns a temperature grid in degC on success, else None.
    """
    t_s = time.time()
    shape, G_pairs, P_vec, G_ground = _build_voxel_network_data(
        kg, qg, xe, ye, ze, hc_top
    )
    nx, ny, nz = shape
    N = nx * ny * nz
    powered = int(np.count_nonzero(P_vec > 0))
    grounded = int(np.count_nonzero(G_ground > 0))
    print(
        f"    voxel RC network     ({time.time()-t_s:.2f}s)  "
        f"N={N}  edges={len(G_pairs)}  powered={powered}  ambient={grounded}"
    )

    _export_resistor_network_netlist(
        "VoxelThermalNetwork",
        N,
        G_pairs,
        P_vec,
        G_ground,
        path=netlist_path,
    )

    ngspice_bin = _find_ngspice_binary()
    _configure_ngspice_environment(ngspice_bin)
    print(
        "    ngspice binary       "
        f"({time.time()-t_s:.2f}s)  {ngspice_bin if ngspice_bin else 'not found'}"
    )
    voltages = _solve_ngspice_subprocess(
        netlist_path,
        [_network_node_name(i) for i in range(N)],
        ngspice_bin=ngspice_bin,
    )
    if voltages is None:
        return None

    T = np.full(N, AMBIENT_TEMP_C)
    for i in range(N):
        node_name = _network_node_name(i)
        if node_name in voltages:
            T[i] = voltages[node_name] + AMBIENT_TEMP_C
    print(f"    ngspice solve done   ({time.time()-t_s:.2f}s)")
    return T.reshape((nx, ny, nz))


def _solve_sparse(kg, qg, xe, ye, ze, hc_top):
    if isinstance(kg, tuple):
        nx, ny, nz = kg[0].shape
    else:
        nx, ny, nz = kg.shape
    N = nx * ny * nz
    t_s = time.time()

    A, b, diag_vals = _build_system(kg, qg, xe, ye, ze, hc_top)
    print(f"    system built         ({time.time()-t_s:.2f}s)  N={N}  nnz={A.nnz}")

    M_inv = sparse.diags(1.0 / np.maximum(diag_vals, 1e-15))
    x0 = np.full(N, AMBIENT_TEMP_C)
    T, info = cg(A, b, x0=x0, M=M_inv, tol=1e-5, maxiter=5000)
    if info != 0:
        print(f"    CG warning: info={info}, falling back to spsolve")
        T = spsolve(A, b)
    print(f"    solve done           ({time.time()-t_s:.2f}s)")
    return T.reshape((nx, ny, nz))


def _solve_iter(kg, qg, xe, ye, ze, hc_top, max_it=8000, tol=0.01, omega=1.4):
    if isinstance(kg, tuple):
        kxg, kyg, kzg = kg
    else:
        kxg = kyg = kzg = kg
    nx, ny, nz = kxg.shape
    eps = 1e-15
    dx = (xe[1:] - xe[:-1]) / 1000.0
    dy = (ye[1:] - ye[:-1]) / 1000.0
    dz = (ze[1:] - ze[:-1]) / 1000.0
    ksx = np.maximum(kxg, eps)
    ksy = np.maximum(kyg, eps)
    ksz = np.maximum(kzg, eps)

    Ax = dy[None, :, None] * dz[None, None, :]
    Gx = 1.0 / np.maximum(
        dx[:nx-1, None, None] / (2 * ksx[:nx-1] * Ax)
        + dx[1:, None, None] / (2 * ksx[1:] * Ax), eps)
    Ay = dx[:, None, None] * dz[None, None, :]
    Gy = 1.0 / np.maximum(
        dy[None, :ny-1, None] / (2 * ksy[:, :ny-1] * Ay)
        + dy[None, 1:, None] / (2 * ksy[:, 1:] * Ay), eps)
    Az = dx[:, None, None] * dy[None, :, None]
    Gz = 1.0 / np.maximum(
        dz[None, None, :nz-1] / (2 * ksz[:, :, :nz-1] * Az)
        + dz[None, None, 1:] / (2 * ksz[:, :, 1:] * Az), eps)

    diag = np.zeros((nx, ny, nz))
    diag[1:] += Gx; diag[:nx-1] += Gx
    diag[:,1:] += Gy; diag[:,:ny-1] += Gy
    diag[:,:,1:] += Gz; diag[:,:,:nz-1] += Gz

    cvol = np.einsum("i,j,k->ijk", dx * 1e3, dy * 1e3, dz * 1e3)
    rhs = qg * cvol

    Af = dx[:, None] * dy[None, :]
    Gt = 1.0 / np.maximum(
        dz[-1] / (2 * ksz[:, :, -1] * Af) + 1.0 / (hc_top * Af + eps),
        eps,
    )
    diag[:,:,-1] += Gt
    rhs[:,:,-1] += Gt * AMBIENT_TEMP_C
    Gb = 1.0 / np.maximum(
        dz[0] / (2 * ksz[:, :, 0] * Af) + 1.0 / (H_BOTTOM * Af + eps),
        eps,
    )
    diag[:,:,0] += Gb
    rhs[:,:,0] += Gb * AMBIENT_TEMP_C

    diag = np.maximum(diag, eps)
    T = np.full((nx, ny, nz), AMBIENT_TEMP_C)

    for it in range(max_it):
        GT = np.zeros_like(T)
        GT[1:] += Gx * T[:nx-1]
        GT[:nx-1] += Gx * T[1:]
        GT[:,1:] += Gy * T[:,:ny-1]
        GT[:,:ny-1] += Gy * T[:,1:]
        GT[:,:,1:] += Gz * T[:,:,:nz-1]
        GT[:,:,:nz-1] += Gz * T[:,:,1:]
        Tn = (rhs + GT) / diag
        Tn = omega * Tn + (1 - omega) * T
        d = np.max(np.abs(Tn - T))
        T = Tn
        if d < tol:
            print(f"  SOR converged in {it + 1} iters (maxdelta={d:.4f})")
            break
    else:
        print(f"  SOR: {max_it} iters, maxdelta={d:.4f}")
    return T


def extract_results(boxes, Tg, xe, ye, ze, layers):
    lm = _build_layer_map(layers)
    res = {}
    for box in boxes:
        i0, i1 = _cr(xe, box.start_x, box.end_x)
        j0, j1 = _cr(ye, box.start_y, box.end_y)
        k0, k1 = _cr(ze, box.start_z, box.end_z)
        if i0 >= i1 or j0 >= j1 or k0 >= k1:
            res[box.name] = (AMBIENT_TEMP_C, AMBIENT_TEMP_C, 0.0, 0.0, 0.0)
            continue
        temps = Tg[i0:i1, j0:j1, k0:k1]
        Rx, Ry, Rz = _box_R(box, lm)
        res[box.name] = (float(np.max(temps)), float(np.mean(temps)), Rx, Ry, Rz)
    return res


# ============================================================================
# Public entry point
# ============================================================================

def solve_thermal(boxes, bonding_boxes, tim_boxes, heatsink_obj, layers,
                  tim_cond=None, infill_cond=None, underfill_cond=None,
                  force_voxel=None, use_center_plane_power=None, **kw):
    """
    Full thermal solve.

    Solver selection (in priority order):
      1. Voxel RC netlist solved by local ngspice (default final-project path)
      2. Voxel sparse/numpy fallback from the same meshed physics
      3. Legacy PySpice box-level network when voxel meshing is not requested

    The simulation is intentionally excluded from the project FoM runtime
    (timing is handled by the caller in therm.py).

    Power assumption: GPU = 270 W (per Piazza clarification — NOT 400 W).

    Parameters
    ----------
    tim_cond : float, optional
        Override TIM conductivity (W/(m·K)).
    infill_cond : float, optional
        Override infill conductivity (W/(m·K)).
    underfill_cond : float, optional
        Override underfill conductivity (W/(m·K)). Unused separately.

    Returns
    -------
    dict : {box_name: (peak_T, avg_T, R_x, R_y, R_z), ...}
    """
    t0 = time.time()
    _purge_redundant_reports()
    _reset_last_solve_summary()

    if tim_cond is not None:
        CONDUCTIVITY["TIM0p5"] = float(tim_cond)
    if infill_cond is not None:
        CONDUCTIVITY["Infill_material"] = float(infill_cond)

    if force_voxel is None:
        force_voxel = FORCE_VOXEL_SOLVER_DEFAULT
    if use_center_plane_power is None:
        use_center_plane_power = USE_CENTER_Z_PLANE_POWER_DEFAULT

    try:
        hc = float((heatsink_obj or {}).get("hc", "7000"))
    except (ValueError, TypeError):
        hc = 7000.0
    hc_eff = _estimate_convective_hc(heatsink_obj, hc)

    # ------------------------------------------------------------------
    # Legacy non-voxel path: box-level PySpice network.
    # ------------------------------------------------------------------
    if HAS_PYSPICE and not force_voxel and not use_center_plane_power:
        print("  Solver: PySpice box-level resistor network")
        try:
            results = solve_thermal_pyspice(
                boxes, bonding_boxes, tim_boxes, heatsink_obj, layers, hc_eff
            )
            print(f"  PySpice solve done   ({time.time() - t0:.2f}s)")
            return results
        except Exception as e:
            print(f"  PySpice solver failed ({e}). Falling back to voxel RC mesh.")
    elif force_voxel or use_center_plane_power:
        print("  Solver: voxel RC mesh (center-plane power model)")
    else:
        print("  PySpice not available. Using voxel RC mesh.")

    # ------------------------------------------------------------------
    # FALLBACK PATH: 3D voxel finite-difference solver
    # ------------------------------------------------------------------
    infill_k = CONDUCTIVITY["Infill_material"]

    all_el = list(boxes)
    if bonding_boxes:
        all_el.extend(bonding_boxes)
    if tim_boxes:
        all_el.extend(tim_boxes)

    hs = heatsink_obj or {}
    if hs:
        print(f"  Heatsink: x={hs.get('x')}, y={hs.get('y')}, "
              f"dx={hs.get('base_dx')}, dy={hs.get('base_dy')}, "
              f"z={hs.get('z')}, dz={hs.get('base_dz')}, "
              f"hc_raw={hs.get('hc')}, hc_effective={hc_eff:.3f}, "
              f"mat={hs.get('material')}")

    xe, ye, ze = build_grid(
        all_el,
        heatsink_obj,
        max_xy=GRID_MAX_XY_MM,
        max_z=GRID_MAX_Z_MM,
        min_s=GRID_MIN_MM,
    )
    nx, ny, nz = len(xe) - 1, len(ye) - 1, len(ze) - 1
    print(f"  Grid: {nx} x {ny} x {nz} = {nx * ny * nz} cells  ({time.time() - t0:.2f}s)")
    _update_last_solve_summary(
        solver_mode="voxel-rc",
        voxel_shape=(int(nx), int(ny), int(nz)),
        voxel_count=int(nx * ny * nz),
    )

    kg = assign_materials(all_el, xe, ye, ze, layers, heatsink_obj, infill_k=infill_k)
    if isinstance(kg, tuple):
        k_min = min(arr.min() for arr in kg)
        k_max = max(arr.max() for arr in kg)
    else:
        k_min = kg.min()
        k_max = kg.max()
    print(f"  Materials assigned  ({time.time() - t0:.2f}s)  "
          f"k range: [{k_min:.3f}, {k_max:.1f}]")

    qg = assign_power(
        boxes, xe, ye, ze, use_center_plane_power=use_center_plane_power
    )
    vol = np.einsum("i,j,k->ijk", xe[1:] - xe[:-1], ye[1:] - ye[:-1], ze[1:] - ze[:-1])
    total_p = (qg * vol).sum()
    print(f"  Power assigned      ({time.time() - t0:.2f}s)  total={total_p:.1f} W")

    print("  Solving voxel RC netlist with local ngspice ...")
    Tg = _solve_voxel_ngspice(kg, qg, xe, ye, ze, hc_eff)
    if Tg is None:
        if HAS_SCIPY:
            print("  ngspice unavailable. Solving fallback (CG with Jacobi preconditioner) ...")
            Tg = _solve_sparse(kg, qg, xe, ye, ze, hc_eff)
            _update_last_solve_summary(
                solver_backend="voxel-cg-fallback",
                used_ngspice=False,
            )
        else:
            print("  ngspice unavailable. Solving fallback (numpy SOR) ...")
            Tg = _solve_iter(kg, qg, xe, ye, ze, hc_eff)
            _update_last_solve_summary(
                solver_backend="voxel-sor-fallback",
                used_ngspice=False,
            )
    else:
        _update_last_solve_summary(
            solver_backend="voxel-ngspice-local",
            used_ngspice=True,
        )
    print(f"  Solve done          ({time.time() - t0:.2f}s)  "
          f"Tmin={Tg.min():.1f}  Tmax={Tg.max():.1f}")

    results = extract_results(boxes, Tg, xe, ye, ze, layers)
    print(f"  Results extracted   ({time.time() - t0:.2f}s)")
    return results
