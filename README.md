# DMASpy
Decentralized Multi-Agent Satellite Simulator

SEAK Lab - Texas A&M University
(c) 2022

## Linux and Mac Install


### Manual Install

  

Install [miniconda](https://docs.conda.io/en/latest/miniconda.html).

  

```

conda create -p ./.venv

conda activate ./.venv

conda install pip

pip install -r requirements.txt

```

Install [InstruPy](github.com/EarthObservationSimulator/instrupy) in DMASpy folder.

Install [OrbitPy](github.com/EarthObservationSimulator/orbitpy) in DMASpy folder.

### Running 3D-CHESS Scenarios

Run dmas/environment.py as follows: `python dmas/environment.py nadir 5561 5562` where `nadir` is your desired scenario and `5561 5562` are the ports for message broadcasts.

Run dmas/test.py as follows: `python dmas/test.py nadir 5561 5562`  in a separate Ubuntu terminal, after activating the conda environment.

### Neo4J Instructions (not strictly necessary, but without this the knowledge graph queries will fail)

Download [Neo4j Desktop](https://neo4j.com/download/).

Start a local DBMS, with password "ceosdb".

Set up github.com/seakers/historical_db. Switch to "ben" branch. Run scraper following directions.

Set up github.com/CREATE-knowledge-planning. Run measurement_type_rule.py. (Email Ben for updated measurement_type_rule.py script).

