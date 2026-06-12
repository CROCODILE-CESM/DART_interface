# Using Parameter Template Tools

Parameter template tools are to generate the json configuration files for DART from the Fortran source code. This workflow is intended for developers who need to update the default DART namelist values or add new parameters based on changes in the DART source code. The user does not need to run this workflow to use the DART-CESM interface, as the generated JSON files are included in the repository. However, if you are making changes to the DART source code or want to update the default parameters, you can follow these steps to regenerate the configuration files.

## Creating input_nml.json for DART

This workflow generates JSON configuration files for DART from Fortran source code.
The workflow uses MOM6, but can be used for other components by changing the model. Note for models that have model_to_dart programs, generate
Makefile.$MODEL.filter, Makefile.$MODEL.model_to_dart, etc. `process_makefile_f90.sh` will collect all the Makefile.$MODEL.* files to extract the Fortran source files for that model.

### 1. Generate the Makefile for filter


```bash
cd $DART_interface/DART/models/$MODEL/work
./quickbuild.sh filter
```

Put this makefile in the `DART_interface/param_templates/` directory as `Makefile.$MODEL.filter`. 

### 2. Extract default namelists from DART source

Create an `input.nml` from the DART source code contained in `Makefile.$MODEL.*`, e.g. for MOM6:

```bash
MODEL=MOM6; ./process_makefile_f90.sh $MODEL > input.nml.$MODEL 2>err
```

Edit `input.nml` and set sensible values for the model as needed.

### 3. Convert input.nml to JSON

```
python nml_to_json.py $MODEL
```

This generates JSON files in the `json/` directory for use in CESM case setup.
`input_nml_$MODEL.json`. This is the file that is read by `buildnml` to create the
`input.nml` used in the assimilation.