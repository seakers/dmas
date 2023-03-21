import json
from copy import deepcopy


def add_sats(base_satellite, satellite_name):
    satellites = []
    r = 2; # number of planes
    s = 2; # number of satellites per plane
    re = 6378
    altitude = 500
    ecc = 0.01
    inc = 67
    argper = 0.0
    for m in range(r):
        for n in range(s):
            new_satellite = {}
            new_satellite = base_satellite.copy()
            new_satellite["@id"] = satellite_name+"_"+str(m)+"_"+str(n)
            new_satellite["name"] = satellite_name+"_"+str(m)+"_"+str(n)
            pu = 360 / (r*s)
            delAnom = pu * r
            delRAAN = pu * s
            RAAN = delRAAN * m
            f = 1
            phasing = pu * f
            
            anom = (n * delAnom + phasing * m)
            new_satellite["orbitState"]["state"]["sma"] = altitude+re
            new_satellite["orbitState"]["state"]["ecc"] = ecc
            new_satellite["orbitState"]["state"]["inc"] = inc
            new_satellite["orbitState"]["state"]["raan"] = RAAN
            new_satellite["orbitState"]["state"]["aop"] = argper
            new_satellite["orbitState"]["state"]["ta"] = anom
            satellites.append(deepcopy(new_satellite))
    return satellites

all_satellites = []



with open('./utils/base_vnir_sat.json', 'r') as openfile:
    base_vnir_satellite = json.load(openfile)
with open('./utils/base_vnirtir_sat.json', 'r') as openfile:
    base_vnirtir_satellite = json.load(openfile)
with open('./utils/base_tir_sat.json', 'r') as openfile:
    base_tir_satellite = json.load(openfile)
with open('./utils/base_alt_sat.json', 'r') as openfile:
    base_alt_satellite = json.load(openfile)

vnir_satellites = add_sats(base_vnir_satellite,"vnir_sat")
vnirtir_satellites = add_sats(base_vnirtir_satellite,"vnirtir_sat")
tir_satellites = add_sats(base_tir_satellite,"tir_sat")
alt_satellites = add_sats(base_alt_satellite,"alt_sat")
all_satellites = vnir_satellites + vnirtir_satellites + tir_satellites + alt_satellites

json_object = json.dumps(all_satellites, indent=4)
 
# Writing to sample.json
with open("./utils/constellation.json", "w") as outfile:
    outfile.write(json_object)
        

