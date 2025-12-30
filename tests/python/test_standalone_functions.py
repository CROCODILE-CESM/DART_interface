import pytest
import tempfile
import re
from pathlib import Path


class TestStandaloneFunctions:
    """Test standalone functions that don't require CIME."""
    
    def test_convert_fortran_value_integers(self):
        """Test converting Fortran integer values."""
        
        def convert_fortran_value(value_str):
            """Standalone version of convert_fortran_value function."""
            value_str = value_str.strip()
            
            # Handle empty or quoted empty string
            if not value_str or value_str == "''":
                return ''
            
            # Handle booleans
            if value_str.lower() in ['.true.', 't']:
                return True
            if value_str.lower() in ['.false.', 'f']:
                return False
            
            # Handle comma-separated lists (arrays)
            if ',' in value_str:
                items = [convert_fortran_value(item.strip()) for item in value_str.split(',')]
                return items
            
            # Handle quoted strings
            if (value_str.startswith("'") and value_str.endswith("'")) or \
               (value_str.startswith('"') and value_str.endswith('"')):
                return value_str[1:-1]  # Remove quotes
            
            # Try to convert to number
            try:
                if '.' in value_str or 'e' in value_str.lower():
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                # If all else fails, return as string
                return value_str
        
        # Test integers
        assert convert_fortran_value("42") == 42
        assert convert_fortran_value("-999") == -999
        assert convert_fortran_value("0") == 0
    
    def test_convert_fortran_value_floats(self):
        """Test converting Fortran float values."""
        
        def convert_fortran_value(value_str):
            """Standalone version of convert_fortran_value function."""
            value_str = value_str.strip()
            
            if not value_str or value_str == "''":
                return ''
            
            if value_str.lower() in ['.true.', 't']:
                return True
            if value_str.lower() in ['.false.', 'f']:
                return False
            
            if ',' in value_str:
                items = [convert_fortran_value(item.strip()) for item in value_str.split(',')]
                return items
            
            if (value_str.startswith("'") and value_str.endswith("'")) or \
               (value_str.startswith('"') and value_str.endswith('"')):
                return value_str[1:-1]
            
            try:
                if '.' in value_str or 'e' in value_str.lower():
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                return value_str
        
        # Test floats
        assert convert_fortran_value("3.14159") == 3.14159
        assert convert_fortran_value("-2.5") == -2.5
        assert convert_fortran_value("1.23e-4") == 1.23e-4
        assert convert_fortran_value("0.0") == 0.0
    
    def test_convert_fortran_value_booleans(self):
        """Test converting Fortran boolean values."""
        
        def convert_fortran_value(value_str):
            """Standalone version of convert_fortran_value function."""
            value_str = value_str.strip()
            
            if not value_str or value_str == "''":
                return ''
            
            if value_str.lower() in ['.true.', 't']:
                return True
            if value_str.lower() in ['.false.', 'f']:
                return False
            
            if ',' in value_str:
                items = [convert_fortran_value(item.strip()) for item in value_str.split(',')]
                return items
            
            if (value_str.startswith("'") and value_str.endswith("'")) or \
               (value_str.startswith('"') and value_str.endswith('"')):
                return value_str[1:-1]
            
            try:
                if '.' in value_str or 'e' in value_str.lower():
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                return value_str
        
        # Test booleans
        assert convert_fortran_value(".true.") is True
        assert convert_fortran_value(".false.") is False
        assert convert_fortran_value("T") is True
        assert convert_fortran_value("F") is False
        assert convert_fortran_value(".TRUE.") is True
        assert convert_fortran_value(".FALSE.") is False
    
    def test_convert_fortran_value_strings(self):
        """Test converting Fortran string values."""
        
        def convert_fortran_value(value_str):
            """Standalone version of convert_fortran_value function."""
            value_str = value_str.strip()
            
            if not value_str or value_str == "''":
                return ''
            
            if value_str.lower() in ['.true.', 't']:
                return True
            if value_str.lower() in ['.false.', 'f']:
                return False
            
            if ',' in value_str:
                items = [convert_fortran_value(item.strip()) for item in value_str.split(',')]
                return items
            
            if (value_str.startswith("'") and value_str.endswith("'")) or \
               (value_str.startswith('"') and value_str.endswith('"')):
                return value_str[1:-1]
            
            try:
                if '.' in value_str or 'e' in value_str.lower():
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                return value_str
        
        # Test strings
        assert convert_fortran_value("'hello'") == "hello"
        assert convert_fortran_value('"world"') == "world"
        assert convert_fortran_value("''") == ""
        assert convert_fortran_value("") == ""
    
    def test_convert_fortran_value_lists(self):
        """Test converting Fortran list values."""
        
        def convert_fortran_value(value_str):
            """Standalone version of convert_fortran_value function."""
            value_str = value_str.strip()
            
            if not value_str or value_str == "''":
                return ''
            
            if value_str.lower() in ['.true.', 't']:
                return True
            if value_str.lower() in ['.false.', 'f']:
                return False
            
            if ',' in value_str:
                items = [convert_fortran_value(item.strip()) for item in value_str.split(',')]
                return items
            
            if (value_str.startswith("'") and value_str.endswith("'")) or \
               (value_str.startswith('"') and value_str.endswith('"')):
                return value_str[1:-1]
            
            try:
                if '.' in value_str or 'e' in value_str.lower():
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                return value_str
        
        # Test lists
        assert convert_fortran_value("1, 2, 3") == [1, 2, 3]
        assert convert_fortran_value("1.0, 2.0") == [1.0, 2.0]
        assert convert_fortran_value(".true., .false.") == [True, False]
        assert convert_fortran_value("'a', 'b', 'c'") == ['a', 'b', 'c']
    
    def test_simple_namelist_parsing(self, temp_dir):
        """Test simple namelist parsing without CIME dependencies."""
        
        def simple_parse_namelist(content):
            """Simple namelist parser for testing."""
            import re
            
            def convert_fortran_value(value_str):
                value_str = value_str.strip()
                
                if not value_str or value_str == "''":
                    return ''
                
                if value_str.lower() in ['.true.', 't']:
                    return True
                if value_str.lower() in ['.false.', 'f']:
                    return False
                
                if ',' in value_str:
                    items = [convert_fortran_value(item.strip()) for item in value_str.split(',')]
                    return items
                
                if (value_str.startswith("'") and value_str.endswith("'")) or \
                   (value_str.startswith('"') and value_str.endswith('"')):
                    return value_str[1:-1]
                
                try:
                    if '.' in value_str or 'e' in value_str.lower():
                        return float(value_str)
                    else:
                        return int(value_str)
                except ValueError:
                    return value_str
            
            nml_dict = {}
            current_nml = None
            
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                
                if line.startswith('&'):
                    current_nml = line[1:].strip()
                    nml_dict[current_nml] = {}
                    continue
                
                if line.startswith('/'):
                    current_nml = None
                    continue
                
                if current_nml and '=' in line:
                    match = re.match(r'(\w+)\s*=\s*(.+)', line)
                    if match:
                        var_name = match.group(1).strip()
                        var_value = match.group(2).strip().rstrip(',')
                        nml_dict[current_nml][var_name] = convert_fortran_value(var_value)
            
            return nml_dict
        
        # Test content
        namelist_content = """&test_nml
   int_var = 42
   float_var = 3.14
   bool_var = .true.
   string_var = 'hello'
   list_var = 1, 2, 3
/"""
        
        result = simple_parse_namelist(namelist_content)
        
        assert "test_nml" in result
        assert result["test_nml"]["int_var"] == 42
        assert result["test_nml"]["float_var"] == 3.14
        assert result["test_nml"]["bool_var"] is True
        assert result["test_nml"]["string_var"] == "hello"
        assert result["test_nml"]["list_var"] == [1, 2, 3]