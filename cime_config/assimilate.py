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
  - Stages the component's inflation restarts onto the fixed input_*inf_*.nc
    names filter requires, and removes the staging links afterwards.
  - If perturb_from_single_instance, only set for cycle 0, so a fresh
    multi-instance case (every instance bit-identical) gets perturbed into
    an ensemble; off for every cycle after.
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


def stage_dart_input_nml(case, rundir, comp):
    """Copy the per-component DART input.nml from Buildconf/dartconf into the run directory.
    The file is stored as input.nml.{comp} and staged as input.nml."""
    src = os.path.join(case.get_value("CASEROOT"), "Buildconf", "dartconf", f"input.nml.{comp}")
    dst = os.path.join(rundir, "input.nml")
    if os.path.exists(src):
        shutil.copy(src, dst)
        logger.info(f"Staged DART input.nml for '{comp}' to {dst}")
    else:
        raise FileNotFoundError(f"DART input.nml for '{comp}' not found at {src}")


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
# Model converter programs (pre/post filter)
# ---------------------------------------------------------------------------

def run_model_programs_for_members(case, comp, programs, exeroot, rundir):
    """
    Run each serial model converter program once per ensemble member (instance).

    Used for pre-filter converters (e.g. cice_to_dart, clm_to_dart) and
    post-filter converters (e.g. dart_to_cice, dart_to_clm).  Programs run
    serially; the instance number (1-based, zero-padded to 4 digits) is passed
    via the DART_INSTANCE environment variable so programs can locate their
    member-specific files.
    """
    if not programs:
        return
    dart_info = DART_COMPONENTS[comp]
    ninst = case.get_value(dart_info["ninst_var"])
    if not ninst or ninst < 1:
        raise ValueError(
            f"Invalid instance count for component '{comp}': {ninst}"
        )
    for program in programs:
        exe = os.path.join(exeroot, "esp", program)
        if not os.path.exists(exe):
            raise FileNotFoundError(f"Converter executable not found: {exe}")
        for member in range(1, ninst + 1):
            member_str = f"{member:04d}"
            logger.info(f"Running {program} for instance {member_str}")
            env = os.environ.copy()
            env["DART_INSTANCE"] = member_str
            try:
                result = subprocess.run(
                    exe, env=env, cwd=rundir, check=True,
                    capture_output=True, text=True
                )
                logger.debug(f"{program} instance {member_str} stdout: {result.stdout}")
                logger.debug(f"{program} instance {member_str} stderr: {result.stderr}")
            except subprocess.CalledProcessError as e:
                logger.error(
                    f"{program} instance {member_str} failed with rc={e.returncode}")
                logger.error(f"stdout: {e.stdout}")
                logger.error(f"stderr: {e.stderr}")
                raise
        logger.info(f"Completed {program} for all {ninst} instances")


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
        'inf_sd_initial': get('inf_sd_initial', 0, 0.0),
    }
    posterior = {
        'inf_flavor': get('inf_flavor', 1, 0),
        'inf_initial_from_restart': get('inf_initial_from_restart', 1, False),
        'inf_sd_initial_from_restart': get('inf_sd_initial_from_restart', 1, False),
        'inf_initial': get('inf_initial', 1, 1.0),
        'inf_sd_initial': get('inf_sd_initial', 1, 0.0),
    }
    return {'prior': prior, 'posterior': posterior}


def set_nml_array_value(input_nml_path, group, var, index, value):
    """
    Set one element of a Fortran namelist array in place.

    Used to turn inf_initial_from_restart off for a bootstrap cycle.  Only the
    named element changes; the other element and all surrounding text are
    preserved.  Handles values continued across lines the same way
    parse_inflation_settings does.  Raises KeyError if group/var is absent.
    """
    def to_fortran(v):
        if isinstance(v, bool):
            return '.true.' if v else '.false.'
        return str(v)

    with open(input_nml_path) as f:
        lines = f.readlines()

    current = None
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('&'):
            current = stripped[1:].strip()
            i += 1
            continue
        if stripped.startswith('/'):
            current = None
            i += 1
            continue

        match = re.match(rf'(\s*){re.escape(var)}\s*=\s*(.+)', lines[i]) \
            if current == group else None
        if match is None:
            i += 1
            continue

        indent, raw = match.group(1), match.group(2).strip()
        start = i
        i += 1
        # Consume continuation lines, mirroring parse_fortran_namelist.
        while raw.rstrip().endswith(',') and i < len(lines):
            nxt = lines[i].strip()
            if nxt.startswith('/') or nxt.startswith('&') or \
                    ('=' in nxt and not nxt.startswith("'")):
                break
            i += 1
            if not nxt or nxt.startswith('!'):
                continue
            raw += ' ' + nxt

        elements = [e.strip() for e in raw.rstrip(',').split(',')]
        while len(elements) <= index:
            elements.append(elements[-1])
        elements[index] = to_fortran(value)
        lines[start:i] = [f"{indent}{var} = {', '.join(elements)}\n"]

        with open(input_nml_path, 'w') as f:
            f.writelines(lines)
        return

    raise KeyError(f"{var} not found in &{group} of {input_nml_path}")


def get_nml_bool(input_nml_path, group, var, default=False):
    """
    Read a scalar boolean namelist value.

    Used to check what the user set perturb_from_single_instance to in
    user_nl_dart, before deciding whether cycle 0 should turn it on. Returns
    `default` if the group or variable is absent. Assumes the value is on a
    single line, true for every scalar filter_nml value the template
    generator writes; unlike set_nml_array_value this does not handle
    continuation lines, since there is nothing to continue for a scalar.
    """
    with open(input_nml_path) as f:
        lines = f.readlines()

    current = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('&'):
            current = stripped[1:].strip()
            continue
        if stripped.startswith('/'):
            current = None
            continue
        if current != group:
            continue
        match = re.match(rf'\s*{re.escape(var)}\s*=\s*(.+)', line)
        if match:
            value = match.group(1).strip().rstrip(',').strip()
            return value.lower() in ('.true.', 't')

    return default


def set_perturb_from_single_instance(rundir, cycle):
    """
    Restrict filter_nml:perturb_from_single_instance to cycle 0.

    perturb_from_single_instance only ever turns on if the user has already
    set it to .true. in user_nl_dart (e.g. for a tutorial multi-instance
    case where every instance starts from an identical restart). When it
    does, it applies on cycle 0 only: from cycle 1 onward the instances have
    diverged through assimilation, so it is forced back to .false.
    regardless of the user's setting. If the user left it .false. (the
    template default), this is a no-op on every cycle.

    The edit lands in the input.nml this cycle already staged via
    stage_dart_input_nml and does not persist: that file is recopied from
    Buildconf/dartconf at the top of every cycle, so the user's original
    setting -- not this cycle's masked value -- is what gets read again next
    cycle.

    Keys off `cycle`, not file presence -- unlike the inflation bootstrap
    (see stage_inflation_files), this does not guard against a job
    resubmission also starting at cycle 0. A resubmit mid-experiment with
    perturb_from_single_instance left .true. in user_nl_dart will re-perturb
    from instance 1, discarding accumulated ensemble spread. See the caveat
    in user_nl_dart and docs/assimilate.md.
    """
    try:
        cycle_int = int(cycle)
    except (ValueError, TypeError):
        logger.warning(
            f"Cycle '{cycle}' is not an integer, "
            "leaving perturb_from_single_instance unchanged"
        )
        return
    input_nml = os.path.join(rundir, "input.nml")
    user_wants_perturb = get_nml_bool(
        input_nml, "filter_nml", "perturb_from_single_instance"
    )
    perturb = user_wants_perturb and cycle_int == 0
    set_nml_array_value(
        input_nml, "filter_nml", "perturb_from_single_instance", 0, perturb
    )
    logger.info(
        f"Set perturb_from_single_instance = {perturb} for cycle {cycle_int}"
    )


# DART's inflation namelist arrays have two columns: the first is prior
# inflation, the second posterior (DART/guide/inflation.rst).  Index into those
# arrays is the position in _INFLATION below.  Note this is not the inflation
# 'flavor' -- flavor is inf_flavor, the inflation scheme (0 none, 2 spatially
# varying, 3 spatially constant, 4 RTPS, 5 enhanced), a separate axis that
# applies to prior and posterior independently.
_INFLATION = ("prior", "posterior")

# Token filter builds inflation file names from: input_priorinf_mean.nc etc.
_INFLATION_FILE_TOKEN = {"prior": "priorinf", "posterior": "postinf"}

# The bootstrap cycle starts inflation from the case's own inf_initial /
# inf_sd_initial, which is what those namelist variables already mean: the values
# used when inflation is not read from a restart (adaptive_inflate_mod.f90:261).
# Set them in user_nl_dart, or per component in user_nl_dart_{comp}.  Because
# every later cycle reads inflation from the restart file instead, they take
# effect on the first cycle only.


def inflation_restart_pattern(case_name, comp, token, field):
    """Glob pattern for the archived inflation restarts written by
    rename_stage_files() at the end of a previous cycle.  `token` is a
    _INFLATION_FILE_TOKEN value: 'priorinf' or 'postinf'."""
    return f"{case_name}.dart.rh.{comp}_output_{token}_{field}.*.nc"


def stage_inflation_files(case, comp, rundir):
    """
    Symlink the newest archived inflation restart for `comp` onto the fixed
    names filter expects (input_priorinf_mean.nc etc.).

    Sources are $CASE.dart.rh.{comp}_output_*inf_*.nc, written by the previous
    cycle's rename_stage_files().  Because every component runs filter in the
    same RUNDIR and DART hardwires the input_* names, staging per component is
    what keeps one component's inflation from being read by another.

    If prior or posterior inflation is requested from restart but no file exists,
    this is the first assimilation for that component: inf_*_from_restart is
    turned off for that column in the
    staged input.nml for this cycle only, so filter initialises inflation from
    the case's own inf_initial / inf_sd_initial and writes a restart the next
    cycle can use.  Those namelist values therefore apply to the first cycle
    only.  The edit is discarded when stage_dart_input_nml re-copies
    input.nml.{comp} at the top of the next cycle.

    Returns the list of staged paths.
    """
    input_nml = os.path.join(rundir, "input.nml")
    if not os.path.exists(input_nml):
        raise FileNotFoundError(f"input.nml not found in {rundir}")

    case_name = case.get_value("CASE")
    settings = parse_inflation_settings(input_nml)
    staged = []

    for idx, inflation in enumerate(_INFLATION):
        token = _INFLATION_FILE_TOKEN[inflation]
        s = settings[inflation]
        if s['inf_flavor'] <= 0:
            continue
        wanted = [field for field, flag in
                  (("mean", 'inf_initial_from_restart'),
                   ("sd", 'inf_sd_initial_from_restart'))
                  if s[flag]]
        if not wanted:
            continue

        # Newest wins.  YYYY-MM-DD-SSSSS sorts chronologically, so a plain
        # lexical sort is enough whether st_archive has pruned or not.
        found = {}
        for field in ("mean", "sd"):
            matches = sorted(glob.glob(os.path.join(
                rundir, inflation_restart_pattern(case_name, comp, token, field))))
            if matches:
                found[field] = matches[-1]

        if not found:
            logger.warning(
                f"{comp}: {inflation} inflation requested from restart but no "
                f"file matches "
                f"{inflation_restart_pattern(case_name, comp, token, '{mean,sd}')}"
                f" in {rundir}.  Treating this as the first assimilation for "
                f"'{comp}': starting {inflation} inflation from the case's own "
                f"namelist values inf_initial = {s['inf_initial']}, "
                f"inf_sd_initial = {s['inf_sd_initial']}, for this cycle only.  "
                f"Later cycles read inflation from the restart this cycle writes."
            )
            # Only the from_restart flags change.  inf_initial / inf_sd_initial
            # already mean 'the values to use when not reading a restart', so the
            # case's own settings are what the first cycle should start from.
            for var in ("inf_initial_from_restart", "inf_sd_initial_from_restart"):
                set_nml_array_value(input_nml, "filter_nml", var, idx, False)
            if s['inf_sd_initial'] <= 0:
                logger.warning(
                    f"{comp}: inf_sd_initial for {inflation} inflation is "
                    f"{s['inf_sd_initial']}, so inflation will be time-constant "
                    f"at inf_initial = {s['inf_initial']} for the whole run, not "
                    f"just this cycle: the zero is written into "
                    f"output_{token}_sd.nc and later cycles read their sd from "
                    f"that file rather than from the namelist, so "
                    f"update_inflation keeps returning early "
                    f"(adaptive_inflate_mod.f90, inflate_sd <= 0).  Set "
                    f"inf_sd_initial > 0 in user_nl_dart (0.6 is the usual "
                    f"starting value) for adaptive inflation."
                )
            continue

        missing = [f for f in wanted if f not in found]
        if missing:
            raise FileNotFoundError(
                f"{comp}: incomplete {inflation} inflation restart set in "
                f"{rundir}. Found {sorted(found)} but not {missing}.  Refusing "
                f"to bootstrap because discarding a partial set would silently "
                f"reset inflation."
            )

        for field in wanted:
            dst = os.path.join(rundir, f"input_{token}_{field}.nc")
            _make_symlink(found[field], dst)
            staged.append(dst)

    return staged


def unstage_inflation_files(rundir):
    """
    Remove the inflation staging symlinks created by stage_inflation_files().

    Runs after filter so a component whose staging was skipped cannot silently
    read the previous component's inflation.  Only symlinks are removed; a real
    file of the same name is left alone and reported.
    """
    for token in _INFLATION_FILE_TOKEN.values():
        for field in ("mean", "sd"):
            path = os.path.join(rundir, f"input_{token}_{field}.nc")
            if os.path.islink(path):
                os.remove(path)
                logger.debug(f"Removed inflation staging symlink {path}")
            elif os.path.exists(path):
                logger.warning(
                    f"{path} is a regular file, not a staging symlink; leaving it "
                    f"in place. It will not be archived."
                )


# ---------------------------------------------------------------------------
# Post-filter file renaming
# ---------------------------------------------------------------------------

def rename_dart_logs(case, comp, model_time, rundir):
    """Rename dart_log.out / dart_log.nml to $CASE.dart.log.{comp}.{date}.{out,nml}.
    The '.log.' piece routes them to $DOUT_S_ROOT/logs/ via st_archive's
    standard log file handling."""
    case_name = case.get_value("CASE")
    date_str = (f"{model_time.year:04}-{model_time.month:02}"
                f"-{model_time.day:02}-{model_time.seconds:05}")
    for suffix in ["out", "nml"]:
        src = os.path.join(rundir, f"dart_log.{suffix}")
        if os.path.exists(src):
            dst = os.path.join(
                rundir, f"{case_name}.dart.log.{comp}.{date_str}.{suffix}")
            os.rename(src, dst)
            logger.info(f"Renamed {src} to {dst}")


def rename_obs_seq_final(case, comp, model_time, rundir):
    """Rename obs_seq.final to $CASE.dart.{comp}_obs_seq_final.{date} so
    st_archive moves it to $DOUT_S_ROOT/esp/hist/."""
    case_name = case.get_value("CASE")
    src = os.path.join(rundir, "obs_seq.final")
    if not os.path.exists(src):
        raise FileNotFoundError(f"obs_seq.final not found in {rundir}")
    date_str = (f"{model_time.year:04}-{model_time.month:02}"
                f"-{model_time.day:02}-{model_time.seconds:05}")
    dst = os.path.join(
        rundir, f"{case_name}.dart.{comp}_obs_seq_final.{date_str}")
    os.rename(src, dst)
    logger.info(f"Renamed obs_seq.final to {dst}")


def rename_stage_files(case, comp, model_time, rundir):
    """
    Rename filter stage output files (forecast, preassim, postassim, analysis,
    output, input) to $CASE.dart.{comp}_{stage}_{member}.{date}.nc so
    st_archive moves them to $DOUT_S_ROOT/esp/hist/.

    Exceptions:
    - output_*inf*.nc become $CASE.dart.rh.{comp}_{...}.{date}.nc: the 'rh'
      extension makes st_archive treat them as restart files, so the newest set
      is copied (not moved) to $DOUT_S_ROOT/rest/<date>/ and left in the run
      directory, while older sets are pruned from it (unless
      DOUT_S_SAVE_INTERIM_RESTART_FILES).  That leaves exactly one dated set per
      component for the next cycle's stage_inflation_files() to symlink onto the
      input_* name filter reads.  Note output_mean / output_sd contain no 'inf'
      and so stay history files.
    - input_*inf*.nc are skipped.  These are stage_inflation_files()' staging
      symlinks, and they are still present here: unstage_inflation_files() runs
      in run_filter_for_component's finally block, i.e. after this function, so
      that a failed filter cannot leave a stale link behind.  Renaming them
      would rename the link, so st_archive would copy the previous cycle's
      inflation into esp/hist/ every cycle and unstage would no longer find it
      under the expected name.  The pattern is deliberately narrow: with 'input'
      in stages_to_write, filter also writes input_mean.nc / input_sd.nc /
      input_member_0001.nc, which contain no 'inf' and are correctly archived as
      history diagnostics.
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
                if fnmatch.fnmatch(base, "output_*inf*"):
                    new_name = f"{case_name}.dart.rh.{comp}_{base}.{date_str}.nc"
                else:
                    new_name = f"{case_name}.dart.{comp}_{base}.{date_str}.nc"
                new_path = os.path.join(rundir, new_name)
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

def run_filter_for_component(case, comp, caseroot, cycle, use_mpi=True):
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

    # Stage per-component DART input.nml (input.nml.{comp} -> input.nml)
    stage_dart_input_nml(case, rundir, comp)

    # If perturb_from_single_instance=.true. set true for cycle 0 only (tutorial
    # multi-instance cases start bit-identical); off for every later cycle.
    set_perturb_from_single_instance(rundir, cycle)

    # Verify required files
    check_required_files(rundir)

    # Build filter_input/output_list.txt from rpointer files
    set_restart_files(rundir, dart_info["rpointer_prefix"], model_time)

    # Component-specific template symlinks
    _SET_TEMPLATE_FILES[comp](case, rundir)

    # Run pre-filter converter programs (e.g. cice_to_dart) for each member
    run_model_programs_for_members(
        case, comp, dart_info.get("pre_filter_programs", []), exeroot, rundir
    )

    # Stage this component's inflation restarts onto the fixed input_* names
    # If there are no inflation restarts,  state_inflation_files 
    # changes the input.nml in the RUNDIR to inf_from_restart = .false.
    # Note, this does not change the buildnml input.nml which is copied in 
    # in stage_dart_input_nml(case, rundir, comp)
    stage_inflation_files(case, comp, rundir)

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

        # Run post-filter converter programs (e.g. dart_to_cice) for each member
        run_model_programs_for_members(
            case, comp, dart_info.get("post_filter_programs", []), exeroot, rundir
        )

        rename_dart_logs(case, comp, model_time, rundir)
        rename_obs_seq_final(case, comp, model_time, rundir)
        rename_stage_files(case, comp, model_time, rundir)

    except subprocess.CalledProcessError as e:
        logger.error(f"filter_{comp} failed with return code {e.returncode}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise
    finally:
        # Drop the inflation staging symlinks unconditionally, so a failed
        # filter cannot leave a stale link to this component's inflation where
        # another component would pick it up.  This runs after
        # rename_stage_files on the success path, which is fine: that function
        # skips input_*inf* by design, so the links are simply left for us.
        # What was linked is already in the log from _make_symlink, so nothing
        # is lost for a post-mortem.
        unstage_inflation_files(rundir)

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
            run_filter_for_component(case, comp, caseroot, cycle, use_mpi=use_mpi)
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
