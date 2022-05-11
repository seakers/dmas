# DMASpy
Decentralized Multi-Agent Satellite Simulator

SEAK Lab - Texas A&M University
(c) 2022

## Linux and Mac Install

### Automatic Install
UNDER DEVELOPMENT
```
 python setup.py install
```

### Manual Install
`{ENVORINMENT_NAME}`: user-defined environment name (`.env` directory name recommended)

Create and activate conda virtual environment
```
conda create -p ./{ENVORINMENT_NAME} python=3.10
conda activate ./{ENVORINMENT_NAME}
conda install pip
```

Install dependencies
```
./{ENVORINMENT_NAME}/bin/pip install -r requirements.txt
```
Set your IDE's interpreter as `./.env/bin/python3.10`

OPTIONAL: rename terminal prompt
```
conda config --set env_prompt '({ENVORINMENT_NAME})'
```

# DEV ONLY
If new libraries are added to the project, add them to the `requirements.txt` file
```
pip freeze > requirements.txt
```
