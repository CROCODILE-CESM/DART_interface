#!/bin/bash

# Extract unique full-path .f90 files from the Makefile and process them

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <model>"
    exit 1
fi

model=$1
makefilename='mk1'
cat Makefile.$model.* > $makefilename
grep -o '/Users[^[:space:]]*\.f90' $makefilename | sort -u | while read -r file; do
    
    # Check if file exists
    if [ -f "$file" ]; then
        python extract_namelist_defaults.py "$file"
    else
        echo "File not found: $file"
    fi
    
done
