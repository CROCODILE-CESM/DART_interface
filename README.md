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

Errors out:
  ERROR: When DART is active, the model calendar must be GREGORIAN.
  Q. Should the calendar be set to Gregorian, rather than the user needing to set ./xmlchange CALENDAR=GREGORIAN
