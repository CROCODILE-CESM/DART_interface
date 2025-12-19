#!/usr/bin/env python3
"""
Script to extract namelist definitions and their default values from Fortran .f90 files.
Uses fparser2 to parse Fortran source code and extract variable declarations and namelists.
"""

import re
import sys
from fparser.two.parser import ParserFactory
from fparser.two import Fortran2003 as f2003
from fparser.common.readfortran import FortranStringReader


def preprocess_fortran(src):
    """Preprocess Fortran source to handle common parsing issues."""
    # Replace "end do <label>" with "end do"
    src = re.sub(r'(?i)end\s+do\s+\w+', 'end do', src)
    # Remove continuation characters that might cause issues
    src = re.sub(r'&\s*\n\s*&', ' ', src)
    return src


def extract_namelist_defaults(filename):
    """
    Extract namelist definitions and their default values from a Fortran file.
    
    Args:
        filename: Path to the Fortran .f90 file
        
    Returns:
        dict: Dictionary with namelist names as keys and variable:default pairs as values
    """
    with open(filename, 'r') as f:
        src = f.read()
    
    # Preprocess the source
    src = preprocess_fortran(src)
    
    # Truncate at 'contains' to avoid parsing executable code
    if 'contains' in src.lower():
        src = src.split('contains')[0]
    
    try:
        # Parse the Fortran source
        parser = ParserFactory().create(std="f2003")
        reader = FortranStringReader(src)
        ast = parser(reader)
    except Exception as e:
        print(f"Error parsing {filename}: {e}")
        return {}
    
    namelists = {}
    declarations = {}
    
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
        
        # Extract variable declarations with default values
        elif isinstance(node, f2003.Type_Declaration_Stmt):
            try:
                # Structure: [declaration_type_spec, attr_spec, entity_decl_list]
                entity_decls = node.items[2]  # entity_decl_list
                if entity_decls is not None:
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
                                var_name = parts[0].strip().lower()
                                default_value = parts[1].strip()
                                declarations[var_name] = default_value
                            else:
                                # No default value for this variable
                                var_name = var_part.strip().lower()
                                declarations[var_name] = None
                    else:
                        # Single variable declaration
                        if '=' in decl_str:
                            parts = decl_str.split('=', 1)
                            var_name = parts[0].strip().lower()
                            default_value = parts[1].strip()
                            declarations[var_name] = default_value
                        else:
                            # No default value
                            var_name = decl_str.strip().lower()
                            declarations[var_name] = None
            except (IndexError, AttributeError, TypeError) as e:
                # Skip problematic declarations
                pass
    
    # Walk the entire AST
    walk_ast(ast)
    
    # Match namelists with their variable defaults
    result = {}
    for nml_name, var_names in namelists.items():
        result[nml_name] = {}
        for var_name in var_names:
            result[nml_name][var_name] = declarations.get(var_name, None)
    
    return result


def format_output(nml_defaults):
    """Format the output in namelist format."""
    if not nml_defaults:
        print("No namelists found.")
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


def main():
    """Main function to handle command line arguments and run extraction."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <fortran_file.f90>")
        print("\nExtract namelist definitions and default values from Fortran source files.")
        sys.exit(1)
    
    filename = sys.argv[1]
    
    try:
        nml_defaults = extract_namelist_defaults(filename)
        format_output(nml_defaults)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
