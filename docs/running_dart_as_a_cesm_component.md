
# Running DART as a CESM component

Welcome to the DART_interface user documentation!

```{contents} Table of Contents
:depth: 1
:local:
```

## Introduction

This documentation will guide you through the process of running DART within the CESM CIME framework. 

The goal of the DART_interface is to allow "out-of-the-box" DA setup and execution for CESM models, within the `./case.setup`, `case.build`, and `case.submit` workflow. This means that you can set up and run a data assimilation case with DART using the standard CESM workflow, without needing to manually configure DART or write custom scripts.


We will cover how to get the code, create a case, set up the case, how to change CESM options and DART namelist options, and finally run the case with data assimilation!

Please note that the _science_ of Data Assimilation is never "out-of-the-box" particularly for coupled Earth system models. You will need to have some understanding of how DART works and how to configure it for your specific use case. This documentation is meant to guide you through the technical process of running DART within CESM, but it is not a tutorial on how to do data assimilation or how to configure DART for your specific use case.
For more information on Data Assimilation with DART, visit the [docs.dart.ucar.edu](https://docs.dart.ucar.edu).





## Get the code

You will need to clone the CROCODILE CESM repository and check out the branch with DART support. The branch is called `full_regional_cesm_da`. After checking out the branch, you will need to run `git-fleximod update` to download all the CESM components including DART.

```
git clone -b full_regional_cesm_da https://github.com/CROCODILE-CESM/CESM.git CESM_DA
cd CESM_DA/  
./bin/git-fleximod update  
```

## Create a case

### Compset choice
To use data assimilation you will need to set up a DA enabled compset.

You can see which compsets are available with DART using `query__config`:

```
cime/scripts/query_config --compsets dart
```

This will output something similar to:

```
Active component: dart
       --------------------------------------
       Compset Alias: Compset Long Name 
       --------------------------------------
   C_DA                 : 2000_DATM%NYF_SLND_MOM6_DROF%NYF_SGLC_SWAV_DART%1
   CR_JRA_DA            : 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_SROF_SGLC_SWAV_DART%1
   CR1850MARBL_JRA_DA   : 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL%MARBL-BIO_SROF_SGLC_SWAV_DART%1
   CR_JRA_GLOFAS_DA     : 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL_DROF%GLOFAS_SGLC_SWAV_DART%1
   CR1850MARBL_JRA_GLOFAS_DA : 1850_DATM%JRA_SLND_SICE_MOM6%REGIONAL%MARBL-BIO_DROF%GLOFAS_SGLC_SWAV_DART%1
   G_DA                 : 2000_DATM%NYF_SLND_CICE_MOM6_DROF%NYF_SGLC_SWAV_DART%1
   G_JRA_DA             : 2000_DATM%JRA-1p5-2023_SLND_CICE_MOM6_DROF%JRA-1p5-2023_SGLC_SWAV_DART%1
   GR_JRA_DA            : 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL_SROF_SGLC_SWAV_DART%1
   GR1850MARBL_JRA_DA   : 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL%MARBL-BIO_SROF_SGLC_SWAV_DART%1
   GR_JRA_GLOFAS_DA     : 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL_DROF%GLOFAS_SGLC_SWAV_DART%1
   GR1850MARBL_JRA_GLOFAS_DA : 1850_DATM%JRA_SLND_CICE_MOM6%REGIONAL%MARBL-BIO_DROF%GLOFAS_SGLC_SWAV_DART%1
```

If you are creating a regional CESM case with CrocoDash, follow the 
[CrocoDash instructions](https://crocodile-cesm.github.io/CrocoDash/latest/) to create
your CESM case. DART requires multiple instances of the model, which are the number of ensemble members in DART. Specify the number of ensemble members X with `--ninst X` along with `--multi-driver` for multiple instances.

If you are not using CrocoDash, you can follow the example below shows to create a case with a DA compset and 3 ensemble members using CESM's create_newcase.

```
./cime/scripts/create_newcase \
                    --run-unsupported \
                    --res T62_t232 \
                    --compset G_DA \
                    --case /glade/work/$USER/da-cases/da-mom6-test.0001 \
                    --ninst 3 --multi-driver --project P86850054

```

`--run-unsupported`: This flag allows you to create a case that is not officially supported by the CESM team. This is necessary for using DART as a component because it is not yet an officially supported configuration.

`--res T62_t232`: This is the resolution of the model. T62 is the atmospheric resolution and t232 is the ocean resolution.

`--compset G_DA`: This specifies the component set to use. G_DA is a G compset with data assimilation using DART.

`--case /glade/work/$USER/da-cases/da-mom6-test.0001` is the path where the case will be created. You can choose a different path if you prefer.  

`--ninst 3`: This specifies the number of instances (ensemble members) to run.  

`--multi-driver`: This flag indicates that the case will use multiple driver instances, which is necessary for 
running DART with multiple ensemble members.  

`--project P86850054`: This is the project code for the case, which is used for accounting purposes on the computing system. You should replace this with your own project code.  

### Set up the case

cd into the case directory and run `./case.setup` to set up the case. This will create the necessary directories and files for the case.

```
cd /glade/work/$USER/da-cases/da-mom6-test.0001
./case.setup
```

### Case Options

There are a few CESM options that need to be set for the case. These are set with `xmlchange` commands. The options are:

```
./xmlchange CALENDAR=GREGORIAN 
./xmlchange DATA_ASSIMILATION_OCN=TRUE 
./xmlchange RUN_STARTDATE=2013-04-01
./preview_namelists --component esp
./case.setup --reset  
```

`CALENDAR=GREGORIAN`: required when DART is active. The build stops with an error if the
calendar is anything else.

`DATA_ASSIMILATION_OCN=TRUE`: turns on assimilation for the ocean. Set
`DATA_ASSIMILATION_ATM`, `DATA_ASSIMILATION_LND` or `DATA_ASSIMILATION_ICE` to `TRUE` for
the other components. At least one of these must be `TRUE`, and all components with DA
enabled must have the same `NINST` (the same ensemble size).

`RUN_STARTDATE`: the start date of the run.

```{note}
Start date is important, as this is used to match observations to model output. Change the start date to match the observations you want to assimilate. The date format is YYYY-MM-DD.
```

`./preview_namelists --component esp` runs the DART `buildnml` on its own. Do this
**before** `./case.build`, because `buildnml` sets `NTASKS_ESP` (the number of tasks
DART runs `filter` on) to the largest `NTASKS` of the active DA components. `NTASKS_ESP`
lives in `env_mach_pes.xml`, which CESM locks when you run `./case.setup`. Running
`preview_namelists` now, followed by `./case.setup --reset`, gets `NTASKS_ESP` set and
`env_mach_pes.xml` re-locked while there is nothing built yet.

```{warning}
If you skip `preview_namelists`, `NTASKS_ESP` is instead changed part way through
`./case.build`, when CESM generates the namelists. The changed `env_mach_pes.xml` no
longer matches the locked copy, so `./case.submit` refuses to run and tells you to run
`./case.setup --reset`.  `./case.setup --reset` sets `BUILD_COMPLETE=FALSE`, so you then
have to build the whole case a second time.
```

`./case.setup --reset` picks up the xml changes above and re-locks `env_mach_pes.xml`.

You can query the options with `./xmlquery` to make sure they are set correctly:

```
./xmlquery CALENDAR
```

Or see all options with 
```
./xmlquery --listall
```

Or see matching options with
```
./xmlquery --partial DATA_ASSIM
```

DART is the ESP component, so its task count and root directory are the `ESP` variables:

```
./xmlquery --partial ESP
```



### Build the case

```
./case.build    
```


## Observation sequence files

The list of observation sequence files is in

```
Buildconf/dart.input_data_list
```

## DART input.nml

DART's runtime options are in a Fortran namelist file called `input.nml`. You do not edit
this file directly. Instead, DART's `buildnml` writes one `input.nml` per active DA
component, starting from a template of DART defaults for that component's model and
applying your changes from `user_nl_dart`.

The dart input.nml created by preview_namelists is in 

```
Buildconf/dartconf/input.nml.ocn
```

Since in this example we have set `DATA_ASSIMILATION_OCN=TRUE`, we are only assimilating ocean observations and therefore the input.nml file is `input.nml.ocn`. If you were assimilating atmosphere observations, the input.nml file would be `input.nml.atm` and so on for land and sea-ice.

During the run, `assimilate.py` copies `input.nml.{comp}` to `$RUNDIR/input.nml` before
running `filter_{comp}` for that component, once per component per assimilation cycle.

```{note}
MOM6 also reads a file called `input.nml`, in the same run directory. `assimilate.py`
backs the MOM6 file up as `mom_input.nml.bak` before staging DART's, and restores it when
`filter` has finished, so the `input.nml` you find in `$RUNDIR` after a run is MOM6's, not
DART's. Look in `Buildconf/dartconf/` for DART's.
```

### Changing namelist options with user_nl_dart

`./case.setup` puts a `user_nl_dart` in your case directory. Add the namelist groups and
variables you want to change, using normal Fortran namelist syntax:

```
&filter_nml
  inf_flavor = 5, 0
  inf_initial = 1.0, 1.0
  inf_sd_initial = 0.6, 0.0
/

&assim_tools_nml
  cutoff = 0.1
/
```

`user_nl_dart` applies to **all** active DA components.

### Component specific namelist options

The components assimilate different observations, of different quantities, at different
scales, so when running DA on mulitple components you will need to set some options 
per component rather than shared.
To set an option for one component only, create a `user_nl_dart_{comp}` file in your case
directory:

| File | Component | DART model |
| --- | --- | --- |
| `user_nl_dart_ocn` | ocean | MOM6 |
| `user_nl_dart_atm` | atmosphere | CAM (`CAM_DYCORE` selects `cam-fv` or `cam-se`) |
| `user_nl_dart_lnd` | land | CLM |
| `user_nl_dart_ice` | sea-ice | CICE |

```{note}
`./case.setup` creates `user_nl_dart` for you, but not the `user_nl_dart_{comp}` files.
Create the ones you need yourself, in `$CASEROOT`.
```

Values are merged variable by variable, in this order, last one wins:

1. the DART default for that component, from `param_templates/json/input_nml_{model}.json`
2. `user_nl_dart`
3. `user_nl_dart_{comp}`

So a `user_nl_dart_{comp}` file only needs to contain the variables that differ from
`user_nl_dart`; you can use both files together. For example, to use a 0.1 radian
localization everywhere except the ocean, where you want 0.05:

```
# user_nl_dart
&assim_tools_nml
  cutoff = 0.1
/
```

```
# user_nl_dart_ocn
&assim_tools_nml
  cutoff = 0.05
/
```

`input.nml.ocn` is then written with `cutoff = 0.05`, and every other active component
gets `cutoff = 0.1`.

### Namelist options you should not set

Some options are set from the case xml variables and are overwritten by `buildnml` after
your `user_nl_dart` changes are applied. Setting these in `user_nl_dart` has no effect:

| Namelist variable | Set from |
| --- | --- |
| `filter_nml:input_state_file_list` | fixed as `filter_input_list.txt`, written each cycle by `assimilate.py` |
| `filter_nml:output_state_file_list` | fixed as `filter_output_list.txt`, written each cycle by `assimilate.py` |
| `ensemble_manager_nml:tasks_per_node` | `MAX_TASKS_PER_NODE` |
| `ensemble_manager_nml:layout` | fixed at `2` |

```{warning}
Do not set `filter_nml:ens_size` in `user_nl_dart`. It is set from `NINST` of the active
DA components, but unlike the variables in the table above, a value in `user_nl_dart`
overrides it. That does not change the number of ensemble members CESM runs, it only
makes `input.nml` disagree with the case, and `filter` will fail. Change the ensemble
size with `--ninst` at `create_newcase` instead.
```

Only variables that already exist in the component's template can be set. A misspelled
variable, or one that belongs to a DART program that is not part of this component's
build, is skipped with a warning rather than being written to `input.nml`:

```text
Variable inf_sd_intial in filter_nml not found in template
Namelist filtr_nml not found in template
```

### Checking your changes

Regenerate the namelists and look at the result:

```
./preview_namelists --component esp
```

This rewrites `Buildconf/dartconf/input.nml.{comp}` and prints any of the warnings above,
so it is worth doing whenever you edit `user_nl_dart`. Namelist changes do **not** need a
rebuild: CESM regenerates the namelists during `./case.submit`.

### Inflation on the first cycle

When using `inf_initial_from_restart=.true.` and `inf_sd_initial_from_restart=.true.`, on the first cycle of a new case, 
there are no existing inflation files for filter to read. 

`assimilate.py` turns the `from_restart` flags off for the first cycle and `filter` starts from 
the nameslist values (e.g. 0.6, 0.6) for `inf_initial` and `inf_sd_initial`. 

Once the first inflation file exists, `inf_initial_from_restart` and
`inf_sd_initial_from_restart` are set back to `.true.`


```{warning}
`inf_sd_initial` must be greater than zero for inflation to adapt. With
`inf_sd_initial = 0.0`, which is the template default, the zero is written into the
inflation restart and read back on every subsequent cycle, so inflation stays fixed at
`inf_initial` for the whole run, not just the first cycle. `0.6` is a common starting
value. 
```

## Run the case

```
./case.submit
```

