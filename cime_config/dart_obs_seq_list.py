import os, sys, re

_CIMEROOT = os.getenv("CIMEROOT")
sys.path.append(os.path.join(_CIMEROOT, "scripts", "Tools"))

from CIME.ParamGen.paramgen import ParamGen


class DART_obs_seq_list(ParamGen):
    """Generates Buildconf/dart.input_data_list: observation sequence files
    required by DART for each active DA component.

    One section is written per active component:
      DATA_ASSIMILATION_OCN == True  ->  ocn_obs_seq entries
      DATA_ASSIMILATION_ATM == True  ->  atm_obs_seq entries
      DATA_ASSIMILATION_LND == True  ->  lnd_obs_seq entries
      DATA_ASSIMILATION_ICE == True  ->  ice_obs_seq entries

    The base directory for all observation files is DART_OBS_ROOT.
    If DART_OBS_ROOT is UNSET (the default), it falls back to
    $DIN_LOC_ROOT/esp/dart.  Override with:
        ./xmlchange DART_OBS_ROOT=/path/to/obs
    """

    def write(self, output_path, case):
        dart_obs_root = case.get_value("DART_OBS_ROOT")
        if not dart_obs_root or dart_obs_root == "UNSET":
            din_loc_root = case.get_value("DIN_LOC_ROOT")
            dart_obs_root = os.path.join(din_loc_root, "esp", "dart")

        def resolve(varname):
            if varname == "DART_OBS_ROOT":
                return dart_obs_root
            return case.get_value(varname)

        self.reduce(resolve)

        run_startdate = case.get_value("RUN_STARTDATE")
        run_startyear = int(run_startdate[:4])

        stop_option = case.get_value("STOP_OPTION").strip()
        stop_n = int(case.get_value("STOP_N"))
        upper_run_duration_sec = 0.0 + \
            ( \
                (stop_option == "nseconds") * 1 + \
                (stop_option == "nminutes") * 60 + \
                (stop_option == "nhours") * 3600 + \
                (stop_option == "ndays") * 86400 + \
                (stop_option == "nmonths") * 86400 * 31 + \
                (stop_option == "nyears") * 86400 * 366 \
            ) * stop_n

        assert upper_run_duration_sec > 0, \
            "DART namelist generator couldn't determine the run duration. This is likely " + \
            "due to an unsupported STOP_OPTION selection."

        run_endyear = int(run_startyear + upper_run_duration_sec / (86400 * 360))

        with open(os.path.join(output_path), 'w') as f:
            for file_category, file_paths in self.data['dart.input_data_list'].items():
                if file_paths is not None:
                    if not isinstance(file_paths, list):
                        file_paths = [file_paths]
                    for i, file_path in enumerate(file_paths):
                        file_path = file_path.replace('"', '').replace("'", "")
                        basename = os.path.basename(file_path)
                        year_match = re.search(r'(\d{4})', basename)
                        if year_match:
                            file_year = int(year_match.group(1))
                            if not (run_startyear <= file_year <= run_endyear):
                                continue
                        if os.path.isabs(file_path):
                            f.write(f"{file_category.strip()}({str(i)}) = {file_path}\n")
