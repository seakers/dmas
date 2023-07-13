from enum import Enum
import json
import os
import shutil

from orbitpy.mission import Mission

class CoordinateTypes(Enum):
    """
    # Coordinate Type

    Describes the type of coordinate being described by a position vector
    """
    CARTESIAN = 'CARTESIAN'
    KEPLERIAN = 'KEPLERIAN'
    LATLON = 'LATLON'

class ModuleTypes(Enum):
    """
    # Types of Internal Modules for agents 
    """
    PLANNER = 'PLANNER'
    SCIENCE = 'SCIENCE'
    ENGINEERING = 'ENGINEERING'

def print_welcome(scenario_name) -> None:
    os.system('cls' if os.name == 'nt' else 'clear')
    out = "======================================================"
    out += '\n   _____ ____        ________  __________________\n  |__  // __ \      / ____/ / / / ____/ ___/ ___/\n   /_ </ / / /_____/ /   / /_/ / __/  \__ \\__ \ \n ___/ / /_/ /_____/ /___/ __  / /___ ___/ /__/ / \n/____/_____/      \____/_/ /_/_____//____/____/ (v1.0)'
    out += "\n======================================================"
    out += '\n\tTexas A&M University - SEAK Lab ©'
    out += "\n======================================================"
    out += f"\nSCENARIO: {scenario_name}"
    print(out)

def setup_results_directory(scenario_name) -> str:
    """
    Creates an empty results directory within the current working directory
    """
    results_path = f'{scenario_name}' if '/results/' in scenario_name else f'./scenarios/{scenario_name}/results'

    if not os.path.exists(results_path):
        # create results directory if it doesn't exist
        os.makedirs(results_path)
    else:
        # clear results in case it already exists
        results_path
        for filename in os.listdir(results_path):
            file_path = os.path.join(results_path, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (file_path, e))

    return results_path

def precompute_orbitdata(scenario_name) -> str:
    """
    Pre-calculates coverage and position data for a given scenario
    """
    
    scenario_dir = f'{scenario_name}' if './scenarios/' in scenario_name else f'./scenarios/{scenario_name}/'
    data_dir = f'{scenario_name}' if './scenarios/' in scenario_name and 'orbitdata/' in scenario_name else f'./scenarios/{scenario_name}/orbitdata/'
   
    changes_to_scenario = False
    with open(scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
        # check if data has been previously calculated
        if os.path.exists(data_dir + 'MissionSpecs.json'):
            with open(data_dir +'MissionSpecs.json', 'r') as mission_specs:
                scenario_dict : dict = json.load(scenario_specs)
                mission_dict = json.load(mission_specs)

                scenario_dict.pop('settings')
                mission_dict.pop('settings')

                if (
                       scenario_dict['epoch'] != mission_dict['epoch']
                    or scenario_dict['duration'] != mission_dict['duration']
                    or scenario_dict['groundStation'] != mission_dict['groundStation']
                    or scenario_dict['grid'] != mission_dict['grid']
                    or scenario_dict['spacecraft'] != mission_dict['spacecraft']
                    # or scenario_dict['scenario'] != mission_dict['scenario']
                    # or scenario_dict['settings'] != mission_dict['settings']
                    ):
                    changes_to_scenario = True
                
                # TODO only re-compute when relevant changes are made to json, not just any changes
                # elif scenario_dict['spacecraft'] != mission_dict['spacecraft']:
                #     spacecraft_dict = scenario_dict['spacecraft']
                #     mission_dict = mission_dict['spacecraft']
                    
                #     if (    spacecraft_dict['@id'] != mission_dict['@id']
                #         or spacecraft_dict['name'] != mission_dict['name']
                #         or spacecraft_dict['spacecraftBus'] != mission_dict['spacecraftBus']
                #         or spacecraft_dict['instrument'] != mission_dict['instrument']
                #         or spacecraft_dict['orbitState'] != mission_dict['orbitState']
                #         ):
                #         changes_to_scenario = True
        else:
            changes_to_scenario = True

    if not os.path.exists(data_dir):
        # if directory does not exists, create it
        os.mkdir(data_dir)
        changes_to_scenario = True

    if not changes_to_scenario:
        # if propagation data files already exist, load results
        print('Orbit data found!')
    else:
        # if propagation data files do not exist, propagate and then load results
        if changes_to_scenario:
            print('Existing orbit data does not match scenario.')
        else:
            print('Orbit data not found.')

        # print('Clearing \'orbitdata\' directory...')    
        # clear files if they exist
        if os.path.exists(data_dir):
            for f in os.listdir(data_dir):
                if os.path.isdir(os.path.join(data_dir, f)):
                    for h in os.listdir(data_dir + f):
                            os.remove(os.path.join(data_dir, f, h))
                    os.rmdir(data_dir + f)
                else:
                    os.remove(os.path.join(data_dir, f)) 
        # print('\'orbitddata\' cleared!')

        with open(scenario_dir +'MissionSpecs.json', 'r') as scenario_specs:
            # load json file as dictionary
            mission_dict : dict = json.load(scenario_specs)

            # set output directory to orbit data directory
            if mission_dict.get("settings", None) is not None:
                mission_dict["settings"]["outDir"] = scenario_dir + '/orbitdata/'
            else:
                mission_dict["settings"] = {}
                mission_dict["settings"]["outDir"] = scenario_dir + '/orbitdata/'

            # propagate data and save to orbit data directory
            print("Propagating orbits...")
            mission : Mission = Mission.from_json(mission_dict)  
            mission.execute()                
            print("Propagation done!")

            # save specifications of propagation in the orbit data directory
            with open(data_dir +'MissionSpecs.json', 'w') as mission_specs:
                mission_specs.write(json.dumps(mission_dict, indent=4))

    return data_dir