
# Running DART as a CESM component

Welcome to the DART_interface user documentation!

```{contents} Table of Contents
:depth: 1
:local:
```

## Introduction

This documentation will guide you through the process of running DART within the CESM CIME framework. 

The goal of the DART_interface is to allow "out-of-the-box" DA setup and execution for CESM models, within the ./case.setup, case.build, and case.submit workflow. This means that you can set up and run a data assimilation case with DART using the standard CESM workflow, without needing to manually configure DART or write custom scripts.


We will cover how to get the code, create a case, set up the case, how to change CESM options and DART namelist options, and finally run the case with data assimilation!

Please note that the _science_ of Data Assimilation is never "out-of-the-box" particularly for coupled Earth system models. You will need to have some understanding of how DART works and how to configure it for your specific use case. This documentation is meant to guide you through the technical process of running DART within CESM, but it is not a tutorial on how to do data assimilation or how to configure DART for your specific use case.
For more information on Data Assimilation with DART, visit the [docs.dart.ucar.edu](https://docs.dart.ucar.edu).





## Get the code

You will need to clone the CESM repository and check out the branch with DART support. The branch is called `dart-cesm3.0-alphabranch`. After checking out the branch, you will need to run `git-fleximod update` to download all the CESM components.

```
git clone https://github.com/hkershaw-brown/CESM.git CESM_DA
cd CESM_DA/  
./bin/git-fleximod update  
```

## Create a case

### Compset choice
To use data assimilation you will need to set up a DA enabled compset. The `G_DA` compset is a good choice for testing because it used NYR forcing which does not take long to initialize. You can use `G_JRA_DA` but his will have a 40 minute initialization cost on your first cycle. 

DART requires multiple instances of the model, which are the number of ensemble members in DART. Specify the number of ensemble members X with `--ninst X` along with `--multi-driver` for multiple instances.

In the example below we are creating a case with 3 ensemble members.

```
./cime/scripts/create_newcase \
                    --run-unsupported \
                    --res TL319_t232 \ 
                    --compset G_DA \
                    --case /glade/work/$USER/da-cases/da-mom6-test.0001 \
                    --ninst 3 --multi-driver --project P86850054

```

`--run-unsupported`: This flag allows you to create a case that is not officially supported by the CESM team. This is necessary for using DART as a component because it is not yet an officially supported configuration.

`--res TL319_t232`: This is the resolution of the model. TL319 is the atmospheric resolution and t232 is the ocean resolution.  

`--compset G_DA`: This specifies the component set to use. G_DA is a data assimilation component set that includes the necessary components for running DART.  

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
./case.setup --reset  
```

```{note}
Start date is important, as this is used to match observations to model output. Change the start date to match the observations you want to assimilate. The date format is YYYY-MM-DD.
```


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

The dart input.nml created by preview_namelists is in 

```
Buildconf/dartconf/input.nml
```

To take a look at DATA_ASSIMILATION variables set in the case:

```
./xmlquery --partial DATA_ASS
```

DART is the ESP component:

```
./xmlquery --partial ESP
```

Edit user_nl_dart   

```
vim user_nl_dart
```


Run:

```
./case.submit
```

