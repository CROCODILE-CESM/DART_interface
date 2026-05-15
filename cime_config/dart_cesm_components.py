"""
Component registry for CESM DART interface.

Maps each DATA_ASSIMILATION_* component key to the DART model name and all
model-specific properties needed by buildlib, buildnml, and assimilate.py.
"""
import os
import re

DART_COMPONENTS = {
    "ocn": {
        "dart_model": "MOM6",
        "ninst_var": "NINST_OCN",
        "ntasks_var": "NTASKS_OCN",
        "rpointer_prefix": "ocn",
        "obs_type_files": [
            "obs_def_ocean_mod.f90",
        ],
        "quantity_files": [
            "ocean_quantities_mod.f90",
        ],
        # MOM6 and DART both use a file called input.nml; it must be backed up
        # before filter runs and restored afterwards.
        "input_nml_conflict": True,
        # Full input_nml JSON template for this component, relative to
        # param_templates/json/.  Generated from the model's work/input.nml
        # using the same toolchain as the MOM6 template.
        "input_nml_model": "input_nml_MOM6.json",
        "pre_filter_programs": [],
        "post_filter_programs": [],
    },
    "atm": {
        "dart_model": None,
        "dart_model_map": {
            "fv": "cam-fv",
            "se": "cam-se",
        },
        "ninst_var": "NINST_ATM",
        "ntasks_var": "NTASKS_ATM",
        "rpointer_prefix": "atm",
        "obs_type_files": [
            "obs_def_gps_mod.f90",
            "obs_def_upper_atm_mod.f90",
            "obs_def_reanalysis_bufr_mod.f90",
            "obs_def_altimeter_mod.f90",
        ],
        "quantity_files": [
            "atmosphere_quantities_mod.f90",
            "space_quantities_mod.f90",
            "chemistry_quantities_mod.f90",
        ],
        "input_nml_conflict": False,
        # ATM has two possible dycores; input_nml_model is resolved at build time
        # via input_nml_model_map using the case's CAM_DYCORE value.
        "input_nml_model": None,
        "input_nml_model_map": {
            "fv": "input_nml_camfv.json",
            "se": "input_nml_camse.json",
        },
        "pre_filter_programs": [],
        "post_filter_programs": [],
    },
    "lnd": {
        "dart_model": "clm",
        "ninst_var": "NINST_LND",
        "ntasks_var": "NTASKS_LND",
        "rpointer_prefix": "lnd",
        "obs_type_files": [
            "obs_def_land_mod.f90",
            "obs_def_tower_mod.f90",
            "obs_def_COSMOS_mod.f90",
        ],
        "quantity_files": [
            "land_quantities_mod.f90",
            "space_quantities_mod.f90",
            "atmosphere_quantities_mod.f90",
        ],
        "input_nml_conflict": False,
        "input_nml_model": "input_nml_clm.json",
        "pre_filter_programs": [
            "clm_to_dart",
        ],
        "post_filter_programs": [
            "dart_to_clm",
        ],
    },
    "ice": {
        "dart_model": "cice",
        "ninst_var": "NINST_ICE",
        "ntasks_var": "NTASKS_ICE",
        "rpointer_prefix": "ice",
        "obs_type_files": [
            "obs_def_cice_mod.f90",
        ],
        "quantity_files": [
            "seaice_quantities_mod.f90",
            "ocean_quantities_mod.f90",
        ],
        "input_nml_conflict": False,
        "input_nml_model": "input_nml_cice.json",
        "pre_filter_programs": [
            "cice_to_dart",
        ],
        "post_filter_programs": [
            "dart_to_cice",
        ],
    },
}

# Ordered list of all component keys — iteration order matters for filter runs.
COMPONENT_KEYS = ["ocn", "atm", "lnd", "ice"]


def get_active_da_components(case):
    """Return ordered list of component keys for which DATA_ASSIMILATION_* is True."""
    return [
        comp
        for comp in COMPONENT_KEYS
        if case.get_value(f"DATA_ASSIMILATION_{comp.upper()}") is True
    ]


def get_dart_model(comp, case):
    """Return the DART model name for a component, resolving dycore maps if needed."""
    info = DART_COMPONENTS[comp]
    dart_model = info.get("dart_model")
    if dart_model is not None:
        return dart_model
    dycore_map = info.get("dart_model_map", {})
    dycore = case.get_value("CAM_DYCORE")
    if dycore not in dycore_map:
        raise ValueError(
            f"Unknown CAM_DYCORE '{dycore}' for component '{comp}'. "
            f"Expected one of: {list(dycore_map.keys())}"
        )
    return dycore_map[dycore]


def parse_model_serial_programs(dart_model, core_dartroot):
    """Parse model_serial_programs from DART/models/{dart_model}/work/quickbuild.sh."""
    quickbuild = os.path.join(core_dartroot, "models", dart_model, "work", "quickbuild.sh")
    if not os.path.exists(quickbuild):
        return []
    with open(quickbuild) as f:
        content = f.read()
    m = re.search(r'model_serial_programs=\(\s*(.*?)\s*\)', content, re.DOTALL)
    if not m:
        return []
    return [p.strip() for p in m.group(1).split() if p.strip()]
