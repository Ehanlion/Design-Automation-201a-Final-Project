# Gotchas for the Lab Project 

These are notes from Piazza about common gotchas for the actual project. These should be followed for added context about how to solve the complex ins and outs of this project.

## Spice Solver Gotcha

Question: By going over the project PDF, I found that it said we are allowed to use either SPICE tool (where we extract the net list and analyze them) or our own RC solver (which are our own python functions). Therefore, I was wondering if we do not want to use the SPICE tool, can we write our own RC solver for this project, which is mentioned in the project PDF?

If we MUST use the SPICE tool, do we need to make a readme doc so that the TA will know where our path to spice is? Since if the code remain unchanged and tested by TA, it might be errors since I may not have the same path and folder that we install the spice on eeapps locally. Thank you for your help!

Also I saw in the previous post that professor mentioned that since we have limited time due to late release of the project, we do not need to do the isolation part. Just want to make sure this is correct.

Answer: Again, you should just use Pyspice either as an API call or by dumping out netlist. I don't want how you solve a linear system of equations to be reason why your code is  faster or slower!

Yes, no isolators need to be inserted. Ignore that part of the project. Just implement a clever way to mesh to get accuracy runtime trade-off.

## Image Generation Gotcha

Question: I was confused why my post.png and post3D.png just seemed to be giant blobs of red so I went digging to try and figure out what was going on.

Isn’t the naming logic in therm.py wrong for our setup?

The code uses box.name[:-1].endswith('HBM'), but our actual box names look like this:

Because of the hierarchy and the #0 or _l1 suffixes, the [:-1] slice and the endswith checks fail. This just dumps every chiplet into the else block, which is why everything is rendering as a giant red blob instead of showing the actual silicon.

Changing the logic to check for substrings fixes the issue for me (although I still don’t know if its correct). Are we allowed to modify these visualization functions?

Answer: Yes, you are allowed to modify these visualization functions. We will check against the numerical output dumped by the code.

## Expected Results and Verification

Question: How can we verify result of our project output ? Is there expected results for the three runs in the project PDF ?

Answer: Just implement a clever way to mesh to get accuracy runtime trade-off and we will check against the dumped netlist information as detailed in the project docs.

## Power Consumption Assumptions

Question: The lab instructions say "The power consumed by the GPU should be estimated to be 400 W", but inside the output_vars2.yaml file which is sourced by therm_xml_parser.py (called by therm.py), the core power is only 270. Do we override this with the 400? Or am I not looking at the right file? The HBM value of 5 W from the lab doc looks right from this file.

Do we assume uniform power distribution to each fine grained grid in the entire system ? for eaample 400W of GPU is evenly distributed to each grid of the GPU

Answers: GPU_chiplet = Chiplet(name=deepest_node.get_name() + ".GPU", core_area=826.2, aspect_ratio= 0.787, fraction_memory=0.0, fraction_logic=1.0, fraction_analog=0.0, assembly_process="silicon_individual_bonding", stackup=stackup, power=270.0, floorplan="", floorplan_dict="", fake=False, height=height

Please use the 270 W values as in therm.py for now. Your code anyway has to be able to run for variety of setups.

The power should be coming from input voxels. Each Chiplet may have a different power consumption which means each voxel can have a different power consumption

## Project Figure of Merit for Solution

Question: Hi everyone — quick question about the final project.

The project PDF mentions the thermal isolator optimization and says the Figure of Merit (FoM) will be announced later, but I haven’t been able to find a Piazza post/announcement that defines it.

Could the staff please clarify what FoM we should optimize (e.g., max HBM temperature, weighted HBM/GPU, constraint-based, etc.) and any required reporting format?

Thanks!

Answer: There is no isolator insertion optimization any more. We simplified the project because it was released later than I had anticipated. Ignore blurbs about "isolator"
 insertion. Your FoM will be some function of accuracy  (a measure of your thermal map) and runtime.

You should also be able to check your solution against the group truth thermal map, which they will provide but we will not have for this project to check with ourselves.

## PySpice and ngspice requirements

pyspice repo: https://github.com/PySpice-org/PySpice

Question: I had to jump through many hoops to get NgSpice running locally, and when I finally did it and ran the simulator with PySpice it gave me the same result as my local RC solver except it was nearly 5x slower.

I wanted to clarify if it is an absolute requirement that we use PySpice or if we are allowed to use our own local RC solver (at our own risk). Even when using PySpice, therm.py can still look somewhat different depending on how ngspice is set up and imported so that PySpice can locate it properly.

Answer: Report and submit code with runtimes and results for both, we will consider PySPICE.

Question 2: I initially implemented my own RC solver to debug and validate the thermal network generation flow, since the original handout seemed to allow either PSpice or an RC solver. Based on the original project description, I have already completed the main requested components, including the thermal network construction, temperature extraction flow, and the originally described optimization work.

After seeing the Piazza clarification, I want to confirm whether the final submission is expected to use PSpice/netlist-based solving, or whether a custom solver is still acceptable if the focus remains on meshing and thermal network construction.

In addition, before seeing the clarification, I had already tested several isolator placements and identified one configuration that gave a clear temperature reduction. Should I still include that result in the final report, or should the isolator part be omitted entirely?

Answer 2: We would expect all final submissions to use PSPICE. You can include the isolator results but they will not be considered for grading.

Question 3: In the previous post @149 PySPICE was mentioned. On the actual project document it says PSPICE and I'm wondering exactly which one is wanted for us to use.

Question 3.5: I was able to install and import PySpice successfully, but a test circuit of mine failed because libngspice.so is missing. I also checked and ngspice and xyce do not appear to be on PATH. Is there a class supported ngspice/xyce installation on eeapps we should use, or are we expected to build/install ngspice locally?

Answer 3: Use ngspice locally. and the repo is GitHub - PySpice-org/PySpice: Simulate electronic circuit using Python and the Ngspice / Xyce simulators · GitHub => GitHub - PySpice-org/PySpice: Simulate electronic circuit using Python and the Ngspice / Xyce simulators · GitHub