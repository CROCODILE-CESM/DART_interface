#!/usr/bin/env python3

"""
Pytest suite for assimilate.py

Tests the multi-component CESM DART assimilation script with mocked CIME
dependencies. Covers single-component (OCN-only, ATM-only, LND-only, ICE-only)
and multi-component (OCN+ICE) DA scenarios.
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import fnmatch

# Mock CIME modules before importing assimilate
sys.modules['standard_script_setup'] = Mock()
sys.modules['CIME'] = Mock()
sys.modules['CIME.case'] = Mock()

# Set CIMEROOT environment variable for import
os.environ['CIMEROOT'] = '/mock/cimeroot'

# Add cime_config directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cime_config'))

import assimilate
from assimilate import ModelTime
import dart_cesm_components
from dart_cesm_components import DART_COMPONENTS, get_active_da_components


class TestModelTime:
    """Test ModelTime namedtuple functionality."""
    
    def test_modeltime_creation(self):
        """Test creating a ModelTime namedtuple."""
        mt = ModelTime(2001, 1, 2, 12345)
        assert mt.year == 2001
        assert mt.month == 1
        assert mt.day == 2
        assert mt.seconds == 12345
    
    def test_modeltime_immutable(self):
        """Test that ModelTime is immutable."""
        mt = ModelTime(2001, 1, 2, 12345)
        with pytest.raises(AttributeError):
            mt.year = 2002
    
    def test_modeltime_indexing(self):
        """Test that ModelTime can be accessed by index."""
        mt = ModelTime(2001, 1, 2, 12345)
        assert mt[0] == 2001
        assert mt[1] == 1
        assert mt[2] == 2
        assert mt[3] == 12345


class TestGetModelTimeFromFilename:
    """Test get_model_time_from_filename function."""
    
    def test_valid_filename(self):
        """Test extracting time from valid filename."""
        filename = "rpointer.ocn_0001.0001-01-02-00000"
        mt = assimilate.get_model_time_from_filename(filename)
        assert mt.year == 1
        assert mt.month == 1
        assert mt.day == 2
        assert mt.seconds == 0
    
    def test_valid_filename_with_nonzero_seconds(self):
        """Test extracting time with non-zero seconds."""
        filename = "rpointer.cpl_0003.2001-12-31-86399"
        mt = assimilate.get_model_time_from_filename(filename)
        assert mt.year == 2001
        assert mt.month == 12
        assert mt.day == 31
        assert mt.seconds == 86399
    
    def test_invalid_filename_format(self):
        """Test that invalid filename raises ValueError."""
        filename = "invalid_filename.txt"
        with pytest.raises(ValueError, match="Could not extract model time"):
            assimilate.get_model_time_from_filename(filename)
    
    def test_partial_timestamp(self):
        """Test filename with incomplete timestamp."""
        filename = "rpointer.ocn_0001.0001-01"
        with pytest.raises(ValueError):
            assimilate.get_model_time_from_filename(filename)


class TestBackupModelInputNml:
    """Test backup_model_input_nml and restore_model_input_nml functions."""

    def test_backup_existing_file(self, tmp_path):
        """Test backing up an existing input.nml file."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        input_nml = rundir / "input.nml"
        input_nml.write_text("test content")

        assimilate.backup_model_input_nml(str(rundir))

        backup_file = rundir / "mom_input.nml.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == "test content"

    def test_backup_nonexistent_file(self, tmp_path, caplog):
        """Test backup when input.nml doesn't exist."""
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.backup_model_input_nml(str(rundir))

        assert "backup skipped" in caplog.text.lower()


class TestRestoreModelInputNml:
    """Test restore_model_input_nml function."""

    def test_restore_from_backup(self, tmp_path):
        """Test restoring input.nml from backup."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        bak = rundir / "mom_input.nml.bak"
        bak.write_text("original model content")
        (rundir / "input.nml").write_text("dart overwrite")

        assimilate.restore_model_input_nml(str(rundir))

        assert (rundir / "input.nml").read_text() == "original model content"

    def test_restore_no_backup(self, tmp_path, caplog):
        """Test restore when no backup exists."""
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.restore_model_input_nml(str(rundir))

        assert "restore skipped" in caplog.text.lower()


class TestCheckRequiredFiles:
    """Test check_required_files function."""
    
    def test_all_files_present(self, tmp_path, caplog):
        """Test when all required files are present."""
        import logging
        caplog.set_level(logging.INFO)
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        (rundir / "input.nml").write_text("")
        (rundir / "obs_seq.out").write_text("")
        
        assimilate.check_required_files(str(rundir))
        
        assert "all required files are present" in caplog.text.lower()
    
    def test_missing_files(self, tmp_path, caplog):
        """Test when required files are missing."""
        import logging
        caplog.set_level(logging.ERROR)
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        with pytest.raises(FileNotFoundError, match="Missing required files"):
            assimilate.check_required_files(str(rundir))


class TestStageDartInputNml:
    """Test stage_dart_input_nml function."""
    
    def test_stage_existing_file(self, tmp_path):
        """Test staging DART input.nml from Buildconf."""
        # Setup mock case
        mock_case = Mock()
        caseroot = tmp_path / "case"
        buildconf = caseroot / "Buildconf" / "dartconf"
        buildconf.mkdir(parents=True)
        src_input = buildconf / "input.nml"
        src_input.write_text("dart config")
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        mock_case.get_value.return_value = str(caseroot)
        
        assimilate.stage_dart_input_nml(mock_case, str(rundir))
        
        dst_input = rundir / "input.nml"
        assert dst_input.exists()
        assert dst_input.read_text() == "dart config"
    
    def test_stage_missing_file(self, tmp_path):
        """Test staging when DART input.nml doesn't exist."""
        mock_case = Mock()
        caseroot = tmp_path / "case"
        caseroot.mkdir()
        mock_case.get_value.return_value = str(caseroot)
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        with pytest.raises(FileNotFoundError):
            assimilate.stage_dart_input_nml(mock_case, str(rundir))


class TestSetRestartFiles:
    """Test set_restart_files function."""

    def test_create_filter_lists_single_rpointer(self, tmp_path):
        """Test creating filter lists from a single rpointer file."""
        rundir = tmp_path / "run"
        rundir.mkdir()

        model_time = ModelTime(2001, 1, 2, 0)
        rpointer = rundir / "rpointer.ocn_0001.2001-01-02-00000"
        rpointer.write_text("restart_file_001.nc\n")

        assimilate.set_restart_files(str(rundir), "ocn", model_time)

        filter_input = rundir / "filter_input_list.txt"
        filter_output = rundir / "filter_output_list.txt"

        assert filter_input.exists()
        assert filter_output.exists()
        assert filter_input.read_text() == "restart_file_001.nc\n"
        assert filter_output.read_text() == "restart_file_001.nc\n"

    def test_create_filter_lists_multiple_rpointers(self, tmp_path):
        """Test creating filter lists from multiple rpointer files."""
        rundir = tmp_path / "run"
        rundir.mkdir()

        model_time = ModelTime(2001, 1, 2, 0)
        (rundir / "rpointer.ocn_0001.2001-01-02-00000").write_text("restart_001.nc\n")
        (rundir / "rpointer.ocn_0002.2001-01-02-00000").write_text("restart_002.nc\n")
        (rundir / "rpointer.ocn_0003.2001-01-02-00000").write_text("restart_003.nc\n")

        assimilate.set_restart_files(str(rundir), "ocn", model_time)

        filter_input = rundir / "filter_input_list.txt"
        content = filter_input.read_text()

        assert "restart_001.nc" in content
        assert "restart_002.nc" in content
        assert "restart_003.nc" in content

    def test_atm_rpointer_prefix(self, tmp_path):
        """Test that the correct prefix is used for ATM component."""
        rundir = tmp_path / "run"
        rundir.mkdir()

        model_time = ModelTime(2001, 1, 2, 0)
        (rundir / "rpointer.atm_0001.2001-01-02-00000").write_text("cam_restart.nc\n")

        assimilate.set_restart_files(str(rundir), "atm", model_time)

        assert (rundir / "filter_input_list.txt").exists()
        assert "cam_restart.nc" in (rundir / "filter_input_list.txt").read_text()

    def test_no_rpointer_files(self, tmp_path):
        """Test when no rpointer files exist raises FileNotFoundError."""
        rundir = tmp_path / "run"
        rundir.mkdir()

        model_time = ModelTime(2001, 1, 2, 0)

        with pytest.raises(FileNotFoundError, match="No rpointer"):
            assimilate.set_restart_files(str(rundir), "ocn", model_time)


class TestSetTemplateFilesOcn:
    """Test set_template_files_ocn (MOM6)."""

    def test_create_symlinks(self, tmp_path):
        """Test creating mom6.r.nc and mom6.static.nc symlinks."""
        mock_case = Mock()
        mock_case.get_value.return_value = "test_case"

        rundir = tmp_path / "run"
        rundir.mkdir()

        filter_input = rundir / "filter_input_list.txt"
        restart_file = rundir / "restart_001.nc"
        restart_file.write_text("")
        filter_input.write_text(f"{restart_file}\n")

        static_file = rundir / "test_case.mom6.h.static.nc"
        static_file.write_text("")

        assimilate.set_template_files_ocn(mock_case, str(rundir))

        assert (rundir / "mom6.r.nc").is_symlink()
        assert (rundir / "mom6.static.nc").is_symlink()

    def test_missing_filter_input_list(self, tmp_path, caplog):
        """Test when filter_input_list.txt doesn't exist."""
        mock_case = Mock()
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.set_template_files_ocn(mock_case, str(rundir))

        assert "filter_input_list.txt not found" in caplog.text


class TestSetTemplateFilesAtm:
    """Test set_template_files_atm (CAM-SE)."""

    def test_create_caminput_symlink(self, tmp_path):
        """Test creating caminput.nc symlink."""
        mock_case = Mock()
        mock_case.get_value.return_value = "test_case"

        rundir = tmp_path / "run"
        rundir.mkdir()

        restart_file = rundir / "cam_restart.nc"
        restart_file.write_text("")
        (rundir / "filter_input_list.txt").write_text(f"{restart_file}\n")

        (rundir / "test_case.cam_0001.i.2001-01-02-00000.nc").write_text("")

        assimilate.set_template_files_atm(mock_case, str(rundir))

        assert (rundir / "caminput.nc").is_symlink()
        assert (rundir / "cam_phis.nc").is_symlink()

    def test_missing_filter_input_list(self, tmp_path, caplog):
        """Test warning when filter_input_list.txt doesn't exist."""
        mock_case = Mock()
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.set_template_files_atm(mock_case, str(rundir))

        assert "filter_input_list.txt not found" in caplog.text


class TestSetTemplateFilesLnd:
    """Test set_template_files_lnd (CLM) — no-op."""

    def test_no_symlinks_created(self, tmp_path, caplog):
        """CLM does not require extra symlinks."""
        import logging
        caplog.set_level(logging.INFO)
        mock_case = Mock()
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.set_template_files_lnd(mock_case, str(rundir))

        assert "no additional template" in caplog.text.lower()


class TestSetTemplateFilesIce:
    """Test set_template_files_ice (CICE) — no-op."""

    def test_no_symlinks_created(self, tmp_path, caplog):
        """CICE does not require extra symlinks."""
        import logging
        caplog.set_level(logging.INFO)
        mock_case = Mock()
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.set_template_files_ice(mock_case, str(rundir))

        assert "no additional template" in caplog.text.lower()


class TestGetModelTime:
    """Test get_model_time function."""
    
    def test_get_model_time_valid(self):
        """Test extracting model time from case."""
        mock_case = Mock()
        mock_case.get_value.return_value = "rpointer.cpl_0001.2001-01-15-43200"
        
        mt = assimilate.get_model_time(mock_case)
        
        assert mt.year == 2001
        assert mt.month == 1
        assert mt.day == 15
        assert mt.seconds == 43200
    
    def test_get_model_time_unset(self):
        """Test when DRV_RESTART_POINTER is not set."""
        mock_case = Mock()
        mock_case.get_value.return_value = "UNSET"
        
        with pytest.raises(ValueError, match="DRV_RESTART_POINTER is not set"):
            assimilate.get_model_time(mock_case)
    
    def test_get_model_time_none(self):
        """Test when DRV_RESTART_POINTER is None."""
        mock_case = Mock()
        mock_case.get_value.return_value = None
        
        with pytest.raises(ValueError, match="DRV_RESTART_POINTER is not set"):
            assimilate.get_model_time(mock_case)

class TestRenameInflationFiles:
    """
    Test rename_inflation_files function matches implementation:
    - Renames output_* files to dart_output_*.<case>.<date_str>.nc
    - Copies dart_output_* files to input_* files for next cycle
    """
    def test_rename_inflation_files(self, tmp_path):
        rundir = tmp_path / "run"
        rundir.mkdir()
 
        # Create dummy inflation files
        files = {
            "priorinf_mean": "prior mean",
            "priorinf_sd": "prior sd",
            "postinf_mean": "post mean",
            "postinf_sd": "post sd"
        }
        for base, content in files.items():
            (rundir / f"output_{base}.nc").write_text(content)

        assimilate.rename_inflation_files(str(rundir))
  
        # Check input_* files
        for base, content in files.items():
            input_file = rundir / f"input_{base}.nc"
            assert input_file.exists()
            assert input_file.read_text() == content

        # Original files should exist
        for base in files:
            assert (rundir / f"output_{base}.nc").exists()

class TestRenameStageFiles:
    """
    Test rename_stage_files function.
    """
    def test_rename_stage_files(self, tmp_path):
        rundir = tmp_path / "run"
        rundir.mkdir()
        case = Mock()
        case.get_value.return_value = "testcase"

        # Define all stages and members
        stages = ["input", "forecast", "preassim", "postassim", "analysis", "output"]
        members = ["mean", "sd", "priorinf_mean", "priorinf_sd", "postinf_mean", "postinf_sd"] + [f"member{i}" for i in range(1, 4)]

        # Create all expected files and their content
        files = {}
        for stage in stages:
            for member in members:
                key = f"{stage}_{member}"
                files[key] = f"{stage} {member}"

        for base, content in files.items():
            print(f"filename: {base}.nc")
            (rundir / f"{base}.nc").write_text(content)

        model_time = ModelTime(2001, 1, 15, 43200)
        assimilate.rename_stage_files(case, model_time, str(rundir))
        date_str = "2001-01-15-43200"

        # Check renamed staged files, except for input_*inf*, output_*inf* files
        for base, content in files.items():
            if fnmatch.fnmatch(base, "input_*inf*"):
                print(f"skipping check for {base}.nc")
                continue
            dart_file = rundir / f"{base}.testcase.{date_str}.nc"
            assert dart_file.exists(), f"Missing {dart_file}"
            assert dart_file.read_text() == content

        # Original files should not exist, except for input_*inf* and output_*inf* files
        for base in files:
            if fnmatch.fnmatch(base, "input_*inf*" ):
                assert (rundir / f"{base}.nc").exists(), f"Should exist: {base}.nc"
            else:
                assert not (rundir / f"{base}.nc").exists(), f"Should not exist: {base}.nc"

class TestRenameDartLogs:
    """Test rename_dart_logs function."""
    def test_rename_dart_logs(self, tmp_path):
        # Setup mock case and model_time
        mock_case = Mock()
        mock_case.get_value.return_value = "testcase"
        model_time = ModelTime(2020, 5, 6, 12345)
        rundir = tmp_path / "run"
        rundir.mkdir()
        # Create dummy log files
        log_out = rundir / "dart_log.out"
        log_nml = rundir / "dart_log.nml"
        log_out.write_text("log out content")
        log_nml.write_text("log nml content")
        # Call function
        assimilate.rename_dart_logs(mock_case, model_time, str(rundir))
        # Check new filenames
        date_str = f"2020-05-06-12345"
        new_log_out = rundir / f"dart_log.testcase.{date_str}.out"
        new_log_nml = rundir / f"dart_log.testcase.{date_str}.nml"
        assert new_log_out.exists()
        assert new_log_nml.exists()
        assert new_log_out.read_text() == "log out content"
        assert new_log_nml.read_text() == "log nml content"

class TestRenameObsSeqFinal:
    """Test rename_obs_seq_final function."""

    def test_rename_obs_seq_final_success(self, tmp_path):
        # Setup
        case = Mock()
        case.get_value.return_value = "testcase"
        model_time = ModelTime(2020, 5, 6, 12345)
        rundir = tmp_path / "run"
        rundir.mkdir()
        obs_seq = rundir / "obs_seq.final"
        obs_seq.write_text("obs seq content")
        # Call function
        assimilate.rename_obs_seq_final(case, model_time, str(rundir))
        date_str = f"2020-05-06-12345"
        new_obs_seq = rundir / f"obs_seq.final.testcase.{date_str}"
        assert new_obs_seq.exists()
        assert new_obs_seq.read_text() == "obs seq content"

    def test_rename_obs_seq_final_missing(self, tmp_path):
        case = Mock()
        case.get_value.return_value = "testcase"
        model_time = ModelTime(2020, 5, 6, 12345)
        rundir = tmp_path / "run"
        rundir.mkdir()
        # obs_seq.final does not exist
        with pytest.raises(FileNotFoundError):
            assimilate.rename_obs_seq_final(case, model_time, str(rundir))


class TestStageInflationFiles:
    def test_stage_inflation_files_required_files_posterior(self, tmp_path):
        # Create input.nml with posterior inflation from file
        nml_content = """
&filter_nml
    inf_flavor                  = 0, 2,
    inf_initial_from_restart    = .false., .true.,
/"""
        rundir = tmp_path / "run"
        rundir.mkdir()
        (rundir / "input.nml").write_text(nml_content)
        # Should raise FileNotFoundError if posterior inflation files are missing
        with pytest.raises(FileNotFoundError) as excinfo:
            assimilate.stage_inflation_files(str(rundir))
        assert "input_postinf_mean.nc" in str(excinfo.value)
        # Create the required posterior inflation files
        (rundir / "input_postinf_mean.nc").write_text("")
        (rundir / "input_postinf_sd.nc").write_text("")
        # Should not raise now
        assimilate.stage_inflation_files(str(rundir))

    def test_stage_inflation_files_required_files_prior(self, tmp_path):
        # Create input.nml with prior inflation from file
        nml_content = """
&filter_nml
   inf_flavor                  = 2, 0,
   inf_initial_from_restart    = .true., .false.,
/"""
        rundir = tmp_path / "run"
        rundir.mkdir()
        (rundir / "input.nml").write_text(nml_content)
        # Should raise FileNotFoundError if inflation files are missing
        with pytest.raises(FileNotFoundError) as excinfo:
            assimilate.stage_inflation_files(str(rundir))
        assert "input_priorinf_mean.nc" in str(excinfo.value)
        # Create the required inflation files
        (rundir / "input_priorinf_mean.nc").write_text("")
        (rundir / "input_priorinf_sd.nc").write_text("")
        # Should not raise now
        assimilate.stage_inflation_files(str(rundir))

    def test_parse_inflation_settings(self, tmp_path):
        # Create a fake input.nml file
        nml_content = """
&filter_nml
inf_flavor                  = 2,                       3,
inf_initial_from_restart    = .true.,                  .false.,
inf_sd_initial_from_restart = .false.,                 .true.,
inf_initial                 = 1.1,                     1.2,
/"""
        nml_path = tmp_path / "input.nml"
        nml_path.write_text(nml_content)

        settings = assimilate.parse_inflation_settings(str(nml_path))
        assert settings['prior']['inf_flavor'] == 2
        assert settings['posterior']['inf_flavor'] == 3
        assert settings['prior']['inf_initial_from_restart'] is True
        assert settings['posterior']['inf_initial_from_restart'] is False
        assert settings['prior']['inf_sd_initial_from_restart'] is False
        assert settings['posterior']['inf_sd_initial_from_restart'] is True
        assert settings['prior']['inf_initial'] == 1.1
        assert settings['posterior']['inf_initial'] == 1.2


    def test_stage_inflation_files_missing_input_nml(self, tmp_path):
        rundir = tmp_path / "run"
        rundir.mkdir()
        with pytest.raises(FileNotFoundError):
            assimilate.stage_inflation_files(str(rundir))


class TestCopyGeometryFileForCycle0:
    """Test copy_geometry_file_for_cycle0 function."""

    def _ocn_active_case(self, casename="testcase"):
        """Return a mock case where OCN DA is active."""
        mock_case = Mock()
        def case_get_value(key):
            if key == "DATA_ASSIMILATION_OCN":
                return True
            return casename
        mock_case.get_value.side_effect = case_get_value
        return mock_case

    def test_copy_geometry_on_cycle_0(self, tmp_path):
        """Test that geometry file is copied on cycle 0."""
        mock_case = self._ocn_active_case()
        rundir = tmp_path / "run"
        rundir.mkdir()

        geometry_file = rundir / "testcase.mom6.h.ocean_geometry.nc"
        geometry_file.write_text("geometry data")

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), 0)

        ocean_geometry = rundir / "ocean_geometry.nc"
        assert ocean_geometry.exists()
        assert ocean_geometry.read_text() == "geometry data"

    def test_no_copy_on_non_zero_cycle(self, tmp_path):
        """Test that geometry file is not copied on cycles other than 0."""
        mock_case = self._ocn_active_case()
        rundir = tmp_path / "run"
        rundir.mkdir()

        (rundir / "testcase.mom6.h.ocean_geometry.nc").write_text("geometry data")

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), 1)

        assert not (rundir / "ocean_geometry.nc").exists()

    def test_skipped_when_ocn_not_active(self, tmp_path):
        """Test that geometry copy is skipped when OCN DA is not active."""
        mock_case = Mock()
        mock_case.get_value.return_value = False   # all DA flags off
        rundir = tmp_path / "run"
        rundir.mkdir()

        (rundir / "testcase.mom6.h.ocean_geometry.nc").write_text("geometry data")

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), 0)

        assert not (rundir / "ocean_geometry.nc").exists()

    def test_multiple_geometry_files_picks_first(self, tmp_path):
        """Test that when multiple geometry files exist, the first (sorted) is copied."""
        mock_case = self._ocn_active_case()
        rundir = tmp_path / "run"
        rundir.mkdir()

        (rundir / "testcase.mom6.h.ocean_geometry_2.nc").write_text("geometry 2")
        (rundir / "testcase.mom6.h.ocean_geometry_1.nc").write_text("geometry 1")
        (rundir / "testcase.mom6.h.ocean_geometry_3.nc").write_text("geometry 3")

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), 0)

        assert (rundir / "ocean_geometry.nc").read_text() == "geometry 1"

    def test_missing_geometry_file_logs_warning(self, tmp_path, caplog):
        """Test that missing geometry file logs a warning on cycle 0."""
        import logging
        caplog.set_level(logging.WARNING)

        mock_case = self._ocn_active_case()
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), 0)

        assert "no mom6 geometry files" in caplog.text.lower()

    def test_non_integer_cycle_string(self, tmp_path, caplog):
        """Test that non-integer cycle value logs warning and does nothing."""
        import logging
        caplog.set_level(logging.WARNING)

        mock_case = self._ocn_active_case()
        rundir = tmp_path / "run"
        rundir.mkdir()

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), "not_a_number")

        assert "not an integer" in caplog.text.lower()

    def test_cycle_as_string_zero(self, tmp_path):
        """Test that cycle as string '0' works correctly."""
        mock_case = self._ocn_active_case()
        rundir = tmp_path / "run"
        rundir.mkdir()

        geometry_file = rundir / "testcase.mom6.h.ocean_geometry.nc"
        geometry_file.write_text("geometry data")

        assimilate.copy_geometry_file_for_cycle0(mock_case, str(rundir), "0")

        assert (rundir / "ocean_geometry.nc").exists()


class TestGetActiveDaComponents:
    """Test get_active_da_components from dart_cesm_components."""

    def _make_case(self, active):
        """Build a mock case with the given set of active component keys."""
        mock_case = Mock()
        def get_value(key):
            for comp in ["OCN", "ATM", "LND", "ICE"]:
                if key == f"DATA_ASSIMILATION_{comp}":
                    return comp.lower() in active
            return False
        mock_case.get_value.side_effect = get_value
        return mock_case

    def test_ocn_only(self):
        case = self._make_case({"ocn"})
        assert get_active_da_components(case) == ["ocn"]

    def test_atm_only(self):
        case = self._make_case({"atm"})
        assert get_active_da_components(case) == ["atm"]

    def test_lnd_only(self):
        case = self._make_case({"lnd"})
        assert get_active_da_components(case) == ["lnd"]

    def test_ice_only(self):
        case = self._make_case({"ice"})
        assert get_active_da_components(case) == ["ice"]

    def test_ocn_and_ice(self):
        case = self._make_case({"ocn", "ice"})
        # order must follow COMPONENT_KEYS: ocn, atm, lnd, ice
        result = get_active_da_components(case)
        assert result == ["ocn", "ice"]

    def test_all_active(self):
        case = self._make_case({"ocn", "atm", "lnd", "ice"})
        assert get_active_da_components(case) == ["ocn", "atm", "lnd", "ice"]

    def test_none_active(self):
        case = self._make_case(set())
        assert get_active_da_components(case) == []


class TestRunFilterForComponent:
    """Test run_filter_for_component function."""

    def _make_case(self, rundir, exeroot, ntasks=4, mpirun="mpirun", casename="testcase"):
        mock_case = Mock()
        def get_value(key):
            return {
                "RUNDIR": rundir,
                "EXEROOT": exeroot,
                "NTASKS_ESP": ntasks,
                "MPI_RUN_COMMAND": mpirun,
                "CASE": casename,
            }.get(key)
        mock_case.get_value.side_effect = get_value
        return mock_case

    @patch('assimilate.rename_stage_files')
    @patch('assimilate.rename_inflation_files')
    @patch('assimilate.rename_obs_seq_final')
    @patch('assimilate.rename_dart_logs')
    @patch('assimilate.stage_inflation_files')
    @patch('assimilate.set_restart_files')
    @patch('assimilate.check_required_files')
    @patch('assimilate.stage_dart_input_nml')
    @patch('assimilate.get_observations')
    @patch('assimilate.get_model_time')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.chdir')
    def test_ocn_filter_success(
        self, mock_chdir, mock_exists, mock_subprocess,
        mock_get_time, mock_get_obs, mock_stage_nml, mock_check,
        mock_set_restart, mock_stage_infl, mock_rename_logs, mock_rename_obs,
        mock_rename_infl, mock_rename_stage
    ):
        """Test successful OCN filter run (includes backup/restore of input.nml)."""
        import tempfile, os as _os
        with tempfile.TemporaryDirectory() as tmpdir:
            exeroot = _os.path.join(tmpdir, "esp")
            _os.makedirs(exeroot)
            mock_exists.return_value = True
            model_time = ModelTime(2001, 1, 15, 0)
            mock_get_time.return_value = model_time
            mock_subprocess.return_value = Mock(stdout="", stderr="")

            mock_case = self._make_case("/run", tmpdir)
            mock_template_fn = Mock()

            with patch('assimilate.backup_model_input_nml') as mock_backup, \
                 patch('assimilate.restore_model_input_nml') as mock_restore, \
                 patch.dict('assimilate._SET_TEMPLATE_FILES', {'ocn': mock_template_fn}):
                assimilate.run_filter_for_component(mock_case, "ocn", "/caseroot")

            mock_backup.assert_called_once_with("/run")
            mock_restore.assert_called_once_with("/run")
            mock_set_restart.assert_called_once_with("/run", "ocn", model_time)
            mock_get_obs.assert_called_once_with(mock_case, "ocn", model_time, "/run")
            mock_subprocess.assert_called_once()

    @patch('assimilate.rename_stage_files')
    @patch('assimilate.rename_inflation_files')
    @patch('assimilate.rename_obs_seq_final')
    @patch('assimilate.rename_dart_logs')
    @patch('assimilate.stage_inflation_files')
    @patch('assimilate.set_restart_files')
    @patch('assimilate.check_required_files')
    @patch('assimilate.stage_dart_input_nml')
    @patch('assimilate.get_observations')
    @patch('assimilate.get_model_time')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.chdir')
    def test_atm_filter_no_backup(
        self, mock_chdir, mock_exists, mock_subprocess,
        mock_get_time, mock_get_obs, mock_stage_nml, mock_check,
        mock_set_restart, mock_stage_infl, mock_rename_logs, mock_rename_obs,
        mock_rename_infl, mock_rename_stage
    ):
        """ATM has no input_nml_conflict — backup/restore must NOT be called."""
        mock_exists.return_value = True
        mock_get_time.return_value = ModelTime(2001, 1, 15, 0)
        mock_subprocess.return_value = Mock(stdout="", stderr="")
        mock_case = self._make_case("/run", "/exe")

        mock_template_fn = Mock()
        with patch('assimilate.backup_model_input_nml') as mock_backup, \
             patch('assimilate.restore_model_input_nml') as mock_restore, \
             patch.dict('assimilate._SET_TEMPLATE_FILES', {'atm': mock_template_fn}):
            assimilate.run_filter_for_component(mock_case, "atm", "/caseroot")

        mock_backup.assert_not_called()
        mock_restore.assert_not_called()
        mock_set_restart.assert_called_once_with("/run", "atm", mock_get_time.return_value)

    @patch('os.path.exists')
    def test_missing_filter_executable(self, mock_exists):
        """Test FileNotFoundError raised when filter_{comp} binary is missing."""
        mock_exists.return_value = False
        mock_case = self._make_case("/run", "/exe")

        with pytest.raises(FileNotFoundError, match="Filter executable not found"):
            assimilate.run_filter_for_component(mock_case, "ocn", "/caseroot")


class TestAssimilateFunction:
    """Test the assimilate() entry point."""

    def _make_case(self, active_comps):
        mock_case = Mock()
        def get_value(key):
            for comp in ["OCN", "ATM", "LND", "ICE"]:
                if key == f"DATA_ASSIMILATION_{comp}":
                    return comp.lower() in active_comps
            if key == "RUNDIR":
                return "/run"
            return None
        mock_case.get_value.side_effect = get_value
        return mock_case

    @patch('assimilate.Case')
    @patch('assimilate.copy_geometry_file_for_cycle0')
    @patch('assimilate.run_filter_for_component')
    def test_single_component_ocn(self, mock_run_filter, mock_geom, mock_Case):
        """OCN-only DA calls run_filter_for_component once with 'ocn'."""
        mock_case_instance = self._make_case({"ocn"})
        mock_Case.return_value.__enter__.return_value = mock_case_instance

        assimilate.assimilate("/case/root", 1)

        mock_run_filter.assert_called_once_with(
            mock_case_instance, "ocn", "/case/root", use_mpi=True
        )

    @patch('assimilate.Case')
    @patch('assimilate.copy_geometry_file_for_cycle0')
    @patch('assimilate.run_filter_for_component')
    def test_single_component_atm(self, mock_run_filter, mock_geom, mock_Case):
        """ATM-only DA calls run_filter_for_component once with 'atm'."""
        mock_case_instance = self._make_case({"atm"})
        mock_Case.return_value.__enter__.return_value = mock_case_instance

        assimilate.assimilate("/case/root", 1)

        mock_run_filter.assert_called_once_with(
            mock_case_instance, "atm", "/case/root", use_mpi=True
        )

    @patch('assimilate.Case')
    @patch('assimilate.copy_geometry_file_for_cycle0')
    @patch('assimilate.run_filter_for_component')
    def test_multi_component_ocn_ice(self, mock_run_filter, mock_geom, mock_Case):
        """OCN+ICE DA calls run_filter_for_component for each in order."""
        mock_case_instance = self._make_case({"ocn", "ice"})
        mock_Case.return_value.__enter__.return_value = mock_case_instance

        assimilate.assimilate("/case/root", 0, use_mpi=False)

        assert mock_run_filter.call_count == 2
        calls = mock_run_filter.call_args_list
        assert calls[0] == call(mock_case_instance, "ocn", "/case/root", use_mpi=False)
        assert calls[1] == call(mock_case_instance, "ice", "/case/root", use_mpi=False)

    @patch('assimilate.Case')
    @patch('assimilate.copy_geometry_file_for_cycle0')
    @patch('assimilate.run_filter_for_component')
    def test_no_active_components_raises(self, mock_run_filter, mock_geom, mock_Case):
        """RuntimeError raised when no DA components are active."""
        mock_case_instance = self._make_case(set())
        mock_Case.return_value.__enter__.return_value = mock_case_instance

        with pytest.raises(RuntimeError, match="no DATA_ASSIMILATION"):
            assimilate.assimilate("/case/root", 1)


class TestMain:
    """Test main() entry point."""

    @patch('assimilate.assimilate')
    def test_main_with_argv(self, mock_assimilate):
        """Test main() calls assimilate() with caseroot and cycle."""
        test_argv = ["assimilate.py", "/case/root", "3"]
        with patch('sys.argv', test_argv):
            assimilate.main()
        mock_assimilate.assert_called_once_with(
            "/case/root", cycle="3", use_mpi=True
        )

    @patch('assimilate.assimilate')
    def test_main_with_no_mpi_flag(self, mock_assimilate):
        """Test main() with --no-mpi passes use_mpi=False."""
        test_argv = ["assimilate.py", "/case/root", "4", "--no-mpi"]
        with patch('sys.argv', test_argv):
            assimilate.main()
        mock_assimilate.assert_called_once_with(
            "/case/root", cycle="4", use_mpi=False
        )

    def test_main_no_argv_errors(self):
        """Test main() exits with code 2 if required args are missing."""
        import io
        for argv in [["assimilate.py"], ["assimilate.py", "/case/root"]]:
            with patch('sys.argv', argv), patch('sys.stderr', new_callable=io.StringIO):
                with pytest.raises(SystemExit) as excinfo:
                    assimilate.main()
                assert excinfo.value.code == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
