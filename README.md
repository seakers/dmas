# Decentralized Multi-Agent Satellite Simulation (DMAS) 

**DMAS** is a simulation platform for decentralized and distributed satellite systems.
It is meant to test and showcase novel Earth-observing satellite mission concepts using higher levels of autonomy. This autonomy ranges from environment detection to autonomous operations planning.

---
## Documentation
For documentation please visit: https://dmas.readthedocs.io/

---
## Installation 

1. Install [miniconda](https://docs.conda.io/en/latest/miniconda.html).

2. Create and activate a virtual conda environment:

```
conda create -p ./.venv python=3.8

conda activate ./.venv
```
3. Install `gfortran`. and `make`. See [here](https://fortran-lang.org/learn/os_setup/install_gfortran).

4. Run make command in terminal in repository directory:
```
make install
```
> ### NOTEs: 
> - **Installation instructions above are only supported in Mac or Linux systems.** For windows installation, use a Windows Subsystem for Linux (WSL) and follow the instructions above.
> - Command line cloning of this repository is recommended as Github Desktop client users may experience problems due to submodule dependencies.
> - Mac users are known to experience issues installing the `propcov` dependency contained within the `orbitpy` submodule during the automated installation procedure. See [`orbitpy`'s installation notes](https://github.com/EarthObservationSimulator/orbitpy/tree/master/propcov) for fixes.
> - For development in Windows, Visual Studio Code's remote development feature in WSL was used. See [instructions for remote develpoment in VSCode](https://code.visualstudio.com/docs/remote/wsl-tutorial) for more details on WSL installation and remote development environment set-up.

---
## Contact 
**Principal Investigator:** 
- Daniel Selva Valero - <dselva@tamu.edu>

**Lead Developers:** 
- Alan Aguilar Jaramillo - <aguilaraj15@tamu.edu>
- Ben Gorr - <bgorr@tamu.edu>
