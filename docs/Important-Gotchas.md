# Important Gotchas

## `therm.py` programming

You are given a Python program therm.py which calls a function simulator_simulate() which you need to
define. The simulator_simulate() function takes the set of boxes as input. Each box is an instance of Box()
class, having start_x, start_y, start_z, end_x, end_y, end_z coordinates and stackup. The stackup consists
of a list of layers, each of which has a material compositions and thickness. The definition of all layers is
also passed as an argument to simulator_simulate() function. All heatsinks are defined in the
heatsink_definitions.xml and the heatsink we are using is specified using heatsink_water_cooled. You are
allowed to pass more inputs as arguments to the simulator_simulate() function if required.

## `simulator_simulate` signature

The simulator_simulate() function is expected to return a **dictionary** as below.

```py
results = simulator_simulate()
results = {
“Box1” : (peak_temperature_of_box1, average_temperature_of_box1,
thermal_resistance_of_box1_in_x, thermal_resistance_of_box1_in_y,
thermal_resistance_of_box1_in_z),
“Box2” : (peak_temperature_of_box1, average_temperature_of_box1,
thermal_resistance_of_box1_in_x, thermal_resistance_of_box1_in_y,
thermal_resistance_of_box1_in_z),
...
...
...
}
```