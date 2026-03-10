"""
thermal_solver.py

Adaptive-grid 3D steady-state thermal solver for the EE201A project.

Key behavior:
- builds an adaptive 3D voxel grid from boxes / bonding / TIM
- assigns thermal conductivity from stackup
- distributes each box power over its owned voxels
- builds a thermal resistor network
- solves with PySpice DC operating point
- reports timing:
    * build/runtime excluding PySpice solve
    * PySpice-only solve time
    * total solver time
- returns:
    {
        box_name: (peak_temp_c, avg_temp_c, Rx, Ry, Rz)
    }

Python 3.6 compatible.
"""

import math
import numpy as np
import os
import csv
import json
import time
from datetime import datetime

try:
    from scipy import sparse
    from scipy.sparse.linalg import cg, LinearOperator
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from PySpice.Spice.Netlist import Circuit
    HAS_PYSPICE = True
except Exception:
    HAS_PYSPICE = False


# ============================================================
# Constants / defaults
# ============================================================

AMBIENT_TEMP_C = 45.0
H_BOTTOM_W_M2K = 10.0
H_TOP_DEFAULT_W_M2K = 5000.0
EPS = 1e-18
BIG_R = 1e30


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
    "dummySi_HBM": 105.0,
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


def _ijk_from_idx(n, grid):
    i = n % grid["nx"]
    q = n // grid["nx"]
    j = q % grid["ny"]
    k = q // grid["ny"]
    return i, j, k


def _overlap_len(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _interval_centers(bounds):
    return 0.5 * (bounds[:-1] + bounds[1:])


def _merge_close_coords(vals, tol=1e-4):
    vals = sorted(float(v) for v in vals)
    if not vals:
        return np.array([], dtype=float)

    merged = [vals[0]]
    for v in vals[1:]:
        if abs(v - merged[-1]) < tol:
            continue
        merged.append(v)

    return np.array(merged, dtype=float)


def _voxel_dims_mm(grid, i, j, k):
    dx_mm = grid["xs"][i + 1] - grid["xs"][i]
    dy_mm = grid["ys"][j + 1] - grid["ys"][j]
    dz_mm = grid["zs"][k + 1] - grid["zs"][k]
    return dx_mm, dy_mm, dz_mm


def _voxel_volume_m3_from_indices(grid, i, j, k):
    dx_mm, dy_mm, dz_mm = _voxel_dims_mm(grid, i, j, k)
    return max(dx_mm, EPS) * 1e-3 * max(dy_mm, EPS) * 1e-3 * max(dz_mm, EPS) * 1e-3


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


def _box_name_lower(box):
    return str(getattr(box, "name", "")).lower()


def _chiplet_type(box):
    try:
        return str(box.chiplet_parent.get_chiplet_type())
    except Exception:
        return ""


def _chiplet_type_lower(box):
    return _chiplet_type(box).lower()


def _is_nonphysical_wrapper_box(box):
    name = str(getattr(box, "name", ""))
    name_l = name.lower()
    ctype = _chiplet_type_lower(box)
    parts = [p for p in name_l.split(".") if p]

    if parts and parts[-1] == "set_primary":
        return True

    if ctype == "power_source" and len(parts) <= 1:
        return False  # keep physical Power_Source box if it really has dimensions/power

    return False


def _is_physical_box(box):
    if _is_nonphysical_wrapper_box(box):
        return False

    w = max(_safe_float(getattr(box, "width", 0.0)), 0.0)
    l = max(_safe_float(getattr(box, "length", 0.0)), 0.0)
    h = max(_safe_float(getattr(box, "height", 0.0)), 0.0)

    return (w > 0.0 and l > 0.0 and h > 0.0)


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


def _box_ambient_conduct(box):
    return _safe_float(getattr(box, "ambient_conduct", 0.0), 0.0)


def _collect_all_boxes(boxes, bonding_box_list, TIM_boxes):
    all_boxes = []
    for group in (boxes, bonding_box_list, TIM_boxes):
        if group:
            all_boxes.extend(group)
    return all_boxes


def _is_gpu_like_box(box):
    name_l = _box_name_lower(box)
    ctype_l = _chiplet_type_lower(box)
    return ("gpu" in name_l) or ("gpu" in ctype_l)


def _is_hbm_like_box(box):
    name_l = _box_name_lower(box)
    ctype_l = _chiplet_type_lower(box)
    return ("hbm" in name_l) or ("hbm" in ctype_l)


def _is_support_box(box):
    name_l = _box_name_lower(box)
    ctype_l = _chiplet_type_lower(box)

    blocked_terms = [
        "bonding",
        "tim",
        "heatsink",
    ]
    for term in blocked_terms:
        if term in name_l:
            return True

    if ctype_l in ["interposer", "substrate"]:
        return False

    return False


def _infer_box_power_w(box):
    """
    Use actual box power from the parsed geometry.

    This keeps the solver compatible with different configs and avoids
    hard-forcing 400W/5W inside the solver.
    """
    if not _is_physical_box(box):
        return 0.0

    if _is_support_box(box):
        return 0.0

    p = max(_safe_float(getattr(box, "power", 0.0)), 0.0)
    return p

def _parallel_resistance(r_list, fallback=None):
    inv_sum = 0.0
    for r in r_list:
        if r > 0.0 and math.isfinite(r):
            inv_sum += 1.0 / r

    if inv_sum > 0.0:
        return 1.0 / inv_sum

    if fallback is not None and fallback > 0.0 and math.isfinite(fallback):
        return fallback

    return BIG_R


def _get_top_htc_w_m2k(heatsink_obj=None):
    if heatsink_obj is not None:
        for attr_name in [
            "get_heat_transfer_coeff",
            "get_heat_transfer_coefficient",
            "get_htc",
            "get_hc",
        ]:
            fn = getattr(heatsink_obj, attr_name, None)
            if callable(fn):
                try:
                    val = _safe_float(fn(), 0.0)
                    if val > 0:
                        return val
                except Exception:
                    pass

        for attr_name in ["htc", "hc", "heat_transfer_coeff", "heat_transfer_coefficient"]:
            if hasattr(heatsink_obj, attr_name):
                val = _safe_float(getattr(heatsink_obj, attr_name), 0.0)
                if val > 0:
                    return val

    return H_TOP_DEFAULT_W_M2K

def _effective_box_conductivity(box, layer_map):
    """
    Estimate an effective conductivity for a whole box from its stackup.
    Falls back to material/Si if needed.
    """
    stack = _parse_stackup(box, layer_map)
    total_t = 0.0
    weighted_k = 0.0

    for thick_mm, k in stack:
        if thick_mm > 0.0 and k > 0.0:
            total_t += thick_mm
            weighted_k += thick_mm * k

    if total_t > 0.0:
        return weighted_k / total_t

    return _get_k(getattr(box, "material", None) or "Si")


def _box_directional_geometry_resistances(box, layer_map):
    """
    Fallback box-level directional thermal resistances based on box geometry.

    Uses:
        Rx = Lx / (k * Ayz)
        Ry = Ly / (k * Axz)
        Rz = Lz / (k * Axy)

    with dimensions converted from mm to meters.
    """
    w_mm = max(_safe_float(getattr(box, "width", 0.0)), 0.0)
    l_mm = max(_safe_float(getattr(box, "length", 0.0)), 0.0)
    h_mm = max(_safe_float(getattr(box, "height", 0.0)), 0.0)

    if w_mm <= 0.0 or l_mm <= 0.0 or h_mm <= 0.0:
        return BIG_R, BIG_R, BIG_R

    k_eff = max(_effective_box_conductivity(box, layer_map), EPS)

    w_m = w_mm * 1e-3
    l_m = l_mm * 1e-3
    h_m = h_mm * 1e-3

    rx = w_m / max(k_eff * l_m * h_m, EPS)
    ry = l_m / max(k_eff * w_m * h_m, EPS)
    rz = h_m / max(k_eff * w_m * l_m, EPS)

    return max(rx, EPS), max(ry, EPS), max(rz, EPS)

# ============================================================
# Adaptive grid generation
# ============================================================

def _interval_overlaps_box_on_axis(a, b, lo, hi):
    return _overlap_len(a, b, lo, hi) > 0.0


def _xy_step_for_interval(axis, a, b, all_boxes, default_step_mm):
    """
    Choose a smaller step where powered / active boxes overlap the interval.
    """
    best = default_step_mm

    for box in all_boxes:
        if not _is_physical_box(box):
            continue

        if axis == "x":
            overlaps = _interval_overlaps_box_on_axis(a, b, _safe_float(box.start_x), _box_end_x(box))
        else:
            overlaps = _interval_overlaps_box_on_axis(a, b, _safe_float(box.start_y), _box_end_y(box))

        if not overlaps:
            continue

        name_l = _box_name_lower(box)
        ctype_l = _chiplet_type_lower(box)
        power = _infer_box_power_w(box)

        if power > 0.0 or "gpu" in name_l or "gpu" in ctype_l:
            best = min(best, max(0.5, 0.5 * default_step_mm))
        elif "hbm" in name_l or "hbm" in ctype_l:
            best = min(best, max(0.75, 0.75 * default_step_mm))
        elif "tim" in name_l or "bonding" in name_l:
            best = min(best, max(0.5, 0.5 * default_step_mm))

    return max(best, 0.1)


def _z_step_for_interval(a, b, all_boxes, default_step_mm):
    """
    Choose a finer z step in thin / important layers.
    """
    length = b - a
    best = default_step_mm

    for box in all_boxes:
        if not _is_physical_box(box):
            continue

        if not _interval_overlaps_box_on_axis(a, b, _safe_float(box.start_z), _box_end_z(box)):
            continue

        name_l = _box_name_lower(box)
        h = max(_safe_float(box.height), 0.0)
        power = _infer_box_power_w(box)

        if "tim" in name_l or "bonding" in name_l:
            best = min(best, max(0.01, min(length, 0.05)))
        elif power > 0.0:
            best = min(best, max(0.02, min(length, 0.10)))
        elif h < 0.15:
            best = min(best, max(0.02, min(length, 0.08)))

    return max(best, 0.005)


def _adaptive_subdivide(bounds, axis, all_boxes, target_step_mm):
    bounds = np.array(sorted(float(v) for v in bounds), dtype=float)
    if len(bounds) < 2:
        return bounds

    refined = [bounds[0]]

    for a, b in zip(bounds[:-1], bounds[1:]):
        length = b - a
        if length <= 0:
            continue

        if axis in ["x", "y"]:
            step = _xy_step_for_interval(axis, a, b, all_boxes, target_step_mm)
        else:
            step = _z_step_for_interval(a, b, all_boxes, target_step_mm)

        nsplit = max(1, int(math.ceil(length / max(step, EPS))))

        for s in range(1, nsplit + 1):
            refined.append(a + length * s / nsplit)

    if axis == "z":
        return _merge_close_coords(refined, tol=1e-6)
    return _merge_close_coords(refined, tol=1e-5)


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
        if not _is_physical_box(box):
            continue

        xs.add(_safe_float(box.start_x))
        xs.add(_box_end_x(box))

        ys.add(_safe_float(box.start_y))
        ys.add(_box_end_y(box))

        zs.add(_safe_float(box.start_z))
        zs.add(_box_end_z(box))

    xs = _merge_close_coords(xs, tol=1e-4)
    ys = _merge_close_coords(ys, tol=1e-4)
    zs = _merge_close_coords(zs, tol=1e-5)

    xs = _adaptive_subdivide(xs, "x", all_boxes, target_dx_mm)
    ys = _adaptive_subdivide(ys, "y", all_boxes, target_dy_mm)
    zs = _adaptive_subdivide(zs, "z", all_boxes, target_dz_mm)

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


# ============================================================
# Ownership / material / power assignment
# ============================================================

def _find_owner_box_for_voxel(xc, yc, zc, ownership_boxes):
    matches = []

    for bi, box in enumerate(ownership_boxes):
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

            if total_vol > 0.0:
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

    for bi, top_voxels in top_surface_voxels_by_box.items():
        box = ownership_boxes[bi]
        g_box = _box_ambient_conduct(box)

        if g_box > 0.0 and len(top_voxels) > 0:
            area_list = []
            total_area = 0.0

            for n in top_voxels:
                i, j, k = _ijk_from_idx(n, grid)
                dx_mm, dy_mm, dz_mm = _voxel_dims_mm(grid, i, j, k)
                a = _face_area_m2("z", dx_mm, dy_mm, dz_mm)
                area_list.append((n, a))
                total_area += a

            if total_area > 0.0:
                for n, a in area_list:
                    voxel_ambient_g[n] += g_box * (a / total_area)

    print("[thermal_solver] total assigned power = {:.6f} W".format(total_power))

    return owner_box_idx, voxel_k, voxel_power, voxel_ambient_g, ownership_boxes, total_power


# ============================================================
# Network conductance helpers
# ============================================================

def _neighbor_resistance(dirn, grid, voxel_k, i1, j1, k1, i2, j2, k2):
    n1 = _idx(i1, j1, k1, grid)
    n2 = _idx(i2, j2, k2, grid)

    dx1, dy1, dz1 = _voxel_dims_mm(grid, i1, j1, k1)
    dx2, dy2, dz2 = _voxel_dims_mm(grid, i2, j2, k2)

    k_a = voxel_k[n1]
    k_b = voxel_k[n2]

    if dirn == "x":
        area = _face_area_m2("x", min(dx1, dx2), 0.5 * (dy1 + dy2), 0.5 * (dz1 + dz2))
        r = ((0.5 * dx1) * 1e-3) / max(k_a * area, EPS) + ((0.5 * dx2) * 1e-3) / max(k_b * area, EPS)
        return max(r, EPS)

    if dirn == "y":
        area = _face_area_m2("y", 0.5 * (dx1 + dx2), min(dy1, dy2), 0.5 * (dz1 + dz2))
        r = ((0.5 * dy1) * 1e-3) / max(k_a * area, EPS) + ((0.5 * dy2) * 1e-3) / max(k_b * area, EPS)
        return max(r, EPS)

    if dirn == "z":
        area = _face_area_m2("z", 0.5 * (dx1 + dx2), 0.5 * (dy1 + dy2), min(dz1, dz2))
        r = ((0.5 * dz1) * 1e-3) / max(k_a * area, EPS) + ((0.5 * dz2) * 1e-3) / max(k_b * area, EPS)
        return max(r, EPS)

    raise ValueError("Unknown direction {}".format(dirn))


def _boundary_ambient_resistance(dirn, grid, voxel_k, i, j, k, htc_w_m2k=None):
    n = _idx(i, j, k, grid)
    dx_mm, dy_mm, dz_mm = _voxel_dims_mm(grid, i, j, k)
    kval = voxel_k[n]

    if dirn == "bottom":
        area = _face_area_m2("z", dx_mm, dy_mm, dz_mm)
        g = H_BOTTOM_W_M2K * area
        return 1.0 / max(g, EPS)

    if dirn == "top":
        area = _face_area_m2("z", dx_mm, dy_mm, dz_mm)
        g = max(_safe_float(htc_w_m2k, H_TOP_DEFAULT_W_M2K), EPS) * area
        return 1.0 / max(g, EPS)

    raise ValueError("Unknown boundary direction {}".format(dirn))


# ============================================================
# PySpice solve
# ============================================================

def solve_with_pyspice(
    grid,
    voxel_k,
    voxel_power,
    voxel_ambient_g,
    heatsink_obj=None,
):
    if not HAS_PYSPICE:
        raise RuntimeError(
            "PySpice is not installed or could not be imported. "
            "Install PySpice and make sure ngspice shared library is available."
        )

    top_htc = _get_top_htc_w_m2k(heatsink_obj)
    circuit = Circuit('thermal_grid')
    circuit.V('amb', 'TAMB', circuit.gnd, AMBIENT_TEMP_C)

    node_names = []
    for n in range(grid["nvox"]):
        node_names.append("T{}".format(n))

    resistor_count = 0
    current_count = 0

    def add_res(node_a, node_b, r_value):
        nonlocal resistor_count
        if r_value <= 0.0 or not math.isfinite(r_value):
            return
        resistor_count += 1
        circuit.R("r{}".format(resistor_count), node_a, node_b, float(r_value))

    def add_current_to_node(node_name, power_w):
        nonlocal current_count
        if power_w <= 0.0:
            return
        current_count += 1
        # Current source from ground -> thermal node injects heat into node
        circuit.I("i{}".format(current_count), circuit.gnd, node_name, float(power_w))

    for k in range(grid["nz"]):
        for j in range(grid["ny"]):
            for i in range(grid["nx"]):
                n = _idx(i, j, k, grid)
                node_n = node_names[n]

                if i + 1 < grid["nx"]:
                    m = _idx(i + 1, j, k, grid)
                    add_res(node_n, node_names[m], _neighbor_resistance("x", grid, voxel_k, i, j, k, i + 1, j, k))

                if j + 1 < grid["ny"]:
                    m = _idx(i, j + 1, k, grid)
                    add_res(node_n, node_names[m], _neighbor_resistance("y", grid, voxel_k, i, j, k, i, j + 1, k))

                if k + 1 < grid["nz"]:
                    m = _idx(i, j, k + 1, grid)
                    add_res(node_n, node_names[m], _neighbor_resistance("z", grid, voxel_k, i, j, k, i, j, k + 1))

                if k == 0:
                    add_res(node_n, 'TAMB', _boundary_ambient_resistance("bottom", grid, voxel_k, i, j, k))

                if voxel_ambient_g[n] > 0.0:
                    add_res(node_n, 'TAMB', 1.0 / max(voxel_ambient_g[n], EPS))
                elif k == grid["nz"] - 1:
                    add_res(node_n, 'TAMB', _boundary_ambient_resistance("top", grid, voxel_k, i, j, k, top_htc))

                if voxel_power[n] > 0.0:
                    add_current_to_node(node_n, voxel_power[n])

    simulator = circuit.simulator(temperature=25, nominal_temperature=25)
    analysis = simulator.operating_point()

    temperatures_c = np.zeros(grid["nvox"], dtype=float)
    for n, node_name in enumerate(node_names):
        try:
            temperatures_c[n] = float(analysis.nodes[node_name])
        except Exception:
            temperatures_c[n] = AMBIENT_TEMP_C

    return temperatures_c


# ============================================================
# Optional SciPy fallback
# ============================================================

def assemble_sparse_system(grid, voxel_k_w_mk, voxel_power_w, voxel_ambient_g=None, heatsink_obj=None):
    if not HAS_SCIPY:
        raise RuntimeError("SciPy is required for sparse fallback solve.")

    nvox = grid["nvox"]
    rows = []
    cols = []
    data = []
    b = np.array(voxel_power_w, dtype=float)

    if voxel_ambient_g is None:
        voxel_ambient_g = np.zeros(nvox, dtype=float)

    top_htc = _get_top_htc_w_m2k(heatsink_obj)
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
        for j in range(grid["ny"]):
            for i in range(grid["nx"]):
                n = _idx(i, j, k, grid)
                dx_mm, dy_mm, dz_mm = _voxel_dims_mm(grid, i, j, k)

                if i + 1 < grid["nx"]:
                    m = _idx(i + 1, j, k, grid)
                    r = _neighbor_resistance("x", grid, voxel_k_w_mk, i, j, k, i + 1, j, k)
                    g = 1.0 / max(r, EPS)
                    add_edge(n, m, g)

                if j + 1 < grid["ny"]:
                    m = _idx(i, j + 1, k, grid)
                    r = _neighbor_resistance("y", grid, voxel_k_w_mk, i, j, k, i, j + 1, k)
                    g = 1.0 / max(r, EPS)
                    add_edge(n, m, g)

                if k + 1 < grid["nz"]:
                    m = _idx(i, j, k + 1, grid)
                    r = _neighbor_resistance("z", grid, voxel_k_w_mk, i, j, k, i, j, k + 1)
                    g = 1.0 / max(r, EPS)
                    add_edge(n, m, g)

                if k == 0:
                    r_amb = _boundary_ambient_resistance("bottom", grid, voxel_k_w_mk, i, j, k)
                    g_amb = 1.0 / max(r_amb, EPS)
                    diag[n] += g_amb
                    b[n] += g_amb * AMBIENT_TEMP_C

                if voxel_ambient_g[n] > 0.0:
                    diag[n] += voxel_ambient_g[n]
                    b[n] += voxel_ambient_g[n] * AMBIENT_TEMP_C
                elif k == grid["nz"] - 1:
                    r_amb = _boundary_ambient_resistance("top", grid, voxel_k_w_mk, i, j, k, top_htc)
                    g_amb = 1.0 / max(r_amb, EPS)
                    diag[n] += g_amb
                    b[n] += g_amb * AMBIENT_TEMP_C

    for n in range(nvox):
        add_entry(n, n, diag[n])

    G = sparse.coo_matrix((data, (rows, cols)), shape=(nvox, nvox)).tocsr()
    return G, b


def solve_steady_state(G, b, tol=1e-8, maxiter=2000):
    if not HAS_SCIPY:
        raise RuntimeError("SciPy is required for sparse fallback solve.")

    diag = G.diagonal().copy()
    diag[np.abs(diag) < EPS] = 1.0
    M_inv = 1.0 / diag
    M = sparse.linalg.LinearOperator(G.shape, matvec=lambda x: M_inv * x)
    T, info = cg(G, b, M=M, tol=tol, maxiter=maxiter)

    if info != 0:
        print("[thermal_solver] WARNING: cg did not fully converge, info={}".format(info))

    return np.asarray(T, dtype=float)


# ============================================================
# Reduction back to boxes
# ============================================================

def _collect_directional_face_resistances(
    grid,
    owner_box_idx,
    voxel_k,
    voxel_ambient_g,
    heatsink_obj,
    bi,
    box=None,
    layer_map=None,
):
    rx_list = []
    ry_list = []
    rz_list = []

    top_htc = _get_top_htc_w_m2k(heatsink_obj)

    for n, owner in enumerate(owner_box_idx):
        if owner != bi:
            continue

        i, j, k = _ijk_from_idx(n, grid)

        # X-direction boundaries
        if i == 0 or owner_box_idx[_idx(i - 1, j, k, grid)] != bi:
            if i > 0:
                rx_list.append(_neighbor_resistance("x", grid, voxel_k, i, j, k, i - 1, j, k))
        if i == grid["nx"] - 1 or owner_box_idx[_idx(i + 1, j, k, grid)] != bi:
            if i < grid["nx"] - 1:
                rx_list.append(_neighbor_resistance("x", grid, voxel_k, i, j, k, i + 1, j, k))

        # Y-direction boundaries
        if j == 0 or owner_box_idx[_idx(i, j - 1, k, grid)] != bi:
            if j > 0:
                ry_list.append(_neighbor_resistance("y", grid, voxel_k, i, j, k, i, j - 1, k))
        if j == grid["ny"] - 1 or owner_box_idx[_idx(i, j + 1, k, grid)] != bi:
            if j < grid["ny"] - 1:
                ry_list.append(_neighbor_resistance("y", grid, voxel_k, i, j, k, i, j + 1, k))

        # Z-direction boundaries
        if k == 0 or owner_box_idx[_idx(i, j, k - 1, grid)] != bi:
            if k > 0:
                rz_list.append(_neighbor_resistance("z", grid, voxel_k, i, j, k, i, j, k - 1))
            else:
                rz_list.append(_boundary_ambient_resistance("bottom", grid, voxel_k, i, j, k))

        if k == grid["nz"] - 1 or owner_box_idx[_idx(i, j, k + 1, grid)] != bi:
            if k < grid["nz"] - 1:
                rz_list.append(_neighbor_resistance("z", grid, voxel_k, i, j, k, i, j, k + 1))
            else:
                if voxel_ambient_g[n] > 0.0:
                    rz_list.append(1.0 / max(voxel_ambient_g[n], EPS))
                else:
                    rz_list.append(_boundary_ambient_resistance("top", grid, voxel_k, i, j, k, top_htc))

    fallback_rx = None
    fallback_ry = None
    fallback_rz = None

    if box is not None:
        fb_rx, fb_ry, fb_rz = _box_directional_geometry_resistances(
            box,
            layer_map if layer_map is not None else {}
        )
        fallback_rx = fb_rx
        fallback_ry = fb_ry
        fallback_rz = fb_rz

    rx = _parallel_resistance(rx_list, fallback=fallback_rx)
    ry = _parallel_resistance(ry_list, fallback=fallback_ry)
    rz = _parallel_resistance(rz_list, fallback=fallback_rz)

    return rx, ry, rz


def reduce_to_box_metrics(
    temperatures_c,
    grid,
    owner_box_idx,
    all_boxes,
    voxel_k,
    voxel_ambient_g,
    heatsink_obj,
    layers=None,
):
    voxels_by_box = {}
    for n, bi in enumerate(owner_box_idx):
        if bi >= 0:
            voxels_by_box.setdefault(int(bi), []).append(float(temperatures_c[n]))

    layer_map = _build_layer_map(layers)
    result = {}

    for bi, box in enumerate(all_boxes):
        temps = voxels_by_box.get(bi, [])
        if temps:
            peak_t = max(temps)
            avg_t = sum(temps) / len(temps)
        else:
            peak_t = AMBIENT_TEMP_C
            avg_t = AMBIENT_TEMP_C

        rx, ry, rz = _collect_directional_face_resistances(
            grid=grid,
            owner_box_idx=owner_box_idx,
            voxel_k=voxel_k,
            voxel_ambient_g=voxel_ambient_g,
            heatsink_obj=heatsink_obj,
            bi=bi,
            box=box,
            layer_map=layer_map,
        )

        result[getattr(box, "name", "box_{}".format(bi))] = (peak_t, avg_t, rx, ry, rz)

    return result


# ============================================================
# Summaries / debug
# ============================================================

def _extract_key_thermal_summary(box_results):
    gpu_peak = None
    gpu_name = None
    hottest_hbm_peak = None
    hottest_hbm_name = None

    for name, vals in box_results.items():
        peak_t = vals[0]
        nl = name.lower()

        if "bonding" in nl or "tim" in nl:
            continue

        if ".gpu" in nl or nl.endswith("gpu"):
            if gpu_peak is None or peak_t > gpu_peak:
                gpu_peak = peak_t
                gpu_name = name

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
    os.makedirs(os.path.dirname(out_csv_path), exist_ok=True)

    fieldnames = [
        "timestamp",
        "project_name",
        "grid_nx",
        "grid_ny",
        "grid_nz",
        "nvox",
        "total_power_w",
        "solver_backend",
        "runtime_build_no_backend_s",
        "runtime_backend_s",
        "runtime_total_s",
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


def _print_grid_summary(grid):
    print("[thermal_solver] grid: nx={}, ny={}, nz={}, nvox={}".format(
        grid["nx"], grid["ny"], grid["nz"], grid["nvox"]
    ))


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
    target_dx_mm=5.0,
    target_dy_mm=5.0,
    target_dz_mm=0.8,
    use_pyspice=False,
    verbose=False,
):
    if tim_cond is not None:
        CONDUCTIVITY["TIM0p5"] = float(tim_cond)
        CONDUCTIVITY["TIM"] = float(tim_cond)

    if infill_cond is not None:
        CONDUCTIVITY["Infill_material"] = float(infill_cond)

    if underfill_cond is not None:
        CONDUCTIVITY["Epoxy"] = float(underfill_cond)

    t0 = time.time()

    grid = build_global_grid(
        boxes,
        bonding_box_list,
        TIM_boxes,
        target_dx_mm=target_dx_mm,
        target_dy_mm=target_dy_mm,
        target_dz_mm=target_dz_mm,
    )
    _print_grid_summary(grid)

    owner_box_idx, voxel_k, voxel_power, voxel_ambient_g, all_boxes, total_power = assign_materials_and_power(
        grid=grid,
        boxes=boxes,
        bonding_box_list=bonding_box_list,
        TIM_boxes=TIM_boxes,
        layers=layers,
        verbose=verbose,
    )

    t_before_pyspice = time.time()

    if use_pyspice:
        temperatures_c = solve_with_pyspice(
            grid=grid,
            voxel_k=voxel_k,
            voxel_power=voxel_power,
            voxel_ambient_g=voxel_ambient_g,
            heatsink_obj=heatsink_obj,
        )
    else:
        if not HAS_SCIPY:
            raise RuntimeError("SciPy is required when use_pyspice=False.")
        G, b = assemble_sparse_system(
            grid=grid,
            voxel_k_w_mk=voxel_k,
            voxel_power_w=voxel_power,
            voxel_ambient_g=voxel_ambient_g,
            heatsink_obj=heatsink_obj,
        )
        temperatures_c = solve_steady_state(G, b)

    t_after_pyspice = time.time()

    results = reduce_to_box_metrics(
        temperatures_c=temperatures_c,
        grid=grid,
        owner_box_idx=owner_box_idx,
        all_boxes=all_boxes,
        voxel_k=voxel_k,
        voxel_ambient_g=voxel_ambient_g,
        heatsink_obj=heatsink_obj,
        layers=layers,
    )

    t_end = time.time()

    runtime_build_no_backend_s = (t_before_pyspice - t0) + (t_end - t_after_pyspice)
    runtime_backend_s = (t_after_pyspice - t_before_pyspice)
    runtime_total_s = (t_end - t0)

    backend_name = "PySpice" if use_pyspice else "SciPy-CG"

    print("[thermal_solver] runtime excluding {} solve: {:.6f} s".format(backend_name, runtime_build_no_backend_s))
    print("[thermal_solver] runtime {} solve only:    {:.6f} s".format(backend_name, runtime_backend_s))
    print("[thermal_solver] runtime total solver:     {:.6f} s".format(runtime_total_s))

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
        "solver_backend": "PySpice" if use_pyspice else "SciPy-CG",
        "runtime_build_no_backend_s": runtime_build_no_backend_s,
        "runtime_backend_s": runtime_backend_s,
        "runtime_total_s": runtime_total_s,
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