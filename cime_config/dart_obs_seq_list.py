import os, sys, re

_CIMEROOT = os.getenv("CIMEROOT")
sys.path.append(os.path.join(_CIMEROOT, "scripts", "Tools"))

from dart_cesm_components import get_active_da_components

_OBS_SEQ_RE = re.compile(r"obs_seq\.0Z\.(\d{8})$")


class DART_obs_seq_list:
    """Generates Buildconf/dart.input_data_list: observation sequence files
    available for each active DA component.

    One section is written per active component:
      DATA_ASSIMILATION_OCN == True  ->  ocn_obs_seq entries
      DATA_ASSIMILATION_ATM == True  ->  atm_obs_seq entries
      DATA_ASSIMILATION_LND == True  ->  lnd_obs_seq entries
      DATA_ASSIMILATION_ICE == True  ->  ice_obs_seq entries

    Observation files are found by recursively scanning
    $DART_OBS_ROOT/{comp}_obs_seq/ for filenames matching
    obs_seq.0Z.YYYYMMDD. There is no constraint on the directory structure
    above the filename, so an observation archive can be organized however
    is convenient -- flat, YYYYMM/, YYYY/MM/, a source-named subfolder, etc.

    The base directory for all observation files is DART_OBS_ROOT. If
    DART_OBS_ROOT is UNSET (the default), it falls back to
    $DIN_LOC_ROOT/esp/dart. Override with:
        ./xmlchange DART_OBS_ROOT=/path/to/obs
    """

    def write(self, output_path, case):
        dart_obs_root = case.get_value("DART_OBS_ROOT")
        if not dart_obs_root or dart_obs_root == "UNSET":
            dart_obs_root = os.path.join(case.get_value("DIN_LOC_ROOT"), "esp", "dart")
        dart_obs_root = os.path.abspath(dart_obs_root)

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

        with open(output_path, 'w') as f:
            for comp in get_active_da_components(case):
                category = f"{comp}_obs_seq"
                comp_dir = os.path.join(dart_obs_root, category)
                found = []
                for root, _dirs, files in os.walk(comp_dir):
                    for name in files:
                        match = _OBS_SEQ_RE.search(name)
                        if not match:
                            continue
                        file_year = int(match.group(1)[:4])
                        if not (run_startyear <= file_year <= run_endyear):
                            continue
                        found.append(os.path.join(root, name))
                for i, file_path in enumerate(sorted(found)):
                    f.write(f"{category}({i}) = {file_path}\n")
