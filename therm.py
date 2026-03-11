"""
Thermal analysis tool for 2.5-D and 3-D GPU + HBM chiplet systems.

Uses click to parse thermal configs, performs chiplet placement and sizing,
and runs an ngspice-first thermal resistance network simulation.

SOLVER ARCHITECTURE:
  The thermal solve (simulator_simulate → thermal_solver.solve_thermal)
  builds a meshed voxel RC network, exports it as a SPICE netlist, and uses
  the project-local ngspice binary as the first-choice solver. This matches
  the project requirement that the RC netlist solving be done with ngspice.
  If ngspice is unavailable or fails, the code falls back to a direct matrix
  solve (scipy sparse CG or numpy SOR) using the same voxel-network physics.

SIMULATION TIMING EXCLUSION:
  The project figure-of-merit runtime covers only sizing and placement — NOT
  the thermal solve. The variable runtime_excluding_simulation_s (printed at
  the end) is what should be reported/compared. Simulation time is printed
  separately as "Simulation runtime (excluded from total runtime)".

POWER — 270 W GPU (NOT 400 W):
  The lab PDF says 400 W.  The Piazza course forum clarified:
    "Please use the 270 W values as in therm.py for now."
  GPU_DEFAULT_POWER_W = 270.0 is set below and applied to the chiplet tree
  before any simulation runs.  The XML configs already carry 270 W as
  core_power; this override makes the choice explicit and auditable.
"""

import csv
import math
import os
import pickle
import re
import time
from pathlib import Path
from typing import List, Tuple

import click
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import yaml
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from rearrange import *
from therm_xml_parser import *
from bonding_xml_parser import *
from heatsink_xml_parser import *

# GPU power: 270 W per Piazza course-staff clarification (Winter 2026).
# The project PDF specifies 400 W but the correct value is 270 W.
# Piazza answer: "Please use the 270 W values as in therm.py for now.
# Your code anyway has to be able to run for variety of setups."
# The XML configs carry this as core_power=270; we override explicitly below
# so the value is unambiguous regardless of XML content.
GPU_DEFAULT_POWER_W = 270.0
POWER_SOURCE_POWER_W = 0.0

sns.set()

# TODO: PROJECT - These constants affect chiplet placement overlap checking.
MOVE_MULTIPLIER = 1  # How many times min_dist to move per step
INFLATION = 1       # Inflation factor for overlap checking

def simulator_simulate(
    boxes,
    bonding_box_list,
    TIM_boxes,
    heatsink_obj=None,
    heatsink_list=None,
    heatsink_name=None,
    bonding_list=None,
    bonding_name_type_dict=None,
    is_repeat=False,
    min_TIM_height=0.01,
    power_dict=None,
    anemoi_parameter_ID=None,
    layers=None,
    tim_cond=None,
    infill_cond=None,
    underfill_cond=None,
):
    """
    Solve the thermal resistance network and return per-box temperature results.

    Delegates to thermal_solver.solve_thermal() which implements the following
    solver hierarchy for final-project runs:

      1. Meshed voxel RC netlist (PRIMARY):
         - Builds a non-uniform 3D grid aligned to chiplet boundaries.
         - Assigns per-voxel conductivities from layer stackup definitions.
         - Deposits GPU/HBM power on each die's center z-plane.
         - Exports the RC netlist and solves it with local ngspice.

      2. Sparse/numpy fallback:
         - Uses scipy sparse CG (or numpy SOR) only if ngspice fails.

    This function is deliberately NOT the timing-critical path. The caller
    wraps it with simulation_start_time / simulation_end_time and the result
    is reported as "Simulation runtime (excluded from total runtime)".

    Returns:
        Dictionary mapping box names to tuples of:
            (peak_temperature_C, average_temperature_C, R_x_K_per_W, R_y_K_per_W, R_z_K_per_W)
    """
    from thermal_solver import solve_thermal

    # Final Project v4 requires GPU/HBM power injection on each die's center
    # z-plane, so we always use the voxel mesh. That mesh is now solved by
    # ngspice first, with the internal linear-algebra path only as fallback.
    return solve_thermal(
        boxes,
        bonding_box_list,
        TIM_boxes,
        heatsink_obj=heatsink_obj,
        layers=layers,
        tim_cond=tim_cond,
        infill_cond=infill_cond,
        underfill_cond=underfill_cond,
        force_voxel=True,
        use_center_plane_power=True,
    )


class Pin:
    """Represents a pin in the chiplet floorplan, assignable to an edge."""

    def __init__(self, name, parent_name):
        self.name = name
        self.parent_name = parent_name
        self.edge_name = None

    def assign_to_edge(self, edge_name):
        """Assign this pin to a specific edge."""
        self.edge_name = edge_name

    def is_assigned(self):
        """Return True if this pin has been assigned to an edge."""
        return self.edge_name is not None


def draw_fig(boxes, out_dir, out_name, limits):
    """
    Generate a 2-D top-down placement plot of chiplets on the substrate.

    Colors boxes by type: interposer (black), HBM (blue), wafer (green), other (red).
    Saves the figure to out_dir/out_name.png.
    """
    os.makedirs(out_dir, exist_ok=True)
    fig, ax = plt.subplots()
    ax.set_aspect('equal')
    for box in boxes:
        name_l = box.name.lower()
        if name_l.endswith("interposer"):
            color = 'black'
        elif 'hbm' in name_l:
            color = 'blue'
        elif name_l.endswith('wafer'):
            color = 'green'
        else:
            color = 'red'
        ax.add_patch(plt.Rectangle((box.start_x, box.start_y), box.width, box.length, fill=True,color=color))
    plt.xlim(limits[0], limits[1])
    plt.ylim(limits[2],limits[3])
    plt.savefig(out_dir+'/'+out_name+'.png')
    plt.close()

def _box_color_3d(box):
    """
    Choose a display color for a box in the 3-D plot.

    Checks chiplet_parent type first (most reliable), then falls back to
    substring matching on box.name so that names with hierarchy suffixes
    like 'substrate.HBM_l1#0' are still classified correctly.
    Per the Image Generation Gotcha: endswith() checks on the raw name fail
    because of hierarchy prefixes and '#n' / '_lN' suffixes; substring
    checks are used throughout.
    """
    cp = getattr(box, "chiplet_parent", None)
    if cp is not None:
        ct = cp.get_chiplet_type().lower()
        if "interposer" in ct:
            return "dimgray", 0.5
        if "substrate" in ct or "pcb" in ct:
            return "darkgray", 0.4
        if "power_source" in ct:
            return "orange", 0.6
        if "gpu" in ct:
            return "red", 1.0   # fully opaque so GPU is never washed out
        if "hbm" in ct:
            return "royalblue", 0.8
        if "dummy" in ct:
            return "lightgray", 0.4

    name_l = box.name.lower()
    if "interposer" in name_l:
        return "dimgray", 0.5
    if "substrate" in name_l or "pcb" in name_l:
        return "darkgray", 0.4
    if "hbm" in name_l:
        return "royalblue", 0.8
    if "wafer" in name_l:
        return "green", 0.7
    if "_tim" in name_l or name_l.endswith("tim"):
        return "lightyellow", 0.3
    if "bonding" in name_l:
        return "cyan", 0.3
    if "dummy_si" in name_l:
        return "lightgray", 0.4
    return "red", 0.8


def draw_fig_3D_zoom(boxes, out_dir, out_name, limits):
    """
    Generate a 3-D visualization of the full box stackup.

    IC packages are very thin relative to their x,y footprint (mm-scale wide,
    sub-mm tall). A dynamic z_scale factor is computed so the layer stack is
    clearly visible rather than appearing flat.

    Boxes are colored by chiplet type using substring matching (per the Image
    Generation Gotcha: endswith() fails on hierarchical names like
    'substrate.HBM_l1#0').

    Saves to out_dir/out_name3D.png.
    """
    os.makedirs(out_dir, exist_ok=True)

    min_z = min(box.start_z for box in boxes)
    max_z = max(box.end_z for box in boxes)
    z_span = max(max_z - min_z, 1e-3)

    x_min_b = min(box.start_x for box in boxes)
    x_max_b = max(box.end_x for box in boxes)
    y_min_b = min(box.start_y for box in boxes)
    y_max_b = max(box.end_y for box in boxes)
    xy_span = max(x_max_b - x_min_b, y_max_b - y_min_b, 1e-3)

    # Scale z so the layer stack is ~25 % of the x,y extent — otherwise
    # the sub-mm chip stack looks completely flat next to a 30-80 mm footprint.
    z_scale = (xy_span * 0.25) / z_span

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")

    # Render order: background (substrate/interposer/PCB) first, then
    # everything else, and GPU absolutely last so it is never occluded.
    def _sort_key(b):
        cp = getattr(b, "chiplet_parent", None)
        if cp is not None:
            ct = cp.get_chiplet_type().lower()
            if "interposer" in ct or "substrate" in ct or "pcb" in ct:
                return 0
            if "gpu" in ct:
                return 2   # GPU always on top
        name_l = b.name.lower()
        if "gpu" in name_l:
            return 2
        return 1

    sorted_boxes = sorted(boxes, key=_sort_key)

    for box in sorted_boxes:
        color, alpha = _box_color_3d(box)

        bx = box.start_x
        by = box.start_y
        bz = box.start_z * z_scale
        bz_top = (box.start_z + box.height) * z_scale

        x = [bx, bx + box.width, bx + box.width, bx, bx]
        y = [by, by, by + box.length, by + box.length, by]
        z_bot = [bz] * 5
        z_top = [bz_top] * 5

        verts = [
            list(zip(x, y, z_bot)),   # bottom face
            list(zip(x, y, z_top)),   # top face
        ]
        for i in range(4):
            verts.append([
                (x[i],   y[i],   z_bot[i]),
                (x[i+1], y[i+1], z_bot[i+1]),
                (x[i+1], y[i+1], z_top[i+1]),
                (x[i],   y[i],   z_top[i]),
            ])

        poly = Poly3DCollection(verts, facecolors=color, edgecolors="k",
                                linewidths=0.3, alpha=alpha)
        poly.set_sort_zpos(bz)
        ax.add_collection3d(poly)

    z_pad = max(z_span * z_scale * 0.05, 0.05)
    ax.set_xlim(limits[0], limits[1])
    ax.set_ylim(limits[2], limits[3])
    ax.set_zlim(min_z * z_scale - z_pad, max_z * z_scale + z_pad)

    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel(f"Z (mm × {z_scale:.0f}×)")

    # elev=25 shows the layered stack; azim=−60 gives a good oblique view.
    ax.view_init(elev=25, azim=-60)

    # Legend patches
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="dimgray",   label="Interposer/Substrate"),
        Patch(facecolor="red",       label="GPU"),
        Patch(facecolor="royalblue", label="HBM"),
        Patch(facecolor="orange",    label="Power Source"),
        Patch(facecolor="lightgray", label="Dummy Si"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=7)
    ax.set_title(out_name, fontsize=9)

    plt.tight_layout()
    plt.savefig(out_dir + "/" + out_name + "3D.png", dpi=150)
    plt.close()

def determine_draw_lim(boxes):
    """
    Compute axis limits for 2-D/3-D plots from box extents.

    Returns (min_x-5, max_x+5, min_y-5, max_y+5) for plot boundaries.
    """
    min_x = 100000
    max_x = -100000
    min_y = 100000
    max_y = -100000
    for box in boxes:
        if box.start_x < min_x:
            min_x = box.start_x
        if box.start_x + box.width > max_x:
            max_x = box.start_x + box.width
        if box.start_y < min_y:
            min_y = box.start_y
        if box.start_y + box.length > max_y:
            max_y = box.start_y + box.length

    return min_x-5,max_x+5,min_y-5,max_y+5


def recursively_lift_box(chiplet, box_list, height):
    """
    Recursively shift a chiplet and all its children upward by the given height.

    Updates start_z for each box in the chiplet subtree.
    """
    box = chiplet.get_box_representation()
    box.start_z = box.start_z + height
    for child in chiplet.get_child_chiplets():
        recursively_lift_box(child, box_list, height)
    return

def create_power_source_backside(boxes, efficiency=0.9):
    """
    Set backside Power_Source power.

    Project v4 requires Power_Source consumption to be 0 W.
    """
    for box in boxes:
        if box.chiplet_parent.get_chiplet_type() == "Power_Source":
            box.power = POWER_SOURCE_POWER_W
            box.chiplet_parent.set_power(POWER_SOURCE_POWER_W)


def calculate_ratio(bonding, box):
    """
    Compute the volume ratio of bonding material to total bonding layer for a box.

    Uses bonding pitch, offset, diameter, and shape (sphere/cylinder/cuboid) to
    determine how much of the layer is conductive material vs. filler.
    """
    radius = bonding.get_diameter() / 2
    n_min_x = max(math.ceil((radius - bonding.get_offset()) / bonding.get_pitch()), 0)
    n_max_x = math.floor((1000 * box.width - bonding.get_offset() - radius) / bonding.get_pitch())
    n_x = n_max_x - n_min_x + 1
    n_min_y = max(math.ceil((radius - bonding.get_offset()) / bonding.get_pitch()), 0)
    n_max_y = math.floor((1000 * box.length - bonding.get_offset() - radius) / bonding.get_pitch())
    n_y = n_max_y - n_min_y + 1
    if n_x <= 0 or n_y <= 0:
        return 0.00
    else:
        if(bonding.get_shape() == "sphere"):
            unit_volume = 4 * math.pi * (radius ** 3) / 3
        elif(bonding.get_shape() == "cylinder"):
            unit_volume = math.pi * (radius ** 2) * bonding.get_height()
        elif(bonding.get_shape() == "cuboid"):
            unit_volume = bonding.get_cross_section_area() * bonding.get_height()
        else:
            raise Exception("Invalid bonding shape")

        material_volume = unit_volume * n_x * n_y
        ratio = material_volume / (1000 * box.width * 1000 * box.length * bonding.get_height())
        return ratio

def get_real_children_recursive(chiplet_list):
    """
    Recursively collect all real (non-fake) child chiplets from a list.

    Traverses through fake chiplets to find their real descendants.
    """
    real_children = []
    fake_children = []
    for chiplet in chiplet_list:
        child_chiplets = chiplet.get_child_chiplets()
        for child_chiplet in child_chiplets:
            if(child_chiplet.get_fake() == False):
                real_children.append(child_chiplet)
            else:
                fake_children.append(child_chiplet)

    if(fake_children != []):
        real_children.extend(get_real_children_recursive(fake_children))

    return real_children


def create_all_bonding(box_list, name_type_dict, bonding_list):
    """
    Create bonding layer boxes between all adjacent chiplets in the stackup.

    Uses bonding definitions and name_type_dict to determine bonding types.
    Returns list of bonding boxes and updates box_list with lifted positions.
    """
    bonding_box_list = []

    bondings = {b.get_name():b for b in bonding_list}
    bonding_dict = {}
    for key in name_type_dict:
        x, y = key.split("#")
        if x not in bonding_dict:
            bonding_dict[x] = {}
        if y not in bonding_dict[x]:
            bonding_dict[x][y] = bondings[name_type_dict[key]]

    bm = [box for box in box_list if box.start_z == 0.000000]
    for b in bm:
        chiplet_tree_root = b.chiplet_parent
        create_bonding(box_list, chiplet_tree_root, bonding_dict, bonding_box_list)
    
    return bonding_box_list

def create_bonding(box_list, base_chiplet, bonding_dict, bonding_box_list):
    """
    Recursively create bonding boxes between base_chiplet and its children.

    Looks up bonding material and dimensions from bonding_dict, computes
    effective conductivity via calculate_ratio, and lifts child chiplets.
    """
    children_of_base = base_chiplet.get_child_chiplets()
    for chiplet in children_of_base:
        try:
            bonding = bonding_dict[base_chiplet.get_chiplet_type()].get(chiplet.get_chiplet_type())
        except Exception:
            bonding = None

        if bonding is not None:
            material = bonding.get_material()
            height = bonding.get_height()
            height_mm = height / 1000

            height_mm = round(height_mm, 6)
            box = chiplet.get_box_representation()
            x = round(box.start_x, 6)
            y = round(box.start_y, 6)
            z = round(box.start_z, 6)
            dx = round(box.width, 6)
            dy = round(box.length, 6)

            ratio = 100 * calculate_ratio(bonding, box)
            bonding_box = Box(x, y, z, dx, dy, height_mm, 0.0, f"1:{material}:{ratio},Epoxy, Silver filled:{100 - ratio}", 0.0, f"{chiplet.name}_bonding")
            recursively_lift_box(chiplet, box_list, height_mm)
            bonding_box_list.append(bonding_box)

        create_bonding(box_list, chiplet, bonding_dict, bonding_box_list)

def recursively_lift_box(chiplet, box_list, height):
    """
    Recursively shift a chiplet and all its children upward by the given height.

    Duplicate of the function above; both are used in different contexts.
    """
    box = chiplet.get_box_representation()
    box.start_z = box.start_z + height
    for child in chiplet.get_child_chiplets():
        recursively_lift_box(child, box_list, height)
    return


def create_TIM_to_heatsink(box_list, material="TIM0p5", min_TIM_height=0.1, system_type=None):
    """
    Create Thermal Interface Material boxes between top chiplets and heatsink.

    For non-3D_1GPU_top: creates TIM for each top-level chiplet. Always adds
    one TIM box covering the interposer/substrate area. Returns list of TIM boxes.
    """
    TIM_boxes = []
    z_min = max([box.end_z for box in box_list])
    if system_type != "3D_1GPU_top":
        for box in box_list:
            if box.chiplet_parent.get_child_chiplets() == []:
                tim_height = z_min - box.end_z
                if tim_height > 0.0001:
                    tim_box = Box(box.start_x, box.start_y, box.end_z, box.width, box.length, tim_height, 0.0, f"1:{material}", 0.0, f"{box.name}_TIM")
                    TIM_boxes.append(tim_box)

    intp_list = [b for b in box_list if b.chiplet_parent.get_chiplet_type() == "interposer" or b.chiplet_parent.get_chiplet_type() == "substrate"]
    intp = intp_list[0]
    for i in intp_list:
        if(i.end_z > intp.end_z):
            intp = i

    tim_box = Box(intp.start_x, intp.start_y, z_min, intp.width, intp.length, min_TIM_height, 0.0, f"1:{material}", 0.0, f"{intp.name}_TIM")
    TIM_boxes.append(tim_box)
    return TIM_boxes

def calculate_GPU_HBM_HTC(box_list, power_dict, hc):
    """
    Compute per-chiplet-type heat transfer coefficients for GPU vs HBM.

    Returns (GPU_HTC, HBM_HTC) in W/(m^2·K).

    To avoid hidden calibration constants, multi-heatsink mode uses the
    heatsink definition HTC directly unless a future physics model is added.
    """
    try:
        base_hc = float(hc)
    except (TypeError, ValueError):
        base_hc = 0.0
    return base_hc, base_hc

def create_multiple_heat_sinks(
    box_list, heatsink_list, heatsink_name, power_dict, min_TIM_height=0.01
):
    """
    Create separate heatsink objects for each top-level chiplet (GPU, HBM).

    Uses per-type HTC from calculate_GPU_HBM_HTC. Returns heatsink data list
    and updated power_dict with GPU_HTC and HBM_HTC entries.
    """
    # dedeepyo : 7-Feb-2025 : Heatsink object creation.
    heatsinks = [h for h in heatsink_list if h.get_name() == heatsink_name]
    if(heatsinks is None):
        raise Exception("Heatsink not found")
    
    fin_height = heatsinks[0].get_fin_height()
    fin_thickness = heatsinks[0].get_fin_thickness()
    material = heatsinks[0].get_material()
    fin_number = heatsinks[0].get_fin_count()
    hc = heatsinks[0].get_hc()
    fluid_speed = heatsinks[0].get_fluid_speed()
    cooled_by = heatsinks[0].get_cooled_by()
    fin_offset = heatsinks[0].get_fin_offset()
    dz = heatsinks[0].get_base_thickness()
    bind_to_ambient = heatsinks[0].get_bind_to_ambient()

    excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
    box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]
    z_min = max([box.end_z for box in box_list_min])
    z = z_min + min_TIM_height

    if fin_number == 0 and fin_thickness > 0:
        x_min = min(box.start_x for box in box_list_min)
        x_max = max(box.end_x for box in box_list_min)
        fin_number = int((x_max - x_min) / (2 * fin_thickness))

    GPU_HTC = hc
    HBM_HTC = hc
    GPU_HTC, HBM_HTC = calculate_GPU_HBM_HTC(box_list, power_dict, hc)

    HTC_dict = {
        "GPU_HTC": GPU_HTC / 1000,  # Convert to kW/m^2-K
        "HBM_HTC": HBM_HTC / 1000
    }
    power_dict.update(HTC_dict)
    heatsink_data_list = []
    chiplet_HTC = {
        "GPU": GPU_HTC,
        "HBM": HBM_HTC,
    }
    box_list_top = []
    for box in box_list:
        if(box.chiplet_parent.get_child_chiplets() == []):
            box_list_top.append(box)
    for box in box_list_top:
        chiplet_type = box.chiplet_parent.get_chiplet_type()
        if chiplet_type.startswith("GPU"):
            local_hc = chiplet_HTC["GPU"]
        elif chiplet_type.startswith("HBM"):
            local_hc = chiplet_HTC["HBM"]
        else:
            local_hc = None
        if local_hc is not None:
            x = box.start_x
            y = box.start_y
            dx = box.width
            dy = box.length
            heatsink_data = {
                "name": f"HS_top_{box.name}",
                "index": 0,
                "material": material,  # Cu-Foil
                "x": str(round(x, 6)),
                "y": str(round(y, 6)),
                "base_dx": str(round(dx, 6)),
                "base_dy": str(round(dy, 6)),
                "z": str(round(z, 6)),
                "base_dz": str(round(dz, 6)),
                "fin_height": str(fin_height),
                "fin_thickness": str(fin_thickness),
                "fin_count": str(fin_number),
                "fin_axis": "Y",
                "hc": str(local_hc),
                "bound": bind_to_ambient,
                "fluid_speed": str(fluid_speed),
                "cooled_by": str(cooled_by),
            }
            heatsink_data_list.append(heatsink_data)
    
    return heatsink_data_list, power_dict


def create_heat_sink(
    box_list,
    heatsink_list,
    heatsink_name,
    min_TIM_height=0.01,
    scale_factor_x=0,
    scale_factor_y=0,
    area_scale_factor=0,
):
    """
    Create a single heatsink covering the top of the chiplet stack.

    Sizes heatsink from box extents with optional scale factors. Returns
    heatsink data dict with geometry, fin parameters, and HTC.
    """
    heatsinks = [h for h in heatsink_list if h.get_name() == heatsink_name]
    if heatsinks is None:
        raise Exception("Heatsink not found")

    excluded_types = []
    box_list_min = [box for box in box_list if box.chiplet_parent.get_chiplet_type() not in excluded_types]
    x_min = min([box.start_x for box in box_list_min])
    x_max = max([box.end_x for box in box_list_min])
    y_min = min([box.start_y for box in box_list_min])
    y_max = max([box.end_y for box in box_list_min])
        
    if(area_scale_factor != 0):
        dimension_scale_factor = math.sqrt(area_scale_factor)
        dx = dimension_scale_factor * (x_max - x_min)
        dy = dimension_scale_factor * (y_max - y_min)
    elif(scale_factor_x == 0):
        if(scale_factor_y == 0):
            dy = heatsinks[0].get_base_length()
        else:
            dy = scale_factor_y * (y_max- y_min)
        dx = heatsinks[0].get_base_width()
    elif(scale_factor_y == 0):
        dy = heatsinks[0].get_base_length()
        dx = scale_factor_x * (x_max - x_min)
    else:
        dx = scale_factor_x * (x_max - x_min)
        dy = scale_factor_y * (y_max- y_min)

    x = (x_max + x_min - dx) / 2
    y = (y_max + y_min - dy) / 2
    z_min = max([box.end_z for box in box_list_min])
    z = z_min + min_TIM_height

    fin_height = heatsinks[0].get_fin_height()
    fin_thickness = heatsinks[0].get_fin_thickness()
    material = heatsinks[0].get_material()
    fin_number = heatsinks[0].get_fin_count()
    hc = heatsinks[0].get_hc()
    fluid_speed = heatsinks[0].get_fluid_speed()
    cooled_by = heatsinks[0].get_cooled_by()
    fin_offset = heatsinks[0].get_fin_offset()
    dz = heatsinks[0].get_base_thickness()
    bind_to_ambient = heatsinks[0].get_bind_to_ambient()

    if(fin_number == 0):
        if(fin_thickness > 0):
            fin_number = int(dx / (2 * fin_thickness))

    heatsink_data = {
        "name": "HS_top",
        "index": 0,
        "material": material,
        "x": str(round(x, 6)),
        "y": str(round(y, 6)),
        "base_dx": str(round(dx, 6)),
        "base_dy": str(round(dy, 6)),
        "z": str(round(z, 6)),
        "base_dz": str(round(dz, 6)),
        "fin_height": str(fin_height),
        "fin_thickness": str(fin_thickness),
        "fin_count": str(fin_number),
        "fin_axis": "Y",
        "hc": str(hc),
        "bound": bind_to_ambient,
        "fluid_speed": str(fluid_speed),
        "cooled_by": str(cooled_by),
    }
    return heatsink_data


def find_deepest_node(chiplet_tree):
    """
    Find the chiplet at maximum depth in the chiplet tree (DFS).

    Used for 3D_1GPU_top config to place GPU on top of the deepest HBM stack.
    """
    if not chiplet_tree or len(chiplet_tree) == 0:
        return None
    
    root = chiplet_tree[0]
    deepest_node = root
    max_depth = 0
    
    def traverse(node, depth):
        nonlocal deepest_node, max_depth
        if depth > max_depth:
            max_depth = depth
            deepest_node = node
        
        for child in node.get_child_chiplets():
            traverse(child, depth + 1)
    
    traverse(root, 0)
    return deepest_node


@click.command("standalone")
@click.option("--therm_conf", help="The thermal config file")
@click.option("--out_dir", help="The output directory")
@click.option("--heatsink_conf", help="The heatsink config file")
@click.option("--bonding_conf", help="The bonding config file")
@click.option("--heatsink", help="The heatsink name")
@click.option("--project_name", help="The project name")
@click.option('--is_repeat', default = False, help='Is this a repeat run?')
@click.option('--hbm_stack_height', default = 1, help='Number of dies per HBM stack')
@click.option('--system_type', default = "2p5D", help='The system type')
@click.option('--dummy_si', default = False, help='Does 3D have dummy Si?')
@click.option('--tim_cond_list', default = [10.0], multiple = True, help='The TIM conductivity list')
@click.option('--infill_cond_list', default = [1.6], multiple = True, help='The infill conductivity list')
@click.option('--underfill_cond_list', default = [1.6], multiple = True, help='The underfill conductivity list')
def therm(therm_conf, heatsink_conf, bonding_conf, heatsink, out_dir, project_name, simtype = "Anemoi", is_repeat = False, hbm_stack_height = 1, system_type = "2p5D", dummy_si = False, tim_cond_list = (5, 10, 50), infill_cond_list = (1.6, 19), underfill_cond_list = (1.6, 19)):
    """
    Main entry point: parse configs, build box stackup, run thermal simulation.

    Performs chiplet sizing, placement, bonding/TIM/heatsink creation, then
    calls simulator_simulate() and writes results to YAML. Supports 3D and
    2.5D configurations.
    """
    chiplet_tree = parse_all_chiplets(therm_conf)

    # Override GPU power to the course-approved 270 W so it is explicit here
    # (the XML already carries this value, but we set it to make the choice visible).
    def _override_gpu_power(tree):
        for ch in tree:
            if ch.get_chiplet_type() == "GPU":
                ch.set_power(GPU_DEFAULT_POWER_W)
            elif ch.get_chiplet_type() == "Power_Source":
                ch.set_power(POWER_SOURCE_POWER_W)
            _override_gpu_power(ch.get_child_chiplets())
    _override_gpu_power(chiplet_tree)
    (w_top, l_top) = recursive_chiplet_sizing(chiplet_tree[0], None)

    def generate_placements_from_floorplan(floorplan, floorplan_dict, chiplet_tree):
        # if floorplan or floorplan_dict = "", then check if the chiplet_tree has only 1 element.
        # if it does, then assign it to the center of the floorplan.
        # if it has more, then exception
        if floorplan == "" or floorplan_dict == "":
            if len(chiplet_tree) == 1:
                grid = [[chiplet_tree[0]]]
                return grid, []
            else:
                raise ValueError("Chiplet tree has more than 1 element with no floorplan definitions")
            
        # if floorplan and floorplan_dict are not empty, then we need to parse them.
        # first, parse the floorplan
        # example floorplan (in XML):
        # floorplan="
        #     HXH
        #     XDX
        #     HXH"
        # example floorplan dict:
        # floorplan_dict="
        # D:(GPU)*
        # H:(HBM0,HBM1,HBM2,HBM3)
        # "
        # first, parse the floorplan dict
        # I want a python dict that goes D:GPU, H:(HBM0,HBM1,HBM2,HBM3)
        # because GPU has an * after it, I want to remove it and instead consider the GPU a fixed chiplet.
        fixed_chiplets = []
        # print("Before split", floorplan_dict)
        floorplan_dict = floorplan_dict.split(' ')
        # now eliminate all substrings that are empty whitespace
        floorplan_dict = [x for x in floorplan_dict if x != ""]
        # now split by :
        floorplan_dict = [x.split(':') for x in floorplan_dict]
        # print("After split", floorplan_dict)
        # now split by *
        # handle asterisk
        for i in range(len(floorplan_dict)):
            if floorplan_dict[i][1][-1] == '*':
                floorplan_dict[i][1] = floorplan_dict[i][1][:-1]
                fix_name = floorplan_dict[i][1]
                # remove "(" and ")" from fix name
                fix_name = fix_name.split('(')[1]
                fix_name = fix_name.split(')')[0]
                fixed_chiplets.append(fix_name)
        # floorplan_dict = {x[0]:x[1] for x in floorplan_dict}  
        # we want to do the above line while checking that x[1] is a list
        # if its a string or not a list, basically not in parentheses, then we want to error out
        for i in range(len(floorplan_dict)):
            if floorplan_dict[i][1][0] != '(':
                raise ValueError("Floorplan dict must have values in parentheses")
            floorplan_dict[i][1] = floorplan_dict[i][1][1:-1]
            floorplan_dict[i][1] = floorplan_dict[i][1].split(',')
        floorplan_dict = {x[0]:x[1] for x in floorplan_dict}

        # ensure the values in the dict exist in the chiplet tree
        for key in floorplan_dict:
            # if key is a single string
            if len(floorplan_dict[key]) == 1:
                # if floorplan_dict[key][0] not in chiplet_tree:
                #     print("Chiplet tree:",chiplet_tree)
                #     raise ValueError("Chiplet {} not found in chiplet tree".format(floorplan_dict[key][0]))
                found = False
                for chiplet in chiplet_tree:
                    if chiplet.get_chiplet_type() == floorplan_dict[key][0]:
                        found = True
                        break
                if not found:
                    raise ValueError("Chiplet {} not found in chiplet tree".format(floorplan_dict[key][0]))
            else:
                for chiplet in floorplan_dict[key]:
                    # if chiplet not in chiplet_tree:
                    #     raise ValueError("Chiplet {} not found in chiplet tree".format(chiplet))
                    for chiplet_tree_chiplet in chiplet_tree:
                        if chiplet_tree_chiplet.get_chiplet_type() == chiplet:
                            found = True
                            break
                    if not found:
                        raise ValueError("Chiplet {} not found in chiplet tree".format(chiplet))


    
        # now parse the floorplan
        # print("Pre split", floorplan)
        # floorplan = floorplan.split('\n')
        # floorplan = [x.strip() for x in floorplan] # dedeepyo : 27-Feb-25
        # floorplan = [x for x in floorplan if x != ""] # dedeepyo : 27-Feb-25
        # floorplan = [list(x) for x in floorplan] # dedeepyo : 27-Feb-25
        # print("After processing", floorplan)
        # floorplan is now a flat list. We need to ensure it is a square.
        # floorpl_len = len(floorplan) # dedeepyo : 27-Feb-25
        # check that it is a square number
        # like literally. Is it 4,9,16,..
        # if math.sqrt(floorpl_len) != int(math.sqrt(floorpl_len)): # dedeepyo : 27-Feb-25
        #     raise ValueError("Floorplan must be a square") # dedeepyo : 27-Feb-25
        # now format it into a square
        # floorplan = [floorplan[i:i+int(math.sqrt(floorpl_len))] for i in range(0,floorpl_len,int(math.sqrt(floorpl_len)))] # dedeepyo : 27-Feb-25

        # dedeepyo : 27-Feb-25 : Fixing the floorplan parsing. Adding rectangular floorplanning.
        floorplan = floorplan.strip("\n").strip().split(' ')
        floorplan = [x for x in floorplan if x != ""]
        floorplan = [list(x) for x in floorplan]
        r = len(floorplan)
        for i in range(r):
            floorplan[i] = [list(x) for x in floorplan[i]]
        # print("Floorplan:",floorplan)
        # print(len(floorplan),len(floorplan[0]))
        # dedeepyo : 27-Feb-25 #
        # # ensure floorplan is an odd square.
        # if len(floorplan) % 2 == 0 or len(floorplan[0]) % 2 == 0:
        #     raise ValueError("Floorplan must be an odd square")
            

        # create a grid with the same dimensions as the floorplan
        grid = [[None for i in range(len(floorplan[0]))] for j in range(len(floorplan))]
        # now, for each element in the floorplan, assign the corresponding chiplet
        # print floorplan and grid shapes
        # print("Floorplan shape:",len(floorplan),len(floorplan[0]))
        # print("Grid shape:",len(grid),len(grid[0]))
        # print("Floorplan:",floorplan)
        # print("Floorplan dict:",floorplan_dict)
        # print(grid)
        for i in range(len(floorplan)):
            for j in range(len(floorplan[0])):
                if floorplan[i][j][0] == 'X':
                    grid[i][j] = None
                else:
                    # print("Checking",floorplan[i][j][0])
                    # try to find an appropriate assignment within the floorplan dict
                    if floorplan[i][j][0] not in floorplan_dict:
                        raise ValueError("Chiplet {} not found in floorplan dict".format(floorplan[i][j][0]))
                    # else, we need to find the first chiplet in the chiplet tree that matches the floorplan dict
                    chosen_chiplet = None
                    for chiplet in chiplet_tree:
                        # print("Checking",chiplet.get_chiplet_type())
                        # print("In",floorplan_dict[floorplan[i][j][0]])
                        if chiplet.get_chiplet_type() in floorplan_dict[floorplan[i][j][0]] and not chiplet.is_assigned_floorplan():
                            chosen_chiplet = chiplet
                            chiplet.set_assigned_floorplan(True)
                            break

                    if chosen_chiplet is None:
                        raise ValueError("Chiplet defined by {} not found in chiplet tree".format(floorplan[i][j][0]))
                    grid[i][j] = chosen_chiplet

                    # grid[i][j] = floorplan_dict[floorplan[i][j][0]][0]
                    # print("Assigned",grid[i][j])

        return grid, fixed_chiplets

    # dedeepyo : 17-Dec-2024 : Implementing copy of placement recursion.
    def copy_placements_recursive(boxes,parent,chiplet_tree, min_dist = 0.0):
        return
    # dedeepyo : 17-Dec-2024

    # dedeepyo : 28-Jan-2025 : Implementing recursive fake chiplet sizing.
    # Assuming any level has either all fake chiplets or all real chiplets.
    # Assuming the base chiplet is never fake.
    def determine_sizing_recursive(boxes,parent,chiplet_tree, min_dist = 0.0, fake_chiplet_size_dict = {}):
        if len(chiplet_tree) == 0:
            return
        
        if not parent:
            grid = [[chiplet_tree[0]]]
            x_coord = 0
            y_coord = 0
            z_coord = 0
            stackup = chiplet_tree[0].get_stackup()
            material = "Si"
            power = chiplet_tree[0].get_power()
            area = chiplet_tree[0].get_core_area()
            aspect_ratio = chiplet_tree[0].get_aspect_ratio()
            height = chiplet_tree[0].get_height()
            width = math.sqrt(area*aspect_ratio)
            length = area/width
            box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet_tree[0].get_name())
            box.assign_chiplet_parent(chiplet_tree[0])
            boxes.append(box)
            determine_sizing_recursive(boxes,box,chiplet_tree[0].get_child_chiplets(), box.chiplet_parent.assembly_process.get_die_separation(), fake_chiplet_size_dict)
        else:
            grid, fixed_chiplets = generate_placements_from_floorplan(parent.chiplet_parent.floorplan,parent.chiplet_parent.floorplan_dict,chiplet_tree)
            parent_coords = parent.get_2d_coords()
            parent_width = parent.width
            parent_length = parent.length
            num_rows = len(grid)
            num_cols = len(grid[0])
            # Assuming fake chiplets are only iterated over once.
            fake_chiplet_dict = {}
            largest_width = 0
            largest_length = 0
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        chiplet_area = chiplet.get_core_area()
                        chiplet_aspect_ratio = chiplet.get_aspect_ratio()
                        chiplet_width = math.sqrt(chiplet_area*chiplet_aspect_ratio)
                        chiplet_length = chiplet_area/chiplet_width
                        # dedeepyo : 28-Jan-2025 : Implementing fake chiplet addition to dictionary.
                        chiplet.set_assigned_floorplan(False)
                        if((chiplet.get_fake() == True) and (fake_chiplet_dict.get(chiplet.get_chiplet_type()) == None)):
                            fake_chiplet_dict[chiplet.get_chiplet_type()] = 0
                        # dedeepyo : 28-Jan-2025 #
                        if chiplet_width > largest_width:
                            largest_width = chiplet_width
                        if chiplet_length > largest_length:
                            largest_length = chiplet_length

            side_length = largest_length
            side_length += min_dist #
            # side_length += min_dist * (1 + INFLATION)
            side_width = largest_width
            side_width += min_dist #
            # side_width += min_dist * (1 + INFLATION)
            grid_length = side_length*num_rows
            grid_width = side_width*num_cols
            grid_x = parent_coords[0] + parent_width/2 - grid_width/2
            grid_y = parent_coords[1] + parent_length/2 - grid_length/2

            children_boxes = []         
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        if(chiplet.get_fake() == True):
                            if(fake_chiplet_dict[chiplet.get_chiplet_type()] == 1):
                                continue
                        x_coord = grid_x + j*side_length + side_length/2
                        y_coord = grid_y + i*side_length + side_length/2
                        z_coord = parent.start_z + parent.height
                        stackup = chiplet.get_stackup()
                        material = "Si"
                        power = chiplet.get_power()
                        aspect_ratio = chiplet.get_aspect_ratio()
                        height = chiplet.get_height()
                        area = chiplet.get_core_area()
                        width = math.sqrt(area*aspect_ratio)
                        length = area/width
                        
                        x_coord = x_coord - width/2
                        y_coord = y_coord - length/2                        
                        box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet.get_name())
                        box.assign_chiplet_parent(chiplet)
                        chiplet.set_box_representation(box)
                        min_dist_for_children = 0.0
                        if(chiplet.get_fake() == True):
                            min_dist_for_children = parent.chiplet_parent.assembly_process.get_die_separation()
                            fake_chiplet_dict[chiplet.get_chiplet_type()] = 1
                        else:
                            min_dist_for_children = chiplet.assembly_process.get_die_separation()
                            boxes.append(box)                        
                        children_boxes.append(box)
                        determine_sizing_recursive(boxes,box,chiplet.get_child_chiplets(), min_dist_for_children, fake_chiplet_size_dict)

            def move_box(box, x, y):
                box.start_x += x #
                box.start_y += y #
                for chiplet in box.chiplet_parent.get_child_chiplets(): #
                    if chiplet.get_box_representation(): #
                        move_box(chiplet.get_box_representation(), x, y) #

            # parent_center = parent.get_2d_center()
            box_destination_pairs = []
            for box in children_boxes:
                if box.chiplet_parent.get_chiplet_type() in fixed_chiplets:
                    continue
                curr_conn = box.chiplet_parent.connections
                coordinates = box.get_2d_center()
                connection_coords = []
                for conn in curr_conn:
                    conn_type = conn.split(".")[-1].split("#")[0]
                    # conn_type = ''.join([i for i in conn_type if not i.isdigit()])
                    # conn_type = conn_type.split("#")[0]
                    # print("Connection type:", conn_type)
                    if conn_type in fixed_chiplets:
                        for fixed_box in boxes:
                            if fixed_box.name == conn:
                                connection_coords.append(fixed_box.get_2d_center())
                avg_x = 0
                avg_y = 0
                for coord in connection_coords:
                    avg_x += coord[0]
                    avg_y += coord[1]
                if len(connection_coords) == 0:
                    continue
                else:
                    avg_x = avg_x / len(connection_coords)
                    avg_y = avg_y / len(connection_coords)
                box_destination_pairs.append((box,(avg_x,avg_y)))

            # f = open("box_movement_log.txt", "a")
            i = 0
            old_boxes = box_destination_pairs.copy()
            N = 1010
            while (True):
                i += 1
                if i > N:
                    break
                if i % 10 == 0:
                    # TODO: Low priority - early exit check for placement convergence
                    same = True
                    for j in range(len(box_destination_pairs)):
                        new_box = box_destination_pairs[j]
                        old_box = old_boxes[j]
                        def is_equal(box1, box2):
                            bound = min_dist
                            return abs(box1[0] - box2[0]) < bound and abs(box1[1] - box2[1]) < bound

                        if not is_equal(new_box[1], old_box[1]):
                            same = False
                            break
                    if not same:
                        break
                old_boxes = box_destination_pairs.copy()

                for box, coordinates in box_destination_pairs:
                    curr_x, curr_y = box.get_2d_center()
                    dist_x = curr_x - coordinates[0]
                    dist_y = curr_y - coordinates[1]
                    multiplier_x = 1
                    multiplier_y = 1
                    if abs(dist_x) > abs(dist_y):
                        # multiplier_x = 1
                        multiplier_y = abs(dist_y) / abs(dist_x)
                    elif abs(dist_x) < abs(dist_y):
                        multiplier_x = abs(dist_x) / abs(dist_y)
                    #     multiplier_y = 1
                    # else:   
                    #     multiplier_x = 1
                    #     multiplier_y = 1

                    delta_x = -min_dist*multiplier_x if dist_x > 0 else min_dist*multiplier_x
                    delta_y = -min_dist*multiplier_y if dist_y > 0 else min_dist*multiplier_y
                    if abs(dist_x) < min_dist:
                        delta_x = 0
                    if abs(dist_y) < min_dist:
                        delta_y = 0
                    
                    # line = "Moving box " + box.name + " from (" + str(curr_x) + "," + str(curr_y) + ") to (" + str(coordinates[0]) + "," + str(coordinates[1]) + " by dist_x of " + str(dist_x) + "and dist_y of " + str(dist_y) + ") with deltas (" + str(delta_x) + "," + str(delta_y) + ")\n"
                    # f.write(line)
                    # f.close()

                    overlap_count = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    move_box(box,0,delta_y)
                    overlap_count_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlap_count_new > overlap_count:
                        move_box(box,0,-delta_y)
                    
                    # f.write("overlap_count of " + str(box.name) + " is " + str(overlap_count) + "\n")
                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and before x-movement is " + str(overlap_count_new) + "\n")
                    move_box(box,delta_x,0)
                    overlap_count_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlap_count_new > overlap_count:
                        move_box(box,-delta_x,0)
                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and after x-movement is " + str(overlap_count_new) + "\n")

            # f.close()
            if(parent.chiplet_parent.get_fake() == True):
                fakes = [c for c in children_boxes if c.chiplet_parent.get_fake() == True]
                if(len(fakes) == 0):
                    min_x = min([c.start_x for c in children_boxes])
                    max_x = max([c.end_x for c in children_boxes])
                    min_y = min([c.start_y for c in children_boxes])
                    max_y = max([c.end_y for c in children_boxes])
                    # parent.start_x = min_x
                    # parent.start_x -= min_dist * INFLATION
                    # parent.start_y = min_y
                    # parent.start_y -= min_dist * INFLATION
                    parent.width = max_x - min_x
                    parent.length = max_y - min_y
                    parent.width += 2 * min_dist * INFLATION
                    parent.length += 2 * min_dist * INFLATION
                    # for cbox in children_boxes:
                        # print("Child box:", cbox.name, "Width:", cbox.width, "Length:", cbox.length, "Start X:", cbox.start_x, "Start Y:", cbox.start_y, "End X:", cbox.end_x, "End Y:", cbox.end_y)
                elif(len(fakes) == len(children_boxes)):
                    # Assuming all fakes are of same type.
                    c  = fakes[0]
                    parent.width = num_cols * c.width 
                    parent.length = num_rows * c.length
                    parent.width += 2 * min_dist * INFLATION
                    parent.length += 2 * min_dist * INFLATION
                else:
                    # TODO : Handle this case
                    print("#TODO : Handle this case")
                
                parent.chiplet_parent.set_core_area(parent.width * parent.length)
                parent.chiplet_parent.set_aspect_ratio(parent.width / parent.length)
                fake_chiplet_size_dict[parent.chiplet_parent.get_chiplet_type()] = (parent.chiplet_parent.get_core_area(), parent.chiplet_parent.get_aspect_ratio())
    # dedeepyo : 28-Jan-2025 #

    def determine_placements_recursive(boxes,parent,chiplet_tree, min_dist = 0.0):
        # parent argument is a Box() class argument that references the original Chiplet() class.
        # if chiplet_tree is empty, return
        if len(chiplet_tree) == 0:
            return

        # dedeepyo : 18-Nov-2024 : This is the recursive function that will determine the placements of the chiplets.
        # We will start with the root chiplet and then recursively determine the placements of the child chiplets.
        # We will use a grid based approach to determine the placements of the chiplets.
        # The grid will be projected onto the parent chiplet.
        # The grid will have a side length of the largest chiplet in the grid.
        # The grid will be centered on the center of the parent chiplet.
        # The grid will have a minimum distance between chiplets based on the assembly process.
        # We will also handle overlaps by moving the chiplets towards the center of mass of their connections.
        # We will also handle fixed chiplets by not moving them at all.
        # We assume the first (or root) chiplet in the XML chiplet tree is not a fake chiplet.
        # We assume the definition of any referenced xml tag (eg. interposer, GPU, HBM, etc.) is present within the definition of the XML chiplet tree which references it.
        # We assume the XML chiplet tree is a tree and not a graph. This means there are no cycles in the XML chiplet tree.
        # We assume the XML chiplet tree is a valid tree. This means there is only one root chiplet and all other chiplets have exactly one parent.
        # We assume the XML chiplet tree is a valid tree. This means there are no disconnected components in the XML chiplet tree.
        # We assume the XML chiplet tree is a valid tree. This means there are no two chiplets in the chiplet XML tree with the exact same parameters. 
        # If there are duplicate definitions for the same chiplet, they must differ in atleast one parameter.
        # We assume "set" of chiplets has an area.
        # We assume the first chiplet at the base of all the chiplets is not a "set".
        # We assume the fake chiplet has an empty stackup string.
        # dedeepyo : 18-Nov-2024

        # this is only the case for the root chiplet (interposer)
        if not parent:
            # print("Parse start")
            # we are starting. Assume coordinates are 0,0
            # just assign the first chiplet to the center
            # this is interposer or PCB so we don't need to get fancy at all.
            grid = [[chiplet_tree[0]]]
            x_coord = 0
            y_coord = 0
            z_coord = 0
            # we need to make a box
            # we dont know exact material. Do a rough guess based on stackup.
            stackup = chiplet_tree[0].get_stackup()
            # stackup example:
            #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
            # actually just assume Si.
            material = "Si"
            power = chiplet_tree[0].get_power()
            area = chiplet_tree[0].get_core_area()
            aspect_ratio = chiplet_tree[0].get_aspect_ratio()
            height = chiplet_tree[0].get_height()
            width = math.sqrt(area*aspect_ratio)
            length = area/width
            box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet_tree[0].get_name())
            box.assign_chiplet_parent(chiplet_tree[0])
            boxes.append(box)
            determine_placements_recursive(boxes,box,chiplet_tree[0].get_child_chiplets(), box.chiplet_parent.assembly_process.get_die_separation())
        else:
            grid, fixed_chiplets = generate_placements_from_floorplan(parent.chiplet_parent.floorplan,parent.chiplet_parent.floorplan_dict,chiplet_tree)
            parent_coords = parent.get_2d_coords()
            # now, we need to determine the grid based on the parent chiplet
            # the grid is projected onto the parent chiplet
            parent_width = parent.width
            parent_length = parent.length

            # how many rows/columns in grid?
            num_rows = len(grid)
            # num_cols = num_rows
            num_cols = len(grid[0])

            # the grid coordinate box size will be based on the largest chiplet dimensions in the grid
            # we need to find the largest width and largest length separately. The larger one of the two will define side length
            largest_width = 0
            largest_length = 0
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        chiplet_area = chiplet.get_core_area()
                        chiplet_aspect_ratio = chiplet.get_aspect_ratio()
                        chiplet_width = math.sqrt(chiplet_area * chiplet_aspect_ratio)
                        chiplet_length = chiplet_area/chiplet_width
                        if chiplet_width > largest_width:
                            largest_width = chiplet_width
                        if chiplet_length > largest_length:
                            largest_length = chiplet_length

            # now, we need to determine the side length of the grid box
            # we will use the larger of the two
            side_length = largest_length
            # side_length += min_dist * (1 + INFLATION) #
            side_length += min_dist #
            # dedeepyo : 29-Jan-2025 : Sizing length and width of grid separately.
            side_width = largest_width
            side_width += min_dist #
            # side_width += min_dist * (1 + INFLATION)
            # dedeepyo : 29-Jan-2025 #
            # print("Side length:",side_length)
            # now, we need to determine the x and y coordinates of the grid box
            # the grid box will be centered on the parent chiplet
            # the grid box will have a side length of side_length
            grid_length = side_length*num_rows
            grid_width = side_width*num_cols
            # the grid will be centered on the center of the parent chiplet
            grid_x = parent_coords[0] + parent_width/2 - grid_width/2
            grid_y = parent_coords[1] + parent_length/2 - grid_length/2
            # now, we need to assign coordinates to each chiplet in the grid
            # we assign them to the center of the grid subbox
            # print("Parent:",parent.name)
            # print("Grid:",grid)
            children_boxes = []         
            for i in range(num_rows):
                for j in range(num_cols):
                    if grid[i][j] is not None:
                        chiplet = grid[i][j]
                        x_coord = grid_x + j*side_width + side_width/2
                        y_coord = grid_y + i*side_length + side_length/2
                        # parent z + parent height
                        z_coord = parent.start_z + parent.height

                        # we dont know exact material. Do a rough guess based on stackup.
                        stackup = chiplet.get_stackup()
                        # stackup example:
                        #         stackup="1:5nm_active,2:5nm_advanced_metal,2:5nm_intermediate_metal,2:5nm_global_metal"
                        # actually just assume Si.
                        material = "Si"
                        power = chiplet.get_power()
                        aspect_ratio = chiplet.get_aspect_ratio()
                        height = chiplet.get_height()
                        area = chiplet.get_core_area()
                        width = math.sqrt(area*aspect_ratio)
                        length = area/width
                        
                        # we need to adjust the box so that it is centered on the grid point.
                        x_coord = x_coord - width/2
                        y_coord = y_coord - length/2                        
                        box = Box(x_coord,y_coord,z_coord,width,length,height,power,stackup,0,chiplet.get_name())
                        box.assign_chiplet_parent(chiplet)
                        chiplet.set_box_representation(box)

                        # dedeepyo : 18-Nov-2024 : Implementing checker and side calculation for fake chiplet.
                        # If the chiplet is a fake chiplet, we need to remove it from the list of boxes.
                        # We update the min_dist for the current chiplet and pass it for its children sitting on top of it unless the current one is a fake chiplet.
                        min_dist_for_children = 0.0
                        if(chiplet.get_fake() == True):
                            # print("Fake chiplet found: ",chiplet.get_name())
                            min_dist_for_children = parent.chiplet_parent.assembly_process.get_die_separation()
                        else:
                            min_dist_for_children = chiplet.assembly_process.get_die_separation()
                            boxes.append(box)
                        # dedeepyo : 18-Nov-2024
                        # print("Created box: ",box.name)
                        children_boxes.append(box)
                        determine_placements_recursive(boxes,box,chiplet.get_child_chiplets(), min_dist_for_children)

            # dedeepyo : 17-Dec-2024 : Implementing copy of placement recursion.
            # determined_placements = {}
            # if(determined_placements.get(grid[i][j].get_chiplet_type()) == None):
            #     determined_placements[grid[i][j].get_chiplet_type()] = box
            # else:
            #     # print("Copying placements for: ",box.name)
            #     copy_placements_recursive(boxes,box,chiplet.get_child_chiplets(), min_dist_for_children, determined_placements[grid[i][j].get_chiplet_type()])
                # print("Copied placements for: ",box.name)
            # dedeepyo : 17-Dec-2024
                    
            def move_box(box, x, y):
                box.start_x += x #
                box.start_y += y #
                # box.end_x += x
                # box.end_y += y
                for chiplet in box.chiplet_parent.get_child_chiplets(): #
                    if chiplet.get_box_representation(): #
                        move_box(chiplet.get_box_representation(), x, y) #

            # dedeepyo : 17-Dec-2024 : Implementing copying placements.            
            # if(reference_box != None):
            #     del_x = reference_box.start_x - parent.start_x
            #     del_y = reference_box.start_y - parent.start_y
            #     move_box(parent, del_x, del_y)
            #     return
            # dedeepyo : 17-Dec-2024
            
            # shrinking step
            # print("FIX:",fixed_chiplets)
            parent_center = parent.get_2d_center()
            box_destination_pairs = []
            for box in children_boxes:
                # print(box.name,":",box.chiplet_parent.connections)
                if box.chiplet_parent.get_chiplet_type() in fixed_chiplets:
                    continue
                curr_conn = box.chiplet_parent.connections
                coordinates = box.get_2d_center()
                # This list is a list of coordinates of boxes that this current box should move towards.
                connection_coords = []
                for conn in curr_conn:
                    conn_type = conn.split(".")[-1]
                    # conn_type = ''.join([i for i in conn_type if not i.isdigit()])
                    conn_type = conn_type.split("#")[0]
                    if conn_type in fixed_chiplets:
                        for fixed_box in boxes:
                            if fixed_box.name == conn:
                                connection_coords.append(fixed_box.get_2d_center())
                # average out to get the "center of mass"
                # print("Box:",box.name,"Connections:",connection_coords)
                avg_x = 0
                avg_y = 0
                for coord in connection_coords:
                    avg_x += coord[0]
                    avg_y += coord[1]
                if len(connection_coords) == 0:
                    # dedeepyo : 26-Jan-2025 : Implementing movement of fake chiplets towards each other to reduce space wastage till they abut (distance between neighbours is more than minimum die separation).
                    # Spreading out real chiplets away from each other till they do not overlap.
                    # Before computing the dimensions of the parent box of the parent chiplet, we need to move the current chiplets, which may be fake, closer to each other.
                    # Assuming either current chiplets are not fake chiplets or all are fake chiplets and none of the grid[i][j] are None or fixed. Otherwise, we have area wastage.
                    # if(box.chiplet_parent.get_fake() == True):
                    #     avg_x = parent_center[0]
                    #     avg_y = parent_center[1]
                    # dedeepyo : 26-Jan-2025 #
                    # else:
                    #     continue
                    continue
                else:
                    avg_x = avg_x / len(connection_coords)
                    avg_y = avg_y / len(connection_coords)
                box_destination_pairs.append((box,(avg_x,avg_y)))

            # f = open("box_placement_movement_log.txt", "a")
            # now, we need to greedily move the box towards the center of mass while respecting overlaps
            i = 0
            old_boxes = box_destination_pairs.copy()
            N = 1010
            # dedeepyo : 27-Jan-2025 : Assigning a higher number of steps for fake chiplets.
            # Assuming either all chiplets in the current set are fake chiplets or none of them are fake chiplets. Else, wastage of iterations.
            # if(children_boxes[0].chiplet_parent.get_fake() == True):
            #     N = 1500
            # dedeepyo : 27-Jan-2025 #
            while (True):
                i += 1
                # number of steps
                if i > N:
                    break
                # THIS EARLY EXIT STUFF DOES NOT WORK
                if i % 10 == 0:
                    # TODO: Low priority - early exit check for placement convergence
                    same = True
                    for j in range(len(box_destination_pairs)):
                        new_box = box_destination_pairs[j]
                        old_box = old_boxes[j]
                        def is_equal(box1, box2):
                            bound = min_dist
                            return abs(box1[0] - box2[0]) < bound and abs(box1[1] - box2[1]) < bound

                        if not is_equal(new_box[1], old_box[1]):
                            same = False
                            break
                    if not same:
                        # print("early exit")
                        break
                old_boxes = box_destination_pairs.copy()

                for box, coordinates in box_destination_pairs:
                    curr_x, curr_y = box.get_2d_center()
                    dist_x = curr_x - coordinates[0]
                    dist_y = curr_y - coordinates[1]
                    # attempt to greedily reduce dist x and dist y by the min dist
                    # we only want to move the box min_dist at a time
                    # multiplier = 1

                    multiplier_x = 1
                    multiplier_y = 1

                    # dedeepyo : 18-Feb-25 : Implementing a more efficient way to move the boxes, to ensure dist_x / dist_y remains constant.
                    if abs(dist_x) > abs(dist_y):
                    #     multiplier_x = 1
                        multiplier_y = abs(dist_y) / abs(dist_x)
                    elif abs(dist_x) < abs(dist_y):
                        multiplier_x = abs(dist_x) / abs(dist_y)
                    #     multiplier_y = 1
                    # else:   
                    #     multiplier_x = 1
                    #     multiplier_y = 1
                    # dedeepyo : 18-Feb-25 #

                    delta_x = -min_dist*multiplier_x if dist_x > 0 else min_dist*multiplier_x
                    delta_y = -min_dist*multiplier_y if dist_y > 0 else min_dist*multiplier_y
                    if abs(dist_x) < min_dist:
                        delta_x = 0
                    if abs(dist_y) < min_dist:
                        delta_y = 0
                    
                    # dedeepyo : 18-Dec-2024 : Implementing overlap check with only current box.
                    # overlap_count = check_all_overlaps_3d(boxes, box, min_dist*INFLATION)
                    # move_box(box,0,delta_y)
                    # overlap_count_new = check_all_overlaps_3d(boxes, box, min_dist*INFLATION)
                    # if overlap_count_new > overlap_count:
                    #     move_box(box,0,-delta_y)
                    # move_box(box,delta_x,0)
                    # overlap_count_new = check_all_overlaps_3d(boxes, box, min_dist*INFLATION)
                    # if overlap_count_new > overlap_count:
                    #     move_box(box,-delta_x,0)
                    # dedeepyo : 27-Jan-2025 #

                    overlaps = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    move_box(box,0,delta_y)
                    overlaps_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlaps_new > overlaps:
                        move_box(box,0,-delta_y)

                    # f.write("overlap_count of " + str(box.name) + " is " + str(overlaps) + "\n")
                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and before x-movement is " + str(overlaps_new) + "\n")
                    move_box(box,delta_x,0)
                    overlaps_new = check_all_overlaps_3d(children_boxes, box, min_dist*INFLATION)
                    if overlaps_new > overlaps:
                        move_box(box,-delta_x,0)

                    # f.write("overlap_count_new of " + str(box.name) + " after y-movement and before x-movement is " + str(overlaps_new) + "\n")
                    
            # TODO: PROJECT - Dummy Si placement for 3D configs; creates 4 Dummy_Si_above boxes.
            if system_type == "3D_1GPU" or system_type == "3D_waferscale" or system_type == "3D_1GPU_top":
                dummy_Si_height = 0.63 # in mm # 0.62 for 8-high, 0.63 for 16-high.
                min_x = min([c.start_x for c in children_boxes]) - min_dist
                max_x = max([c.end_x for c in children_boxes]) + min_dist
                min_y = min([c.start_y for c in children_boxes]) - min_dist
                max_y = max([c.end_y for c in children_boxes]) + min_dist
                if(parent.start_x < min_x):
                    if(parent.start_y < min_y):
                        if(parent.end_x > max_x):
                            if(parent.end_y > max_y):
                                box = Box(parent.start_x, parent.start_y, parent.end_z, min_x - parent.start_x, parent.length, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_1")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_1", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                                
                                box = Box(max_x, parent.start_y, parent.end_z, parent.end_x - max_x, parent.length, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_2")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_2", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                                
                                box = Box(min_x, parent.start_y, parent.end_z, max_x - min_x, min_y - parent.start_y, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_3")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_3", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                                
                                box = Box(min_x, max_y, parent.end_z, max_x - min_x, parent.end_y - max_y, dummy_Si_height, 0.0, "1:dummySi_HBM", 0, parent.name + ".Dummy_Si_above_4")
                                chiplet = Chiplet(name = parent.name + ".Dummy_Si_above_4", core_area = box.width * box.length, aspect_ratio = box.width / box.length, assembly_process = parent.chiplet_parent.get_assembly_process(), stackup = "1:dummySi_HBM", height = dummy_Si_height)
                                r = parent.chiplet_parent.add_child_chiplet(chiplet)
                                boxes.append(box)
                                box.assign_chiplet_parent(chiplet)
                                chiplet.set_box_representation(box)
                            # TODO: PROJECT - Other Dummy_Si placement cases not handled. 
            # dedeepyo : 10-Oct-25 #

            # f.close()
            # dedeepyo : 26-Jan-2025 : Implementing set sizing based on child chiplet dimensions.
            # Assuming all the minimum possible dimensions of the present set of chiplets are already known / calculated.
            # if(parent.chiplet_parent.get_fake() == True):
            #     min_x = min([c.start_x for c in children_boxes])
            #     max_x = max([c.end_x for c in children_boxes])
            #     min_y = min([c.start_y for c in children_boxes])
            #     max_y = max([c.end_y for c in children_boxes])
            #     parent.start_x = min_x
            #     parent.start_y = min_y
            #     parent.width = max_x - min_x
            #     parent.length = max_y - min_y
            #     parent.chiplet_parent.set_core_area(parent.width * parent.length)
            #     parent.chiplet_parent.set_aspect_ratio(parent.width / parent.length)
            # dedeepyo : 26-Jan-2025

    # dedeepyo : 28-Jan-2025 : Assigning recursive fake chiplet sizing.
    fake_chiplet_size_dict = {}
    sizing_start_time = time.time()
    print("Starting sizing at ", sizing_start_time)
    boxes_unique = []
    determine_sizing_recursive(boxes_unique, None, chiplet_tree, 0.0, fake_chiplet_size_dict)
    sizing_end_time = time.time()
    sizing_runtime_s = sizing_end_time - sizing_start_time
    print("Sizing done at ", sizing_end_time)
    print("Sizing runtime (s): ", sizing_runtime_s)
    # time.sleep(5)
    # dedeepyo : 29-Jan-2025
    # print(fake_chiplet_size_dict)
    # fake_chiplet_size_dict = {
    #     'set_primary' : (1420.092338, 0.4578712122),
    #     'set_secondary' : (5680.369353, 0.4578712122)
    # }
    # for box in boxes_unique:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y))
    # return #TODO: Comment out later.
    # dedeepyo : 29-Jan-2025 : Sizing fake chiplets.
    recursively_copy_chiplet_sizes(fake_chiplet_size_dict, chiplet_tree[0])
    # dedeepyo : 29-Jan-2025 #

    placement_start_time = time.time()
    print("Starting placement at ", placement_start_time)
    boxes = []
    determine_placements_recursive(boxes, None, chiplet_tree, 0.0)
    placement_end_time = time.time()
    placement_runtime_s = placement_end_time - placement_start_time
    print("Placement done at ", placement_end_time)
    print("Placement runtime (s): ", placement_runtime_s)
    runtime_excluding_simulation_s = sizing_runtime_s + placement_runtime_s
    print("Total runtime (pre-simulation): ", runtime_excluding_simulation_s)

    # dedeepyo : 18-Nov-2024 : Implementing checker for fake chiplet.
    # If the chiplet is a fake chiplet, we need to remove it from the list of boxes.
    # We create and delete a box for the chiplet that is actually a fake chiplet.
    # temp_box_names = [b.name for b in boxes if b.chiplet_parent.get_fake() == True]
    # for box_name in temp_box_names:
    #     for box in boxes:
    #         if box.name == box_name:
    #             if(box.chiplet_parent.get_fake() == True):
    #                 boxes.remove(box)
                    # print("Removed fake chiplet box: ", box.name + " for chiplet: " + box.chiplet_parent.get_name())
    # for box in boxes:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y) + " " + str(box.end_x) + " " + str(box.end_y))
    # dedeepyo : 18-Nov-2024

    # dedeepyo : 29-Jan-2025 : Testing dimensions.
    # print(min([c.start_x for c in boxes if c.name != "interposer" or c.name != "Power_Source"]),max([c.end_x for c in boxes if c.name != "interposer" or c.name != "Power_Source"]))
    # print(min([c.start_y for c in boxes if c.name != "interposer" or c.name != "Power_Source"]),max([c.end_y for c in boxes if c.name != "interposer" or c.name != "Power_Source"]))
    # dedeepyo : 29-Jan-2025 #

    # now, draw everything
    limits = determine_draw_lim(boxes)
    run_name = project_name if project_name else "post"
    draw_fig(boxes, out_dir, run_name, limits)
    draw_fig_3D_zoom(boxes, out_dir, run_name, limits)
    print("Placement finished, plots generated")
    # print(str(boxes))
    # return #TODO: Comment out later.

    # for box in boxes:
    #     if(box.chiplet_parent.get_chiplet_type() == "GPU" or box.chiplet_parent.get_chiplet_type() == "HBM_l1"):
    #         print("Created : ", box.name + " at (" + str(box.start_x) + "," + str(box.start_y) + "," + str(box.start_z) + ") with width " + str(box.width) + " and length " + str(box.length) + " and height " + str(box.height))

    # return #TODO: Comment out later.

    # TODO: PROJECT - Layer definitions path; contains material conductivities for thermal solver.
    layers = parse_Layer_netlist("configs/layer_definitions.xml")
    heatsink_list = heatsink_definition_list_from_file(heatsink_conf)
    bonding_list = bonding_definition_list_from_file(bonding_conf)
    heatsink_name = heatsink
    # TODO: PROJECT - Bonding type mapping for chiplet pairs; used in create_all_bonding.
    bonding_name_type_dict = {
        "GPU#HBM_l4": "bonding_Cu_pillar", "HBM_l4#GPU": "bonding_Cu_pillar",
        "GPU#HBM_l12": "bonding_Cu_pillar", "HBM_l12#GPU": "bonding_Cu_pillar",
        "GPU#HBM_l16": "bonding_Cu_pillar", "HBM_l16#GPU": "bonding_Cu_pillar",
        "GPU#HBM_l8": "bonding_Cu_pillar", "HBM_l8#GPU": "bonding_Cu_pillar",
        "GPU#HBM": "bonding_Cu_pillar", "HBM#GPU": "bonding_Cu_pillar",
        "GPU#interposer": "bonding_Cu_pillar", "interposer#GPU": "bonding_Cu_pillar",
        "interposer#HBM": "bonding_Cu_pillar", "HBM#interposer": "bonding_Cu_pillar",
        "interposer#PCB": "bonding_bga_ball", "PCB#interposer": "bonding_bga_ball",
        "interposer#substrate": "bonding_bga_ball", "substrate#interposer": "bonding_bga_ball",
        "substrate#Power_Source": "bonding_bga_ball", "Power_Source#substrate": "bonding_bga_ball",
        "interposer#Power_Source": "bonding_bga_ball", "Power_Source#interposer": "bonding_bga_ball",
        "GPU#substrate": "bonding_Cu_pillar", "substrate#GPU": "bonding_Cu_pillar",
        "substrate#HBM": "bonding_Cu_pillar", "HBM#substrate": "bonding_Cu_pillar",
        "GPU#PCB": "bonding_Cu_pillar", "PCB#GPU": "bonding_Cu_pillar",
        "PCB#HBM": "bonding_Cu_pillar", "HBM#PCB": "bonding_Cu_pillar",
        "PCB#Power_Source": "bonding_bga_ball", "Power_Source#PCB": "bonding_bga_ball",
    }
    # bonding_name = bonding_name_type_dict
    recursively_remove_fake_chiplets(chiplet_tree[0])
    # recursively_find_fakes(chiplet_tree[0])
    is_repeat = is_repeat # False
    min_TIM_height = 0.1 # 0.02 # 0.1 # 0.01, 0.02, 0.05, 0.1
    suffix = ""
    
    # print(str(boxes))
    # print("After creating bonding, TIM and heatsink:")
    # for box in boxes:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y) + " " + str(box.end_x) + " " + str(box.end_y))

    # dedeepyo : 01-Dec-25 : Implementing GPU on top.
    # Box(x_coord,y_coord,z_coord,width,length,height,power,"1:5nm_GPU_active_3D,20:5nm_GPU_metal",0,"Power_Source.substrate.HBM.GPU")
    # dedeepyo : 03-Dec-25 : Implementing GPU on top.
    if(system_type == "3D_1GPU_top"):
        # <chip name="GPU"
            # bb_area="$core_area"
            # bb_cost=""
            # bb_quality=""
            # bb_power=""
            # aspect_ratio="0.787"
            # x_location=""
            # y_location=""
        
            # core_area="0.0"
            # fraction_memory="0.0"
            # fraction_logic="1.0"
            # fraction_analog="0.0"
            # gate_flop_ratio="1.0"
            # reticle_share="1.0"
            # buried="False"
            # assembly_process="silicon_individual_bonding"
            # test_process="KGD_free_test"
            # stackup="1:5nm_GPU_active_3D,20:5nm_GPU_metal"
            # wafer_process="process_1"
            # v_rail="5,1.8"
            # reg_eff="1.0,0.9"
            # reg_type="none,side"
            # core_voltage="1.0"
            # power="$core_power"
            # quantity="1000000"
            # fake="False"

            # floorplan=""
            # floorplan_dict=""></chip>
        deepest_node = find_deepest_node(chiplet_tree)
        deepest_node_box = deepest_node.get_box_representation()
        z_coord = deepest_node_box.start_z + deepest_node_box.height

        GPU_stackup = "1:5nm_GPU_active_3D,20:5nm_GPU_metal"
        height = 0
        stackup_list = GPU_stackup.split(",")
        for stackup in stackup_list:
            layer_num, layer_name = stackup.split(":")
            for layer in layers:
                if layer.get_name() == layer_name:
                    height += (int(layer_num) * layer.get_thickness())

        height = round(height, 3) #CHECK: 3 decimal places. 
        
        # GPU power: 270 W (GPU_DEFAULT_POWER_W) — NOT 400 W from lab PDF.
        # Piazza: "Please use the 270 W values as in therm.py for now."
        GPU_chiplet = Chiplet(name=deepest_node.get_name() + ".GPU", core_area=826.2, aspect_ratio= 0.787, fraction_memory=0.0, fraction_logic=1.0, fraction_analog=0.0, assembly_process="silicon_individual_bonding", stackup=stackup, power=GPU_DEFAULT_POWER_W, floorplan="", floorplan_dict="", fake=False, height=height)
        width = math.sqrt(GPU_chiplet.get_core_area() * GPU_chiplet.get_aspect_ratio())
        length = GPU_chiplet.get_core_area() / width
        # Center the GPU die over the HBM array it sits on top of.
        # The original code used (0,0) which placed the GPU at the origin
        # regardless of where the HBM stacks are, making it invisible in plots.
        _hbm_boxes = [b for b in boxes if "hbm" in b.name.lower()]
        if _hbm_boxes:
            _hx = min(b.start_x for b in _hbm_boxes)
            _hx2 = max(b.end_x for b in _hbm_boxes)
            _hy = min(b.start_y for b in _hbm_boxes)
            _hy2 = max(b.end_y for b in _hbm_boxes)
            _gpu_x = (_hx + _hx2) / 2 - width / 2
            _gpu_y = (_hy + _hy2) / 2 - length / 2
        else:
            _gpu_x, _gpu_y = 0.0, 0.0
        GPU_box = Box(_gpu_x, _gpu_y, z_coord, width, length, GPU_chiplet.get_height(), GPU_chiplet.get_power(), GPU_chiplet.get_stackup(), 0, GPU_chiplet.get_name())
        GPU_box.assign_chiplet_parent(GPU_chiplet)
        GPU_chiplet.set_box_representation(GPU_box)
        boxes.append(GPU_box)  # TODO: PROJECT - GPU box added for 3D_1GPU_top config

        deepest_node.add_child_chiplet(GPU_chiplet)
    # dedeepyo : 01-Dec-25 #

    bonding_box_list = create_all_bonding(box_list = boxes, name_type_dict = bonding_name_type_dict, bonding_list = bonding_list) #        
    TIM_boxes = create_TIM_to_heatsink(box_list = boxes, material = "TIM0p5", min_TIM_height = min_TIM_height, system_type = system_type)
    heatsink_obj = create_heat_sink(box_list = boxes, heatsink_list = heatsink_list, heatsink_name = heatsink_name, min_TIM_height = min_TIM_height, scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = 1)
    # Project v4: keep Power_Source at 0 W.
    create_power_source_backside(boxes)
    power_dict = initialize_power_dict_values(boxes)

    # print("After creating bonding, TIM and heatsink:")
    # for box in boxes:
    #     print(box.name + " " + str(box.start_z) + " " + str(box.end_z) + " " + str(box.height) + " " + str(box.width) + " " + str(box.length) + " " + str(box.start_x) + " " + str(box.start_y) + " " + str(box.end_x) + " " + str(box.end_y))
    
    # print(str(boxes))    
    # return #TODO: Comment out later.

    # dedeepyo : 21-Jun-25 : Implmenting multiple heatsinks. 
    # heatsink_list till now stored definitions of heatsinks. From now on, it will store the actual heatsink objects used with coordinates.
    multiple_heatsinks = False # True if multiple heatsinks are used, False if only one heatsink is used.
    if not multiple_heatsinks:
        heatsink_list = []
    else:
        heatsink_list_new, power_dict_new = create_multiple_heat_sinks(box_list = boxes, heatsink_list = heatsink_list, heatsink_name = heatsink_name, min_TIM_height = min_TIM_height, power_dict = power_dict) # , scale_factor_x = 0, scale_factor_y = 0, area_scale_factor = 1)
        heatsink_list = heatsink_list_new
        power_dict = power_dict_new
    # dedeepyo : 21-Jun-25

    # dedeepyo : 01-Dec-25 #
    # Below is only Anemoi, above is tool-agnostic.
    # dedeepyo : 01-Dec-25 #
    data = {
                'boxes' : boxes,
                'heatsink_list' : heatsink_list,
                'heatsink_name' : heatsink_name,
                'bonding_box_list' : bonding_box_list,
                'heatsink_obj' : heatsink_obj,
                'TIM_boxes' : TIM_boxes,
                'suffix' : suffix,
                'is_repeat' : is_repeat,
                'min_TIM_height' : min_TIM_height,
                'layers' : layers
    }
    with open('data_dray1_051425.pkl', 'wb') as f:
        pickle.dump(data, f)

    # return
    # GPU_peak_temperature_list = []
    # HBM_peak_temperature_list = []
    GPU_time_frac_idle_list = []
    GPU_min_peak_temperature_list = []
    HBM_min_peak_temperature_list = []
    
    # box_temperatures = {box.name : [] for box in boxes}
    # print(box_temperatures)
    # results = simulator.simulate(boxes, bonding_box_list, TIM_boxes, heatsink_obj = heatsink_obj, heatsink_list = heatsink_list, heatsink_name = heatsink_name, bonding_list = bonding_list, bonding_name_type_dict = bonding_name_type_dict, is_repeat = is_repeat,  min_TIM_height = min_TIM_height, layers = layers) #
    anemoi_parameter_ID = {} # Uncomment
    # anemoi_parameter_ID = {'interposer_power': 1949, 'substrate_power': 1950, 'PCB_power': 1951, 'GPU_power': 1946, 'Power_Source_power': 1952, 'HBM_power': 1947, 'GPU_HTC_power': 1953, 'HBM_l_power': 1948, 'HBM_HTC_power': 1954}
    # print("Power dict initialized: ", power_dict)

    if not is_repeat:
        simulation_start_time = time.time()
        print("Starting simulation at ", simulation_start_time)

        # TODO: PROJECT - simulator_simulate() is called here; implement thermal solver above.
        results = simulator_simulate(
            boxes,
            bonding_box_list,
            TIM_boxes,
            heatsink_obj=heatsink_obj,
            heatsink_list=heatsink_list,
            heatsink_name=heatsink_name,
            bonding_list=bonding_list,
            bonding_name_type_dict=bonding_name_type_dict,
            is_repeat=is_repeat,
            min_TIM_height=min_TIM_height,
            power_dict=power_dict,
            anemoi_parameter_ID=anemoi_parameter_ID,
            layers=layers,
            tim_cond=float(tim_cond_list[0]) if tim_cond_list else None,
            infill_cond=float(infill_cond_list[0]) if infill_cond_list else None,
            underfill_cond=float(underfill_cond_list[0]) if underfill_cond_list else None,
        )
        
        simulation_end_time = time.time()
        simulation_runtime_s = simulation_end_time - simulation_start_time
        print("Simulation finished at ", simulation_end_time)
        print(f"PySpice solve time: {simulation_runtime_s:.3f} seconds")
        print(f"Total runtime: {runtime_excluding_simulation_s:.3f} seconds")

        print("Results written to txt and yaml — see out_dir for details.")

        os.makedirs(out_dir, exist_ok=True)
        yaml_output_path = os.path.join(out_dir, run_name + "_results.yaml")
        txt_output_path = os.path.join(out_dir, run_name + "_results.txt")

        # Serialize results as plain lists so graders can parse with yaml.safe_load
        serializable_results = {
            name: [float(v) for v in values]
            for name, values in results.items()
        }
        with open(yaml_output_path, 'w') as f:
            yaml.safe_dump(serializable_results, f, default_flow_style=False)
        print(f"Results written to {yaml_output_path}")

        # Mirror the per-box dictionary in plain-text form for quick grading checks.
        with open(txt_output_path, "w") as f:
            f.write(
                "# tuple format: "
                "(peak_temperature_C, average_temperature_C, "
                "thermal_resistance_x, thermal_resistance_y, thermal_resistance_z)\n"
            )
            f.write("results = {\n")
            for name in sorted(serializable_results):
                peak, avg, r_x, r_y, r_z = serializable_results[name]
                f.write(
                    f'    "{name}": '
                    f"({peak:.6f}, {avg:.6f}, {r_x:.6f}, {r_y:.6f}, {r_z:.6f}),\n"
                )
            f.write("}\n")
        print(f"Results written to {txt_output_path}")

        return

def get_GPU_count(boxes):
    """Count the number of GPU chiplets in the box list."""
    GPU_count = 0
    for box in boxes:
        if box.chiplet_parent.get_chiplet_type() == "GPU":
            GPU_count += 1
    return GPU_count

def GPU_throttling(GPU_power=275, GPU_time_frac_idle=0.2, GPU_idle_power=47):
    """
    Compute time-averaged GPU power accounting for idle fraction.

    Returns weighted average of active and idle power.
    """
    GPU_power_throttled = (
        GPU_power * (1 - GPU_time_frac_idle) + GPU_idle_power * GPU_time_frac_idle
    )
    return GPU_power_throttled

def HBM_throttled_performance(bandwidth, latency, HBM_peak_temperature=74):
    """
    Apply temperature-based throttling to HBM bandwidth and latency.

    Above 74C, bandwidth scales down; above 75C/85C, latency increases.
    """
    if HBM_peak_temperature > 74:
        bandwidth *= (2.82 - 0.018 * HBM_peak_temperature)
    if HBM_peak_temperature > 85:
        latency *= 1.714
    elif 75 < HBM_peak_temperature <= 85:
        latency *= 1.238
    
    return bandwidth, latency

def HBM_throttled_power(
    bandwidth_throttled, HBM_power, bandwidth_reference=1986, HBM_peak_temperature=74
):
    """
    Compute HBM power with temperature-dependent refresh and bandwidth scaling.

    Refresh energy scales with temperature; non-refresh scales with bandwidth.
    """
    refresh_energy = 0.12 * HBM_power
    non_refresh_energy = HBM_power - refresh_energy
    if(bandwidth_throttled < bandwidth_reference):
        non_refresh_energy *= (bandwidth_throttled / bandwidth_reference)
    if(HBM_peak_temperature > 85):
        refresh_energy *= 4.004
    elif(HBM_peak_temperature > 75 and HBM_peak_temperature <= 85):
        refresh_energy *= 2.0
    return refresh_energy + non_refresh_energy
    
def update_power_source_backside(boxes, power_dict, efficiency=0.9):
    """
    Update chiplet powers from power_dict and keep Power_Source at 0 W (v4).
    """
    for box in boxes:
        if(box.chiplet_parent.get_chiplet_type() != "Power_Source"):
            if(box.chiplet_parent.get_chiplet_type()[0:5] == "HBM_l"):
                box.power = power_dict["HBM_l"]
            elif(box.chiplet_parent.get_chiplet_type() == "HBM"):
                box.power = power_dict["HBM"]
            elif(box.chiplet_parent.get_chiplet_type() == "GPU"):
                box.power = power_dict["GPU"]
            elif(box.power > 0.00):
                print(f"Chiplet type: {box.chiplet_parent.get_chiplet_type()} has power {box.power}W\n")
        else:
            box.power = POWER_SOURCE_POWER_W
            box.chiplet_parent.set_power(POWER_SOURCE_POWER_W)
    return POWER_SOURCE_POWER_W

def initialize_power_dict_values(boxes):
    """
    Build power_dict mapping chiplet types (GPU, HBM, HBM_l) to power values.

    Project v4 sets Power_Source power to 0 W, so it is intentionally omitted.
    """
    power_dict = {}
    for box in boxes: # Assuming all boxes of a particular type have same power.
        if(box.chiplet_parent.get_chiplet_type() == "GPU"):
            power_dict["GPU"] = box.power
        elif(box.chiplet_parent.get_chiplet_type() == "HBM"):
            power_dict["HBM"] = box.power
        elif(box.chiplet_parent.get_chiplet_type()[0:5] == "HBM_l"):
            power_dict["HBM_l"] = box.power
    return power_dict

def read_data(filename):
    """Read a file of space-separated 4-column numeric data into a numpy array."""
    data = []
    with open(filename, 'r') as f:
        for line in f:
            if line.strip():
                parts = line.strip().split()
                if len(parts) == 4:
                    data.append([float(x) for x in parts])
    return np.array(data)

def interpolate_and_report(
    data,
    col2_values,
    file_handle,
    system_name,
    HTC,
    TIM_conductivity,
    infill_conductivity,
    underfill_conductivity,
    HBM_stack_height,
    dummy_Si,
):
    """
    Fit linear regression for GPU/HBM peak temps vs. col2, write slopes/intercepts to CSV.

    Used for calibration data generation.
    """
    slope_intercept_dict = {}
    for val in col2_values:
        slope_intercept_dict[val] = {'peak_GPU_temp': (0.0, 0.0), 'peak_HBM_temp': (0.0, 0.0)}
        mask = np.isclose(data[:,1], val)
        subset = data[mask]
        if subset.shape[0] < 2:
            continue  # Need at least 2 points for regression
        x = subset[:,0].reshape(-1, 1)
        for col_idx, col_name in zip([2,3], ['peak_GPU_temp', 'peak_HBM_temp']):
            y = subset[:,col_idx]
            model = LinearRegression()
            model.fit(x, y)
            y_pred = model.predict(x)
            r2 = r2_score(y, y_pred)
            slope_intercept_dict[val][col_name] = (f"{model.coef_[0]:.3f}", f"{model.intercept_:.2f}")

    for key1 in slope_intercept_dict:
        file_handle.write(f"{system_name},{key1},{HTC},{TIM_conductivity},{infill_conductivity},{underfill_conductivity},{HBM_stack_height},{dummy_Si},{slope_intercept_dict[key1]['peak_GPU_temp'][0]},{slope_intercept_dict[key1]['peak_GPU_temp'][1]},{slope_intercept_dict[key1]['peak_HBM_temp'][0]},{slope_intercept_dict[key1]['peak_HBM_temp'][1]}\n")


def write_calibration_to_csv(
    system_name,
    HBM_power,
    HTC,
    TIM_cond,
    infill_cond,
    underfill_cond,
    HBM_stack_height,
    dummy_Si,
    calibrate_GPU_slope,
    calibrate_GPU_intercept,
    calibrate_HBM_slope,
    calibrate_HBM_intercept,
    csv_file_path="calibration_data.csv"
):
    """
    Write calibration data to CSV file.
    
    Args:
        system_name: Name of the system (e.g., "2p5D_1GPU")
        HBM_power: HBM power in Watts
        HTC: Heat Transfer Coefficient in W/(m^2*K)
        TIM_cond: TIM conductivity in W/(m*K)
        infill_cond: Infill conductivity in W/(m*K)
        underfill_cond: Underfill conductivity in W/(m*K)
        HBM_stack_height: HBM stack height (number of dies)
        dummy_Si: Boolean indicating if dummy Si is present
        calibrate_GPU_slope: GPU calibration slope
        calibrate_GPU_intercept: GPU calibration intercept
        calibrate_HBM_slope: HBM calibration slope
        calibrate_HBM_intercept: HBM calibration intercept
        csv_file_path: Path to the CSV file (default: "calibration_data.csv")
    """
    # Ensure dummy_Si is a boolean and convert to string for CSV
    dummy_Si_str = str(bool(dummy_Si))
    
    # Prepare the row data
    row_data = [
        system_name,
        str(HBM_power),
        str(HTC),
        str(TIM_cond),
        str(infill_cond),
        str(underfill_cond),
        str(HBM_stack_height),
        dummy_Si_str,
        str(calibrate_GPU_slope),
        str(calibrate_GPU_intercept),
        str(calibrate_HBM_slope),
        str(calibrate_HBM_intercept)
    ]
    
    # Check if file exists to determine if we need to write header
    file_exists = os.path.exists(csv_file_path)
    
    # Open file in append mode
    with open(csv_file_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header if file doesn't exist
        if not file_exists:
            header = [
                "system_name",
                "HBM_power(W)",
                "HTC(W/(m2K))",
                "TIM_conductivity(W/(mK))",
                "infill_conductivity(W/(mK))",
                "underfill_conductivity(W/(mK))",
                "HBM_stack_height",
                "dummy_Si",
                "calibrate_GPU_slope",
                "calibrate_GPU_intercept",
                "calibrate_HBM_slope",
                "calibrate_HBM_intercept"
            ]
            writer.writerow(header)
        
        # Write the data row
        writer.writerow(row_data)

def parse_calibration_block(
    block: str,
) -> Tuple[str, List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    Extract condition line and calibration tuples for GPU and HBM from a text block.

    Parses calibrate_GPU and calibrate_HBM entries with setpoint and (slope, intercept).
    """
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Empty calibration block encountered")

    condition_with_suffix = lines[0]
    colon_index = condition_with_suffix.find(":")
    if colon_index == -1:
        raise ValueError(f"Condition line missing ':' separator: {condition_with_suffix!r}")
    condition_line = condition_with_suffix[: colon_index + 1]

    gpu_entries: List[Tuple[str, str]] = []
    hbm_entries: List[Tuple[str, str]] = []
    entry_pattern = re.compile(r"calibrate_(GPU|HBM) :: ([^:]+) : \(([^)]+)\)")

    for line in lines[1:]:
        match = entry_pattern.search(line)
        if not match:
            continue
        target, setpoint, values = match.groups()
        if target.upper() == "GPU":
            gpu_entries.append((setpoint.strip(), values.strip()))
        else:
            hbm_entries.append((setpoint.strip(), values.strip()))

    if not gpu_entries and not hbm_entries:
        raise ValueError(f"No calibration entries found for block starting: {condition_line}")

    return condition_line, gpu_entries, hbm_entries

def format_condition_block(
    condition: str, entries: List[Tuple[str, str]]
) -> List[str]:
    """
    Render a calibration condition block as Python dict assignment lines.

    Produces temperature_dict entries for GPU or HBM calibration.
    """
    if not entries:
        return []

    output = [condition, '    temperature_dict["3D_1GPU"] = {']
    for index, (setpoint, values) in enumerate(entries):
        trailing = "," if index < len(entries) - 1 else ""
        output.append(f"        {setpoint} : ({values}){trailing}")
    output.append("    }")
    output.append("")
    return output

def convert(source: Path, destination: Path, hbm_stack_height=1) -> None:
    """
    Convert calibration text blocks from source file to Python format in destination.

    Parses calibrate_GPU and calibrate_HBM blocks and writes formatted output.
    """
    raw_text = source.read_text()
    blocks = [block.strip() for block in raw_text.split("\n\n") if block.strip()]

    gpu_sections: List[List[str]] = []
    hbm_sections: List[List[str]] = []

    for block in blocks:
        condition, gpu_entries, hbm_entries = parse_calibration_block(block)
        gpu_block = format_condition_block(condition, gpu_entries)
        if gpu_block:
            gpu_sections.append(gpu_block)
        hbm_block = format_condition_block(condition, hbm_entries)
        if hbm_block:
            hbm_sections.append(hbm_block)

    output_lines: List[str] = []
    output_lines.append("hbm_stack_height = {}".format(hbm_stack_height))

    if gpu_sections:
        output_lines.append("calibrate_GPU")
        for block in gpu_sections:
            output_lines.extend(block)

    if hbm_sections:
        if output_lines and output_lines[-1] != "":
            output_lines.append("")
        output_lines.append("calibrate_HBM")
        for block in hbm_sections:
            output_lines.extend(block)

    while output_lines and output_lines[-1] == "":
        output_lines.pop()

    destination.write_text("\n".join(output_lines) + "\n")

if __name__ == "__main__":
    therm()
