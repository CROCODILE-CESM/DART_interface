import f90nml
import yaml

# Read Fortran namelist
nml = f90nml.read('input.nml')

# Transform to add "values" wrapper
def wrap_in_values(data):
    """Recursively wrap leaf values in {'values': value} structure."""
    if isinstance(data, dict):
        return {key: wrap_in_values(val) for key, val in data.items()}
    else:
        # Clean up string values - convert ' ' to ''
        if isinstance(data, str) and data.strip() == '':
            data = ''
        # Leaf node - wrap it
        return {'values': data}

# Apply transformation
wrapped_nml = wrap_in_values(nml.todict())

# Write to YAML
with open('input_nml.yaml', 'w') as f:
    yaml.dump(wrapped_nml, f, default_flow_style=False)