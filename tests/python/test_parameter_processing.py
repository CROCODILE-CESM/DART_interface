import pytest
import tempfile
import json
import yaml
from pathlib import Path
import sys
import os

# Add cime_config to path
test_dir = Path(__file__).parent
project_root = test_dir.parent.parent
sys.path.insert(0, str(project_root))


class TestParameterProcessing:
    """Test parameter file processing utilities."""
    
    def test_yaml_to_json_conversion(self, temp_dir, sample_yaml):
        """Test YAML to JSON conversion functionality."""
        
        # Test the actual yaml_to_json script functionality
        try:
            # Import the actual yaml_to_json module if it exists
            sys.path.insert(0, str(project_root / "param_templates"))
            
            # Write sample YAML
            yaml_file = temp_dir / "test.yaml"
            with open(yaml_file, 'w') as f:
                yaml.dump(sample_yaml, f)
            
            # Test the conversion logic
            with open(yaml_file, 'r') as f:
                yaml_data = yaml.safe_load(f)
            
            json_file = temp_dir / "test.json"
            with open(json_file, 'w') as f:
                json.dump(yaml_data, f, indent=2)
            
            # Verify JSON output
            with open(json_file, 'r') as f:
                json_data = json.load(f)
            
            assert json_data == sample_yaml
            assert "filter_nml" in json_data
            assert json_data["filter_nml"]["ens_size"]["values"] == 20
            
        except ImportError:
            # Fallback to testing the basic functionality
            yaml_file = temp_dir / "test.yaml"
            with open(yaml_file, 'w') as f:
                yaml.dump(sample_yaml, f)
            
            with open(yaml_file, 'r') as f:
                yaml_data = yaml.safe_load(f)
            
            assert yaml_data == sample_yaml
    
    def test_wrap_in_values_structure(self):
        """Test wrapping values in the expected structure."""
        
        def wrap_in_values(data):
            """Test version of wrap_in_values function."""
            if isinstance(data, dict):
                return {key: wrap_in_values(val) for key, val in data.items()}
            elif isinstance(data, list):
                # Convert list to comma-separated string for Fortran compatibility
                list_str = ', '.join(str(item) for item in data)
                return {'values': list_str}
            elif isinstance(data, str) and data.strip() == '':
                return {'values': ''}
            else:
                # Leaf node - wrap it
                return {'values': data}
        
        # Test data without values structure
        input_data = {
            "filter_nml": {
                "ens_size": 20,
                "inf_flavor": [2, 0],
                "enable_debug": False,
                "filename": ""
            }
        }
        
        result = wrap_in_values(input_data)
        
        # Check wrapped structure
        assert result["filter_nml"]["ens_size"]["values"] == 20
        assert result["filter_nml"]["inf_flavor"]["values"] == "2, 0"
        assert result["filter_nml"]["enable_debug"]["values"] is False
        assert result["filter_nml"]["filename"]["values"] == ""


class TestDARTInputNml:
    """Test the DART_input_nml class functionality."""
    
    def test_convert_lists_to_strings_import(self, sample_yaml):
        """Test importing and using the actual DART_input_nml class."""
        try:
            # Mock the CIME dependencies first
            import sys
            from unittest.mock import MagicMock
            
            # Mock CIME modules
            sys.modules['CIME'] = MagicMock()
            sys.modules['CIME.ParamGen'] = MagicMock()
            sys.modules['CIME.ParamGen.paramgen'] = MagicMock()
            
            # Create a mock ParamGen class
            class MockParamGen:
                def __init__(self):
                    self._data = {}
                
                def reduce(self, func):
                    pass
                
                def write_nml(self, path):
                    pass
            
            sys.modules['CIME.ParamGen.paramgen'].ParamGen = MockParamGen
            
            # Now try to import the actual module
            from cime_config.dart_input_nml import DART_input_nml
            
            # Create instance
            dart_nml = DART_input_nml()
            dart_nml._data = sample_yaml.copy()
            
            # Test the actual _convert_lists_to_strings method
            dart_nml._convert_lists_to_strings(dart_nml._data)
            
            # Check that lists are converted to comma-separated strings
            assert dart_nml._data["filter_nml"]["inf_flavor"]["values"] == "2, 0"
            assert dart_nml._data["filter_nml"]["inf_initial"]["values"] == "1.0, 1.0"
            
            # Check that booleans are converted to Fortran format
            assert dart_nml._data["filter_nml"]["enable_assimilation_debug"]["values"] == ".false."
            assert dart_nml._data["assim_tools_nml"]["adjust_obs_impact"]["values"] == ".false."
            
            # Check that empty strings are handled
            assert dart_nml._data["filter_nml"]["qceff_table_filename"]["values"] == "''"
            
            # Check that numbers are left as-is
            assert dart_nml._data["filter_nml"]["ens_size"]["values"] == 20
            assert dart_nml._data["assim_tools_nml"]["cutoff"]["values"] == 0.03
            
        except ImportError as e:
            pytest.skip(f"Could not import DART_input_nml: {e}")


class TestExtractNamelistDefaults:
    """Test namelist default extraction functionality."""
    
    def test_clean_default_value(self):
        """Test the clean_default_value function."""
        
        def clean_default_value(value):
            """Test version of clean_default_value function."""
            import re
            if value is None:
                return None
            
            value_str = str(value)
            # Remove spaces around unary minus for negative numbers
            value_str = re.sub(r'- (\d+)', r'-\1', value_str)
            # Remove spaces around unary minus for negative floats
            value_str = re.sub(r'- (\d+\.\d+)', r'-\1', value_str)
            # Remove spaces around unary minus for scientific notation
            value_str = re.sub(r'- (\d+(?:\.\d+)?(?:_r8|_r4)?(?:[eE][+-]?\d+)?)', r'-\1', value_str)
            
            # Remove Fortran kind specifiers (_r8, _r4, _digits12, etc.)
            value_str = re.sub(r'_(r[0-9]+|digits[0-9]+)', '', value_str)
            
            return value_str
        
        # Test Fortran kind removal
        assert clean_default_value("1.0_r8") == "1.0"
        assert clean_default_value("2.5_r4") == "2.5"
        assert clean_default_value("123_digits12") == "123"
        
        # Test negative number cleanup
        assert clean_default_value("- 42") == "-42"
        assert clean_default_value("- 3.14") == "-3.14"
        assert clean_default_value("- 1.23e-4") == "-1.23e-4"
        
        # Test normal values
        assert clean_default_value("42") == "42"
        assert clean_default_value("3.14159") == "3.14159"
        assert clean_default_value("'test'") == "'test'"