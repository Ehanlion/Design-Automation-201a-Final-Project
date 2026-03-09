"""
thermal_solver.py

Baseline 3D steady-state thermal solver for the EE201A final project.

Python 3.6 compatible version.
"""

import math
import numpy as np
import os
import csv
import json
from datetime import datetime

try:
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ============================================================
# Constants / defaults
# ============================================================

AMBIENT_TEMP_C = 45.0
GPU_TOTAL_POWER_W = 400.0
HBM_STACK_POWER_W = 5.0

H_BOTTOM_W_M2K = 10.0
H_TOP_DEFAULT_W_M2K = 5000.0
EPS = 1e-18


# ============================================================
# Material database
# ============================================================

CONDUCTIVITY = {
    "Air": 0.025,
    "FR-4": 0.10,
    "Cu-Foil": 400.0,
    "Cu": 400.0,
    "Copper": 400.0,
    "Si": 105.0,
    "Silicon": 105.0,
    "Aluminium": 205.0,
    "Aluminum": 205.0,
    "TIM001": 100.0,
    "TIM": 100.0,
    "TIM0p5": 5.0,
    "Glass": 1.36,
    "SnPb 67/37": 36.0,
    "Epoxy, Silver filled": 1.6,
    "EpAg": 1.6,
    "EpAg_filled": 1.6,
    "Infill_material": 19.0,
    "Polymer1": 675.0,
    "SiO2": 1.1,
    "AlN": 237.0,
    "Epoxy": 0.3,
    "Water": 0.6,
}


# ============================================================
# Basic helpers
# ============================================================

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def _box_end_x(box):
    return _safe_float(getattr(box, "end_x", getattr(box, "start_x", 0.0) + getattr(box, "width", 0.0)))


def _box_end_y(box):
    return _safe_float(getattr(box, "end_y", getattr(box, "start_y", 0.0) + getattr(box, "length", 0.0)))


def _box_end_z(box):
    return _safe_float(getattr(box, "end_z", getattr(box, "start_z", 0.0) + getattr(box, "height", 0.0)))


def _idx(i, j, k, grid):
    return (k * grid["ny"] + j) * grid["nx"] + i


def _overlap_len(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _interval_centers(bounds):
    return 0.5 * (bounds[:-1] + bounds[1:])

def _voxel_volume_m3_from_indices(grid, i, j, k):
    dx_mm = grid["xs"][i + 1] - grid["xs"][i]
    dy_mm = grid["ys"][j + 1] - grid["ys"][j]
    dz_mm = grid["zs"][k + 1] - grid["zs"][k]
    return max(dx_mm, EPS) * 1e-3 * max(dy_mm, EPS) * 1e-3 * max(dz_mm, EPS) * 1e-3


def _top_face_area_m2_from_indices(grid, i, j):
    dx_mm = grid["xs"][i + 1] - grid["xs"][i]
    dy_mm = grid["ys"][j + 1] - grid["ys"][j]
    return max(dx_mm, EPS) * 1e-3 * max(dy_mm, EPS) * 1e-3


def _ijk_from_idx(n, grid):
    i = n % grid["nx"]
    q = n // grid["nx"]
    j = q % grid["ny"]
    k = q // grid["ny"]
    return i, j, k

def _merge_close_coords(vals, tol=1e-4):
    """
    Merge nearly identical coordinates to avoid tiny sliver voxels.

    tol is in the same geometry units as the box coordinates (mm).
    """
    vals = sorted(float(v) for v in vals)
    if not vals:
        return np.array([], dtype=float)

    merged = [vals[0]]
    for v in vals[1:]:
        if abs(v - merged[-1]) < tol:
            continue
        merged.append(v)

    return np.array(merged, dtype=float)

def _box_ambient_conduct(box):
    """
    Repo Box stores ambient_conduct directly.
    Treat it as a total conductance in W/K for that box, not HTC.
    """
    return _safe_float(getattr(box, "ambient_conduct", 0.0), 0.0)

def _is_nonphysical_wrapper_box(box):
    """
    Exclude only the actual wrapper/container box itself.
    Do NOT exclude descendant boxes just because their hierarchical
    names contain 'set_primary'.
    """
    name = str(getattr(box, "name", ""))
    name_l = name.lower()
    ctype = str(_chiplet_type(box)).lower()

    # Split hierarchical path into exact nodes
    parts = [p for p in name_l.split(".") if p]

    # Exclude ONLY the actual set_primary wrapper box itself
    # Example excluded:
    #   Power_Source.substrate.set_primary
    # Example kept:
    #   Power_Source.substrate.set_primary.GPU
    if parts and parts[-1] == "set_primary":
        return True

    # Exclude the actual Power_Source box itself, but not descendants
    # Example excluded:
    #   Power_Source
    # Example kept:
    #   Power_Source.substrate
    if ctype == "power_source" and len(parts) <= 1:
        return True

    return False


def _is_physical_box(box):
    if _is_nonphysical_wrapper_box(box):
        return False

    w = max(_safe_float(getattr(box, "width", 0.0)), 0.0)
    l = max(_safe_float(getattr(box, "length", 0.0)), 0.0)
    h = max(_safe_float(getattr(box, "height", 0.0)), 0.0)

    if w <= 0.0 or l <= 0.0 or h <= 0.0:
        return False

    return True


def _box_geometric_volume_m3(box):
    return (
        max(_safe_float(getattr(box, "width", 0.0)), EPS) * 1e-3 *
        max(_safe_float(getattr(box, "length", 0.0)), EPS) * 1e-3 *
        max(_safe_float(getattr(box, "height", 0.0)), EPS) * 1e-3
    )


def _extract_key_thermal_summary(box_results):
    """
    Pull out the headline metrics you actually care about for quick comparisons.
    """
    gpu_peak = None
    gpu_name = None
    hottest_hbm_peak = None
    hottest_hbm_name = None

    for name, vals in box_results.items():
        peak_t = vals[0]
        nl = name.lower()

        if "bonding" in nl or "tim" in nl:
            continue

        if (".gpu" in nl or nl.endswith("gpu")):
            if gpu_peak is None or peak_t > gpu_peak:
                gpu_peak = peak_t
                gpu_name = name

        # only top-level HBM boxes, not the internal HBM_l* layers
        if "hbm#" in nl and ".hbm_l" not in nl:
            if hottest_hbm_peak is None or peak_t > hottest_hbm_peak:
                hottest_hbm_peak = peak_t
                hottest_hbm_name = name

    return {
        "gpu_box": gpu_name,
        "gpu_peak_c": gpu_peak,
        "hbm_box": hottest_hbm_name,
        "hbm_peak_c": hottest_hbm_peak,
    }


def _append_summary_csv(summary_row, out_csv_path):
    """
    Append one row per simulation/config to a CSV file for easy tracking in git.
    """
    os.makedirs(os.path.dirname(out_csv_path), exist_ok=True)

    fieldnames = [
        "timestamp",
        "project_name",
        "grid_nx",
        "grid_ny",
        "grid_nz",
        "nvox",
        "total_power_w",
        "gpu_box",
        "gpu_peak_c",
        "hbm_box",
        "hbm_peak_c",
    ]

    write_header = not os.path.exists(out_csv_path)

    with open(out_csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(summary_row)


def _write_summary_json(summary_row, out_json_path):
    os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
    with open(out_json_path, "w") as f:
        json.dump(summary_row, f, indent=2, sort_keys=True)

# ============================================================
# Material / stackup parsing
# ============================================================

def _get_k(mat_str):
    if not mat_str:
        return CONDUCTIVITY.get("Si", 105.0)

    mat_str = str(mat_str).strip()

    if mat_str in CONDUCTIVITY:
        return CONDUCTIVITY[mat_str]

    if "," in mat_str and ":" in mat_str:
        num = 0.0
        den = 0.0
        for part in mat_str.split(","):
            part = part.strip()
            if not part:
                continue

            toks = [t.strip() for t in part.split(":")]
            if len(toks) >= 3:
                mat_name = toks[-2]
                frac = _safe_float(toks[-1], 0.0)
            elif len(toks) == 2:
                mat_name = toks[0]
                frac = _safe_float(toks[1], 0.0)
            else:
                continue

            if frac > 1.0:
                frac /= 100.0

            k = CONDUCTIVITY.get(mat_name, 1.0)
            num += frac * k
            den += frac

        if den > 0:
            return num / den

    return CONDUCTIVITY.get(mat_str, CONDUCTIVITY.get("Si", 105.0))


def _build_layer_map(layers):
    layer_map = {}
    if not layers:
        return layer_map

    for layer in layers:
        try:
            lname = layer.get_name()
            lthick = _safe_float(layer.get_thickness())
            lmat = layer.get_material()
            layer_map[lname] = (lthick, lmat, _get_k(lmat))
        except Exception:
            continue

    return layer_map


def _parse_stackup(box, layer_map):
    su = getattr(box, "stackup", None)
    if not su:
        mat = getattr(box, "material", None)
        return [(max(_safe_float(box.height), 1e-6), _get_k(mat if mat else "Si"))]

    su = str(su).strip()
    if not su:
        return [(max(_safe_float(box.height), 1e-6), _get_k("Si"))]

    result = []

    first = su.split(",", 1)[0]
    if first.count(":") >= 2:
        return [(max(_safe_float(box.height), 1e-6), _get_k(su))]

    for entry in su.split(","):
        entry = entry.strip()
        if not entry:
            continue

        toks = [t.strip() for t in entry.split(":")]
        if len(toks) < 2:
            continue

        count = _safe_float(toks[0], 1.0)
        layer_name = toks[1]

        if layer_name in layer_map:
            thick_mm, _, k = layer_map[layer_name]
            result.append((count * thick_mm, k))
        else:
            result.append((count * 0.1, _get_k(layer_name)))

    if not result:
        result = [(max(_safe_float(box.height), 1e-6), _get_k("Si"))]

    return result


def _retrieve_conductivity(box, voxel_z_lo_mm, voxel_z_hi_mm, layer_map):
    stack = _parse_stackup(box, layer_map)

    z_local_lo = voxel_z_lo_mm - _safe_float(box.start_z)
    z_local_hi = voxel_z_hi_mm - _safe_float(box.start_z)

    cursor = 0.0
    weighted_sum = 0.0
    covered = 0.0

    for thick_mm, k in stack:
        lay_lo = cursor
        lay_hi = cursor + thick_mm
        ov = _overlap_len(z_local_lo, z_local_hi, lay_lo, lay_hi)
        if ov > 0:
            weighted_sum += ov * k
            covered += ov
        cursor = lay_hi

    if covered > 0:
        return weighted_sum / covered

    return _get_k(getattr(box, "material", None) or "Si")


# ============================================================
# Box classification / power
# ============================================================

def _box_name_lower(box):
    return str(getattr(box, "name", "")).lower()


def _chiplet_type_lower(box):
    try:
        return str(box.chiplet_parent.get_chiplet_type()).lower()
    except Exception:
        return ""


def _is_gpu_box(box):
    nm = _box_name_lower(box)
    tp = _chiplet_type_lower(box)
    return ("gpu" in nm) or ("gpu" in tp) or ("wafer" in nm and "hbm" not in nm)


def _is_hbm_box(box):
    nm = _box_name_lower(box)
    tp = _chiplet_type_lower(box)
    return ("hbm" in nm) or ("dram" in nm) or ("hbm" in tp)


def _chiplet_type(box):
    try:
        return str(box.chiplet_parent.get_chiplet_type())
    except Exception:
        return ""


def _infer_box_power_w(box):
    """
    Use repo metadata instead of broad name matching.

    Rules:
    - Power_Source contributes 0 W to the thermal target model.
    - GPU should be forced to 400 W total per project spec.
    - HBM should be 5 W per stack total per project spec.
      The existing hierarchy appears to split that as:
          HBM      = 1.0 W
          HBM_l*   = 0.5 W each for 8 layers
      which sums to 5 W, so we preserve that distribution.
    - Passive/support regions get 0.
    """
    ctype = _chiplet_type(box)
    name = str(getattr(box, "name", "")).lower()

    if ctype == "Power_Source":
        return 0.0

    # Project spec override: GPU total should be 400 W
    if ctype == "GPU":
        return 400.0

    # Preserve existing per-stack decomposition if present
    if ctype == "HBM":
        return 1.0

    if ctype.startswith("HBM_l"):
        return 0.5

    blocked_terms = [
        "bonding",
        "tim",
        "substrate",
        "interposer",
        "underfill",
        "infill",
        "heatsink",
    ]
    for term in blocked_terms:
        if term in name:
            return 0.0

    return 0.0


# ============================================================
# Geometry aggregation
# ============================================================

def _collect_all_boxes(boxes, bonding_box_list, TIM_boxes):
    all_boxes = []
    for group in (boxes, bonding_box_list, TIM_boxes):
        if group:
            all_boxes.extend(group)
    return all_boxes


def _subdivide_intervals(bounds, target_step_mm):
    """
    Given sorted boundary coordinates, subdivide each interval so that
    no cell is larger than target_step_mm.
    """
    bounds = np.array(sorted(float(v) for v in bounds), dtype=float)
    if len(bounds) < 2:
        return bounds

    refined = [bounds[0]]

    for a, b in zip(bounds[:-1], bounds[1:]):
        length = b - a
        if length <= 0:
            continue

        if target_step_mm is None or target_step_mm <= 0:
            nsplit = 1
        else:
            nsplit = max(1, int(math.ceil(length / target_step_mm)))

        for s in range(1, nsplit + 1):
            refined.append(a + length * s / nsplit)

    return _merge_close_coords(refined, tol=1e-6)


def build_global_grid(
    boxes,
    bonding_box_list,
    TIM_boxes,
    target_dx_mm=2.0,
    target_dy_mm=2.0,
    target_dz_mm=0.25,
):
    all_boxes = _collect_all_boxes(boxes, bonding_box_list, TIM_boxes)

    xs = set()
    ys = set()
    zs = set()

    for box in all_boxes:
        xs.add(_safe_float(box.start_x))
        xs.add(_box_end_x(box))

        ys.add(_safe_float(box.start_y))
        ys.add(_box_end_y(box))

        zs.add(_safe_float(box.start_z))
        zs.add(_box_end_z(box))

    xs = _merge_close_coords(xs, tol=1e-4)
    ys = _merge_close_coords(ys, tol=1e-4)
    zs = _merge_close_coords(zs, tol=1e-5)

    # NEW: refine each interval
    xs = _subdivide_intervals(xs, target_dx_mm)
    ys = _subdivide_intervals(ys, target_dy_mm)
    zs = _subdivide_intervals(zs, target_dz_mm)

    if len(xs) < 2 or len(ys) < 2 or len(zs) < 2:
        raise RuntimeError("Global thermal grid is degenerate; not enough unique x/y/z boundaries.")

    return {
        "xs": xs,
        "ys": ys,
        "zs": zs,
        "nx": len(xs) - 1,
        "ny": len(ys) - 1,
        "nz": len(zs) - 1,
        "nvox": (len(xs) - 1) * (len(ys) - 1) * (len(zs) - 1),
    }


def _find_owner_box_for_voxel(xc, yc, zc, all_boxes):
    matches = []

    for bi, box in enumerate(all_boxes):
        x0 = _safe_float(box.start_x)
        x1 = _box_end_x(box)
        y0 = _safe_float(box.start_y)
        y1 = _box_end_y(box)
        z0 = _safe_float(box.start_z)
        z1 = _box_end_z(box)

        inside = (
            x0 - 1e-12 <= xc <= x1 + 1e-12 and
            y0 - 1e-12 <= yc <= y1 + 1e-12 and
            z0 - 1e-12 <= zc <= z1 + 1e-12
        )
        if inside:
            vol = max((x1 - x0) * (y1 - y0) * (z1 - z0), EPS)
            matches.append((vol, bi))

    if not matches:
        return -1

    matches.sort(key=lambda t: t[0])
    return matches[0][1]


def assign_materials_and_power(grid, boxes, bonding_box_list, TIM_boxes, layers=None, verbose=False):
    all_boxes = _collect_all_boxes(boxes, bonding_box_list, TIM_boxes)
    ownership_boxes = [b for b in all_boxes if _is_physical_box(b)]
    layer_map = _build_layer_map(layers)

    owner_box_idx = np.full(grid["nvox"], -1, dtype=int)
    voxel_k = np.full(grid["nvox"], _get_k("Air"), dtype=float)
    voxel_power = np.zeros(grid["nvox"], dtype=float)
    voxel_ambient_g = np.zeros(grid["nvox"], dtype=float)

    xcs = _interval_centers(grid["xs"])
    ycs = _interval_centers(grid["ys"])
    zcs = _interval_centers(grid["zs"])

    # Pass 1: ownership + material
    for k in range(grid["nz"]):
        zlo = grid["zs"][k]
        zhi = grid["zs"][k + 1]
        zc = zcs[k]

        for j in range(grid["ny"]):
            yc = ycs[j]
            for i in range(grid["nx"]):
                xc = xcs[i]
                n = _idx(i, j, k, grid)

                bi = _find_owner_box_for_voxel(xc, yc, zc, ownership_boxes)
                owner_box_idx[n] = bi

                if bi >= 0:
                    box = ownership_boxes[bi]
                    voxel_k[n] = _retrieve_conductivity(box, zlo, zhi, layer_map)
                else:
                    voxel_k[n] = _get_k("Air")

    voxels_by_box = {}
    top_surface_voxels_by_box = {}

    # Pass 2: group voxels by owner and detect top-of-box voxels
    for k in range(grid["nz"]):
        for j in range(grid["ny"]):
            for i in range(grid["nx"]):
                n = _idx(i, j, k, grid)
                bi = owner_box_idx[n]
                if bi < 0:
                    continue

                voxels_by_box.setdefault(int(bi), []).append(n)

                is_top_surface = False
                if k == grid["nz"] - 1:
                    is_top_surface = True
                else:
                    nabove = _idx(i, j, k + 1, grid)
                    if owner_box_idx[nabove] != bi:
                        is_top_surface = True

                if is_top_surface:
                    top_surface_voxels_by_box.setdefault(int(bi), []).append(n)

    if verbose:
        print("[thermal_solver] powered boxes:")
    total_power = 0.0

    # Pass 3: distribute power by owned voxel volume
    for bi, voxel_list in sorted(voxels_by_box.items()):
        box = ownership_boxes[bi]
        pbox = _infer_box_power_w(box)

        if pbox > 0.0:
            voxel_volumes = []
            total_vol = 0.0

            for n in voxel_list:
                i, j, k = _ijk_from_idx(n, grid)
                v = _voxel_volume_m3_from_indices(grid, i, j, k)
                voxel_volumes.append((n, v))
                total_vol += v

            if total_vol <= 0.0:
                continue

            for n, v in voxel_volumes:
                voxel_power[n] += pbox * (v / total_vol)

            total_power += pbox
            if verbose:
                print("  {} : chiplet_type={} power={:.6f} W, owned_voxels={}, owned_volume={:.6e} m^3".format(
                    getattr(box, "name", "box_{}".format(bi)),
                    _chiplet_type(box),
                    pbox,
                    len(voxel_list),
                    total_vol
                ))

    # Pass 4: distribute box ambient conductance by exposed top area
    for bi, top_voxels in top_surface_voxels_by_box.items():
        box = ownership_boxes[bi]
        g_box = _box_ambient_conduct(box)

        if g_box > 0.0 and len(top_voxels) > 0:
            area_list = []
            total_area = 0.0

            for n in top_voxels:
                i, j, k = _ijk_from_idx(n, grid)
                a = _top_face_area_m2_from_indices(grid, i, j)
                area_list.append((n, a))
                total_area += a

            if total_area > 0.0:
                for n, a in area_list:
                    voxel_ambient_g[n] += g_box * (a / total_area)

    print("[thermal_solver] total assigned power = {:.6f} W".format(total_power))

    # sanity report for powered boxes
    if verbose:
        print("[thermal_solver] ownership sanity check:")
        for bi, voxel_list in sorted(voxels_by_box.items()):
            box = ownership_boxes[bi]
            pbox = _infer_box_power_w(box)
            if pbox <= 0.0:
                continue

            owned_vol = 0.0
            for n in voxel_list:
                i, j, k = _ijk_from_idx(n, grid)
                owned_vol += _voxel_volume_m3_from_indices(grid, i, j, k)

            geom_vol = _box_geometric_volume_m3(box)
            ratio = owned_vol / max(geom_vol, EPS)
            pden = pbox / max(owned_vol, EPS)

            print(
                "  {} : geom_vol={:.6e} m^3 owned_vol={:.6e} m^3 "
                "owned/geom={:.3f} power={:.6f} W power_density={:.6e} W/m^3".format(
                    getattr(box, "name", "box_{}".format(bi)),
                    geom_vol,
                    owned_vol,
                    ratio,
                    pbox,
                    pden
                )
            )

    return owner_box_idx, voxel_k, voxel_power, voxel_ambient_g, ownership_boxes, total_power


# ============================================================
# Boundary / heatsink handling
# ============================================================

def _get_top_htc_w_m2k(heatsink_obj=None):
    if heatsink_obj is not None:
        for attr_name in [
            "get_heat_transfer_coeff",
            "get_heat_transfer_coefficient",
            "get_htc",
        ]:
            fn = getattr(heatsink_obj, attr_name, None)
            if callable(fn):
                try:
                    val = _safe_float(fn(), 0.0)
                    if val > 0:
                        return val
                except Exception:
                    pass

        for attr_name in ["htc", "heat_transfer_coeff", "heat_transfer_coefficient"]:
            if hasattr(heatsink_obj, attr_name):
                val = _safe_float(getattr(heatsink_obj, attr_name), 0.0)
                if val > 0:
                    return val

    return H_TOP_DEFAULT_W_M2K


def _face_area_m2(dirn, dx_mm, dy_mm, dz_mm):
    dx_m = dx_mm * 1e-3
    dy_m = dy_mm * 1e-3
    dz_m = dz_mm * 1e-3

    if dirn == "x":
        return max(dy_m * dz_m, EPS)
    if dirn == "y":
        return max(dx_m * dz_m, EPS)
    if dirn == "z":
        return max(dx_m * dy_m, EPS)

    raise ValueError("Unknown direction {}".format(dirn))


def _neighbor_conductance_w_k(k1, k2, center_dist_mm, area_m2):
    d_m = center_dist_mm * 1e-3
    r = (0.5 * d_m) / max(k1 * area_m2, EPS) + (0.5 * d_m) / max(k2 * area_m2, EPS)
    return 1.0 / max(r, EPS)


# ============================================================
# Matrix assembly
# ============================================================

def assemble_sparse_system(grid, voxel_k_w_mk, voxel_power_w, voxel_ambient_g=None, heatsink_obj=None):
    if not HAS_SCIPY:
        raise RuntimeError("SciPy is required for the sparse thermal solve.")

    nvox = grid["nvox"]
    rows = []
    cols = []
    data = []
    b = np.array(voxel_power_w, dtype=float)

    if voxel_ambient_g is None:
        voxel_ambient_g = np.zeros(nvox, dtype=float)

    top_htc = _get_top_htc_w_m2k(heatsink_obj)

    dxs = grid["xs"][1:] - grid["xs"][:-1]
    dys = grid["ys"][1:] - grid["ys"][:-1]
    dzs = grid["zs"][1:] - grid["zs"][:-1]

    diag = np.zeros(nvox, dtype=float)

    def add_entry(r, c, val):
        rows.append(r)
        cols.append(c)
        data.append(val)

    def add_edge(n, m, g):
        diag[n] += g
        diag[m] += g
        add_entry(n, m, -g)
        add_entry(m, n, -g)

    for k in range(grid["nz"]):
        dz_mm = dzs[k]
        for j in range(grid["ny"]):
            dy_mm = dys[j]
            for i in range(grid["nx"]):
                dx_mm = dxs[i]
                n = _idx(i, j, k, grid)
                k_here = voxel_k_w_mk[n]

                if i + 1 < grid["nx"]:
                    m = _idx(i + 1, j, k, grid)
                    area = _face_area_m2("x", dx_mm, dy_mm, dz_mm)
                    center_dist_mm = 0.5 * dx_mm + 0.5 * dxs[i + 1]
                    g = _neighbor_conductance_w_k(k_here, voxel_k_w_mk[m], center_dist_mm, area)
                    add_edge(n, m, g)

                if j + 1 < grid["ny"]:
                    m = _idx(i, j + 1, k, grid)
                    area = _face_area_m2("y", dx_mm, dy_mm, dz_mm)
                    center_dist_mm = 0.5 * dy_mm + 0.5 * dys[j + 1]
                    g = _neighbor_conductance_w_k(k_here, voxel_k_w_mk[m], center_dist_mm, area)
                    add_edge(n, m, g)

                if k + 1 < grid["nz"]:
                    m = _idx(i, j, k + 1, grid)
                    area = _face_area_m2("z", dx_mm, dy_mm, dz_mm)
                    center_dist_mm = 0.5 * dz_mm + 0.5 * dzs[k + 1]
                    g = _neighbor_conductance_w_k(k_here, voxel_k_w_mk[m], center_dist_mm, area)
                    add_edge(n, m, g)

                # weak fallback cooling at package bottom
                if k == 0:
                    area = _face_area_m2("z", dx_mm, dy_mm, dz_mm)
                    g_amb = H_BOTTOM_W_M2K * area
                    diag[n] += g_amb
                    b[n] += g_amb * AMBIENT_TEMP_C

                # main box-defined cooling path
                if voxel_ambient_g[n] > 0.0:
                    diag[n] += voxel_ambient_g[n]
                    b[n] += voxel_ambient_g[n] * AMBIENT_TEMP_C

                # last-resort fallback at very top
                elif k == grid["nz"] - 1:
                    area = _face_area_m2("z", dx_mm, dy_mm, dz_mm)
                    g_amb = top_htc * area
                    diag[n] += g_amb
                    b[n] += g_amb * AMBIENT_TEMP_C

    for n in range(nvox):
        add_entry(n, n, diag[n])

    G = sparse.coo_matrix((data, (rows, cols)), shape=(nvox, nvox)).tocsr()
    return G, b


def solve_steady_state(G, b):
    if not HAS_SCIPY:
        raise RuntimeError("SciPy is required for the sparse thermal solve.")

    T = spsolve(G, b)
    return np.asarray(T, dtype=float)


# ============================================================
# Reduction back to boxes
# ============================================================

def _box_directional_resistances(box):
    mat = getattr(box, "material", None)
    k = _get_k(mat if mat else "Si")

    w_m = max(_safe_float(box.width) * 1e-3, EPS)
    l_m = max(_safe_float(box.length) * 1e-3, EPS)
    h_m = max(_safe_float(box.height) * 1e-3, EPS)

    rx = w_m / max(k * l_m * h_m, EPS)
    ry = l_m / max(k * w_m * h_m, EPS)
    rz = h_m / max(k * w_m * l_m, EPS)
    return rx, ry, rz


def reduce_to_box_metrics(temperatures_c, owner_box_idx, all_boxes):
    voxels_by_box = {}
    for n, bi in enumerate(owner_box_idx):
        if bi >= 0:
            voxels_by_box.setdefault(int(bi), []).append(float(temperatures_c[n]))

    result = {}

    for bi, box in enumerate(all_boxes):
        temps = voxels_by_box.get(bi, [])
        if temps:
            peak_t = max(temps)
            avg_t = sum(temps) / len(temps)
        else:
            peak_t = AMBIENT_TEMP_C
            avg_t = AMBIENT_TEMP_C

        rx, ry, rz = _box_directional_resistances(box)
        result[getattr(box, "name", "box_{}".format(bi))] = (peak_t, avg_t, rx, ry, rz)

    return result


# ============================================================
# Debug helpers
# ============================================================

def _print_grid_summary(grid):
    print(
        "[thermal_solver] grid: nx={}, ny={}, nz={}, nvox={}".format(
            grid["nx"], grid["ny"], grid["nz"], grid["nvox"]
        )
    )

def _print_temperature_summary(box_results):
    gpu_items = []
    hbm_items = []

    for k, v in box_results.items():
        kl = k.lower()

        if "bonding" in kl or "tim" in kl:
            continue

        if ".gpu" in kl or kl.endswith("gpu"):
            gpu_items.append((k, v))

        if "hbm#" in kl and ".hbm_l" not in kl:
            hbm_items.append((k, v))

    if gpu_items:
        hottest_gpu = max(gpu_items, key=lambda kv: kv[1][0])
        print("[thermal_solver] hottest GPU-like box: {} peak={:.3f} C".format(
            hottest_gpu[0], hottest_gpu[1][0]
        ))

    if hbm_items:
        hottest_hbm = max(hbm_items, key=lambda kv: kv[1][0])
        print("[thermal_solver] hottest HBM-like box: {} peak={:.3f} C".format(
            hottest_hbm[0], hottest_hbm[1][0]
        ))


# ============================================================
# Top-level API
# ============================================================

def solve_thermal(
    boxes,
    bonding_box_list,
    TIM_boxes,
    heatsink_obj=None,
    layers=None,
    tim_cond=None,
    infill_cond=None,
    underfill_cond=None,
    project_name=None,
    summary_dir="out_therm/summaries",
    target_dx_mm=2.0,
    target_dy_mm=2.0,
    target_dz_mm=0.25,
    verbose=False,
):
    if tim_cond is not None:
        CONDUCTIVITY["TIM0p5"] = float(tim_cond)
        CONDUCTIVITY["TIM"] = float(tim_cond)

    if infill_cond is not None:
        CONDUCTIVITY["Infill_material"] = float(infill_cond)

    if underfill_cond is not None:
        CONDUCTIVITY["Epoxy"] = float(underfill_cond)

    grid = build_global_grid(
        boxes,
        bonding_box_list,
        TIM_boxes,
        target_dx_mm=target_dx_mm,
        target_dy_mm=target_dy_mm,
        target_dz_mm=target_dz_mm,
    )

    owner_box_idx, voxel_k, voxel_power, voxel_ambient_g, all_boxes, total_power = assign_materials_and_power(
        grid=grid,
        boxes=boxes,
        bonding_box_list=bonding_box_list,
        TIM_boxes=TIM_boxes,
        layers=layers,
        verbose=verbose,
    )

    # print("[thermal_solver] total assigned power = {:.6f} W".format(np.sum(voxel_power)))

    if not HAS_SCIPY:
        raise RuntimeError("SciPy is not installed in the environment. Please install scipy.")

    G, b = assemble_sparse_system(
        grid=grid,
        voxel_k_w_mk=voxel_k,
        voxel_power_w=voxel_power,
        voxel_ambient_g=voxel_ambient_g,
        heatsink_obj=heatsink_obj,
    )

    temperatures_c = solve_steady_state(G, b)

    results = reduce_to_box_metrics(
        temperatures_c=temperatures_c,
        owner_box_idx=owner_box_idx,
        all_boxes=all_boxes,
    )

    _print_temperature_summary(results)

    summary = _extract_key_thermal_summary(results)
    summary_row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "project_name": project_name if project_name else "unknown_project",
        "grid_nx": grid["nx"],
        "grid_ny": grid["ny"],
        "grid_nz": grid["nz"],
        "nvox": grid["nvox"],
        "total_power_w": total_power,
        "gpu_box": summary["gpu_box"],
        "gpu_peak_c": summary["gpu_peak_c"],
        "hbm_box": summary["hbm_box"],
        "hbm_peak_c": summary["hbm_peak_c"],
    }

    print("[thermal_solver] FINAL_SUMMARY project={} gpu_peak_c={:.3f} hbm_peak_c={:.3f} nvox={}".format(
        summary_row["project_name"],
        summary_row["gpu_peak_c"] if summary_row["gpu_peak_c"] is not None else float("nan"),
        summary_row["hbm_peak_c"] if summary_row["hbm_peak_c"] is not None else float("nan"),
        summary_row["nvox"],
    ))

    csv_path = os.path.join(summary_dir, "thermal_summary.csv")
    json_name = "{}_summary.json".format(summary_row["project_name"])
    json_path = os.path.join(summary_dir, json_name)

    _append_summary_csv(summary_row, csv_path)
    _write_summary_json(summary_row, json_path)

    return results