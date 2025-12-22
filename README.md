# DART_interface
CESM-DART interface for MOM6 CROCODILE

Repos needed:

CESM: The Community Earth System Model  
https://github.com/hkershaw-brown/CESM.git  
dart-cesm3.0-alphabranch  

CMEPS: NUOPC based Community Mediator for Earth Prediction Systems
https://github.com/hkershaw-brown/CMEPS.git   
branch: dart-cmeps1.1.17  
tag: vdart-cmeps1.1.17  

DART_interface (this repo)
https://github.com/CROCODILE-CESM/DART_interface.git  
branch: main  
tag: croc-0.0.1   

Tools in DART_interface:
- extract_namelist_defaults.py : Extracts default namelist values from a Fortran source file.
- process_makefile_f90.sh : Extract the .f90 files from a DART Makefile then call `extract_namelist_defaults.py` on each file to create a namelist defaults input.nml file for DART. 

To create an input.nml from the DART source code, run

```
./process_makefile_f90.sh > input.nml 2>err     
```

The makefile Makefile.mom6.filter was created with the following commands:

```
cd $DART_interface/DART/models/MOM6/work
./quickbuid.sh filter
```



Errors out:  
  ERROR: When DART is active, the model calendar must be GREGORIAN.  
  Q. Should the calendar be set to Gregorian, rather than the user needing to set ./xmlchange CALENDAR=GREGORIAN
