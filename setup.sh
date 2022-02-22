#!/bin/sh

# Author: Alan Aguilar
# Copyright (c) SEAK Lab - Texas A&M University
# Install shell script for Linux and MacOS

conda create -p ./.venv
conda activate ./.venv
conda install pip
./.venv/bin/pip install -r requirements.txt
conda install -c conda-forge orekit
conda config --set env_prompt '.venv'