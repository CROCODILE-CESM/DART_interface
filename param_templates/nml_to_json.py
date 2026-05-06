#!/usr/bin/env python3
"""Convert a Fortran namelist to JSON for a given model (nml -> yaml -> json)."""

import argparse
import json
import logging
import os
import sys

import f90nml
import yaml

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Transform to add "values" wrapper
def wrap_in_values(data):
    """Recursively wrap leaf values in {'values': value} structure."""
    if isinstance(data, dict):
        return {key: wrap_in_values(val) for key, val in data.items()}
    # Clean up blank strings, convert ' ' to ''
    if isinstance(data, str) and data.strip() == '':
        data = ''
    # Leaf node - wrap it
    return {'values': data}


def nml_to_json(model, workdir):
    nml_file = os.path.join(workdir, f'input.nml.{model}')
    if not os.path.isfile(nml_file):
        logger.error(f"Namelist file '{nml_file}' not found")
        sys.exit(1)

    # Read Fortran namelist and wrap values
    nml = f90nml.read(nml_file)
    # Apply transformation to wrap leaf values in {"values": value} structure
    wrapped = wrap_in_values(nml.todict())

    # Write intermediate YAML
    yaml_file = os.path.join(workdir, f'input_nml_{model}.yaml')
    with open(yaml_file, 'w') as f:
        yaml.dump(wrapped, f, default_flow_style=False)
    logger.info(f'Written YAML to {yaml_file}')

    # Write JSON
    output_dir = os.path.join(workdir, 'json')
    os.makedirs(output_dir, exist_ok=True)
    json_file = os.path.join(output_dir, f'input_nml_{model}.json')
    with open(json_file, 'w') as f:
        json.dump(wrapped, f, separators=(',', ': '), sort_keys=True, indent=3)
    logger.info(f'Written JSON to {json_file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Convert a Fortran namelist to JSON for a given model.')
    parser.add_argument('model', help='Model name (e.g. cice, cam, clm)')
    parser.add_argument('-d', default='./',
                        help='Path to the directory containing the namelist files (default: ./)')
    args = parser.parse_args()

    nml_to_json(args.model, args.d)
