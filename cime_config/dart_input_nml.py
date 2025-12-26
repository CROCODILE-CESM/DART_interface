import os, sys, shutil

# Are these two lines needed?
_CIMEROOT = os.getenv("CIMEROOT")
sys.path.append(os.path.join(_CIMEROOT, "scripts", "Tools"))

from CIME.ParamGen.paramgen import ParamGen

class DART_input_nml(ParamGen):
    """Encapsulates data and read/write methods for DART input.nml file"""

    def write(self, output_path, case):
        # From the general template (input_nml.yaml), reduce a custom input.nml for this case
        self.reduce(lambda varname: case.get_value(varname))
        # Convert lists to comma-separated strings for Fortran format
        self._convert_lists_to_strings(self._data)
        # write the data in namelist format
        self.write_nml(output_path)

    def _convert_lists_to_strings(self, data):
        """Recursively convert lists to comma-separated strings, strings,
           and booleans to Fortran format."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, bool):
                    # Convert Python bool to Fortran bool
                    data[key] = '.true.' if value else '.false.'
                elif isinstance(value, (int, float)):
                    # Keep numbers as-is (don't convert to string)
                    pass
                elif isinstance(value, str) and value == '':
                    # Convert empty string to Fortran empty string
                    data[key] = "''"
                elif isinstance(value, str):
                    # Wrap non-empty strings in single quotes
                    data[key] = f"'{value}'"
                elif isinstance(value, list):
                    # Convert list items, including booleans and strings
                    converted_items = []
                    for item in value:
                        if isinstance(item, bool):
                            converted_items.append('.true.' if item else '.false.')
                        elif isinstance(item, str):
                            converted_items.append(f"'{item}'")
                        else:
                            converted_items.append(str(item))
                    data[key] = ', '.join(converted_items)
                elif isinstance(value, dict):
                    self._convert_lists_to_strings(value)
