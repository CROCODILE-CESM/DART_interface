
# Running DART as a CESM component

Welcome to the DART_interface user documentation!

Notes on creating, building and submitting a case

## Clone:  

```
git clone https://github.com/hkershaw-brown/CESM.git CESM_DA
cd CESM_DA/  
git checkout dart-cesm3.0-alphabranch  
./bin/git-fleximod update  
```

## Create case:  

`ninst` is the number of ensemble members, `multi-driver` is needed for multiple instances, and `project` is the allocation to charge for the run.

```
./cime/scripts/create_newcase --run-unsupported --res TL319_t232 --compset G_JRA_DA --case /glade/work/hkershaw/crocodile_dec2025/cases/da-mom6-test.0008 --ninst 3 --multi-driver --project P86850054 

```

```{note}
Start date is important for observations 
```

```
cd glade/work/hkershaw/crocodile_dec2025/cases/da-mom6-test.0008
./case.setup
./xmlchange CALENDAR=GREGORIAN 
./xmlchange DATA_ASSIMILATION_OCN=TRUE 
./xmlchange RUN_STARTDATE=2013-04-01
./case.setup --reset  

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
vim user_nml_dart
```


Run:

```
./case.submit
```

