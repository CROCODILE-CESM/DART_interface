#!/bin/bash

# Extract unique full-path .f90 files from the Makefile and process them
grep -o '/Users[^[:space:]]*\.f90' Makefile.mom6.filter | sort -u | while read -r file; do
    
    # Check if file exists
    if [ -f "$file" ]; then
        python extract_namelist_defaults.py "$file"
    else
        echo "File not found: $file"
    fi
    
done