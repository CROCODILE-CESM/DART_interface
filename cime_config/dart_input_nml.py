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
        # write the data in namelist format
        self.write_nml(output_path)
