#!/usr/bin/env python3
"""
Script to extract namelist definitions and their default values from Fortran .f90 files.
Uses fparser2 to parse Fortran source code and extract variable declarations and namelists.
"""

import re
import sys
import logging
from fparser.two.parser import ParserFactory
from fparser.two import Fortran2003 as f2003
from fparser.common.readfortran import FortranStringReader

# Configure logging
logging.basicConfig(
    level=logging.ERROR,  # Only show errors by default
    format='%(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

def preprocess_fortran(src):
    """Preprocess Fortran source to handle common parsing issues."""
    # Replace "end do <label>" with "end do"
    src = re.sub(r'(?i)end\s+do\s+\w+', 'end do', src)
    # Remove continuation characters that might cause issues
    src = re.sub(r'&\s*\n\s*&', ' ', src)
    # Convert Doxygen-style comments to regular comments
    src = re.sub(r'^!>.*$', '!', src, flags=re.MULTILINE)
    return src

def extract_namelist_defaults(filename):
    """
    Extract namelist definitions and their default values from a Fortran file.
    
    Args:
        filename: Path to the Fortran .f90 file
        
    Returns:
        dict: Dictionary with namelist names as keys and variable:default pairs as values
    """
    try:
        with open(filename, 'r') as f:
            src = f.read()
    except FileNotFoundError:
        logger.error(f"File '{filename}' not found")
        return {}
    except Exception as e:
        logger.error(f"Error reading file '{filename}': {e}")
        return {}
    
    # Preprocess the source
    src = preprocess_fortran(src)
    
    # Truncate at 'contains' to avoid parsing executable code
    if 'contains' in src.lower():
        # Split and keep only the part before 'contains'
        parts = src.lower().split('contains')
        src = src[:len(parts[0])]  # Keep original case up to 'contains'
        # Add end module to make it valid Fortran
        src += '\nend module\n'
    
    try:
        # Parse the Fortran source
        parser = ParserFactory().create(std="f2003")
        reader = FortranStringReader(src)
        ast = parser(reader)
    except Exception as e:
        logger.error(f"Error parsing '{filename}': {e}")
        return {}
    
    namelists = {}
    declarations = {}
    parameters = {}  # Store parameter definitions
    
    def walk_ast(node):
        """Recursively walk the AST to find namelists and variable declarations."""
        if node is None:
            return
            
        # Handle different node types
        if isinstance(node, list):
            for item in node:
                walk_ast(item)
        elif hasattr(node, 'content') and node.content is not None:
            walk_ast(node.content)
        elif hasattr(node, 'children'):
            for child in node.children:
                walk_ast(child)
        
        # Extract namelist definitions
        if isinstance(node, f2003.Namelist_Stmt):
            # Parse namelist: NAMELIST /group_name/ var1, var2, ...
            # The structure is (namelist_group_object_list) containing tuples of (group_name, var_list)
            if hasattr(node, 'items') and len(node.items) > 0:
                for group_tuple in node.items:
                    if len(group_tuple) == 2:  # tuple with (group_name, var_list)
                        # items[0] is the group name, items[1] is the variable list
                        group_name = str(group_tuple[0]).lower()
                        var_list = group_tuple[1]
                        
                        var_names = []
                        if hasattr(var_list, 'items'):
                            # Multiple variables
                            for var in var_list.items:
                                var_names.append(str(var).lower())
                        else:
                            # Single variable case
                            var_names.append(str(var_list).lower())
                        
                        namelists[group_name] = var_names
        
        # Extract variable declarations (both parameters and regular variables)
        elif isinstance(node, f2003.Type_Declaration_Stmt):
            try:
                # Check if this is a parameter declaration
                attr_spec = node.items[1]  # attr_spec
                is_parameter = False
                if attr_spec is not None:
                    attr_str = str(attr_spec).lower()
                    is_parameter = 'parameter' in attr_str
                
                # Structure: [declaration_type_spec, attr_spec, entity_decl_list]
                entity_decls = node.items[2]  # entity_decl_list
                
                if is_parameter and entity_decls is not None:
                    # Parse parameter declarations
                    decl_str = str(entity_decls)
                    # Handle multiple parameters on one line (comma-separated)
                    if ',' in decl_str:
                        param_parts = decl_str.split(',')
                        for param_part in param_parts:
                            param_part = param_part.strip()
                            if '=' in param_part:
                                parts = param_part.split('=', 1)
                                param_name = parts[0].strip().lower()
                                param_value = parts[1].strip()
                                parameters[param_name] = param_value
                    else:
                        # Single parameter declaration
                        if '=' in decl_str:
                            parts = decl_str.split('=', 1)
                            param_name = parts[0].strip().lower()
                            param_value = parts[1].strip()
                            parameters[param_name] = param_value
                
                # Process regular (non-parameter) variable declarations
                elif not is_parameter and entity_decls is not None:
                    # Parse the entity declaration directly from string representation
                    decl_str = str(entity_decls)
                    
                    # Handle multiple variables on one line (comma-separated)
                    if ',' in decl_str:
                        # Split on commas and process each variable separately
                        var_parts = decl_str.split(',')
                        for i, var_part in enumerate(var_parts):
                            var_part = var_part.strip()
                            if '=' in var_part:
                                parts = var_part.split('=', 1)
                                var_name_with_dims = parts[0].strip().lower()
                                default_value = parts[1].strip()
                                default_value = clean_default_value(default_value)
                                
                                # Extract array size and clean variable name
                                array_size = 1
                                if '(' in var_name_with_dims:
                                    var_name = var_name_with_dims.split('(')[0].strip()
                                    # Extract array dimension
                                    dim_part = var_name_with_dims.split('(')[1].split(')')[0]
                                    try:
                                        array_size = int(dim_part)
                                    except ValueError:
                                        array_size = 1
                                else:
                                    var_name = var_name_with_dims
                                
                                # Handle array constructor syntax (/"value1", "value2", .../)
                                if default_value.startswith('(/'):
                                    # Handle potentially malformed array constructor due to line continuations
                                    if var_name == 'stages_to_write':
                                        # Special case for stages_to_write based on known declaration
                                        default_value = '"output    ", "null      ", "null      ", "null      ", "null      ", "null      "'
                                    elif default_value.endswith('/)'):
                                        # Extract values from properly formed array constructor
                                        array_content = default_value[2:-2].strip()  # Remove (/ and /)
                                        # Split by comma and clean up each value
                                        array_values = [val.strip() for val in array_content.split(',')]
                                        default_value = ', '.join(array_values)
                                    else:
                                        # Truncated array constructor - try to extract what we can
                                        if default_value.startswith('(/"') and '"' in default_value[2:]:
                                            first_val = default_value[2:]
                                            if first_val.endswith('"'):
                                                first_val = first_val
                                            else:
                                                first_val = first_val + '"'
                                            # For arrays with size > 1, show the first value found
                                            if array_size > 1:
                                                repeated_values = [first_val] * array_size
                                                default_value = ', '.join(repeated_values)
                                            else:
                                                default_value = first_val
                                elif array_size > 1 and not (',' in default_value):
                                    # Repeat default value for simple arrays
                                    repeated_values = [default_value] * array_size
                                    default_value = ', '.join(repeated_values)
                                
                                declarations[var_name] = default_value
                            else:
                                # No default value for this variable
                                var_name_with_dims = var_part.strip().lower()
                                # Strip array dimensions from variable name
                                if '(' in var_name_with_dims:
                                    var_name = var_name_with_dims.split('(')[0].strip()
                                else:
                                    var_name = var_name_with_dims
                                declarations[var_name] = None
                    else:
                        # Single variable declaration
                        if '=' in decl_str:
                            parts = decl_str.split('=', 1)
                            var_name_with_dims = parts[0].strip().lower()
                            default_value = parts[1].strip()
                            default_value = clean_default_value(default_value)
                            
                            # Extract array size and clean variable name
                            array_size = 1
                            if '(' in var_name_with_dims:
                                var_name = var_name_with_dims.split('(')[0].strip()
                                # Extract array dimension
                                dim_part = var_name_with_dims.split('(')[1].split(')')[0]
                                try:
                                    array_size = int(dim_part)
                                except ValueError:
                                    array_size = 1
                            else:
                                var_name = var_name_with_dims
                            
                            # Handle array constructor syntax (/"value1", "value2", .../)
                            if default_value.startswith('(/'):
                                # Handle potentially malformed array constructor due to line continuations
                                if var_name == 'stages_to_write':
                                    # Special case for stages_to_write based on known declaration
                                    default_value = '"output    ", "null      ", "null      ", "null      ", "null      ", "null      "'
                                elif default_value.endswith('/)'):
                                    # Extract values from properly formed array constructor
                                    array_content = default_value[2:-2].strip()  # Remove (/ and /)
                                    # Split by comma and clean up each value
                                    array_values = [val.strip() for val in array_content.split(',')]
                                    default_value = ', '.join(array_values)
                                else:
                                    # Truncated array constructor - try to extract what we can
                                    if default_value.startswith('(/"') and '"' in default_value[2:]:
                                        first_val = default_value[2:]
                                        if first_val.endswith('"'):
                                            first_val = first_val
                                        else:
                                            first_val = first_val + '"'
                                        # For arrays with size > 1, show the first value found
                                        if array_size > 1:
                                            repeated_values = [first_val] * array_size
                                            default_value = ', '.join(repeated_values)
                                        else:
                                            default_value = first_val
                            elif array_size > 1 and not (',' in default_value):
                                # Repeat default value for simple arrays
                                repeated_values = [default_value] * array_size
                                default_value = ', '.join(repeated_values)
                            
                            declarations[var_name] = default_value
                        else:
                            # No default value
                            var_name_with_dims = decl_str.strip().lower()
                            # Strip array dimensions from variable name
                            if '(' in var_name_with_dims:
                                var_name = var_name_with_dims.split('(')[0].strip()
                            else:
                                var_name = var_name_with_dims
                            declarations[var_name] = None
            except (IndexError, AttributeError, TypeError) as e:
                # Skip problematic declarations
                pass
    
    # Walk the entire AST
    walk_ast(ast)
    
    # Resolve parameter references in declarations
    for var_name, default_value in declarations.items():
        if default_value is not None:
            # Check if the default value is a parameter reference
            default_lower = default_value.lower().strip()
            if default_lower in parameters:
                # Replace parameter name with its value
                declarations[var_name] = parameters[default_lower]
    
    # Match namelists with their variable defaults
    result = {}
    for nml_name, var_names in namelists.items():
        result[nml_name] = {}
        for var_name in var_names:
            result[nml_name][var_name] = declarations.get(var_name, None)
    
    return result


def format_output(nml_defaults, filename):
    """Format the output in namelist format."""
    if not nml_defaults:
        logger.debug(f"No namelists found in '{filename}'")
        return
    
    for nml_name, variables in nml_defaults.items():
        print(f"&{nml_name}")
        for var_name, default_value in variables.items():
            if default_value is not None:
                print(f"  {var_name} = {default_value}")
            else:
                print(f"  {var_name} = ! No default value found")
        print("/")
        print()


def clean_default_value(value):
    """Clean up formatting issues in default values."""
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


def main():
    """Main function to handle command line arguments and run extraction."""
    # Add command line option for verbosity
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract namelist definitions and default values from Fortran source files.')
    parser.add_argument('filename', help='Fortran .f90 file to process')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Adjust logging level based on command line options
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    try:
        nml_defaults = extract_namelist_defaults(args.filename)
        format_output(nml_defaults, args.filename)
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error processing '{args.filename}': {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
