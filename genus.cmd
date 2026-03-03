# Cadence Genus(TM) Synthesis Solution, Version 21.11-s126_1, built Dec 20 2021 12:52:46

# Date: Wed Mar 05 07:21:43 2025
# Host: sysml.ee.ucla.edu (x86_64 w/Linux 4.18.0-553.40.1.el8_10.x86_64) (64cores*128cpus*1physical cpu*AMD EPYC 9554P 64-Core Processor 1024KB)
# OS:   Red Hat Enterprise Linux release 8.10 (Ootpa)

set_db information_level 9
suppress_messages LBR-40 LBR-399 LBR-9
set_db init_hdl_search_path {~/}
set_db hdl_error_on_blackbox true
set_db init_lib_search_path {/app/library/tsmc/TSMC65/Standard_Cells/TSMC_N65_ARM/Artisan/aci/sc-ad10/astro/plib}
set_db library tsmc_cln65_sc_a10_4X2Z_hvt.plib
set hdl_files {pipeline_latch.v}
set DNAME pipeline_latch
set DESIGN pipeline_latch
set clkpin clk
read_hdl -v2001 ${hdl_files}
elaborate $DESIGN
set clk_period 227
set clock [define_clock -period ${clk_period} -name ${clkpin} [clock_ports]]
suppress_messages TUI-253
set_input_delay -clock ${clkpin} 0 [vfind /designs/${DESIGN}/ports -port *]
set_output_delay -clock ${clkpin} 0 [vfind /designs/${DESIGN}/ports -port *]
dc::set_clock_transition 0.08 ${clkpin}
check_design -unresolved
set_db tns_opto true
report_timing -lint
syn_generic
syn_map
syn_opt
report_timing -lint
report_timing > ~/output/synth_report_timing.txt
report_gates  > ~/output/synth_report_gates.txt
report_power  > ~/output/synth_report_power.txt
report_area   > ~/output/synth_report_area.txt
write_hdl > ~/output/${DNAME}_synth.v
write_sdc >  ~/output/${DNAME}.sdc
report_timing -lint -verbose
puts \n
puts "Synthesis Finished!         "
puts \n
puts "Check output/ for synthesis results and reports."
puts \n
 
quit
