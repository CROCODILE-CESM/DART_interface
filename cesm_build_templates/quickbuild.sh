#!/usr/bin/env bash

# DART software - Copyright UCAR. This open source software is provided
# by UCAR, "as is", without charge, subject to all terms of use at
# http://www.image.ucar.edu/DAReS/DART/DART_download

main() {

export DART=$(git rev-parse --show-toplevel)
source "$DART"/build_templates/buildfunctions.sh

# DART_MODEL must be set in the environment by the caller (buildlib).
# Supported values: MOM6, cam-se, clm, cice
MODEL=${DART_MODEL:?'DART_MODEL environment variable must be set by the caller'}
LOCATION=threed_sphere
# DART_EXTRA is optional; cam-se needs it to point at cam-common-code.
EXTRA=${DART_EXTRA:-}


programs=(
filter
perfect_model_obs
)

serial_programs=(
fill_inflation_restart
)

model_programs=(
)

model_serial_programs=(
)

# quickbuild arguments
arguments "$@"

# clean the directory
\rm -f -- *.o *.mod Makefile .cppdefs

# build any NetCDF files from .cdl files
cdl_to_netcdf

# build and run preprocess before making any other DART executables
buildpreprocess

# build 
buildit

# clean up
\rm -f -- *.o *.mod Makefile

}

main "$@"
