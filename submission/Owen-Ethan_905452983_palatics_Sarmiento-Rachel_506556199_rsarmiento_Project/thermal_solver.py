"""
3D Finite-Difference Thermal Solver for EE201A Final Project.

Builds a non-uniform 3D grid aligned to chiplet/bonding/TIM/heatsink
boundaries, assigns per-voxel material conductivities using layer-by-layer
stackup resolution, distributes power sources, assembles a sparse thermal
conductance matrix, and solves for steady-state temperatures via Conjugate
Gradient (with numpy iterative SOR fallback).
"""

import math
import time
import numpy as np

try:
    from scipy import sparse
    from scipy.sparse.linalg import spsolve, cg
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


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
GPU_TOTAL_POWER_W = 400.0
HBM_STACK_POWER_W = 5.0
H_BOTTOM = 10.0


# ----------------------------------------------------------------
# Material helpers
# ----------------------------------------------------------------

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
    """Compute effective k for a specific z-slice through the box stackup.

    Walks through each layer in the stackup (bottom-up), finds the overlap
    between the layer's z-span and the voxel's z-span, and computes a
    thickness-weighted average conductivity.
    """
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


# ----------------------------------------------------------------
# Grid construction
# ----------------------------------------------------------------

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


# ----------------------------------------------------------------
# Cell-range helper
# ----------------------------------------------------------------

def _cr(edges, lo, hi, eps=0.0005):
    i0 = max(0, int(np.searchsorted(edges, lo - eps)))
    i1 = min(len(edges) - 1, int(np.searchsorted(edges, hi - eps)))
    return i0, i1


# ----------------------------------------------------------------
# Assign material conductivities (layer-by-layer)
# ----------------------------------------------------------------

def assign_materials(all_boxes, xe, ye, ze, layers, hs_obj, infill_k=19.0):
    nx, ny, nz = len(xe) - 1, len(ye) - 1, len(ze) - 1
    k = np.full((nx, ny, nz), CONDUCTIVITY["Air"])
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
            k[ci0:ci1, cj0:cj1, kk] = infill_k

    for box in sorted(all_boxes, key=lambda b: b.width * b.length * b.height, reverse=True):
        i0, i1 = _cr(xe, box.start_x, box.end_x)
        j0, j1 = _cr(ye, box.start_y, box.end_y)
        k0, k1 = _cr(ze, box.start_z, box.end_z)
        if i0 >= i1 or j0 >= j1 or k0 >= k1:
            continue
        for kk in range(k0, k1):
            vz_lo = ze[kk]
            vz_hi = ze[kk + 1]
            kv = _retrieve_conductivity(box, vz_lo, vz_hi, lm)
            k[i0:i1, j0:j1, kk] = kv

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
            k[i0:i1, j0:j1, k0:k1] = hk
    return k


# ----------------------------------------------------------------
# Assign power sources
# ----------------------------------------------------------------

def assign_power(boxes, xe, ye, ze):
    """Map chiplet power onto the voxel grid using per-box power values.

    Prefer explicit power values attached to each Box (from the XML configs).
    If no positive power is found, fall back to legacy constants so the solver
    still runs. Power is distributed uniformly across the voxels overlapped by
    each powered box.
    """

    nx, ny, nz = len(xe) - 1, len(ye) - 1, len(ze) - 1
    q = np.zeros((nx, ny, nz))

    powered_boxes = []
    for box in boxes:
        try:
            pwr = float(getattr(box, "power", 0.0) or 0.0)
        except (TypeError, ValueError):
            pwr = 0.0
        if pwr > 0:
            powered_boxes.append((box, pwr))

    # Fallback to legacy constants if XML powers were not present
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
        dxc = xe[i0 + 1 : i1 + 1] - xe[i0:i1]
        dyc = ye[j0 + 1 : j1 + 1] - ye[j0:j1]
        dzc = ze[k0 + 1 : k1 + 1] - ze[k0:k1]
        vol = np.einsum("i,j,k->ijk", dxc, dyc, dzc)
        tv = vol.sum()
        if tv > 0:
            q[i0:i1, j0:j1, k0:k1] += pwr / tv

    return q


# ----------------------------------------------------------------
# System assembly and CG solver
# ----------------------------------------------------------------

def _build_system(kg, qg, xe, ye, ze, hc_top):
    """Build sparse conductance matrix A and RHS vector b."""
    nx, ny, nz = kg.shape
    N = nx * ny * nz
    eps = 1e-15

    dx = (xe[1:] - xe[:-1]) / 1000.0
    dy = (ye[1:] - ye[:-1]) / 1000.0
    dz = (ze[1:] - ze[:-1]) / 1000.0
    ks = np.maximum(kg, eps)

    Ax = dy[None, :, None] * dz[None, None, :]
    Gx = 1.0 / np.maximum(
        dx[:nx-1, None, None] / (2 * ks[:nx-1] * Ax)
        + dx[1:, None, None] / (2 * ks[1:] * Ax), eps)
    Ay = dx[:, None, None] * dz[None, None, :]
    Gy = 1.0 / np.maximum(
        dy[None, :ny-1, None] / (2 * ks[:, :ny-1] * Ay)
        + dy[None, 1:, None] / (2 * ks[:, 1:] * Ay), eps)
    Az = dx[:, None, None] * dy[None, :, None]
    Gz = 1.0 / np.maximum(
        dz[None, None, :nz-1] / (2 * ks[:, :, :nz-1] * Az)
        + dz[None, None, 1:] / (2 * ks[:, :, 1:] * Az), eps)

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
    Gt = 1.0 / np.maximum(dz[-1] / (2 * ks[:,:,-1] * Af) + 1.0 / (hc_top * Af + eps), eps)
    diag[:,:,-1] += Gt
    rhs[:,:,-1] += Gt * AMBIENT_TEMP_C

    Gb = 1.0 / np.maximum(dz[0] / (2 * ks[:,:,0] * Af) + 1.0 / (H_BOTTOM * Af + eps), eps)
    diag[:,:,0] += Gb
    rhs[:,:,0] += Gb * AMBIENT_TEMP_C

    rows = np.concatenate([lx, rx, ly, ry, lz, rz, ci.ravel()])
    cols = np.concatenate([rx, lx, ry, ly, rz, lz, ci.ravel()])
    vals = np.concatenate([-gx, -gx, -gy, -gy, -gz, -gz, diag.ravel()])

    A = sparse.csr_matrix(
        (vals, (rows.astype(np.int64), cols.astype(np.int64))), shape=(N, N))
    return A, rhs.ravel(), diag.ravel()


def _solve_sparse(kg, qg, xe, ye, ze, hc_top):
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


# ----------------------------------------------------------------
# Iterative SOR solver (numpy-only fallback)
# ----------------------------------------------------------------

def _solve_iter(kg, qg, xe, ye, ze, hc_top, max_it=8000, tol=0.01, omega=1.4):
    nx, ny, nz = kg.shape
    eps = 1e-15
    dx = (xe[1:] - xe[:-1]) / 1000.0
    dy = (ye[1:] - ye[:-1]) / 1000.0
    dz = (ze[1:] - ze[:-1]) / 1000.0
    ks = np.maximum(kg, eps)

    Ax = dy[None, :, None] * dz[None, None, :]
    Gx = 1.0 / np.maximum(
        dx[:nx-1, None, None] / (2 * ks[:nx-1] * Ax)
        + dx[1:, None, None] / (2 * ks[1:] * Ax), eps)
    Ay = dx[:, None, None] * dz[None, None, :]
    Gy = 1.0 / np.maximum(
        dy[None, :ny-1, None] / (2 * ks[:, :ny-1] * Ay)
        + dy[None, 1:, None] / (2 * ks[:, 1:] * Ay), eps)
    Az = dx[:, None, None] * dy[None, :, None]
    Gz = 1.0 / np.maximum(
        dz[None, None, :nz-1] / (2 * ks[:, :, :nz-1] * Az)
        + dz[None, None, 1:] / (2 * ks[:, :, 1:] * Az), eps)

    diag = np.zeros((nx, ny, nz))
    diag[1:] += Gx; diag[:nx-1] += Gx
    diag[:,1:] += Gy; diag[:,:ny-1] += Gy
    diag[:,:,1:] += Gz; diag[:,:,:nz-1] += Gz

    cvol = np.einsum("i,j,k->ijk", dx * 1e3, dy * 1e3, dz * 1e3)
    rhs = qg * cvol

    Af = dx[:, None] * dy[None, :]
    Gt = 1.0 / np.maximum(dz[-1] / (2 * ks[:,:,-1] * Af) + 1.0 / (hc_top * Af + eps), eps)
    diag[:,:,-1] += Gt
    rhs[:,:,-1] += Gt * AMBIENT_TEMP_C
    Gb = 1.0 / np.maximum(dz[0] / (2 * ks[:,:,0] * Af) + 1.0 / (H_BOTTOM * Af + eps), eps)
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


# ----------------------------------------------------------------
# Box-level analytical resistances
# ----------------------------------------------------------------

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


# ----------------------------------------------------------------
# Results extraction
# ----------------------------------------------------------------

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


# ----------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------

def solve_thermal(boxes, bonding_boxes, tim_boxes, heatsink_obj, layers,
                  tim_cond=None, infill_cond=None, underfill_cond=None, **kw):
    """
    Full 3D thermal solve.

    Parameters
    ----------
    tim_cond : float, optional
        Override TIM conductivity (W/(m·K)). Default uses CONDUCTIVITY["TIM0p5"].
    infill_cond : float, optional
        Override infill conductivity (W/(m·K)). Default uses CONDUCTIVITY["Infill_material"].
    underfill_cond : float, optional
        Override underfill conductivity (W/(m·K)). Not currently used separately.

    Returns
    -------
    dict : {box_name: (peak_T, avg_T, R_x, R_y, R_z), ...}
    """
    t0 = time.time()

    if tim_cond is not None:
        CONDUCTIVITY["TIM0p5"] = float(tim_cond)
    if infill_cond is not None:
        CONDUCTIVITY["Infill_material"] = float(infill_cond)

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
              f"hc={hs.get('hc')}, mat={hs.get('material')}")

    xe, ye, ze = build_grid(all_el, heatsink_obj, max_xy=2.0, max_z=0.3, min_s=0.001)
    nx, ny, nz = len(xe) - 1, len(ye) - 1, len(ze) - 1
    print(f"  Grid: {nx} x {ny} x {nz} = {nx * ny * nz} cells  ({time.time() - t0:.2f}s)")

    kg = assign_materials(all_el, xe, ye, ze, layers, heatsink_obj, infill_k=infill_k)
    print(f"  Materials assigned  ({time.time() - t0:.2f}s)  "
          f"k range: [{kg.min():.3f}, {kg.max():.1f}]")

    qg = assign_power(boxes, xe, ye, ze)
    vol = np.einsum("i,j,k->ijk", xe[1:] - xe[:-1], ye[1:] - ye[:-1], ze[1:] - ze[:-1])
    total_p = (qg * vol).sum()
    print(f"  Power assigned      ({time.time() - t0:.2f}s)  total={total_p:.1f} W")

    try:
        hc = float(hs.get("hc", "7000"))
    except (ValueError, TypeError):
        hc = 7000.0

    if HAS_SCIPY:
        print("  Solving (CG with Jacobi preconditioner) ...")
        Tg = _solve_sparse(kg, qg, xe, ye, ze, hc)
    else:
        print("  Solving (numpy SOR) ...")
        Tg = _solve_iter(kg, qg, xe, ye, ze, hc)
    print(f"  Solve done          ({time.time() - t0:.2f}s)  "
          f"Tmin={Tg.min():.1f}  Tmax={Tg.max():.1f}")

    results = extract_results(boxes, Tg, xe, ye, ze, layers)
    print(f"  Results extracted   ({time.time() - t0:.2f}s)")
    return results
