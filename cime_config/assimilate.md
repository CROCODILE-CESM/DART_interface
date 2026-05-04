# assimilate.py

CIME data assimilation script called by CESM at the end of each model advance.
CIME invokes it as:

```
assimilate.py <caseroot> <cycle>
```

It can also be run directly for testing:

```bash
python assimilate.py /path/to/caseroot 0
python assimilate.py /path/to/caseroot 0 --no-mpi
```

---

## Overview

For each active DA component (`DATA_ASSIMILATION_{OCN|ATM|LND|ICE}=TRUE`) the
script runs the DART `filter` executable built for that component, managing all
the file staging required before and after the run.

The order of operations for each component is:

1. Stage the observation sequence file (`obs_seq.out`)
2. Back up `input.nml` if there is a name clash with the model (MOM6 only)
3. Stage the per-component DART `input.nml.{comp}` as `input.nml`
4. Check required files are present (`input.nml`, `obs_seq.out`)
5. Build `filter_input_list.txt` / `filter_output_list.txt` from rpointer files
6. Create component-specific template symlinks
7. Run pre-filter converter programs for each ensemble member (e.g. `cice_to_dart`)
8. Verify inflation restart files are present (if inflation is configured)
9. Run `filter_{comp}` with MPI
10. Run post-filter converter programs for each ensemble member (e.g. `dart_to_cice`)
11. Rename output files (logs, `obs_seq.final`, inflation files, stage files)
12. Restore model `input.nml` if it was backed up (MOM6 only)

---

## Component Registry

The set of active components and their properties (rpointer prefix,
`input_nml_conflict` flag, etc.) comes from `dart_cesm_components.py`.
`get_active_da_components(case)` returns the ordered list of active component
keys (`ocn`, `atm`, `lnd`, `ice`) based on the case XML variables.

---

## Functions

### Utilities

#### `get_model_time_from_filename(filename)`
Extracts model time from a filename such as
`rpointer.ocn_0001.0001-01-02-00000`, returning a `ModelTime` namedtuple with
fields `year`, `month`, `day`, `seconds`.

#### `get_model_time(case)`
Gets the current model time from the `DRV_RESTART_POINTER` case XML variable.

#### `find_files_for_model_time(rundir, rpointer_prefix, model_time)`
Globs for `rpointer.{prefix}_*.{timestamp}` files in `rundir` matching the
given model time.

---

### Observation and Input Staging

#### `get_observations(case, comp, rundir)`
Finds the correct `obs_seq.out` for the component (by model time) and copies it
to `rundir`.

#### `stage_dart_input_nml(case, rundir, comp)`
Each component's filter requires its own `input.nml` (the model state variables,
obs kinds, and other settings differ per component).  `buildnml` generates a
file `Buildconf/dartconf/input.nml.{comp}` for every active component during
the build phase.  This function copies it into `rundir` as `input.nml`
immediately before running `filter_{comp}`.

---

### Model Converter Programs (Pre/Post Filter)

Some DART models require serial converter programs to translate between the
model's native restart format and DART's internal state-vector format.  These
are declared in `dart_cesm_components.py`:

| Component | Pre-filter | Post-filter |
|-----------|-----------|-------------|
| CLM (land) | `clm_to_dart` | `dart_to_clm` |
| CICE (ice) | `cice_to_dart` | `dart_to_cice` |
| MOM6, CAM-SE | — | — |

#### `run_model_programs_for_members(case, comp, programs, exeroot, rundir)`
Runs each listed program once per ensemble member (`NINST_{COMP}` times).
Members are numbered 1-based and zero-padded to 4 digits (`0001`, `0002`, …).
The instance number is passed to the program via the `DART_INSTANCE` environment
variable so it can locate its member-specific restart files.  Programs run
serially and any non-zero return code raises immediately.

**Execution order per component:**
```
cice_to_dart inst_0001
cice_to_dart inst_0002
...
filter_ice  (MPI, all members)
dart_to_cice inst_0001
dart_to_cice inst_0002
...
```

---


#### `set_restart_files(rundir, rpointer_prefix, model_time)`
Reads all matching rpointer files for the component and model time, concatenates
the restart file names listed in them into `filter_input_list.txt`, and copies
that to `filter_output_list.txt`.  DART reads these lists to find the ensemble
member restart files.

---

### Component-Specific Template Symlinks

Some DART `model_mod` implementations need specific files to be accessible under
fixed names.

#### `set_template_files_ocn(case, rundir)` — MOM6
- `mom6.r.nc` → first restart file from `filter_input_list.txt`
- `mom6.static.nc` → first `{casename}.mom6.h.static*` file

#### `set_template_files_atm(case, rundir)` — CAM-SE
- `caminput.nc` → first restart file from `filter_input_list.txt`
- `cam_phis.nc` → first `{casename}.cam*.i.*` file (surface geopotential)

#### `set_template_files_lnd` / `set_template_files_ice`
No extra symlinks required for CLM or CICE.

---

### MOM6 `input.nml` Conflict Handling

MOM6 and DART both use a file named `input.nml` in the run directory.

#### `backup_model_input_nml(rundir)`
Copies `input.nml` to `mom_input.nml.bak` before DART stages its own version.

#### `restore_model_input_nml(rundir)`
Restores `input.nml` from `mom_input.nml.bak` after `filter` completes.
Called in a `finally` block so restoration happens even if filter fails.

---

### Observation Staging

#### `get_observations(case, comp, model_time, rundir)`
Finds the correct observation sequence file for the component and model date by
scanning `Buildconf/dart.input_data_list` for lines tagged `{comp}_obs_seq`
matching the date pattern `obs_seq.0Z.{YYYYMMDD}`.  Symlinks the file into
`rundir` as `obs_seq.out`.

---

### Inflation File Handling

#### `parse_inflation_settings(input_nml_path)`
Parses `filter_nml` from the DART `input.nml` using a built-in Fortran namelist
parser.  Returns a dict with `prior` and `posterior` keys containing the
inflation flavour and restart flags.

#### `stage_inflation_files(rundir)`
If inflation is active and configured to read from restart (`inf_flavor > 0` and
`inf_initial_from_restart = .true.`), checks that the required files are present:
- `input_priorinf_mean.nc`, `input_priorinf_sd.nc`
- `input_postinf_mean.nc`, `input_postinf_sd.nc`

#### `rename_inflation_files(rundir)`
After filter runs, copies `output_{priorinf,postinf}_{mean,sd}.nc` to
`input_{priorinf,postinf}_{mean,sd}.nc` so they are ready for the next cycle.

---

### Post-Filter File Renaming

All output files are renamed to include the case name and model time so that
files from different cycles do not overwrite each other.

#### `rename_dart_logs(case, model_time, rundir)`
`dart_log.out` → `dart_log.{case}.{datetime}.out`
`dart_log.nml` → `dart_log.{case}.{datetime}.nml`

#### `rename_obs_seq_final(case, model_time, rundir)`
`obs_seq.final` → `obs_seq.final.{case}.{datetime}`

#### `rename_stage_files(case, model_time, rundir)`
Renames all `{stage}_{member}.nc` files (stages: `input`, `forecast`,
`preassim`, `postassim`, `analysis`, `output`) to
`{stage}_{member}.{case}.{datetime}.nc`.
Inflation input files (`input_*inf*.nc`) are skipped because they are consumed
by the next cycle.

---

### MOM6 Cycle-0 Geometry File

#### `copy_geometry_file_for_cycle0(case, rundir, cycle)`
MOM6 only writes `ocean_geometry.nc` on cycle 0.  This function copies
`{casename}.mom6.h.ocean_geometry*` to `ocean_geometry.nc` on cycle 0 so it is
available for subsequent cycles.

---

### Per-Component Filter Run

#### `run_filter_for_component(case, comp, caseroot, use_mpi=True)`
Orchestrates all of the above steps for a single component.  Runs
`$EXEROOT/esp/filter_{comp}` using the MPI run command from the case
(`MPI_RUN_COMMAND`) and number of tasks (`NTASKS_ESP`).

---

### Entry Points

#### `assimilate(caseroot, cycle, rundir=None, use_mpi=True)`
Main entry point called by CIME.  Iterates over active components and calls
`run_filter_for_component` for each.  Also calls
`copy_geometry_file_for_cycle0` before the component loop.

#### `main()`
Command-line entry point with `argparse`. Accepts `caseroot`, `cycle`, and
`--no-mpi` flag.
