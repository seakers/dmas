#!/bin/bash

for ((a=0; a<1; a++)); do
    gnome-terminal -- python ./dmas/agent.py
done

gnome-terminal -- python ./dmas/environment.py