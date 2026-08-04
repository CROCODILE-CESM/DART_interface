#!/usr/bin/env python3

"""
Pytest suite for assimilate.py

Tests the multi-component CESM DART assimilation script with mocked CIME
dependencies. Covers single-component (OCN-only, ATM-only, LND-only, ICE-only)
and multi-component (OCN+ICE) DA scenarios.
"""

import os
import sys
import subprocess
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
        """Test staging per-component DART input.nml from Buildconf."""
        mock_case = Mock()
        caseroot = tmp_path / "case"
        buildconf = caseroot / "Buildconf" / "dartconf"
        buildconf.mkdir(parents=True)
        src_input = buildconf / "input.nml.ocn"
        src_input.write_text("dart ocn config")
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        mock_case.get_value.return_value = str(caseroot)
        
        assimilate.stage_dart_input_nml(mock_case, str(rundir), "ocn")
        
        dst_input = rundir / "input.nml"
        assert dst_input.exists()
        assert dst_input.read_text() == "dart ocn config"
    
    def test_stage_missing_file(self, tmp_path):
        """Test staging when per-component DART input.nml doesn't exist."""
        mock_case = Mock()
        caseroot = tmp_path / "case"
        caseroot.mkdir()
        mock_case.get_value.return_value = str(caseroot)
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        with pytest.raises(FileNotFoundError):
            assimilate.stage_dart_input_nml(mock_case, str(rundir), "ocn")


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

class TestUnstageInflationFiles:
    """Test unstage_inflation_files removes staging symlinks only."""

    def test_removes_symlinks(self, tmp_path):
        rundir = tmp_path / "run"
        rundir.mkdir()
        target = rundir / "testcase.dart.rh.ocn_output_priorinf_mean.2001-01-15-00000.nc"
        target.write_text("prior mean")
        link = rundir / "input_priorinf_mean.nc"
        link.symlink_to(target)

        assimilate.unstage_inflation_files(str(rundir))

        assert not link.exists() and not link.is_symlink()
        assert target.exists(), "unstage must not touch the archived restart"

    def test_leaves_regular_file(self, tmp_path):
        """A real file of the same name is reported, not deleted."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        real = rundir / "input_postinf_sd.nc"
        real.write_text("hand placed")

        assimilate.unstage_inflation_files(str(rundir))

        assert real.exists()
        assert real.read_text() == "hand placed"

    def test_tolerates_absence(self, tmp_path):
        rundir = tmp_path / "run"
        rundir.mkdir()
        assimilate.unstage_inflation_files(str(rundir))  # must not raise


class TestSetNmlArrayValue:
    """Test the targeted namelist array element rewriter."""

    def _write(self, tmp_path, text):
        path = tmp_path / "input.nml"
        path.write_text(text)
        return str(path)

    def test_sets_second_element_only(self, tmp_path):
        path = self._write(tmp_path, """
&filter_nml
  inf_flavor = 2, 2
  inf_initial_from_restart = .TRUE., .TRUE.
  inf_initial = 1.0, 1.0
/
""")
        assimilate.set_nml_array_value(
            path, "filter_nml", "inf_initial_from_restart", 1, False)

        settings = assimilate.parse_inflation_settings(path)
        assert settings['prior']['inf_initial_from_restart'] is True
        assert settings['posterior']['inf_initial_from_restart'] is False
        # Neighbouring variables untouched
        assert settings['prior']['inf_flavor'] == 2
        assert settings['prior']['inf_initial'] == 1.0

    def test_sets_first_element_only(self, tmp_path):
        path = self._write(tmp_path, """
&filter_nml
  inf_initial_from_restart = .true., .true.,
/
""")
        assimilate.set_nml_array_value(
            path, "filter_nml", "inf_initial_from_restart", 0, False)

        settings = assimilate.parse_inflation_settings(path)
        assert settings['prior']['inf_initial_from_restart'] is False
        assert settings['posterior']['inf_initial_from_restart'] is True

    def test_only_edits_named_group(self, tmp_path):
        path = self._write(tmp_path, """
&other_nml
  inf_initial_from_restart = .true., .true.
/
&filter_nml
  inf_initial_from_restart = .true., .true.
/
""")
        assimilate.set_nml_array_value(
            path, "filter_nml", "inf_initial_from_restart", 0, False)

        text = open(path).read()
        other = text.split("&filter_nml")[0]
        assert ".true., .true." in other, "&other_nml must not be modified"

    def test_missing_var_raises(self, tmp_path):
        path = self._write(tmp_path, "&filter_nml\n  inf_flavor = 0, 0\n/\n")
        with pytest.raises(KeyError):
            assimilate.set_nml_array_value(
                path, "filter_nml", "inf_initial_from_restart", 0, False)


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
        assimilate.rename_stage_files(case, "ocn", model_time, str(rundir))
        date_str = "2001-01-15-43200"

        # Check renamed staged files, except for input_*inf* (skipped) and
        # output_*inf* (renamed to .rh. restart-history files)
        for base, content in files.items():
            if fnmatch.fnmatch(base, "input_*inf*"):
                print(f"skipping check for {base}.nc")
                continue
            if fnmatch.fnmatch(base, "output_*inf*"):
                dart_file = rundir / f"testcase.dart.rh.ocn_{base}.{date_str}.nc"
            else:
                dart_file = rundir / f"testcase.dart.ocn_{base}.{date_str}.nc"
            assert dart_file.exists(), f"Missing {dart_file}"
            assert dart_file.read_text() == content

        # Original files should not exist, except for input_*inf* files
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
        assimilate.rename_dart_logs(mock_case, "ocn", model_time, str(rundir))
        # Check new filenames
        date_str = f"2020-05-06-12345"
        new_log_out = rundir / f"testcase.dart.log.ocn.{date_str}.out"
        new_log_nml = rundir / f"testcase.dart.log.ocn.{date_str}.nml"
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
        assimilate.rename_obs_seq_final(case, "ocn", model_time, str(rundir))
        date_str = f"2020-05-06-12345"
        new_obs_seq = rundir / f"testcase.dart.ocn_obs_seq_final.{date_str}"
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
            assimilate.rename_obs_seq_final(case, "ocn", model_time, str(rundir))


class TestStageInflationFiles:
    """
    stage_inflation_files symlinks the newest $CASE.dart.rh.{comp}_output_*
    restart onto the fixed input_* name filter reads, per component.
    """

    BOTH_KINDS = """
&filter_nml
   inf_flavor                  = 2, 2
   inf_initial_from_restart    = .true., .true.
   inf_sd_initial_from_restart = .true., .true.
   inf_initial                 = 1.0, 1.0
   inf_sd_initial              = 0.6, 0.6
/
"""

    def _rundir(self, tmp_path, nml=None):
        rundir = tmp_path / "run"
        rundir.mkdir()
        (rundir / "input.nml").write_text(nml if nml else self.BOTH_KINDS)
        return rundir

    def _case(self, casename="testcase"):
        case = Mock()
        case.get_value.return_value = casename
        return case

    def _restart(self, rundir, comp, token, field, date, content=None):
        name = f"testcase.dart.rh.{comp}_output_{token}_{field}.{date}.nc"
        path = rundir / name
        path.write_text(content if content is not None else name)
        return path

    def test_newest_wins(self, tmp_path):
        """With several dated restarts present, the latest date is staged."""
        rundir = self._rundir(tmp_path)
        dates = ["1976-01-01-00000", "1976-01-03-00000", "1976-01-02-00000"]
        for date in dates:
            for token in ("priorinf", "postinf"):
                for field in ("mean", "sd"):
                    self._restart(rundir, "ocn", token, field, date)

        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        link = rundir / "input_priorinf_mean.nc"
        assert link.is_symlink()
        assert os.path.basename(os.readlink(str(link))) == \
            "testcase.dart.rh.ocn_output_priorinf_mean.1976-01-03-00000.nc"

    def test_per_component_isolation(self, tmp_path):
        """This is the regression test for cross-component clobbering: with ocn
        and atm restarts both present, staging atm must pick the atm file."""
        rundir = self._rundir(tmp_path)
        date = "1976-01-01-00000"
        for comp in ("ocn", "atm"):
            for token in ("priorinf", "postinf"):
                for field in ("mean", "sd"):
                    self._restart(rundir, comp, token, field, date)

        assimilate.stage_inflation_files(self._case(), "atm", str(rundir))
        link = rundir / "input_priorinf_mean.nc"
        assert link.read_text() == \
            "testcase.dart.rh.atm_output_priorinf_mean.1976-01-01-00000.nc"

        # Restaging for ocn must repoint the same fixed name.
        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))
        assert link.read_text() == \
            "testcase.dart.rh.ocn_output_priorinf_mean.1976-01-01-00000.nc"

    def test_flavor_zero_stages_nothing(self, tmp_path):
        rundir = self._rundir(tmp_path, """
&filter_nml
   inf_flavor                  = 0, 0
   inf_initial_from_restart    = .true., .true.
   inf_sd_initial_from_restart = .true., .true.
/
""")
        assert assimilate.stage_inflation_files(
            self._case(), "ocn", str(rundir)) == []
        assert not (rundir / "input_priorinf_mean.nc").exists()

    def test_not_from_restart_stages_nothing(self, tmp_path):
        """Namelist-initialised inflation needs no staging and no bootstrap."""
        nml = """
&filter_nml
   inf_flavor                  = 2, 2
   inf_initial_from_restart    = .false., .false.
   inf_sd_initial_from_restart = .false., .false.
/
"""
        rundir = self._rundir(tmp_path, nml)
        assert assimilate.stage_inflation_files(
            self._case(), "ocn", str(rundir)) == []
        # input.nml must be untouched — no bootstrap happened
        assert (rundir / "input.nml").read_text() == nml

    def test_only_requested_fields_staged(self, tmp_path):
        """sd not from restart: mean is staged, sd is not."""
        rundir = self._rundir(tmp_path, """
&filter_nml
   inf_flavor                  = 2, 0
   inf_initial_from_restart    = .true., .false.
   inf_sd_initial_from_restart = .false., .false.
/
""")
        for field in ("mean", "sd"):
            self._restart(rundir, "ocn", "priorinf", field, "1976-01-01-00000")

        staged = assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        assert (rundir / "input_priorinf_mean.nc").is_symlink()
        assert not (rundir / "input_priorinf_sd.nc").exists()
        assert len(staged) == 1

    def test_bootstrap_when_no_restart(self, tmp_path):
        """First assimilation: no restart exists, so inf_*_from_restart is
        turned off for this cycle and filter uses the namelist values."""
        rundir = self._rundir(tmp_path)

        staged = assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        assert staged == []
        assert not (rundir / "input_priorinf_mean.nc").exists()
        settings = assimilate.parse_inflation_settings(str(rundir / "input.nml"))
        for key in ("prior", "posterior"):
            assert settings[key]['inf_initial_from_restart'] is False
            assert settings[key]['inf_sd_initial_from_restart'] is False
            # flavor and the case's initial values must survive the rewrite
            assert settings[key]['inf_flavor'] == 2
            assert settings[key]['inf_initial'] == 1.0
            assert settings[key]['inf_sd_initial'] == 0.6

    def test_bootstrap_preserves_case_initial_values(self, tmp_path):
        """
        The bootstrap must leave inf_initial / inf_sd_initial alone: those
        namelist variables already mean 'the values to use when not reading a
        restart', so the case's own settings are what the first cycle starts
        from.  Only the from_restart flags are flipped.
        """
        rundir = self._rundir(tmp_path, """
&filter_nml
   inf_flavor                  = 2, 2
   inf_initial_from_restart    = .true., .true.
   inf_sd_initial_from_restart = .true., .true.
   inf_initial                 = 1.4, 1.7
   inf_sd_initial              = 0.6, 0.9
/
""")
        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        settings = assimilate.parse_inflation_settings(str(rundir / "input.nml"))
        # Flags off so filter does not try to read a file that is not there ...
        for key in ("prior", "posterior"):
            assert settings[key]['inf_initial_from_restart'] is False
            assert settings[key]['inf_sd_initial_from_restart'] is False
        # ... but every value the user chose survives, per component and per
        # prior/posterior slot.
        assert settings['prior']['inf_initial'] == 1.4
        assert settings['posterior']['inf_initial'] == 1.7
        assert settings['prior']['inf_sd_initial'] == 0.6
        assert settings['posterior']['inf_sd_initial'] == 0.9
        assert settings['prior']['inf_flavor'] == 2

    def test_no_namelist_edit_when_restart_exists(self, tmp_path):
        """A cycle with real inflation to read must not touch input.nml at all."""
        nml = """
&filter_nml
   inf_flavor                  = 2, 2
   inf_initial_from_restart    = .true., .true.
   inf_sd_initial_from_restart = .true., .true.
   inf_initial                 = 1.4, 1.7
   inf_sd_initial              = 0.6, 0.9
/
"""
        rundir = self._rundir(tmp_path, nml)
        for token in ("priorinf", "postinf"):
            for field in ("mean", "sd"):
                self._restart(rundir, "ocn", token, field, "1976-01-01-00000")

        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        assert (rundir / "input.nml").read_text() == nml, \
            "input.nml must be untouched when inflation restarts exist"

    def test_bootstrap_warns_when_sd_is_zero(self, tmp_path, caplog):
        """inf_sd_initial = 0 with inflation on freezes inflation for the whole
        run, not just the bootstrap cycle, so say so at runtime.  The shipped
        templates default to 0.0, so this is easy to hit by accident."""
        import logging
        caplog.set_level(logging.WARNING)
        rundir = self._rundir(tmp_path, """
&filter_nml
   inf_flavor                  = 2, 0
   inf_initial_from_restart    = .true., .false.
   inf_sd_initial_from_restart = .true., .false.
   inf_initial                 = 1.0, 1.0
   inf_sd_initial              = 0.0, 0.0
/
""")
        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))
        assert "time-constant" in caplog.text

    def test_bootstrap_quiet_when_sd_positive(self, tmp_path, caplog):
        """A positive sd is the normal adaptive case — no scary warning."""
        import logging
        caplog.set_level(logging.WARNING)
        rundir = self._rundir(tmp_path)  # BOTH_KINDS has inf_sd_initial = 0.6

        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        assert "time-constant" not in caplog.text
        assert "first assimilation" in caplog.text

    def test_bootstrap_is_per_kind(self, tmp_path):
        """Prior has a restart, posterior does not (posterior inflation enabled
        mid-experiment): only posterior is bootstrapped."""
        rundir = self._rundir(tmp_path)
        for field in ("mean", "sd"):
            self._restart(rundir, "ocn", "priorinf", field, "1976-01-01-00000")

        staged = assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

        assert len(staged) == 2
        assert (rundir / "input_priorinf_mean.nc").is_symlink()
        assert not (rundir / "input_postinf_mean.nc").exists()
        settings = assimilate.parse_inflation_settings(str(rundir / "input.nml"))
        assert settings['prior']['inf_initial_from_restart'] is True
        assert settings['posterior']['inf_initial_from_restart'] is False

    def test_partial_set_raises(self, tmp_path):
        """A half-present set means something went wrong; bootstrapping would
        silently discard accumulated inflation, so refuse instead."""
        rundir = self._rundir(tmp_path)
        self._restart(rundir, "ocn", "priorinf", "mean", "1976-01-01-00000")
        self._restart(rundir, "ocn", "postinf", "mean", "1976-01-01-00000")
        self._restart(rundir, "ocn", "postinf", "sd", "1976-01-01-00000")

        with pytest.raises(FileNotFoundError, match="incomplete prior inflation"):
            assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))

    def test_stage_then_unstage_leaves_restart(self, tmp_path):
        """Round trip: rename_stage_files must see no input_*inf* left behind."""
        rundir = self._rundir(tmp_path)
        for token in ("priorinf", "postinf"):
            for field in ("mean", "sd"):
                self._restart(rundir, "ocn", token, field, "1976-01-01-00000")

        assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))
        assimilate.unstage_inflation_files(str(rundir))

        leftover = [p.name for p in rundir.glob("input_*inf_*.nc")]
        assert leftover == []
        assert len(list(rundir.glob("testcase.dart.rh.ocn_output_*.nc"))) == 4

    def test_bootstrap_does_not_persist_to_next_cycle(self, tmp_path):
        """
        The bootstrap flip is applied to the staged copy in RUNDIR only.  Nothing
        has to set inf_initial_from_restart back to .true.: stage_dart_input_nml
        re-copies Buildconf/dartconf/input.nml.{comp} at the top of every cycle,
        so the edit is discarded.  This test drives the real staging function to
        pin that, and asserts the case's own copy is never modified.
        """
        caseroot = tmp_path / "case"
        confdir = caseroot / "Buildconf" / "dartconf"
        confdir.mkdir(parents=True)
        source = confdir / "input.nml.ocn"
        source.write_text(self.BOTH_KINDS)

        rundir = tmp_path / "run"
        rundir.mkdir()

        case = Mock()
        case.get_value.side_effect = lambda key: {
            "CASEROOT": str(caseroot), "CASE": "testcase"}.get(key)

        # Cycle 1: nothing to stage, so the staged copy is flipped off.
        assimilate.stage_dart_input_nml(case, str(rundir), "ocn")
        assimilate.stage_inflation_files(case, "ocn", str(rundir))
        staged = assimilate.parse_inflation_settings(str(rundir / "input.nml"))
        assert staged['prior']['inf_initial_from_restart'] is False

        # The case's copy is untouched, which is what makes the flip revert.
        assert source.read_text() == self.BOTH_KINDS

        # Cycle 2: restaging restores .true., and now a restart exists.
        for token in ("priorinf", "postinf"):
            for field in ("mean", "sd"):
                self._restart(rundir, "ocn", token, field, "1976-01-01-00000")
        assimilate.stage_dart_input_nml(case, str(rundir), "ocn")
        restaged = assimilate.parse_inflation_settings(str(rundir / "input.nml"))
        assert restaged['prior']['inf_initial_from_restart'] is True

        assimilate.stage_inflation_files(case, "ocn", str(rundir))
        assert (rundir / "input_priorinf_mean.nc").is_symlink()
        final = assimilate.parse_inflation_settings(str(rundir / "input.nml"))
        assert final['prior']['inf_initial_from_restart'] is True

    def test_two_cycles_two_components(self, tmp_path):
        """
        End-to-end regression test for cross-component clobbering.

        Emulates two cycles of ocn+ICE DA sharing one run directory: cycle 1
        bootstraps both components, cycle 2 must read each component's OWN
        cycle-1 inflation.  Before per-component staging, cycle 2's second
        component read the first component's field.
        """
        rundir = self._rundir(tmp_path)
        case = self._case()

        def fake_filter(comp, cycle):
            """Stand in for filter: record what was linked, write output_*."""
            read = {}
            for token in ("priorinf", "postinf"):
                for field in ("mean", "sd"):
                    src = rundir / f"input_{token}_{field}.nc"
                    read[f"{token}_{field}"] = src.read_text() if src.exists() else None
                    (rundir / f"output_{token}_{field}.nc").write_text(
                        f"{comp}/cycle{cycle}")
            return read

        observed = {}
        for cycle, model_time in ((1, ModelTime(1976, 1, 1, 0)),
                                  (2, ModelTime(1976, 1, 2, 0))):
            for comp in ("ocn", "ice"):
                (rundir / "input.nml").write_text(self.BOTH_KINDS)
                assimilate.stage_inflation_files(case, comp, str(rundir))
                settings = assimilate.parse_inflation_settings(
                    str(rundir / "input.nml"))
                read = fake_filter(comp, cycle)
                # Production order: renames run in the try block, unstage in the
                # finally.  rename_stage_files must tolerate the links still
                # being present.
                assimilate.rename_stage_files(case, comp, model_time, str(rundir))
                assimilate.unstage_inflation_files(str(rundir))
                observed[(cycle, comp)] = (
                    settings['prior']['inf_initial_from_restart'],
                    read['priorinf_mean'])

        # Cycle 1: nothing to read, so both components bootstrap.
        for comp in ("ocn", "ice"):
            assert observed[(1, comp)] == (False, None)

        # Cycle 2: each component reads its own cycle-1 inflation.
        assert observed[(2, "ocn")] == (True, "ocn/cycle1")
        assert observed[(2, "ice")] == (True, "ice/cycle1")

        # Both cycles' restarts are present and per component; no untagged
        # inflation file survives for st_archive to trip over.
        assert list(rundir.glob("input_*inf_*.nc")) == []
        for comp in ("ocn", "ice"):
            for date in ("1976-01-01-00000", "1976-01-02-00000"):
                assert (rundir /
                        f"testcase.dart.rh.{comp}_output_priorinf_mean.{date}.nc"
                        ).exists()

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
            assimilate.stage_inflation_files(self._case(), "ocn", str(rundir))


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
    @patch('assimilate.unstage_inflation_files')
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
        mock_unstage_infl, mock_rename_stage
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
    @patch('assimilate.unstage_inflation_files')
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
        mock_unstage_infl, mock_rename_stage
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

    @patch('assimilate.rename_stage_files')
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
    def test_unstage_runs_when_filter_fails(
        self, mock_chdir, mock_exists, mock_subprocess,
        mock_get_time, mock_get_obs, mock_stage_nml, mock_check,
        mock_set_restart, mock_stage_infl, mock_rename_logs, mock_rename_obs,
        mock_rename_stage
    ):
        """
        A failed filter must still drop the inflation staging symlinks, or a
        stale link to this component's inflation is left in RUNDIR where another
        component could pick it up.  unstage_inflation_files therefore lives in
        the finally block, not the try.
        """
        mock_exists.return_value = True
        mock_get_time.return_value = ModelTime(2001, 1, 15, 0)
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            returncode=134, cmd="filter_atm", output="", stderr="ERROR from filter")
        mock_case = self._make_case("/run", "/exe")

        with patch('assimilate.unstage_inflation_files') as mock_unstage, \
             patch.dict('assimilate._SET_TEMPLATE_FILES', {'atm': Mock()}):
            with pytest.raises(subprocess.CalledProcessError):
                assimilate.run_filter_for_component(mock_case, "atm", "/caseroot")

        mock_unstage.assert_called_once_with("/run")
        # The renames are on the success path only.
        mock_rename_stage.assert_not_called()
        mock_rename_obs.assert_not_called()

    @patch('assimilate.rename_stage_files')
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
    def test_unstage_runs_when_post_converter_fails(
        self, mock_chdir, mock_exists, mock_subprocess,
        mock_get_time, mock_get_obs, mock_stage_nml, mock_check,
        mock_set_restart, mock_stage_infl, mock_rename_logs, mock_rename_obs,
        mock_rename_stage
    ):
        """Same guarantee when a post-filter converter (dart_to_cice etc.) is
        what fails, which is also inside the try block."""
        mock_exists.return_value = True
        mock_get_time.return_value = ModelTime(2001, 1, 15, 0)
        mock_subprocess.return_value = Mock(stdout="", stderr="")
        mock_case = self._make_case("/run", "/exe")

        with patch('assimilate.unstage_inflation_files') as mock_unstage, \
             patch('assimilate.run_model_programs_for_members',
                   side_effect=[None, RuntimeError("dart_to_cice blew up")]), \
             patch.dict('assimilate._SET_TEMPLATE_FILES', {'ice': Mock()}):
            with pytest.raises(RuntimeError, match="dart_to_cice"):
                assimilate.run_filter_for_component(mock_case, "ice", "/caseroot")

        mock_unstage.assert_called_once_with("/run")
        mock_rename_stage.assert_not_called()

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
