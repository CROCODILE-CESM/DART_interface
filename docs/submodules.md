# Required Repositories

The CESM branch used for development and testing of the DART-CESM interface is `full_regional_cesm_da` on a 
the CROCODILE fork of the `CESM` repository: https://github.com/CROCODILE-CESM/CESM.git 
This branch is based on CESM 3.0 and includes modifications to support DART assimilation. 

**CESM:** The Community Earth System Model  
https://github.com/hkershaw-brown/CESM/tree/dart-cesm3.0-alphabranch  
Branch: `full_regional_cesm_da`

Compared to CESM, the CESM DA development branch `full_regional_cesm_da` has different git submodules for CIME, CMEPS, and additionally the DART_interface repository itself. The submodules are set to specific branches and tags that are compatible with the CESM modifications for DART assimilation.

The `full_regional_cesm_da` takes care of setting the following submodules:

**CMEPS:** NUOPC based Community Mediator for Earth Prediction Systems  
https://github.com/hkershaw-brown/CMEPS.git  
Branch: `dart-cmeps1.1.48`  
Tag: `vdart-cmeps1.1.48`

**DART_interface** (this repository)  
https://github.com/CROCODILE-CESM/DART_interface.git  
Branch: `main`  
Tag: `croc-0.0.5` 

**CIME:** The Common Infrastructure for Modeling the Earth  
https://github.com/hkershaw-brown/cime  
Branch: `dart-cime6.2.2`  
Tag: `vdart-cime6.2.2`  
