#!/usr/bin/env python3

"""
Script to run DART filter for data assimilation.
"""

import os
import shutil
import sys
import subprocess
import logging
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