# Anemoi Simulator Reference

Extracted from the legacy `thermal_simulators/anemoi_sim.py` before removal.
This file preserves all data, algorithms, and domain knowledge that may be
useful when implementing `simulator_simulate()`.

---

## Material Thermal Conductivities (W/(m·K))

These are the conductivity values used by the Anemoi cloud solver. They map
directly to the material names found in `layer_definitions.xml` and the box
stackup strings.

```python
conductivity_values = {
    "Air": 0.025,
    "FR-4": 0.1,
    "Cu-Foil": 400,
    "Si": 105,
    "Aluminium": 205,
    "TIM001": 100,
    "Glass": 1.36,
    "TIM": 100,
    "SnPb 67/37": 36,
    "Epoxy, Silver filled": 1.6,
    "SiO2": 1.1,
    "AlN": 237,
    "EpAg": 1.6,           # same as "Epoxy, Silver filled"; used in layer_definitions.xml for 5nm_HBM2HBM_metal
    "Infill_material": 19,
    "Polymer1": 675,
    "TIM0p5": 1.0,          # TIM between top chiplets and heatsink
}
```

---

## Default Power Values (in milliwatts)

```python
power_values = {
    "GPU":          270_000.0,   # 270 W (config default; project PDF says 400 W)
    "HBM":            2_400.0,   # 2.4 W per HBM layer
    "HBM_l":          1_200.0,   # 1.2 W per HBM sub-layer
    "interposer":         0.0,
    "substrate":          0.0,
    "PCB":                0.0,
    "Power_Source":       0.0,
    "GPU_HTC":       10_000.0,   # HTC value in W/(m²·K), not actual power
    "HBM_HTC":       10_000.0,   # HTC value in W/(m²·K), not actual power
}
```

> **Note:** The project PDF specifies GPU = 400 W and each HBM = 5 W. The
> config files use 270 W for GPU, which is adjusted at runtime.

---

## Anemoi Parameter Mapping

Maps chiplet types to parameter names used in the Anemoi API:

```python
anemoi_parameters = {
    "GPU":          "GPU_power",
    "HBM":          "HBM_power",
    "HBM_l":        "HBM_l_power",
    "interposer":   "interposer_power",
    "substrate":    "substrate_power",
    "PCB":          "PCB_power",
    "Power_Source":  "Power_Source_power",
    "GPU_HTC":      "GPU_HTC_power",    # actually HTC, not power
    "HBM_HTC":      "HBM_HTC_power",    # actually HTC, not power
}
```

---

## Solver Configuration (Anemoi Defaults)

These were the settings used when creating an Anemoi project:

| Parameter | Value | Description |
|-----------|-------|-------------|
| ambient | 45 °C | Ambient temperature |
| resolution | 0.5 mm | Mesh resolution |
| precision | 0.05 | Solver precision |
| iterations | 50,000 | Max solver iterations |
| abs_tol | 0.1 | Absolute tolerance |
| duration | 20 s | Transient duration |
| steps | 10 | Transient time steps |
| dx/dy/dz min/max | 100 mm | World boundary padding |
| hc | 16.1 W/(m²·K) | Default convection coefficient |

---

## Voxelization / Grid Resolution Calculation

The Anemoi simulator calculated voxel resolution based on the largest box
(excluding interposer, substrate, PCB, Power_Source):

```python
def calculate_voxel_resolution_and_max_sizes(box_list):
    excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
    box_list_min = [b for b in box_list if b.chiplet_parent.get_chiplet_type() not in excluded_types]

    max_x = max(b.start_x + b.width  for b in box_list_min)
    max_y = max(b.start_y + b.length for b in box_list_min)
    max_z = max(b.start_z + b.height for b in box_list_min)

    base_box = max(box_list_min, key=lambda b: b.width * b.length * b.height)
    voxel_res_x = base_box.width  / 100.0
    voxel_res_y = base_box.length / 100.0
    voxel_res_z = base_box.height / 50.0

    return [voxel_res_x, voxel_res_y, voxel_res_z], [max_x, max_y, max_z]
```

---

## Conductivity Retrieval from Box Stackup

Given a box and a z-range within it, this computes the effective conductivity by
overlapping layer thicknesses with the voxel span. Layers are parsed from the
box stackup string (`"<count>:<layer_name>,<count>:<layer_name>,..."`).

```python
def retrieve_conductivity(box, voxel_start_z, voxel_end_z, layers):
    """
    Returns effective thermal conductivity for a voxel z-slice through a box.

    For each layer in the stackup:
      1. Look up the layer in `layers` to get thickness and material.
      2. If the material is composite (e.g. "Cu-Foil:0.7,Epoxy, Silver filled:0.3"),
         compute weighted average conductivity.
      3. Compute overlap fraction between this layer's z-span and the voxel's z-span.
      4. Sum up (overlap_fraction * layer_conductivity) across all layers.
    """

    def determine_layer_prop(layers_info, start_z, voxel_start_z, voxel_end_z):
        conductivity = 0
        current_z = start_z
        for thickness, cond in layers_info:
            layer_start_z = current_z
            layer_end_z   = layer_start_z + thickness
            current_z = layer_end_z
            overlap_start = max(layer_start_z, voxel_start_z)
            overlap_end   = min(layer_end_z,   voxel_end_z)
            if overlap_start < overlap_end:
                overlap_proportion = (overlap_end - overlap_start) / (voxel_end_z - voxel_start_z)
                conductivity += overlap_proportion * cond
        return conductivity

    layers_info = []
    for entry in box.get_box_stackup().split(","):
        layer_num, layer_name = entry.split(":")
        for layer in layers:
            if layer.get_name() == layer_name:
                t = int(layer_num) * layer.get_thickness()
                m = layer.get_material()
                m_parts = m.split(",")
                if len(m_parts) > 1:
                    mat1, ratio1 = m_parts[0].split(":")
                    mat2, ratio2 = m_parts[1].split(":")
                    c = (float(ratio1) * conductivity_values[mat1]
                       + float(ratio2) * conductivity_values[mat2])
                else:
                    c = conductivity_values[m]
        layers_info.insert(0, (t, c))  # stackup is stored bottom-up

    return determine_layer_prop(layers_info, box.start_z, voxel_start_z, voxel_end_z)
```

---

## Layer Height + Conductivity Map

Builds a lookup dict from layer definitions — maps layer name to
`(thickness, material_string, effective_conductivity)`:

```python
def create_layer_height_map(layers):
    result = {}
    for layer in layers:
        m = layer.get_material()
        m_parts = m.split(",")
        if len(m_parts) > 1:
            mat1, ratio1 = m_parts[0].split(":")
            mat2, ratio2 = m_parts[1].split(":")
            total = float(ratio1) + float(ratio2)
            cond = (float(ratio1) * conductivity_values[mat1]
                  + float(ratio2) * conductivity_values[mat2]) / total
        else:
            cond = conductivity_values[m]
        result[layer.get_name()] = (layer.get_thickness(), m, cond)
    return result
```

---

## Bonding Ratio Calculation

Computes the fill ratio of bonding material within a bonding layer
(what fraction of the layer volume is actually bonding material vs. epoxy fill):

```python
def calculate_ratio(bonding, box):
    """
    bonding: Bonding object with get_diameter(), get_offset(), get_pitch(),
             get_shape(), get_height(), get_cross_section_area()
    box:     Box object with width/length in mm

    Returns: ratio (0.0 to 1.0) of bonding material volume to total layer volume
    """
    radius = bonding.get_diameter() / 2
    # Count bumps in x direction
    n_min_x = max(math.ceil((radius - bonding.get_offset()) / bonding.get_pitch()), 0)
    n_max_x = math.floor((1000 * box.width - bonding.get_offset() - radius) / bonding.get_pitch())
    n_x = n_max_x - n_min_x + 1
    # Count bumps in y direction
    n_min_y = max(math.ceil((radius - bonding.get_offset()) / bonding.get_pitch()), 0)
    n_max_y = math.floor((1000 * box.length - bonding.get_offset() - radius) / bonding.get_pitch())
    n_y = n_max_y - n_min_y + 1

    if n_x <= 0 or n_y <= 0:
        return 0.00

    if bonding.get_shape() == "sphere":
        unit_volume = 4 * math.pi * (radius ** 3) / 3
    elif bonding.get_shape() == "cylinder":
        unit_volume = math.pi * (radius ** 2) * bonding.get_height()
    elif bonding.get_shape() == "cuboid":
        unit_volume = bonding.get_cross_section_area() * bonding.get_height()
    else:
        raise Exception("Invalid bonding shape")

    material_volume = unit_volume * n_x * n_y
    total_volume = 1000 * box.width * 1000 * box.length * bonding.get_height()
    return material_volume / total_volume
```

---

## Box Serialization (Voxelization)

The `serialize_dray` method maps boxes onto a 3D voxel grid, computing
per-voxel power density and conductivity. Key points:

- Excludes interposer, substrate, PCB, Power_Source from voxelization
- Handles partial overlap at voxel boundaries (fractional contributions)
- Power is distributed proportionally based on volume overlap
- Conductivity is computed per-layer through the stackup
- Uses `+= overlap_fraction * value` pattern for boundary voxels
  across all 26 boundary cases (6 faces, 12 edges, 8 corners)

---

## Temperature Extraction Per Chiplet

After solving, temperatures are mapped back to boxes:

```python
def chiplets_temperature(temp_map_3D, box_list):
    """
    For each box, slice the 3D temperature map to the box's voxel range,
    filter out invalid temps (<=0), then compute:
      - max_temperature = np.max(temps)
      - temp_avg = np.mean(temps)

    Tracks separately for GPU and HBM chiplet types.
    """
    for box in box_list:
        start_x_n = math.floor(box.start_x / voxel_res[0])
        end_x_n   = math.ceil(box.end_x   / voxel_res[0])
        start_y_n = math.floor(box.start_y / voxel_res[1])
        end_y_n   = math.ceil(box.end_y   / voxel_res[1])
        start_z_n = math.floor(box.start_z / voxel_res[2])
        end_z_n   = math.ceil(box.end_z   / voxel_res[2])

        temps = temp_map_3D[start_x_n:end_x_n, start_y_n:end_y_n, start_z_n:end_z_n]
        temps = temps[temps > 0]  # filter invalid
        max_temperature = np.max(temps)
        temp_avg = np.mean(temps)
```

---

## Heatsink Geometry Construction

Key logic for heatsink placement:

- Position: centered over the chiplet footprint (excluding interposer/substrate/PCB)
- z-position: top of tallest chiplet + min_TIM_height (default 0.01 mm)
- Gap between chiplets and heatsink is filled with `Infill_material` (k=19)
- Fin count: if not specified, defaults to `int(dx / (2 * fin_thickness))`
- Bottom heatsink: uses negative fin_height and base_thickness

---

## Bonding Box Stackup Format

Bonding boxes use a special stackup format:
`<layer_count>:<material_name>:<material_ratio>,<fill_material_name>:<fill_ratio>`

Parsed as:
```python
material_composition = box.get_box_stackup()[2:].split(",", 1)
material_composition = [m.split(":") for m in material_composition]
material_name = material_composition[0][0]
fill_material_name = material_composition[1][0]
ratio = float(material_composition[0][1])
```

---

## Chiplet Types and Excluded Types

Several methods exclude certain chiplet types from calculations:

```python
excluded_types = ["interposer", "substrate", "PCB", "Power_Source"]
```

These are the "base" or "passive" elements — voxelization and temperature
extraction focus on the active chiplets (GPU, HBM, HBM_l, Dummy_Si, etc.).

---

## 3D Overlap Check

Used for mapping temperatures back to boxes:

```python
def check_overlap(box, x0, y0, z0, x1, y1, z1):
    if box.end_z < z0 or z1 < box.start_z:
        return False
    if box.end_x < x0 or x1 < box.start_x:
        return False
    if box.end_y < y0 or y1 < box.start_y:
        return False
    return True
```

---

## Anemoi Simulation Flow (for reference)

The full simulation pipeline was:

1. **Clean project** — delete old boxes, sources, heatsinks
2. **Load bonding boxes** — create PCB layers for bonding
3. **Initialize power parameters** — set GPU/HBM power as named parameters
4. **Load boxes** — create PCB/box objects on the Anemoi server
5. **Load TIM boxes** — create TIM material boxes
6. **Load heatsink** — create heatsink geometry
7. **Fill gaps** — fill empty space with infill material
8. **Solve** — run the Anemoi solver (poll until complete)
9. **Serialize** — build local voxel grid with power/conductivity maps
10. **Map solution** — transfer Anemoi voxel temperatures to local grid
11. **Extract temperatures** — compute peak/avg per chiplet from the 3D map

Your local solver replaces steps 1-8 and 10. Steps 9 and 11 show how to
discretize the geometry and extract results — adapt these for your own grid.
