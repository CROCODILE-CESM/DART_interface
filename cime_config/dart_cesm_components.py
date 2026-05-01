"""
Component registry for CESM DART interface.

Maps each DATA_ASSIMILATION_* component key to the DART model name and all
model-specific properties needed by buildlib, buildnml, and assimilate.py.
"""

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
        "model_serial_programs": [],
    },
    "atm": {
        "dart_model": "cam-se",
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
        "model_serial_programs": [
            "column_rand",
        ],
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
        "model_serial_programs": [
            "clm_to_dart",
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
        "model_serial_programs": [
            "cice_to_dart",
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
