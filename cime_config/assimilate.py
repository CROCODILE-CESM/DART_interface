#!/usr/bin/env python3

"""
Data assimilation script for CESM.

Supports ocean (MOM6), atmosphere (CAM-SE), land (CLM), and sea-ice (CICE)
data assimilation, individually or in combination.  Which components are active
is determined by the CESM case XML variables DATA_ASSIMILATION_{OCN|ATM|LND|ICE}.

For each active component the script:
  - Stages DART input.nml into the run directory.
  - For MOM6: backs up and restores input.nml (name clash with DART).
  - Finds component restart files via rpointer files and writes
    filter_input_list.txt / filter_output_list.txt.
  - Sets component-specific template file symlinks required by the model_mod.
  - Stages the correct observation sequence file.
  - Runs the per-component DART filter executable (filter_{comp}) with MPI.
  - Renames output logs, obs_seq.final, inflation files, and stage files.
"""

import os
import shutil
import sys
import subprocess
import logging
import glob
import re
from pathlib import Path
from collections import namedtuple
import fnmatch

logging.basicConfig(level=logging.INFO)

ModelTime = namedtuple('ModelTime', ['year', 'month', 'day', 'seconds'])

_CIMEROOT = os.getenv("CIMEROOT")
if not _CIMEROOT:
    raise EnvironmentError("CIMEROOT environment variable is not set")

sys.path.append(os.path.join(_CIMEROOT, "CIME", "Tools"))
sys.path.append(os.path.join(_CIMEROOT, "CIME", "scripts"))

_assimilate_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _assimilate_dir)

from standard_script_setup import *
from CIME.case import Case
from dart_cesm_components import DART_COMPONENTS, get_active_da_components

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Generic utilities
# ---------------------------------------------------------------------------

def get_model_time_from_filename(filename):
    """
    Extract model time from a filename containing a timestamp like
    rpointer.ocn_0001.0001-01-02-00000.
    Returns a ModelTime namedtuple.
    """
    match = re.search(r'\.(\d{4})-(\d{2})-(\d{2})-(\d{5})$', filename)
    if match:
        year, month, day, seconds = map(int, match.groups())
        return ModelTime(year, month, day, seconds)
    else:
        logger.error("Filename is missing or does not match expected pattern.")
        raise ValueError(f"Could not extract model time from filename: {filename}")


def get_model_time(case):
    """Get model time from DRV_RESTART_POINTER which points to the coupler restart."""
    rpointer = case.get_value("DRV_RESTART_POINTER")
    if not rpointer or rpointer == "UNSET":
        raise ValueError("DRV_RESTART_POINTER is not set in the case.")
    model_time = get_model_time_from_filename(rpointer)
    logger.info(
        f"Model time extracted from {rpointer}: "
        f"{model_time.year}-{model_time.month:02}-{model_time.day:02} "
        f"{model_time.seconds} seconds"
    )
    return model_time


def find_files_for_model_time(rundir, rpointer_prefix, model_time):
    """
    Find all rpointer.{prefix}_* files in rundir matching model_time.
    """
    timestamp = (f"{model_time.year:04}-{model_time.month:02}"
                 f"-{model_time.day:02}-{model_time.seconds:05}")
    pattern = os.path.join(rundir, f"rpointer.{rpointer_prefix}_*.{timestamp}")
    return glob.glob(pattern)


def stage_dart_input_nml(case, rundir):
    """Copy the DART input.nml from Buildconf/dartconf into the run directory."""
    src = os.path.join(case.get_value("CASEROOT"), "Buildconf", "dartconf", "input.nml")
    dst = os.path.join(rundir, "input.nml")
    if os.path.exists(src):
        shutil.copy(src, dst)
        logger.info(f"Staged DART input.nml to {dst}")
    else:
        raise FileNotFoundError(f"DART input.nml not found at {src}")


def check_required_files(rundir):
    """Verify that the minimum set of files needed by filter are present."""
    missing = [
        f for f in ["input.nml", "obs_seq.out"]
        if not os.path.exists(os.path.join(rundir, f))
    ]
    if missing:
        raise FileNotFoundError(f"Missing required files in {rundir}: {', '.join(missing)}")
    logger.info("All required files are present.")


# ---------------------------------------------------------------------------
# Restart-file staging (generic)
# ---------------------------------------------------------------------------

def set_restart_files(rundir, rpointer_prefix, model_time):
    """
    Build filter_input_list.txt / filter_output_list.txt from rpointer files
    for the given component prefix and model time.
    """
    rpointer_files = find_files_for_model_time(rundir, rpointer_prefix, model_time)
    if not rpointer_files:
        raise FileNotFoundError(
            f"No rpointer.{rpointer_prefix}_???? files found in {rundir}."
        )

    filter_input_list = os.path.join(rundir, "filter_input_list.txt")
    with open(filter_input_list, 'w') as outfile:
        for rp in sorted(rpointer_files):
            with open(rp, 'r') as infile:
                outfile.write(infile.read())
    logger.info(f"Created {filter_input_list} from {len(rpointer_files)} rpointer files")

    filter_output_list = os.path.join(rundir, "filter_output_list.txt")
    shutil.copy(filter_input_list, filter_output_list)
    logger.info(f"Copied {filter_input_list} to {filter_output_list}")


# ---------------------------------------------------------------------------
# Component-specific template-file staging
# ---------------------------------------------------------------------------

def _make_symlink(src, dst):
    """Create or replace a symlink dst -> src."""
    if os.path.exists(dst) or os.path.islink(dst):
        os.remove(dst)
    os.symlink(src, dst)
    logger.info(f"Created symlink: {dst} -> {src}")


def set_template_files_ocn(case, rundir):
    """
    MOM6: symlink mom6.r.nc (first restart) and mom6.static.nc (static grid file).
    """
    filter_input_list = os.path.join(rundir, "filter_input_list.txt")
    if os.path.exists(filter_input_list):
        with open(filter_input_list) as f:
            first_restart = f.readline().strip()
        if first_restart:
            _make_symlink(first_restart, os.path.join(rundir, "mom6.r.nc"))
        else:
            logger.warning("filter_input_list.txt is empty, cannot create mom6.r.nc symlink")
    else:
        logger.warning(f"filter_input_list.txt not found in {rundir}")

    casename = case.get_value("CASE")
    static_files = sorted(glob.glob(os.path.join(rundir, f"{casename}.mom6.h.static*")))
    if static_files:
        _make_symlink(static_files[0], os.path.join(rundir, "mom6.static.nc"))
    else:
        logger.warning(f"No MOM6 static files found in {rundir}")


def set_template_files_atm(case, rundir):
    """
    CAM-SE: symlink caminput.nc (first member restart) and cam_phis.nc (surface geopotential).
    cam_phis.nc is the same for all members; use the first member's file.
    """
    filter_input_list = os.path.join(rundir, "filter_input_list.txt")
    if os.path.exists(filter_input_list):
        with open(filter_input_list) as f:
            first_restart = f.readline().strip()
        if first_restart:
            _make_symlink(first_restart, os.path.join(rundir, "caminput.nc"))
        else:
            logger.warning("filter_input_list.txt is empty, cannot create caminput.nc symlink")
    else:
        logger.warning(f"filter_input_list.txt not found in {rundir}")

    casename = case.get_value("CASE")
    phis_files = sorted(glob.glob(os.path.join(rundir, f"{casename}.cam*.i.*")))
    if phis_files:
        _make_symlink(phis_files[0], os.path.join(rundir, "cam_phis.nc"))
    else:
        logger.warning(f"No CAM initial files for cam_phis.nc found in {rundir}")


def set_template_files_lnd(case, rundir):
    """
    CLM: no extra template symlinks required beyond the restart list.
    """
    logger.info("CLM: no additional template file symlinks required.")


def set_template_files_ice(case, rundir):
    """
    CICE: no extra template symlinks required beyond the restart list.
    """
    logger.info("CICE: no additional template file symlinks required.")


_SET_TEMPLATE_FILES = {
    "ocn": set_template_files_ocn,
    "atm": set_template_files_atm,
    "lnd": set_template_files_lnd,
    "ice": set_template_files_ice,
}


# ---------------------------------------------------------------------------
# MOM6-specific input.nml conflict handling
# ---------------------------------------------------------------------------

def backup_model_input_nml(rundir):
    """Back up model input.nml before filter overwrites it (MOM6 only)."""
    src = os.path.join(rundir, "input.nml")
    bak = os.path.join(rundir, "mom_input.nml.bak")
    if os.path.exists(src):
        shutil.copy(src, bak)
        logger.info(f"Backed up model input.nml to {bak}")
    else:
        logger.warning(f"model input.nml not found in {rundir}, backup skipped.")


def restore_model_input_nml(rundir):
    """Restore model input.nml from backup after filter finishes (MOM6 only)."""
    bak = os.path.join(rundir, "mom_input.nml.bak")
    dst = os.path.join(rundir, "input.nml")
    if os.path.exists(bak):
        shutil.copy(bak, dst)
        logger.info(f"Restored model input.nml from {bak}")
    else:
        logger.warning(f"No backup model input.nml found in {rundir}, restore skipped.")


# ---------------------------------------------------------------------------
# Observation staging
# ---------------------------------------------------------------------------

def get_observations(case, comp, model_time, rundir):
    """
    Symlink the correct obs_seq file for the given component and model time
    into rundir as obs_seq.out.
    """
    date_str = f"{model_time.year:04}{model_time.month:02}{model_time.day:02}"
    obs_seq_pattern = f"obs_seq.0Z.{date_str}"
    category_key = f"{comp}_obs_seq"

    input_data_list_path = os.path.join(
        case.get_value("CASEROOT"), "Buildconf", "dart.input_data_list"
    )

    obs_files = []
    with open(input_data_list_path) as f:
        for line in f:
            if category_key in line:
                obs_file = line.split("=", 1)[-1].strip()
                if obs_seq_pattern in obs_file:
                    obs_files.append(obs_file)

    if not obs_files:
        logger.warning(f"No observation sequence found for {comp} on {date_str}")
        return

    dest = os.path.join(rundir, "obs_seq.out")
    if os.path.exists(dest):
        os.remove(dest)
    os.symlink(obs_files[0], dest)
    logger.info(f"Staged observation file: {obs_files[0]} -> {dest}")


# ---------------------------------------------------------------------------
# Inflation file handling
# ---------------------------------------------------------------------------

def parse_inflation_settings(input_nml_path):
    """
    Parse filter_nml inflation settings from a Fortran namelist.
    Returns a dict with 'prior' and 'posterior' keys.
    """
    def parse_fortran_namelist(filepath):
        """Simple parser for Fortran namelist files."""
        def convert_fortran_value(value_str):
            value_str = value_str.strip()
            if not value_str or value_str == "''":
                return ''
            if value_str.lower() in ['.true.', 't']:
                return True
            if value_str.lower() in ['.false.', 'f']:
                return False
            if ',' in value_str:
                return [convert_fortran_value(i.strip()) for i in value_str.split(',')]
            if (value_str.startswith("'") and value_str.endswith("'")) or \
               (value_str.startswith('"') and value_str.endswith('"')):
                return value_str[1:-1]
            try:
                return float(value_str) if ('.' in value_str or 'e' in value_str.lower()) \
                    else int(value_str)
            except ValueError:
                return value_str

        nml_dict = {}
        current_nml = None
        with open(filepath) as f:
            lines = f.readlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line or line.startswith('!'):
                continue
            if line.startswith('&'):
                current_nml = line[1:].strip()
                nml_dict[current_nml] = {}
                continue
            if line.startswith('/'):
                current_nml = None
                continue
            if current_nml and '=' in line:
                match = re.match(r'(\w+)\s*=\s*(.+)', line)
                if match:
                    var_name = match.group(1).strip()
                    var_value = match.group(2).strip()
                    while var_value.rstrip().endswith(',') and i < len(lines):
                        next_line = lines[i].strip()
                        i += 1
                        if next_line.startswith('/') or next_line.startswith('&'):
                            i -= 1
                            break
                        if not next_line or next_line.startswith('!'):
                            continue
                        if '=' in next_line and not next_line.startswith("'"):
                            i -= 1
                            break
                        var_value += ' ' + next_line.strip()
                    var_value = var_value.rstrip(',').strip()
                    nml_dict[current_nml][var_name] = convert_fortran_value(var_value)
        return nml_dict

    nml_data = parse_fortran_namelist(input_nml_path)
    filter_nml = nml_data.get('filter_nml', {})

    def get(key, idx, default):
        arr = filter_nml.get(key, [default, default])
        if not isinstance(arr, list):
            arr = [arr]
        while len(arr) < 2:
            arr.append(arr[0])
        return arr[idx]

    prior = {
        'inf_flavor': get('inf_flavor', 0, 0),
        'inf_initial_from_restart': get('inf_initial_from_restart', 0, False),
        'inf_sd_initial_from_restart': get('inf_sd_initial_from_restart', 0, False),
        'inf_initial': get('inf_initial', 0, 1.0),
    }
    posterior = {
        'inf_flavor': get('inf_flavor', 1, 0),
        'inf_initial_from_restart': get('inf_initial_from_restart', 1, False),
        'inf_sd_initial_from_restart': get('inf_sd_initial_from_restart', 1, False),
        'inf_initial': get('inf_initial', 1, 1.0),
    }
    return {'prior': prior, 'posterior': posterior}


def stage_inflation_files(rundir):
    """
    Verify that inflation restart files required by input.nml are present.
    DART expects: input_priorinf_mean.nc, input_priorinf_sd.nc,
                  input_postinf_mean.nc,  input_postinf_sd.nc
    """
    input_nml = os.path.join(rundir, "input.nml")
    if not os.path.exists(input_nml):
        raise FileNotFoundError(f"input.nml not found in {rundir}")

    settings = parse_inflation_settings(input_nml)

    def check(label, mean_file, sd_file):
        missing = [f for f in [mean_file, sd_file]
                   if not os.path.exists(os.path.join(rundir, f))]
        if missing:
            raise FileNotFoundError(
                f"Missing {label} inflation file(s) in {rundir}: {', '.join(missing)}"
            )

    if settings['prior']['inf_flavor'] > 0 and settings['prior']['inf_initial_from_restart']:
        check("prior", "input_priorinf_mean.nc", "input_priorinf_sd.nc")
    if settings['posterior']['inf_flavor'] > 0 and settings['posterior']['inf_initial_from_restart']:
        check("posterior", "input_postinf_mean.nc", "input_postinf_sd.nc")


def rename_inflation_files(rundir):
    """Copy output inflation files to input_* names for the next cycle."""
    for base_name in ["priorinf_mean", "priorinf_sd", "postinf_mean", "postinf_sd"]:
        src = os.path.join(rundir, f"output_{base_name}.nc")
        if os.path.exists(src):
            dst = os.path.join(rundir, f"input_{base_name}.nc")
            shutil.copy(src, dst)
            logger.info(f"Copied {src} to {dst} for next cycle")


# ---------------------------------------------------------------------------
# Post-filter file renaming
# ---------------------------------------------------------------------------

def rename_dart_logs(case, model_time, rundir):
    """Rename dart_log.out / dart_log.nml to include case name and model time."""
    case_name = case.get_value("CASE")
    date_str = (f"{model_time.year:04}-{model_time.month:02}"
                f"-{model_time.day:02}-{model_time.seconds:05}")
    for suffix in ["out", "nml"]:
        src = os.path.join(rundir, f"dart_log.{suffix}")
        if os.path.exists(src):
            dst = os.path.join(rundir, f"dart_log.{case_name}.{date_str}.{suffix}")
            os.rename(src, dst)
            logger.info(f"Renamed {src} to {dst}")


def rename_obs_seq_final(case, model_time, rundir):
    """Rename obs_seq.final to obs_seq.final.<case>.<model_time>."""
    case_name = case.get_value("CASE")
    src = os.path.join(rundir, "obs_seq.final")
    if not os.path.exists(src):
        raise FileNotFoundError(f"obs_seq.final not found in {rundir}")
    date_str = (f"{model_time.year:04}-{model_time.month:02}"
                f"-{model_time.day:02}-{model_time.seconds:05}")
    dst = os.path.join(rundir, f"obs_seq.final.{case_name}.{date_str}")
    os.rename(src, dst)
    logger.info(f"Renamed obs_seq.final to {dst}")


def rename_stage_files(case, model_time, rundir):
    """
    Rename filter stage output files (forecast, preassim, postassim, analysis,
    output, input) to include case name and model time.  Inflation input files
    (input_*inf*.nc) are skipped because they are consumed by the next cycle.
    """
    case_name = case.get_value("CASE")
    date_str = (f"{model_time.year:04}-{model_time.month:02}"
                f"-{model_time.day:02}-{model_time.seconds:05}")
    stages = ["input", "forecast", "preassim", "postassim", "analysis", "output"]
    members = ["member*", "mean", "sd",
               "priorinf_mean", "priorinf_sd", "postinf_mean", "postinf_sd"]
    for stage in stages:
        for member in members:
            for filepath in glob.glob(os.path.join(rundir, f"{stage}_{member}.nc")):
                base = os.path.splitext(os.path.basename(filepath))[0]
                if fnmatch.fnmatch(base, "input_*inf*"):
                    logger.debug(f"Skipping inflation file rename: {filepath}")
                    continue
                new_path = os.path.join(rundir, f"{base}.{case_name}.{date_str}.nc")
                os.rename(filepath, new_path)
                logger.debug(f"Renamed {filepath} to {new_path}")


# ---------------------------------------------------------------------------
# MOM6-only cycle-0 geometry file
# ---------------------------------------------------------------------------

def copy_geometry_file_for_cycle0(case, rundir, cycle):
    """
    MOM6 only: on cycle 0 copy the geometry file to ocean_geometry.nc so it is
    available for subsequent cycles (MOM6 only writes it on cycle 0).
    """
    if "ocn" not in get_active_da_components(case):
        return
    try:
        cycle_int = int(cycle)
    except (ValueError, TypeError):
        logger.warning(f"Cycle '{cycle}' is not an integer, skipping geometry file copy")
        return
    if cycle_int != 0:
        return
    casename = case.get_value("CASE")
    geometry_files = sorted(
        glob.glob(os.path.join(rundir, f"{casename}.mom6.h.ocean_geometry*"))
    )
    if geometry_files:
        dst = os.path.join(rundir, "ocean_geometry.nc")
        shutil.copy(geometry_files[0], dst)
        logger.info(f"Copied {geometry_files[0]} to {dst} for cycle 0")
    else:
        logger.warning(f"No MOM6 geometry files found in {rundir} for cycle 0")


# ---------------------------------------------------------------------------
# Per-component filter run
# ---------------------------------------------------------------------------

def run_filter_for_component(case, comp, caseroot, use_mpi=True):
    """
    Run the DART filter for a single DA component.

    comp: one of 'ocn', 'atm', 'lnd', 'ice'
    """
    dart_info = DART_COMPONENTS[comp]
    rundir = case.get_value("RUNDIR")
    exeroot = case.get_value("EXEROOT")

    filter_exe = os.path.join(exeroot, "esp", f"filter_{comp}")
    if not os.path.exists(filter_exe):
        raise FileNotFoundError(f"Filter executable not found: {filter_exe}")

    os.chdir(rundir)
    model_time = get_model_time(case)

    # Stage observations for this component
    get_observations(case, comp, model_time, rundir)

    # MOM6 name-clash: back up model input.nml before DART writes its own
    if dart_info["input_nml_conflict"]:
        backup_model_input_nml(rundir)

    # Stage DART input.nml
    stage_dart_input_nml(case, rundir)

    # Verify required files
    check_required_files(rundir)

    # Build filter_input/output_list.txt from rpointer files
    set_restart_files(rundir, dart_info["rpointer_prefix"], model_time)

    # Component-specific template symlinks
    _SET_TEMPLATE_FILES[comp](case, rundir)

    # Verify / stage inflation files
    stage_inflation_files(rundir)

    logger.info(f"Running DART filter_{comp} in {rundir}")
    try:
        if use_mpi:
            ntasks = case.get_value("NTASKS_ESP")
            mpirun = case.get_value("MPI_RUN_COMMAND")
            if not ntasks or ntasks == "UNSET":
                ntasks = 1
            if not mpirun or mpirun == "UNSET":
                mpirun = "mpirun"
            cmd = f"{mpirun} {filter_exe}"
        else:
            cmd = filter_exe

        logger.info(f"Executing: {cmd}")
        result = subprocess.run(cmd, shell=True, check=True,
                                capture_output=True, text=True)
        logger.info(f"filter_{comp} completed successfully")
        logger.debug(f"stdout: {result.stdout}")
        logger.debug(f"stderr: {result.stderr}")

        rename_dart_logs(case, model_time, rundir)
        rename_obs_seq_final(case, model_time, rundir)
        rename_inflation_files(rundir)
        rename_stage_files(case, model_time, rundir)

    except subprocess.CalledProcessError as e:
        logger.error(f"filter_{comp} failed with return code {e.returncode}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise
    finally:
        # Always restore model input.nml if it was backed up
        if dart_info["input_nml_conflict"]:
            restore_model_input_nml(rundir)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assimilate(caseroot, cycle, rundir=None, use_mpi=True):
    """
    Main entry point for data assimilation, callable as a function by CIME.

    caseroot: Path to the case root directory.
    cycle:    Cycle identifier (string or int).
    rundir:   Optionally override the run directory (otherwise taken from case).
    use_mpi:  Whether to use MPI to run the filter (default True).
    """
    with Case(caseroot) as case:
        if rundir is None:
            rundir = case.get_value("RUNDIR")

        active_comps = get_active_da_components(case)
        # HK @todo: user may want to run some cycles with no DA, e.g. spin up?
        if not active_comps:
            raise RuntimeError(
                "assimilate called but no DATA_ASSIMILATION_* flags are True."
            )

        # MOM6 cycle-0 geometry file must be copied before filter runs
        copy_geometry_file_for_cycle0(case, rundir, cycle)

        for comp in active_comps:
            logger.info(f"=== Starting DA for component: {comp} ===")
            run_filter_for_component(case, comp, caseroot, use_mpi=use_mpi)
            logger.info(f"=== Finished DA for component: {comp} ===")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run DART assimilation for a CESM case.")
    parser.add_argument("caseroot", help="Path to the case root directory.")
    parser.add_argument("cycle", help="Cycle number.")
    parser.add_argument(
        "--no-mpi", action="store_true",
        help="Run filter without MPI (serial mode, for testing on login node)."
    )
    args = parser.parse_args()
    assimilate(args.caseroot, cycle=args.cycle, use_mpi=not args.no_mpi)


if __name__ == "__main__":
    main()
