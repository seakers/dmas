# Decentralized Multi-Agent Satellite Simulation (DMAS) 

**DMAS** is a simulation platform for decentralized and distributed satellite systems.
It is meant to test and showcase novel Earth-observing satellite mission concepts using higher levels of autonomy. This autonomy ranges from environment detection to autonomous operations planning.

## Documentation
For documentation please visit: https://dmas.readthedocs.io/

## Installation 

> NOTE: Installation instructions are only supported in Mac or Linux systems. For windows installation use a Windows Subsystem for Linux (WSL) to follow the instructions below.

1. Install [miniconda](https://docs.conda.io/en/latest/miniconda.html).

2. Create and activate a virtual conda environment:

```
conda create -p ./.venv python=3.8

conda activate ./.venv
```

3. Install [InstruPy](github.com/EarthObservationSimulator/instrupy) and [OrbitPy](github.com/EarthObservationSimulator/orbitpy) libraries in the `.venv` environment.

4. Install in dependencies in `.venv` virtual environment.
```
pip install -e .
```

## Contact 
**Principal Investigator:** 
- Daniel Selva Valero <dselva@tamu.edu>

**Lead Developers:** 
- Alan Aguilar Jaramillo <aguilaraj15@tamu.edu>
- Ben Gorr <bgorr@tamu.edu>
