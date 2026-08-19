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

1. Stage the observation sequence file (`obs_seq.out`). If no observation
   sequence exists for this component's window, all remaining steps below
   are skipped and `filter_{comp}` is not run this cycle.
2. Back up `input.nml` if there is a name clash with the model (MOM6 only)
3. Stage the per-component DART `input.nml.{comp}` as `input.nml`
4. Check required files are present (`input.nml`, `obs_seq.out`)
5. Build `filter_input_list.txt` / `filter_output_list.txt` from rpointer files
6. Create component-specific template symlinks
7. Run pre-filter converter programs for each ensemble member (e.g. `cice_to_dart`)
8. Stage this component's inflation restarts onto the fixed `input_*inf_*.nc`
   names filter reads, or turn `inf_*_from_restart` off for this cycle if there
   is no restart yet (first assimilation)
9. Run `filter_{comp}` with MPI
10. Run post-filter converter programs for each ensemble member (e.g. `dart_to_cice`)
11. Rename output files (logs, `obs_seq.final`, stage files, inflation restarts)
12. Remove the inflation staging symlinks — in a `finally` block, so a failed
    filter cannot leave a stale link behind
13. Restore model `input.nml` if it was backed up (MOM6 only)

Steps 12 and 13 are both in the `finally` block, so they run whether or not
filter succeeded.  Step 11 runs only on the success path, which is why the
renames precede the unstage.

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

### Input Staging

#### `stage_dart_input_nml(case, rundir, comp)`
Each component's filter requires its own `input.nml` (the model state variables,
obs kinds, and other settings differ per component).  `buildnml` generates a
file `Buildconf/dartconf/input.nml.{comp}` for every active component during
the build phase.  This function copies it into `rundir` as `input.nml`
immediately before running `filter_{comp}`.

Because this recopies the file at the top of every cycle, any runtime edit made
to `rundir/input.nml` lasts for one component-cycle only.  The inflation
bootstrap (below) relies on that.

#### `check_required_files(rundir)`
Raises `FileNotFoundError` unless both `input.nml` and `obs_seq.out` are present
in `rundir`.

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
`rundir` as `obs_seq.out` and returns `True`.

Returns `False` if no observation sequence matches this component/date (a
window with no observations is expected to happen sometimes). In that case
any `obs_seq.out` already in `rundir` -- e.g. a symlink left over from the
previous cycle -- is removed, so a stale file can never be mistaken for this
cycle's observations.

---

### Inflation File Handling

Inflation is the only DART file that has to survive from one cycle to the next:
filter writes `output_*inf_*.nc` at the end of cycle *N* and reads the same
fields back as `input_*inf_*.nc` at the start of cycle *N+1*.

Two facts make this awkward. DART hardwires those names relative to the current
working directory (`set_filename_info` in `filter_mod.f90`) with no namelist
override, and every component runs filter in the same `RUNDIR`. A single
untagged set of files therefore cannot represent more than one component.

The interface solves this by keeping the persistent copy **component tagged and
dated**, and treating the fixed names as transient staging symlinks:

```
$CASE.dart.rh.{comp}_output_{priorinf|postinf}_{mean|sd}.YYYY-MM-DD-SSSSS.nc
```

#### `parse_inflation_settings(input_nml_path)`
Parses `filter_nml` from the DART `input.nml` using a built-in Fortran namelist
parser.  Returns `{'prior': {...}, 'posterior': {...}}` — one entry per column of
DART's inflation namelist arrays — each containing `inf_flavor`,
`inf_initial_from_restart`, `inf_sd_initial_from_restart`, `inf_initial` and
`inf_sd_initial`.

Note `inf_flavor` is the inflation *scheme* (0 none, 2 spatially varying, 3
spatially constant, 4 RTPS, 5 enhanced), a separate axis from the prior/posterior
distinction, and it applies to each independently.

#### `inflation_restart_pattern(case_name, comp, token, field)`
Builds the glob for the archived restarts, where `token` is `priorinf` or
`postinf` and `field` is `mean` or `sd`.

#### `stage_inflation_files(case, comp, rundir)`
For each of prior and posterior, if that column has `inf_flavor > 0` and asks for
inflation from restart, globs `$CASE.dart.rh.{comp}_output_*` and symlinks the
newest match onto the fixed name filter reads.  Selection is by newest timestamp
rather than an rpointer file; `YYYY-MM-DD-SSSSS` sorts chronologically, so a
lexical sort suffices.  Returns the list of staged paths.

Only the fields actually requested are staged: `mean` if
`inf_initial_from_restart`, `sd` if `inf_sd_initial_from_restart`.

**First assimilation.** If a column asks for inflation from restart but no file
matches, this is the first cycle for that component. `inf_initial_from_restart`
and `inf_sd_initial_from_restart` are set `.false.` for that column in the staged
`input.nml` only, so filter initialises inflation from the case's own
`inf_initial` / `inf_sd_initial` and writes a restart the next cycle can use.
Those namelist values therefore apply to the **first cycle only** — see
`user_nl_dart` for the user-facing description.

Nothing has to set the flags back: `stage_dart_input_nml` recopies
`input.nml.{comp}` at the top of the next cycle, so the edit does not persist,
and `Buildconf/dartconf/input.nml.{comp}` is never written to.

Detection is by absence of a restart file, **not** `cycle == 0`, which is true at
the start of every submission. Evaluation is per column, so enabling posterior
inflation partway through an experiment bootstraps only the posterior and leaves
accumulated prior inflation intact. A half present set (mean but not sd) raises
rather than bootstrapping, since bootstrapping would discard real inflation
state.

A warning is logged if inflation is on but `inf_sd_initial <= 0`.
`update_inflation` returns early when `inflate_sd <= 0` and the `sd_lower_bound`
clamp is downstream of that guard, so the zero is written into the inflation
restart and every later cycle reads sd from that file rather than from the
namelist: inflation stays time-constant for the whole run, not just the first
cycle. The shipped templates default to `0.0`.

#### `unstage_inflation_files(rundir)`
Removes the `input_*inf_*.nc` staging symlinks.  Called from
`run_filter_for_component`'s `finally` block, so a failed filter cannot leave a
stale link to one component's inflation where another component would pick it
up.  Only symlinks are removed; a real file of the same name is left alone and
reported.

#### `set_nml_array_value(input_nml_path, group, var, index, value)`
Sets one element of a Fortran namelist array in place, preserving the other
element and all surrounding text, and handling values continued across lines.
Used by the bootstrap to flip a single `inf_*_from_restart` column, and by
`set_perturb_from_single_instance` below.  Raises `KeyError` if the group or
variable is absent.

#### `get_nml_bool(input_nml_path, group, var, default=False)`
Reads a scalar (non-array) boolean namelist value back out, returning
`default` if the group or variable is absent. Used by
`set_perturb_from_single_instance` below to check what the user set
`perturb_from_single_instance` to before deciding whether cycle 0 should
turn it on. Assumes the value is on a single line, unlike
`set_nml_array_value`, which has to handle array values continued across
lines.

---

### Ensemble Perturbation (cycle 0)

A tutorial multi-instance case starts every instance from an identical
restart, so the ensemble has no spread until something perturbs it. DART's
`filter_nml:perturb_from_single_instance` does this: when `.true.`, filter
reads only the first instance's restart and internally perturbs it into a
full ensemble, rather than reading all N per-instance restarts. No change is
needed to how `filter_input_list.txt` is built (`set_restart_files`) --
filter simply reads fewer lines of the same list
(`ninput_files = 1` in `filter_mod.f90` when `perturb_from_single_instance`
is set).

#### `set_perturb_from_single_instance(rundir, cycle)`
Called from `run_filter_for_component` right after `stage_dart_input_nml`.
Only ever turns perturbation on if the user already set
`filter_nml:perturb_from_single_instance = .true.` in `user_nl_dart`
(`get_nml_bool` reads that setting back from the just-staged `input.nml`
before deciding); it does not turn the flag on out of nowhere. Given the
user asked for it, the setting is then restricted to `cycle == 0`: `.true.`
on cycle 0, forced back to `.false.` on every cycle after via
`set_nml_array_value`, regardless of the user's setting. If the user left
it `.false.` (the template default), this is a no-op every cycle. Like the
inflation bootstrap, the edit lands in the `input.nml` already staged into
`RUNDIR` this cycle and does not persist: `stage_dart_input_nml` recopies
`input.nml.{comp}` from `Buildconf/dartconf` at the top of the next cycle,
so the user's original setting -- not this cycle's masked value -- is what
gets read again next cycle.

**This deliberately keys off `cycle`, not file presence**, unlike
`stage_inflation_files`. `cycle` counts within one job submission and is 0
at the start of every submission (see "First assimilation" above), so a job
resubmitted mid-experiment with `perturb_from_single_instance` still `.true.`
in `user_nl_dart` will hit `cycle == 0` again and re-perturb from instance 1,
discarding whatever ensemble spread assimilation had already built up. This
is the same ambiguity noted for `copy_geometry_file_for_cycle0` below;
`user_nl_dart` carries the corresponding warning to turn the setting back
off before resubmitting an in-progress experiment.

A non-integer `cycle` logs a warning and leaves `perturb_from_single_instance`
unchanged, mirroring `copy_geometry_file_for_cycle0`'s handling of the same
case.

---

### Post-Filter File Renaming

Filter writes fixed, unqualified names.  Every output is renamed to include the
case name, the component and the model time, so that files from different cycles
and different components do not overwrite each other, and so that `st_archive`
can classify them.  `{date}` below is `YYYY-MM-DD-SSSSS`.

#### `rename_dart_logs(case, comp, model_time, rundir)`
`dart_log.out` → `$CASE.dart.log.{comp}.{date}.out`
`dart_log.nml` → `$CASE.dart.log.{comp}.{date}.nml`

The `.log.` element is what routes these to `$DOUT_S_ROOT/logs/` via
`st_archive`'s standard log handling, so they need no `config_archive.xml` entry.

#### `rename_obs_seq_final(case, comp, model_time, rundir)`
`obs_seq.final` → `$CASE.dart.{comp}_obs_seq_final.{date}`

#### `rename_stage_files(case, comp, model_time, rundir)`
Renames all `{stage}_{member}.nc` files — stages `input`, `forecast`, `preassim`,
`postassim`, `analysis`, `output`; members `member*`, `mean`, `sd`, and the four
inflation fields — to `$CASE.dart.{comp}_{stage}_{member}.{date}.nc`, which
`st_archive` moves to `$DOUT_S_ROOT/esp/hist/`.

Two exceptions:

- **`output_*inf*.nc`** become `$CASE.dart.rh.{comp}_{...}.{date}.nc`.  The `rh`
  extension makes `st_archive` treat them as restarts rather than history, so the
  newest set is *copied* to `$DOUT_S_ROOT/rest/<date>/` and left in the run
  directory while older sets are pruned from it.  That leaves exactly one dated
  set per component for the next cycle's `stage_inflation_files` to find.
  `output_mean` / `output_sd` contain no `inf` and stay history files.
- **`input_*inf*.nc`** are skipped.  These are the staging symlinks, and they are
  still present at this point because `unstage_inflation_files` runs afterwards in
  the `finally` block.  Renaming them would rename the link, so `st_archive`
  would copy the previous cycle's inflation into `esp/hist/` every cycle.  The
  pattern is deliberately narrow: with `input` in `stages_to_write`, filter also
  writes `input_mean.nc` / `input_sd.nc` / `input_member_0001.nc`, which contain
  no `inf` and are correctly archived as history diagnostics.

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

Stages observations first.  If `get_observations` returns `False` (no
observation sequence for this component's window), every remaining step --
including `check_required_files`, inflation staging, and running filter --
is skipped and the function returns `False` immediately.  Otherwise, filter
and everything after it run inside a `try`, and the function returns `True`
on success.  A non-zero return code raises `subprocess.CalledProcessError`
after logging filter's stdout and stderr, which aborts the whole component
loop — no later component runs.  The `finally` block always runs
`unstage_inflation_files` and, for MOM6, `restore_model_input_nml` -- but
only once observations were staged and the rest of the setup ran; it does
not run on the no-observations early return, since nothing was staged or
backed up yet.

---

### Entry Points

#### `assimilate(caseroot, cycle, rundir=None, use_mpi=True)`
Main entry point called by CIME.  Iterates over active components and calls
`run_filter_for_component` for each, logging whether that component's filter
ran or was skipped for lack of observations this cycle.  Also calls
`copy_geometry_file_for_cycle0` before the component loop.

#### `main()`
Command-line entry point with `argparse`. Accepts `caseroot`, `cycle`, and
`--no-mpi` flag.

---

## Short-Term Archiver Contract

`cime_config/config_archive.xml` tells `st_archive` how to classify the files
named above.  The naming is not free — these constraints come from CIME's
matching logic in `CIME/case/case_st_archive.py` and `CIME/XML/archive_base.py`.

| declaration | value | effect |
|---|---|---|
| `rest_file_extension` | `rh` | `$CASE.dart.rh.*` are restarts: newest set copied to `rest/<date>/`, older pruned from `RUNDIR` |
| `hist_file_extension` | `\w+_\w+` | everything else `$CASE.dart.*` is history, moved to `esp/hist/` |
| `rest_history_varname` | `unset` | no history files are tied to restarts |
| `rpointer` | `unset` | DART writes no rpointer; inflation is selected by newest timestamp instead |

Three constraints worth knowing before changing any name:

1. **The restart extension must never contain an underscore.**  History matching
   is `dart\.` + `hist_file_extension`, unanchored.  An extension containing an
   underscore would also satisfy `\w+_\w+`, and the inflation restarts would be
   moved to `esp/hist/` instead of archived as restarts.
2. **Timestamps must match a coupler restart.**  `st_archive` discovers dates by
   globbing `$CASE.cpl.r.*.nc`.  A DART file stamped with any other date matches
   nothing and is silently left in `RUNDIR`.  Times come from
   `DRV_RESTART_POINTER`, so they agree by construction.
3. **The restart name must have no dots between `.rh.` and the date**, because
   restart matching is `_?\d*\.rh\.[^\.]*\.?<date>`.

`test_file_names` in the same file is a self-test fixture, not production
configuration.  Each `<tfile>` becomes a stub file whose contents are its
`disposition`; `st_archive` runs over them and every file is checked to have
ended up where that word says.  `copy` means it must remain in `RUNDIR` *and*
appear under `archive/`; `move` means gone from `RUNDIR` and present in
`archive/`; `ignore` means it stays put and must never be archived — which is
correct for `input_*inf_*.nc`, since those carry no `$CASE` prefix and no date and
so could not be attributed to a component or a cycle.

The `STARCHIVE` phase of every CIME system test calls `case.test_env_archive()`,
so `./create_test` on any DART test exercises this.
