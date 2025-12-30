import pytest
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Add the cime_config directory to Python path for testing
test_dir = Path(__file__).parent
project_root = test_dir.parent.parent
cime_config_dir = project_root / "cime_config"
sys.path.insert(0, str(cime_config_dir))
sys.path.insert(0, str(project_root))

# Mock CIME modules if they're not available
def mock_cime_modules():
    """Mock CIME modules for testing."""
    # Mock the CIME modules
    cime_case = MagicMock()
    cime_utils = MagicMock()
    cime_buildnml = MagicMock()
    standard_script_setup = MagicMock()
    
    sys.modules['CIME'] = MagicMock()
    sys.modules['CIME.case'] = cime_case
    sys.modules['CIME.utils'] = cime_utils
    sys.modules['CIME.buildnml'] = cime_buildnml
    sys.modules['standard_script_setup'] = standard_script_setup
    
    # Set up specific mocks
    cime_case.Case = MagicMock()
    cime_utils.expect = MagicMock()
    cime_utils.symlink_force = MagicMock()
    cime_buildnml.parse_input = MagicMock()
    cime_buildnml.create_namelist_infile = MagicMock()

# Check if CIME is available, if not, mock it
try:
    import CIME
    CIME_AVAILABLE = True
except ImportError:
    mock_cime_modules()
    CIME_AVAILABLE = False

@pytest.fixture
def cime_available():
    """Fixture to indicate if CIME is available."""
    return CIME_AVAILABLE

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def sample_namelist():
    """Sample Fortran namelist content for testing."""
    return """&filter_nml
   ens_size                    = 20
   num_groups                  = 1
   inf_flavor                  = 2, 0
   inf_initial                 = 1.0, 1.0
   enable_assimilation_debug   = .false.
   qceff_table_filename        = ''
/

&assim_tools_nml
   cutoff                      = 0.03
   adaptive_cutoff_floor       = 0.0
   adaptive_localization_threshold = -1
   adjust_obs_impact           = .false.
/"""

@pytest.fixture
def sample_yaml():
    """Sample YAML content matching the namelist."""
    return {
        "filter_nml": {
            "ens_size": {"values": 20},
            "num_groups": {"values": 1},
            "inf_flavor": {"values": [2, 0]},
            "inf_initial": {"values": [1.0, 1.0]},
            "enable_assimilation_debug": {"values": False},
            "qceff_table_filename": {"values": ""}
        },
        "assim_tools_nml": {
            "cutoff": {"values": 0.03},
            "adaptive_cutoff_floor": {"values": 0.0},
            "adaptive_localization_threshold": {"values": -1},
            "adjust_obs_impact": {"values": False}
        }
    }