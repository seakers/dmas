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
conda create -p desired/path/to/virtual/environment python=3.8

conda activate desired/path/to/virtual/environment
```
3. Install `gfortran`. and `make`. See [here](https://fortran-lang.org/learn/os_setup/install_gfortran).

4. Install [`instrupy`](https://github.com/EarthObservationSimulator/instrupy) and [`orbitpy`](https://github.com/Aslan15/orbitpy).

4. Install `dmas` library by running `make` command in terminal in repository directory:
```
make 
```
> ### NOTES: 
> - **Installation instructions above are only supported in Mac or Linux systems.** For windows installation, use a Windows Subsystem for Linux (WSL) and follow the instructions above.
> - Mac users are known to experience issues installing the `propcov` dependency contained within the `orbitpy` library during installation. See [`orbitpy`'s installation notes](https://github.com/EarthObservationSimulator/orbitpy/tree/master/propcov) for fixes.
> - For development in Windows, Visual Studio Code's remote development feature in WSL was used. See [instructions for remote development in VSCode](https://code.visualstudio.com/docs/remote/wsl-tutorial) for more details on WSL installation and remote development environment set-up.

---
## Contact 
**Principal Investigator:** 
- Daniel Selva Valero - <dselva@tamu.edu>

**Lead Developers:** 
- Alan Aguilar Jaramillo - <aguilaraj15@tamu.edu>
- Ben Gorr - <bgorr@tamu.edu>
