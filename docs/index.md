% To build the docs
% cd docs
% sphinx-build -b html . _build/html

# DART_interface

Welcome to the documentation for the CESM-DART interface developed as part of [CROCODILE](https://github.com/CROCODILE-CESM), a collaboration between NCAR and WHOI.

The DART_interface provides the infrastructure to integrate the Data Assimilation Research Testbed (DART) with the Community Earth System Model (CESM). It supports data assimilation for multiple CESM components: ocean (MOM6), atmosphere (CAM-SE), land (CLM), and sea-ice (CICE), individually or in combination.

```{toctree}
:maxdepth: 2
:caption: User Documentation
running_dart_as_a_cesm_component
observations
```

```{toctree}
:maxdepth: 3
:caption: Developer Documentation
repo_overview
submodules
param_temp_use
assimilate
multi_component_design
call_tree
```


