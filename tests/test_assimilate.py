#!/usr/bin/env python3

"""
Pytest suite for assimilate.py

Tests the data assimilation script for CESM MOM6 with mocked CIME dependencies.
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch, mock_open, MagicMock, call
from pathlib import Path
import tempfile
import shutil

# Mock CIME modules before importing assimilate
sys.modules['standard_script_setup'] = Mock()
sys.modules['CIME'] = Mock()
sys.modules['CIME.case'] = Mock()

# Set CIMEROOT environment variable for import
os.environ['CIMEROOT'] = '/mock/cimeroot'

# Add parent directory to path to import assimilate
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'cime_config'))

import assimilate
from assimilate import ModelTime


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


class TestBackupMomInputNml:
    """Test backup_mom_input_nml function."""
    
    def test_backup_existing_file(self, tmp_path):
        """Test backing up an existing input.nml file."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        input_nml = rundir / "input.nml"
        input_nml.write_text("test content")
        
        assimilate.backup_mom_input_nml(str(rundir))
        
        backup_file = rundir / "mom_input.nml.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == "test content"
    
    def test_backup_nonexistent_file(self, tmp_path, caplog):
        """Test backup when input.nml doesn't exist."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        assimilate.backup_mom_input_nml(str(rundir))
        
        assert "backup skipped" in caplog.text.lower()


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
        
        assert "missing required files" in caplog.text.lower()
        assert "input.nml" in caplog.text
        assert "obs_seq.out" in caplog.text


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
        
        assimilate.set_restart_files(str(rundir), model_time)
        
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
        
        assimilate.set_restart_files(str(rundir), model_time)
        
        filter_input = rundir / "filter_input_list.txt"
        content = filter_input.read_text()
        
        assert "restart_001.nc" in content
        assert "restart_002.nc" in content
        assert "restart_003.nc" in content
    
    def test_no_rpointer_files(self, tmp_path, caplog):
        """Test when no rpointer files exist."""
        import logging
        caplog.set_level(logging.WARNING)
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        model_time = ModelTime(2001, 1, 2, 0)
        
        with pytest.raises(FileNotFoundError, match="No rpointer"):
            assimilate.set_restart_files(str(rundir), model_time)
        
        assert "no rpointer" in caplog.text.lower()


class TestSetTemplateFiles:
    """Test set_template_files function."""
    
    def test_create_symlinks(self, tmp_path):
        """Test creating template file symlinks."""
        mock_case = Mock()
        mock_case.get_value.return_value = "test_case"
        
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        # Create filter_input_list.txt
        filter_input = rundir / "filter_input_list.txt"
        filter_input.write_text("restart_001.nc\n")
        
        # Create actual restart file
        restart_file = rundir / "restart_001.nc"
        restart_file.write_text("")
        
        # Create static file
        static_file = rundir / "test_case.mom6.h.static.nc"
        static_file.write_text("")
        
        assimilate.set_template_files(mock_case, str(rundir))
        
        mom6_r = rundir / "mom6.r.nc"
        mom6_static = rundir / "mom6.static.nc"
        
        assert mom6_r.is_symlink()
        assert mom6_static.is_symlink()
        assert mom6_r.resolve() == restart_file.resolve()
        assert mom6_static.resolve() == static_file.resolve()
    
    def test_missing_filter_input_list(self, tmp_path, caplog):
        """Test when filter_input_list.txt doesn't exist."""
        mock_case = Mock()
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        assimilate.set_template_files(mock_case, str(rundir))
        
        assert "filter_input_list.txt not found" in caplog.text


class TestCleanUp:
    """Test clean_up function."""
    
    def test_restore_backup(self, tmp_path):
        """Test restoring MOM input.nml from backup."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        backup = rundir / "mom_input.nml.bak"
        backup.write_text("original mom content")
        
        input_nml = rundir / "input.nml"
        input_nml.write_text("dart content")
        
        assimilate.clean_up(str(rundir))
        
        assert input_nml.read_text() == "original mom content"
    
    def test_no_backup_exists(self, tmp_path, caplog):
        """Test cleanup when no backup exists."""
        rundir = tmp_path / "run"
        rundir.mkdir()
        
        assimilate.clean_up(str(rundir))
        
        assert "cleanup skipped" in caplog.text.lower()


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


class TestRunFilter:
    """Test run_filter function."""
    
    @patch('assimilate.os.rename')
    @patch('assimilate.clean_up')
    @patch('assimilate.set_template_files')
    @patch('assimilate.set_restart_files')
    @patch('assimilate.check_required_files')
    @patch('assimilate.stage_dart_input_nml')
    @patch('assimilate.backup_mom_input_nml')
    @patch('assimilate.get_observations', create=True)
    @patch('assimilate.get_model_time')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.chdir')
    def test_run_filter_success(
        self, mock_chdir, mock_exists, mock_subprocess,
        mock_get_time, mock_get_obs, mock_backup, mock_stage,
        mock_check, mock_set_restart, mock_set_template, mock_cleanup,
	mock_rename
    ):
        """Test successful filter run."""
        # Setup mocks
        mock_case = Mock()
        mock_case.get_value.side_effect = lambda x: {
            "RUNDIR": "/run/dir",
            "EXEROOT": "/exe/root",
            "NTASKS_ESP": 4,
            "MPI_RUN_COMMAND": "mpirun -np 4",
            "CASE": "testcase"
        }.get(x)
        mock_exists.return_value = True
        model_time = ModelTime(2001, 1, 15, 43200)
        mock_get_time.return_value = model_time
        mock_result = Mock()
        mock_result.stdout = "Filter output"
        mock_subprocess.return_value = mock_result
        # Run function
        assimilate.run_filter(mock_case, "/case/root")
        # Verify calls
        mock_chdir.assert_called_once_with("/run/dir")
        mock_get_time.assert_called_once_with(mock_case)
        mock_get_obs.assert_called_once_with(mock_case, model_time, "/run/dir")
        mock_backup.assert_called_once_with("/run/dir")
        mock_stage.assert_called_once_with(mock_case, "/run/dir")
        mock_check.assert_called_once_with("/run/dir")
        mock_set_restart.assert_called_once_with("/run/dir", model_time)
        mock_set_template.assert_called_once_with(mock_case, "/run/dir")
        mock_subprocess.assert_called_once()
        mock_cleanup.assert_called_once_with("/run/dir")
        # check log renaming
        date_str = "20010115_43200"
        mock_rename.assert_any_call("/run/dir/dart_log.out", f"/run/dir/dart_log_testcase_{date_str}.out")
        mock_rename.assert_any_call("/run/dir/dart_log.nml", f"/run/dir/dart_log_testcase_{date_str}.nml")
    
    @patch('assimilate.get_model_time')
    @patch('os.path.exists')
    def test_run_filter_missing_executable(self, mock_exists, mock_get_time):
        """Test when filter executable doesn't exist."""
        mock_case = Mock()
        mock_case.get_value.side_effect = lambda x: {
            "RUNDIR": "/run/dir",
            "EXEROOT": "/exe/root"
        }.get(x)
        
        mock_exists.return_value = False
        
        with pytest.raises(FileNotFoundError, match="Filter executable not found"):
            assimilate.run_filter(mock_case, "/case/root")
    
    @patch('assimilate.clean_up')
    @patch('assimilate.set_template_files')
    @patch('assimilate.set_restart_files')
    @patch('assimilate.check_required_files')
    @patch('assimilate.stage_dart_input_nml')
    @patch('assimilate.backup_mom_input_nml')
    @patch('assimilate.get_observations', create=True)
    @patch('assimilate.get_model_time')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.chdir')
    def test_run_filter_subprocess_error(
        self, mock_chdir, mock_exists, mock_subprocess,
        mock_get_time, mock_get_obs, mock_backup, mock_stage,
        mock_check, mock_set_restart, mock_set_template, mock_cleanup
    ):
        """Test when subprocess returns error."""
        mock_case = Mock()
        mock_case.get_value.side_effect = lambda x: {
            "RUNDIR": "/run/dir",
            "EXEROOT": "/exe/root",
            "NTASKS_ESP": 4,
            "MPI_RUN_COMMAND": "mpirun"
        }.get(x)
        
        mock_exists.return_value = True
        mock_get_time.return_value = ModelTime(2001, 1, 15, 43200)
        
        # Simulate subprocess error
        import subprocess
        mock_subprocess.side_effect = subprocess.CalledProcessError(
            1, "filter", stderr="Filter error"
        )
        
        with pytest.raises(subprocess.CalledProcessError):
            assimilate.run_filter(mock_case, "/case/root")

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
        date_str = f"20200506_12345"
        new_log_out = rundir / f"dart_log_testcase_{date_str}.out"
        new_log_nml = rundir / f"dart_log_testcase_{date_str}.nml"
        assert new_log_out.exists()
        assert new_log_nml.exists()
        assert new_log_out.read_text() == "log out content"
        assert new_log_nml.read_text() == "log nml content"

class TestMain:
    """Test main and assimilate() entry points."""


    @patch('assimilate.Case')
    @patch('assimilate.run_filter')
    def test_assimilate_function_default(self, mock_run_filter, mock_Case):
        """Test assimilate() function with caseroot argument (default use_mpi)."""
        mock_case_instance = Mock()
        mock_Case.return_value.__enter__.return_value = mock_case_instance
        assimilate.assimilate("/case/root")
        mock_Case.assert_called_once_with("/case/root")
        mock_run_filter.assert_called_once_with(mock_case_instance, "/case/root", use_mpi=True)

    @patch('assimilate.Case')
    @patch('assimilate.run_filter')
    def test_assimilate_function_no_mpi(self, mock_run_filter, mock_Case):
        """Test assimilate() function with use_mpi=False."""
        mock_case_instance = Mock()
        mock_Case.return_value.__enter__.return_value = mock_case_instance
        assimilate.assimilate("/case/root", use_mpi=False)
        mock_Case.assert_called_once_with("/case/root")
        mock_run_filter.assert_called_once_with(mock_case_instance, "/case/root", use_mpi=False)


    @patch('assimilate.Case')
    @patch('assimilate.run_filter')
    def test_main_with_argv(self, mock_run_filter, mock_Case):
        """Test main() with command-line caseroot argument (default: use_mpi)."""
        mock_case_instance = Mock()
        mock_Case.return_value.__enter__.return_value = mock_case_instance
        test_argv = ["assimilate.py", "/case/root"]
        with patch('sys.argv', test_argv):
            assimilate.main()
        mock_Case.assert_called_once_with("/case/root")
        mock_run_filter.assert_called_once_with(mock_case_instance, "/case/root", use_mpi=True)

    @patch('assimilate.Case')
    @patch('assimilate.run_filter')
    def test_main_with_no_mpi_flag(self, mock_run_filter, mock_Case):
        """Test main() with --no-mpi flag disables MPI."""
        mock_case_instance = Mock()
        mock_Case.return_value.__enter__.return_value = mock_case_instance
        test_argv = ["assimilate.py", "/case/root", "--no-mpi"]
        with patch('sys.argv', test_argv):
            assimilate.main()
        mock_Case.assert_called_once_with("/case/root")
        mock_run_filter.assert_called_once_with(mock_case_instance, "/case/root", use_mpi=False)

    def test_main_no_argv_errors(self):
        """Test main() errors if no caseroot argument is given."""
        import io
        test_argv = ["assimilate.py"]
        with patch('sys.argv', test_argv), patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as excinfo:
                assimilate.main()
            assert excinfo.value.code == 2  # argparse exits with code 2 for missing required args


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
