# Observations

```{contents} Table of Contents
:depth: 1
:local:
```

## Overview

DART needs an observation sequence file (`obs_seq.out`) for each active DA
component, for each assimilation cycle. Finding the right file for a given
component and date happens in two stages:

1. **Build time** -- `buildnml` scans the observation archive and writes a
   manifest of every observation sequence file it found for each active
   component, one line per file, to `Buildconf/dart.input_data_list`.
2. **Run time** -- for each active component, `assimilate.py` looks up the
   entry in that manifest matching the component and the current model date,
   and symlinks it into the run directory as `obs_seq.out`.

## Directory layout and naming convention

Observation sequence files live under a single root directory,
`$DART_OBS_ROOT`, in one subdirectory per component:

```
$DART_OBS_ROOT/
├── ocn_obs_seq/
├── atm_obs_seq/
├── lnd_obs_seq/
└── ice_obs_seq/
```

Within a component's directory, `DART_obs_seq_list` (`cime_config/dart_obs_seq_list.py`)
recursively scans for files whose name matches `obs_seq.0Z.YYYYMMDD` --
**there is no constraint on the directory structure above the filename**.
A flat directory, `YYYYMM/`, `YYYY/MM/`, or a source-named subfolder (e.g.
`WOD13/` for the World Ocean Database obs that ship with CESM, or a
`CrocoLake/` folder for your own archive) all work with no configuration.

Only the `{comp}_obs_seq/` top level and the `obs_seq.0Z.YYYYMMDD` filename
pattern are fixed. An archive using a different filename convention needs
either renaming to match, or editing the matching logic in
`DART_obs_seq_list.write` (build time) and `get_observations` in
`cime_config/assimilate.py` (run time).

## User options

### `DART_OBS_ROOT`

Root directory for all observation sequence files.

```
./xmlchange DART_OBS_ROOT=/path/to/obs
```

Defaults to `UNSET`, in which case `$DIN_LOC_ROOT/esp/dart` is used instead.

### `DATA_ASSIMILATION_OCN` / `ATM` / `LND` / `ICE`

Which components' observation manifests are built, and whose `filter` runs
each cycle. See [Case Options](running_dart_as_a_cesm_component.md#case-options)
and [Running without DA (spin-up)](running_dart_as_a_cesm_component.md#running-without-da-spin-up).

### `RUN_STARTDATE`

Used two ways:

- At build time, together with `STOP_OPTION`/`STOP_N`, to bound which years'
  observation files are worth listing in the manifest (files outside the
  run's date range are dropped rather than written out).
- At run time, to match the model's current date against the manifest for
  each cycle.

```{note}
Start date is important, as this is used to match observations to model
output. Change the start date to match the observations you want to
assimilate. The date format is YYYY-MM-DD.
```

### Observation types: `&obs_kind_nml`

Which observation *types* `filter` assimilates or evaluates is independent
of which files are found -- it's controlled by the `&obs_kind_nml` namelist
(`assimilate_these_obs_types`, `evaluate_these_obs_types`,
`use_precomputed_fos_these_obs_types`), set via `user_nl_dart` or
`user_nl_dart_{comp}`. See
[Changing namelist options with user_nl_dart](running_dart_as_a_cesm_component.md#changing-namelist-options-with-user_nl_dart)
and
[Component specific namelist options](running_dart_as_a_cesm_component.md#component-specific-namelist-options).

Which observation *kinds* a component's `filter_{comp}` binary can recognize
at all is fixed at build time, from that component's registered obs-type and
quantity modules -- see
[Multi-component design](multi_component_design.md) for how these are
registered per component.

## Inspecting the observation manifest

The full list of observation sequence files DART considers available for
the run is written to:

```
Buildconf/dart.input_data_list
```

Each line has the form `{comp}_obs_seq(N) = /absolute/path/to/obs_seq.0Z.YYYYMMDD`.
This is useful for checking what will be staged before submitting, or for
debugging why a cycle found no observations.

## No observations for a cycle

If no observation sequence file matches a component's date for a given
cycle, that component's `filter` step is skipped for that cycle only --
other active components still run normally. Any `obs_seq.out` left over
from a previous cycle is removed first, so a stale symlink can't be mistaken
for the current window's observations.

See [get_observations](assimilate.md#observation-staging) and
[run_filter_for_component](assimilate.md#per-component-filter-run) in [assimilate.py](assimilate.md) for the
full mechanics.
