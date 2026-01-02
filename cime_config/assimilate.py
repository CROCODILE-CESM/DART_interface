#!/usr/bin/env python3

"""
Script to run DART filter for data assimilation.
"""

import os
import shutil
import sys
import subprocess
import logging
import glob
from pathlib import Path

_CIMEROOT = os.getenv("CIMEROOT")
sys.path.append(os.path.join(_CIMEROOT, "scripts", "Tools"))

from standard_script_setup import *
from CIME.case import Case

logger = logging.getLogger(__name__)


def backup_mom_input_nml(rundir):
    """Backup the MOM input.nml file."""
    mom_input_nml = os.path.join(rundir, "input.nml")
    mom_input_nml_backup = os.path.join(rundir, "mom_input.nml.bak")
    if os.path.exists(mom_input_nml):
        shutil.copy(mom_input_nml, mom_input_nml_backup)
        logger.info(f"Backed up MOM input.nml to {mom_input_nml_backup}")
    else:
        logger.warning(f"MOM input.nml not found in {rundir}, backup skipped.")

def check_required_files(rundir):
    """Check for the presence of required files in the run directory."""
    missing_files = []
    required_files = ["input.nml", "obs_seq.out"]
    for filename in required_files:
        if not os.path.exists(os.path.join(rundir, filename)):
            missing_files.append(filename)
    if missing_files:
        logger.warning(f"Missing required files in {rundir}: {', '.join(missing_files)}")
    else:
        logger.info("All required files are present.")

def stage_dart_input_nml(case, rundir):
    """Stage the DART input.nml file into the run directory."""
    dart_input_nml_src = os.path.join(case.get_value("CASEROOT"), "Buildconf", "dartconf", "input.nml")
    dart_input_nml_dst = os.path.join(rundir, "input.nml")
    if os.path.exists(dart_input_nml_src):
        shutil.copy(dart_input_nml_src, dart_input_nml_dst)
        logger.info(f"Staged DART input.nml to {dart_input_nml_dst}")
    else:
        logger.error(f"DART input.nml not found at {dart_input_nml_src}")
        raise FileNotFoundError(f"DART input.nml not found at {dart_input_nml_src}")

def set_restart_files(rundir):
    """Create filter_input_list.txt and filter_output_list.txt from rpointer files."""
    # Find all rpointer.ocn_???? files (where ???? is 4 digits)
    rpointer_pattern = os.path.join(rundir, "rpointer.ocn_????")
    rpointer_files = sorted(glob.glob(rpointer_pattern))
    
    if not rpointer_files:
        logger.warning(f"No rpointer.ocn_???? files found in {rundir}")
        return
    
    # Concatenate all rpointer files into filter_input_list.txt
    filter_input_list = os.path.join(rundir, "filter_input_list.txt")
    with open(filter_input_list, 'w') as outfile:
        for rpointer_file in rpointer_files:
            with open(rpointer_file, 'r') as infile:
                outfile.write(infile.read())
    
    logger.info(f"Created {filter_input_list} from {len(rpointer_files)} rpointer files")
    
    # Copy filter_input_list.txt to filter_output_list.txt
    filter_output_list = os.path.join(rundir, "filter_output_list.txt")
    shutil.copy(filter_input_list, filter_output_list)
    logger.info(f"Copied {filter_input_list} to {filter_output_list}")


def set_template_files(case, rundir):
    """Create symlinks for template files (mom6.r.nc and mom6.static.nc)."""
    # Create symlink mom6.r.nc pointing to first file in filter_input_list.txt
    filter_input_list = os.path.join(rundir, "filter_input_list.txt")
    if os.path.exists(filter_input_list):
        with open(filter_input_list, 'r') as f:
            first_restart_file = f.readline().strip()
        
        if first_restart_file:
            mom6_r_nc = os.path.join(rundir, "mom6.r.nc")
            # Remove existing symlink if present
            if os.path.exists(mom6_r_nc) or os.path.islink(mom6_r_nc):
                os.remove(mom6_r_nc)
            os.symlink(first_restart_file, mom6_r_nc)
            logger.info(f"Created symlink: {mom6_r_nc} -> {first_restart_file}")
        else:
            logger.warning("filter_input_list.txt is empty, cannot create mom6.r.nc symlink")
    else:
        logger.warning(f"filter_input_list.txt not found in {rundir}")
    
    # Create symlink mom6.static.nc pointing to first matching static file
    casename = case.get_value("CASE")
    static_pattern = os.path.join(rundir, f"{casename}.mom6.h.static*")
    static_files = sorted(glob.glob(static_pattern))
    
    if static_files:
        first_static_file = static_files[0]
        mom6_static_nc = os.path.join(rundir, "mom6.static.nc")
        # Remove existing symlink if present
        if os.path.exists(mom6_static_nc) or os.path.islink(mom6_static_nc):
            os.remove(mom6_static_nc)
        os.symlink(first_static_file, mom6_static_nc)
        logger.info(f"Created symlink: {mom6_static_nc} -> {first_static_file}")
    else:
        logger.warning(f"No static files matching {static_pattern} found")


def clean_up(rundir):
    """Put mom input.nml back after filter run."""
    mom_input_nml = os.path.join(rundir, "input.nml")
    mom_input_nml_backup = os.path.join(rundir, "mom_input.nml.bak")
    if os.path.exists(mom_input_nml_backup):
        shutil.copy(mom_input_nml_backup, mom_input_nml)
        logger.info(f"Restored MOM input.nml from backup in {rundir}")
    else:
        logger.warning(f"No backup MOM input.nml found in {rundir}, cleanup skipped.")

def run_filter(case, caseroot):
    """Run the DART filter executable."""
    
    # Get necessary paths
    rundir = case.get_value("RUNDIR")
    exeroot = case.get_value("EXEROOT")
    
    # Path to filter executable
    filter_exe = os.path.join(exeroot, "esp", "filter")
    
    # Check if filter executable exists
    if not os.path.exists(filter_exe):
        raise FileNotFoundError(f"Filter executable not found: {filter_exe}")
    
    # Change to run directory
    os.chdir(rundir)

    # Get model time HK TODO
    # Bash version gets model time from rpointer.ocn_0001 file
    # is this time available in CASE?
    #get_model_time()
 
    #get_observations() # HK TODO need model time first

    # Back up mom input.nml
    backup_mom_input_nml(rundir)

    stage_dart_input_nml(case, rundir)

    # Check for required input files
    check_required_files(rundir)

    # Set the model restart files for dart to read and update
    set_restart_files(rundir)
    
    # Set the required model template files
    set_template_files(rundir)

    # Run filter
    logger.info(f"Running DART filter in {rundir}")
    
    try:
        # Always run filter with MPI
        ntasks = case.get_value("NTASKS_ESP")
        mpirun = case.get_value("MPI_RUN_COMMAND")
        if not ntasks or ntasks == "UNSET":
            ntasks = 1  # Default to 1 if not set
        if not mpirun or mpirun == "UNSET":
            mpirun = "mpibind"  # Default Derecho mpirun command
        cmd = f"{mpirun} {filter_exe}"
        
        logger.info(f"Executing: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True, 
                              capture_output=True, text=True)
        
        logger.info("Filter completed successfully")
        logger.debug(f"Filter output: {result.stdout}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Filter failed with return code {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        raise

    # Clean up and restore mom input.nml
    clean_up(rundir)

def main():
    """Main entry point."""
    caseroot = os.getcwd()
    
    with Case(caseroot) as case:
        run_filter(case, caseroot)

if __name__ == "__main__":
    main()