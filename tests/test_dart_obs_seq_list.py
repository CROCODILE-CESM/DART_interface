#!/usr/bin/env python3

"""
Pytest suite for dart_obs_seq_list.py

Tests the filesystem-scan based discovery of observation sequence files
used to write Buildconf/dart.input_data_list.
"""

import os
import sys
from unittest.mock import Mock

os.environ.setdefault('CIMEROOT', '/mock/cimeroot')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cime_config'))

from dart_obs_seq_list import DART_obs_seq_list


def make_case(obs_root, active_comps=("ocn",), run_startdate="2005-01-01",
              stop_option="ndays", stop_n=10):
    values = {
        "DART_OBS_ROOT": obs_root,
        "DIN_LOC_ROOT": "/unused/din_loc_root",
        "RUN_STARTDATE": run_startdate,
        "STOP_OPTION": stop_option,
        "STOP_N": stop_n,
    }
    for comp in ("ocn", "atm", "lnd", "ice"):
        values[f"DATA_ASSIMILATION_{comp.upper()}"] = comp in active_comps

    case = Mock()
    case.get_value = lambda key: values[key]
    return case


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def read_manifest(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def test_finds_files_regardless_of_subdir_structure(tmp_path):
    obs_root = tmp_path / "obs"
    nested = obs_root / "ocn_obs_seq" / "WOD13" / "200501" / "obs_seq.0Z.20050102"
    flat = obs_root / "ocn_obs_seq" / "obs_seq.0Z.20050103"
    touch(str(nested))
    touch(str(flat))

    case = make_case(str(obs_root))
    output_path = tmp_path / "dart.input_data_list"
    DART_obs_seq_list().write(str(output_path), case)

    lines = read_manifest(str(output_path))
    assert any(str(nested) in line for line in lines)
    assert any(str(flat) in line for line in lines)


def test_filters_by_year_window(tmp_path):
    obs_root = tmp_path / "obs"
    in_window = obs_root / "ocn_obs_seq" / "obs_seq.0Z.20050105"
    out_of_window = obs_root / "ocn_obs_seq" / "obs_seq.0Z.19990105"
    touch(str(in_window))
    touch(str(out_of_window))

    case = make_case(str(obs_root), run_startdate="2005-01-01",
                      stop_option="ndays", stop_n=10)
    output_path = tmp_path / "dart.input_data_list"
    DART_obs_seq_list().write(str(output_path), case)

    lines = read_manifest(str(output_path))
    assert any(str(in_window) in line for line in lines)
    assert not any(str(out_of_window) in line for line in lines)


def test_only_active_components_included(tmp_path):
    obs_root = tmp_path / "obs"
    ocn_file = obs_root / "ocn_obs_seq" / "obs_seq.0Z.20050101"
    atm_file = obs_root / "atm_obs_seq" / "obs_seq.0Z.20050101"
    touch(str(ocn_file))
    touch(str(atm_file))

    case = make_case(str(obs_root), active_comps=("ocn",))
    output_path = tmp_path / "dart.input_data_list"
    DART_obs_seq_list().write(str(output_path), case)

    lines = read_manifest(str(output_path))
    assert any("ocn_obs_seq" in line for line in lines)
    assert not any("atm_obs_seq" in line for line in lines)


def test_non_matching_filenames_ignored(tmp_path):
    obs_root = tmp_path / "obs"
    good = obs_root / "ocn_obs_seq" / "obs_seq.0Z.20050101"
    bad = obs_root / "ocn_obs_seq" / "README.txt"
    touch(str(good))
    touch(str(bad))

    case = make_case(str(obs_root))
    output_path = tmp_path / "dart.input_data_list"
    DART_obs_seq_list().write(str(output_path), case)

    lines = read_manifest(str(output_path))
    assert len(lines) == 1
    assert str(good) in lines[0]


def test_missing_component_directory_writes_no_entries(tmp_path):
    obs_root = tmp_path / "obs"
    os.makedirs(str(obs_root))

    case = make_case(str(obs_root), active_comps=("ocn",))
    output_path = tmp_path / "dart.input_data_list"
    DART_obs_seq_list().write(str(output_path), case)

    assert read_manifest(str(output_path)) == []


def test_unset_dart_obs_root_falls_back_to_din_loc_root(tmp_path):
    din_loc_root = tmp_path / "din_loc_root"
    obs_file = din_loc_root / "esp" / "dart" / "ocn_obs_seq" / "obs_seq.0Z.20050101"
    touch(str(obs_file))

    case = make_case("UNSET")
    case.get_value = lambda key, _values={
        "DART_OBS_ROOT": "UNSET",
        "DIN_LOC_ROOT": str(din_loc_root),
        "RUN_STARTDATE": "2005-01-01",
        "STOP_OPTION": "ndays",
        "STOP_N": 10,
        "DATA_ASSIMILATION_OCN": True,
        "DATA_ASSIMILATION_ATM": False,
        "DATA_ASSIMILATION_LND": False,
        "DATA_ASSIMILATION_ICE": False,
    }: _values[key]

    output_path = tmp_path / "dart.input_data_list"
    DART_obs_seq_list().write(str(output_path), case)

    lines = read_manifest(str(output_path))
    assert any(str(obs_file) in line for line in lines)
