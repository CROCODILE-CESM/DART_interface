# Multi-Component DART Interface Design

## Architectural Context

DART's `filter` executable is compiled against a single `model_mod.f90`. This is the fundamental constraint: **one filter binary per active DA component**. Multi-component DA runs each component's filter sequentially. The current interface builds one `filter` for MOM6; the new interface must build and run `filter_ocn`, `filter_atm`, `filter_lnd`, and `filter_ice` as needed.

Which components have DA active is determined by the CESM case XML variables:
- `DATA_ASSIMILATION_OCN` — ocean (MOM6)
- `DATA_ASSIMILATION_ATM` — atmosphere (CAM-SE)
- `DATA_ASSIMILATION_LND` — land (CLM)
- `DATA_ASSIMILATION_ICE` — sea ice (CICE)

---

## Phase 1 — Component Registry

**New file: `cime_config/dart_cesm_components.py`**

A single source of truth mapping each CESM `DATA_ASSIMILATION_*` key to all model-specific properties. This is read by `buildlib`, `buildnml`, and `assimilate.py`.

```python
DART_COMPONENTS = {
    "ocn": {
        "dart_model": "MOM6",
        "ninst_var":  "NINST_OCN",
        "ntasks_var": "NTASKS_OCN",
        "rpointer_prefix": "ocn",
        "obs_type_files": ["obs_def_ocean_mod.f90"],
        "quantity_files": ["ocean_quantities_mod.f90"],
        "input_nml_conflict": True,   # MOM6 and DART both write input.nml
    },
    "atm": {
        "dart_model": "cam-se",
        "ninst_var":  "NINST_ATM",
        "ntasks_var": "NTASKS_ATM",
        "rpointer_prefix": "atm",
        "obs_type_files": ["obs_def_gps_mod.f90", "obs_def_upper_atm_mod.f90",
                           "obs_def_reanalysis_bufr_mod.f90", "obs_def_altimeter_mod.f90"],
        "quantity_files": ["atmosphere_quantities_mod.f90", "space_quantities_mod.f90",
                           "chemistry_quantities_mod.f90"],
        "input_nml_conflict": False,
    },
    "lnd": {
        "dart_model": "clm",
        "ninst_var":  "NINST_LND",
        "ntasks_var": "NTASKS_LND",
        "rpointer_prefix": "lnd",
        "obs_type_files": ["obs_def_land_mod.f90", "obs_def_tower_mod.f90",
                           "obs_def_COSMOS_mod.f90"],
        "quantity_files": ["land_quantities_mod.f90", "space_quantities_mod.f90",
                           "atmosphere_quantities_mod.f90"],
        "input_nml_conflict": False,
    },
    "ice": {
        "dart_model": "cice",
        "ninst_var":  "NINST_ICE",
        "ntasks_var": "NTASKS_ICE",
        "rpointer_prefix": "ice",
        "obs_type_files": ["obs_def_cice_mod.f90"],
        "quantity_files": ["seaice_quantities_mod.f90", "ocean_quantities_mod.f90"],
        "input_nml_conflict": False,
    },
}
```

---

## Phase 2 — `buildlib` Changes

**File: `cime_config/buildlib`** — `CESM_DART_config()`

| What is hardcoded now | Generalisation |
|---|---|
| `MODEL=MOM6` in quickbuild.sh | Iterate active DA components; substitute `MODEL` from registry |
| Single `preprocess_input.nml` with ocean obs types | Generate per-component `preprocess_input_{comp}.nml`; for multi-component, merge all `obs_type_files` and `quantity_files` lists into one file (preprocess runs once; obs types are additive) |
| Single `filter` executable | Build in a per-component subdirectory; copy result as `filter_{comp}` into `exeroot/esp/` |
| `NTASKS_ESP = NTASKS_OCN` | `NTASKS_ESP = max(NTASKS_{comp})` over active DA components |

**File: `cesm_build_templates/quickbuild.sh`**

Make `MODEL` and `EXTRA` substitutable via environment variables. Change:

```bash
MODEL=MOM6
```

to:

```bash
MODEL=${DART_MODEL:?'DART_MODEL env var must be set'}
EXTRA=${DART_EXTRA:-}   # optional, only needed for cam-se
```

`buildlib` sets `DART_MODEL` and `DART_EXTRA` before invoking `quickbuild.sh` for each component.

**New files: `cesm_build_templates/preprocess_input_{comp}.nml`**

One template per component (`ocn`, `atm`, `lnd`, `ice`) with the correct `obs_type_files` / `quantity_files` taken from the registry. `buildlib` picks the right one, or merges them when multiple components are active.

---

## Phase 3 — `buildnml` Changes

**File: `cime_config/buildnml`**

| Location | Current | Change |
|---|---|---|
| `gen_DART_input_nml` — `ens_size` | `ninst_ocn` | Use `case.get_value(registry[comp]["ninst_var"])` for the first active DA component. Add consistency check that all active components have equal `NINST`. |
| `set_cesm_data_assimilation_options` — `NTASKS_ESP` | `NTASKS_OCN` | `max(case.get_value(registry[comp]["ntasks_var"]) for comp in active_comps)` |
| `stage_sampling_error_correction` — ensemble size check | `ninst_ocn` | Use the same generalised `ens_size` variable |

**File: `cime_config/dart_input_data_list.py`**

Remove the assertion:

```python
assert n_da_comp==0 or (n_da_comp==1 and data_assimilation["ocn"] is True)
```

Replace with per-component iteration over active DA components.

**File: `param_templates/input_data_list.yaml`**

Add entries for each component, guarded by their respective `DATA_ASSIMILATION_*` flag:

```yaml
dart.input_data_list:
    ocn_obs_seq:
        $DATA_ASSIMILATION_OCN == True:
            = [...]   # existing WOD13 entries
    atm_obs_seq:
        $DATA_ASSIMILATION_ATM == True:
            = [f"${DIN_LOC_ROOT}/esp/dart/atm_obs_seq/..."]
    lnd_obs_seq:
        $DATA_ASSIMILATION_LND == True:
            = [f"${DIN_LOC_ROOT}/esp/dart/lnd_obs_seq/..."]
    ice_obs_seq:
        $DATA_ASSIMILATION_ICE == True:
            = [f"${DIN_LOC_ROOT}/esp/dart/ice_obs_seq/..."]
```

**File: `param_templates/DART_params.yaml`**

Generalise `BASEOBSDIR` to have per-component conditional values.

---

## Phase 4 — `assimilate.py` Changes

The per-component logic is cleanly separated. The main `assimilate()` loop calls `run_filter_for_component()` for each active DA component.

### Functions to generalise

| Function | Current | Change |
|---|---|---|
| `set_restart_files(rundir, model_time)` | Hardcodes `"ocn"` as rpointer prefix | Add `comp` argument; look up prefix from registry |
| `set_template_files(case, rundir)` | MOM6-specific symlinks (`mom6.r.nc`, `mom6.static.nc`) | Dispatch by component to per-component implementations |
| `get_observations(case, model_time, rundir)` | Searches only for `ocn_obs_seq` in data list | Add `comp` argument; search for `{comp}_obs_seq` |
| `run_filter(case, caseroot, use_mpi)` | Single `filter` binary | Rename to `run_filter_for_component(case, comp, caseroot, use_mpi)`; use `filter_{comp}` binary |
| `backup_mom_input_nml` / `clean_up` | Always called | Guard with `if registry[comp]["input_nml_conflict"]` |
| `copy_geometry_file_for_cycle0` | Always called | Guard as MOM6-only |

### Component-specific template file functions to add

- `set_template_files_atm(case, rundir)` — symlinks for `caminput.nc` and `cam_phis.nc` (from `rpointer.atm_*`)
- `set_template_files_lnd(case, rundir)` — CLM restarts (pattern: `{case}.clm2_{inst}.r.{timestamp}.nc`)
- `set_template_files_ice(case, rundir)` — CICE restarts (pattern: `{case}.cice_{inst}.r.{timestamp}.nc`)

### New `assimilate()` main loop

```python
def assimilate(caseroot, cycle, rundir=None, use_mpi=True):
    with Case(caseroot) as case:
        if rundir is None:
            rundir = case.get_value("RUNDIR")
        active_comps = get_active_da_components(case)
        for comp in active_comps:
            run_filter_for_component(case, comp, caseroot, use_mpi=use_mpi)
```

---

## Phase 5 — Tests

Update `tests/test_assimilate.py` to cover:

- Single-component cases: OCN-only, ATM-only, LND-only, ICE-only
- A two-component case (e.g., OCN+ICE) verifying both filters are invoked in sequence
- `dart_input_data_list.py` multi-component obs list generation

---

## Summary of Files Changed

| File | Change |
|---|---|
| **new** `cime_config/dart_cesm_components.py` | Component registry |
| `cime_config/buildlib` | Per-component build loop; parameterised quickbuild.sh; merged preprocess |
| `cime_config/buildnml` | Use registry for ens_size, NTASKS_ESP, sampling error check |
| `cime_config/dart_input_data_list.py` | Remove OCN-only assertion; iterate active components |
| `cime_config/assimilate.py` | Dispatch all per-component operations; guarded MOM6 cleanup |
| `cesm_build_templates/quickbuild.sh` | `MODEL` and `EXTRA` read from environment variables |
| **new** `cesm_build_templates/preprocess_input_atm.nml` | CAM-SE preprocess template |
| **new** `cesm_build_templates/preprocess_input_lnd.nml` | CLM preprocess template |
| **new** `cesm_build_templates/preprocess_input_ice.nml` | CICE preprocess template |
| `param_templates/input_data_list.yaml` | Add `atm_obs_seq`, `lnd_obs_seq`, `ice_obs_seq` sections |
| `param_templates/DART_params.yaml` | Generalise `BASEOBSDIR` per component |
