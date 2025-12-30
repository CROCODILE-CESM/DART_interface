import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to path
test_dir = Path(__file__).parent
project_root = test_dir.parent.parent
sys.path.insert(0, str(project_root))


class TestDARTInputDataList:
    """Test DART_input_data_list module."""
    
    def test_import_dart_input_data_list(self):
        """Test importing DART_input_data_list with mocked CIME."""
        
        # Mock CIME modules
        sys.modules['CIME'] = MagicMock()
        sys.modules['CIME.ParamGen'] = MagicMock()
        sys.modules['CIME.ParamGen.paramgen'] = MagicMock()
        
        # Create a mock ParamGen class
        class MockParamGen:
            def __init__(self):
                self._data = {}
            
            @classmethod
            def from_json(cls, json_file):
                instance = cls()
                instance._data = {"mock": "data"}
                return instance
            
            def reduce(self, func):
                pass
            
            def write(self, path, case):
                pass
        
        sys.modules['CIME.ParamGen.paramgen'].ParamGen = MockParamGen
        
        try:
            from cime_config.dart_input_data_list import DART_input_data_list
            
            # Test basic functionality
            assert hasattr(DART_input_data_list, 'from_json')
            
            # Test instantiation (should not fail)
            instance = DART_input_data_list()
            assert hasattr(instance, 'write')
            
        except ImportError as e:
            pytest.fail(f"Could not import DART_input_data_list: {e}")


class TestDARTInputNmlModule:
    """Test DART_input_nml module functionality."""
    
    def test_import_dart_input_nml(self):
        """Test importing DART_input_nml with mocked CIME."""
        
        # Mock CIME modules
        sys.modules['CIME'] = MagicMock()
        sys.modules['CIME.ParamGen'] = MagicMock()
        sys.modules['CIME.ParamGen.paramgen'] = MagicMock()
        
        class MockParamGen:
            def __init__(self):
                self._data = {}
            
            @classmethod
            def from_json(cls, json_file):
                instance = cls()
                instance._data = {"mock": "data"}
                return instance
            
            def reduce(self, func):
                pass
            
            def write_nml(self, path):
                pass
        
        sys.modules['CIME.ParamGen.paramgen'].ParamGen = MockParamGen
        
        try:
            from cime_config.dart_input_nml import DART_input_nml
            
            # Test basic functionality
            assert hasattr(DART_input_nml, '_convert_lists_to_strings')
            
            # Test instantiation
            instance = DART_input_nml()
            assert hasattr(instance, 'write')
            assert hasattr(instance, '_convert_lists_to_strings')
            
        except ImportError as e:
            pytest.fail(f"Could not import DART_input_nml: {e}")
    
    def test_convert_lists_to_strings_method(self):
        """Test the _convert_lists_to_strings method with actual code."""
        
        # Mock CIME first
        sys.modules['CIME'] = MagicMock()
        sys.modules['CIME.ParamGen'] = MagicMock()
        sys.modules['CIME.ParamGen.paramgen'] = MagicMock()
        
        class MockParamGen:
            def __init__(self):
                self._data = {}
        
        sys.modules['CIME.ParamGen.paramgen'].ParamGen = MockParamGen
        
        try:
            from cime_config.dart_input_nml import DART_input_nml
            
            # Create test data
            test_data = {
                "test_nml": {
                    "list_var": [1, 2, 3],
                    "bool_var": True,
                    "str_var": "test",
                    "empty_str": "",
                    "int_var": 42,
                    "float_var": 3.14,
                    "nested": {
                        "nested_list": [4, 5, 6],
                        "nested_bool": False
                    }
                }
            }
            
            # Create instance and test method
            instance = DART_input_nml()
            instance._convert_lists_to_strings(test_data)
            
            # Verify conversions
            assert test_data["test_nml"]["list_var"] == "1, 2, 3"
            assert test_data["test_nml"]["bool_var"] == ".true."
            assert test_data["test_nml"]["str_var"] == "'test'"
            assert test_data["test_nml"]["empty_str"] == "''"
            assert test_data["test_nml"]["int_var"] == 42
            assert test_data["test_nml"]["float_var"] == 3.14
            assert test_data["test_nml"]["nested"]["nested_list"] == "4, 5, 6"
            assert test_data["test_nml"]["nested"]["nested_bool"] == ".false."
            
        except ImportError as e:
            pytest.skip(f"Could not import DART_input_nml: {e}")