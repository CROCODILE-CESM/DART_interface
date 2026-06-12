# DART_interface

**CESM-DART interface for MOM6 in the CROCODILE project**

This repository provides the infrastructure to integrate the Data Assimilation Research Testbed (DART) with the Community Earth System Model (CESM).
It supports data assimilation for multiple CESM components: ocean (MOM6), atmosphere (CAM-SE), land (CLM), and sea-ice (CICE), individually or in combination.

Documentation is available [online](https://crocodile-cesm.github.io/DART_interface/) or in the docs directory.

For developers:

**Building the Documentation**

To build the documentation, navigate to the `docs` directory and run:

```bash
sphinx-build -b html . _build/html
```

**Running Tests**

There are some basic tests in the `tests` directory, run using pytest.

Note if you run pytest from the root directory, it will try and run python tests in DART.  To avoid this, cd into tests before running or specify the path to the tests:

```bash
pytest tests
```