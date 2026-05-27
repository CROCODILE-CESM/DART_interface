```

CIME case.setup
└── buildnml(case, caseroot, "dart")
    ├── get_active_da_components(case)          [dart_cesm_components]
    ├── consistency_checks()
    ├── gen_DART_input_nml()
    │   ├── get_active_da_components(case)
    │   ├── parse_fortran_namelist(user_nl_dart)
    │   └── for each comp:
    │       ├── DART_input_nml.from_json(template_path)  [dart_input_nml]
    │       │   └── ParamGen.from_json()                 [CIME]
    │       └── DART_input_nml.write(input.nml.{comp}, case)
    │           ├── ParamGen.reduce()                    [CIME]
    │           ├── _convert_lists_to_strings()
    │           └── ParamGen.write_nml()                 [CIME]
    ├── gen_input_obs_data_list()
    │   ├── DART_input_data_list.from_json()    [dart_input_data_list]
    │   └── DART_input_data_list.write(dart.input_data_list, case)
    │       └── ParamGen.reduce()                        [CIME]
    ├── set_cesm_data_assimilation_options()
    │   └── get_active_da_components(case)
    └── stage_sampling_error_correction(input_nml)

CIME case.build
└── buildlib(caseroot, libroot, bldroot)
    └── CESM_DART_config(case)
        ├── get_active_da_components(case)      [dart_cesm_components]
        ├── get_dart_model(comp, case)          [dart_cesm_components]
        ├── _stage_clean_script(...)
        │   └── parse_model_serial_programs()   [dart_cesm_components]
        └── for each missing comp:
            └── _build_dart_for_component(comp, ...)
                ├── _build_preprocess_nml(comp, ...)
                │   └── DART_COMPONENTS[comp]
                └── parse_model_serial_programs()   [dart_cesm_components]
                    (then runs quickbuild.sh as subprocess)

CIME model advance (each cycle)
└── assimilate(caseroot, cycle)
    ├── get_active_da_components(case)          [dart_cesm_components]
    ├── copy_geometry_file_for_cycle0(case, rundir, cycle)
    │   └── get_active_da_components(case)
    └── for each comp:
        └── run_filter_for_component(case, comp, caseroot)
            ├── get_model_time(case)
            │   └── get_model_time_from_filename(rpointer)
            ├── get_observations(case, comp, model_time, rundir)
            ├── backup_model_input_nml(rundir)    [if input_nml_conflict]
            ├── stage_dart_input_nml(case, rundir, comp)
            ├── check_required_files(rundir)
            ├── set_restart_files(rundir, prefix, model_time)
            │   └── find_files_for_model_time(rundir, prefix, model_time)
            ├── _SET_TEMPLATE_FILES[comp](case, rundir)
            │   ├── set_template_files_ocn()  → _make_symlink()
            │   ├── set_template_files_atm()  → _make_symlink()
            │   ├── set_template_files_lnd()  (no-op)
            │   └── set_template_files_ice()  (no-op)
            ├── run_model_programs_for_members(pre_filter_programs)
            ├── stage_inflation_files(rundir)
            │   └── parse_inflation_settings(input.nml)
            ├── subprocess: filter_{comp}
            ├── run_model_programs_for_members(post_filter_programs)
            ├── rename_dart_logs()
            ├── rename_obs_seq_final()
            ├── rename_inflation_files()
            ├── rename_stage_files()
            └── restore_model_input_nml(rundir) [if input_nml_conflict, in finally]

```
