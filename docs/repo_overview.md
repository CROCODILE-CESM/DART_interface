# Repository Overview

The DART_interface includes:

- **CIME integration scripts** (`cime_config/`) - Scripts to run DART assimilation within CESM workflows
- **Parameter template tools** (`param_templates/`) - Utilities for managing DART configuration files
- **Build templates** (`cesm_build_templates/`) - Templates for building DART with CESM
- **NUOPC driver** (`nuopc_driver/`) - NUOPC component interface for DART. This is a dummy interface as DART is not a NUOPC component.
- **Test suite** (`tests/`) - Automated tests for assimilation scripts

## Key Components

### `cime_config/assimilate.py`
The main data assimilation script that:
- Stages DART input files and observations
- Manages MOM6 restart files for ensemble members
- Runs the DART filter executable
- Handles file backup and restoration to avoid naming conflicts between component models and DART

### `cime_config/buildnml`
CIME script that generates DART namelists and configuration files during case setup. This script is called automatically by CESM during the `case.setup` and `case.build` phases, and is called by `preview_namelists`.

**Key responsibilities:**
- **Configuration validation** - Verifies calendar is set to GREGORIAN (required by DART)
- **Namelist generation** - Creates `input.nml` from JSON templates with case-specific values:
  - Sets ensemble size (`ens_size`) to match the number of instances
  - Merges user customizations from `user_nl_dart` (common to all components) and optionally `user_nl_dart_{comp}` (component-specific, takes precedence) into the template
  - Includes a custom Fortran namelist parser to handle user overrides
- **Variable configuration** - Sets CESM XML variables:
  - `DATA_ASSIMILATION_SCRIPT` - Points to `assimilate.py`
  - `NTASKS_ESP` - Sets number of tasks for DART equal to the number of tasks used for the ocean component.
- **File staging** - Copies sampling error correction table if needed (for ensemble sizes 3-200)
- **Input data list** - Generates list of required observational data files

For each active DA component, the script reads from the corresponding `param_templates/json/input_nml_{comp}.json` template, 
applies any common overrides from `user_nl_dart` and any component-specific overrides from `user_nl_dart_{comp}` (e.g. `user_nl_dart_cam`, 
`user_nl_dart_ocn`), and writes to `Buildconf/dartconf/input.nml.{comp}`.

You can run `./preview_namelists --comp esp` to create `Buildconf/dartconf/input.nml` without running a full case setup.

### `cime_config/buildlib`
CIME script that builds the DART executables and creates the DART library during `case.build`.

**Key responsibilities:**
- **Compiler configuration** - Selects appropriate `mkmf.template` based on compiler (Intel or GNU)
- **Multi-component support** - Builds DART executables independently for each active DA component (ocean, atmosphere, land, sea-ice), each in its own `build_{comp}/` subdirectory to avoid object-file conflicts
- **Per-component DART executables** - For each active component builds:
  - `filter_{comp}` - Main assimilation executable
  - `perfect_model_obs_{comp}` - Creates synthetic observations from model state
  - `fill_inflation_restart_{comp}` - Utility to create restart files for inflation parameters
- **Model-specific serial programs** - Some models require additional converter programs that run before and after `filter`. These are built and installed to `$EXEROOT/esp/`:
  - CLM (land): `clm_to_dart`, `dart_to_clm`
  - CICE (sea-ice): `cice_to_dart`, `dart_to_cice`
- **Preprocess** - Writes a per-component `input.nml` containing only that component's obs types and quantities, then runs DART's `preprocess` program to generate the obs kind/def modules before compilation
- **Quickbuild automation** - Stages and executes a customised `quickbuild.sh` for each component:
  - Substitutes absolute path for the DART source directory
  - Injects model-specific serial programs into `model_serial_programs`
  - Modifies `mkmf` to use parallel make (`-j 8`) for faster compilation
- **Clean support** - Stages a `clean_build` script at `$EXEROOT/esp/` so that CIME's `cleanesp` Makefile target removes all DART executables and build directories
- **Library creation** - Builds a minimal `libesp.a` library containing the NUOPC driver stub
- **Validation** - Checks that `DATA_ASSIMILATION_CYCLES` is greater than 0

The build process places executables in `$EXEROOT/esp/` where they can be accessed during the assimilation cycle.

### Parameter Template Tools (`param_templates/`)

DART has a large number of configurable parameters, many of which have default values defined in the Fortran source code. To manage these parameters and generate the necessary configuration files for CESM, this repository includes several scripts:

**`extract_namelist_defaults.py`**  
Extracts default namelist values from DART Fortran source files using the fparser2 library. This script parses `.f90` files to identify namelist declarations and their default values, outputting them in Fortran namelist format.

**`process_makefile_f90.sh`**  
Bash script that extracts all `.f90` source files listed in the DART Makefile.$MODEL.* files and calls `extract_namelist_defaults.py` on each source file to generate a complete `input.nml` file with default values for all DART modules.


The 'Makefile.MOM6.filter' included in this repository was created by running `quickbuild.sh filter` in the MOM6 DART model work directory.

The input.nml generated by `process_makefile_f90.sh` has to be **hand edited** to have
sensible defaults for DART-MOM6|CICE|CLM|CAM-SE. 
Sensible defaults are needed in the input.nml so every user-settable option is set, allowing these options to be changed with user_nl_dart.

The model state variables in model_nml for MOM6 have been set to:

```
 model_state_variables = 'Salt', 'QTY_SALINITY ', 'UPDATE',
                          'Temp', 'QTY_POTENTIAL_TEMPERATURE', 'UPDATE',
                          'u', 'QTY_U_CURRENT_COMPONENT ', 'UPDATE',
                          'v', 'QTY_V_CURRENT_COMPONENT ', 'UPDATE',
                          'h', 'QTY_LAYER_THICKNESS ', 'UPDATE',
```

The observation kinds to be assimilated in obs_kind_nml have been set to:

```
&obs_kind_nml
  assimilate_these_obs_types = 'FLOAT_SALINITY',
                               'FLOAT_TEMPERATURE',
                               'DRIFTER_SALINITY',
                               'DRIFTER_TEMPERATURE',
                               'GLIDER_SALINITY',
                               'GLIDER_TEMPERATURE',
                               'MOORING_SALINITY',
                               'MOORING_TEMPERATURE',
                               'BOTTLE_SALINITY',
                               'BOTTLE_TEMPERATURE',
                               'CTD_SALINITY',
                               'CTD_TEMPERATURE',
                               'XCTD_SALINITY',
                               'XCTD_TEMPERATURE',
                               'XBT_TEMPERATURE',
                               'APB_TEMPERATURE',
```

 

**`nml_to_json.py`**  
Converts Fortran namelist files (`input.nml`) to JSON format (`input_nml.json`). Uses the f90nml library to parse namelists and wraps each value in a `{'values': value}` structure for compatibility with CESM parameter management.
The intermediate YAML file is saved, but the final output is a JSON file that can be used in the CESM case setup process.

## Testing

The repository includes a pytest suite for the assimilation scripts:

```bash
cd tests
pytest test_assimilate.py -v
```

Tests use mocking to simulate CIME dependencies and verify correct behavior without requiring a full CESM installation.

## Known Issues

- **Calendar Requirement:** When DART is active, the model calendar must be set to GREGORIAN. Users currently need to manually run `./xmlchange CALENDAR=GREGORIAN`. Consider automating this in future versions? Let people run with a NOLEAP calendar for synthetic obs?
