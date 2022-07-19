
import os, json, argparse
import time
from dmas.simulation import Simulation

def main(user_dir):
    """ This script executes a mission according to an input JSON configuration file. 
    It takes as argument the path to the user directory where it expects a :code:`MissionSpecs.json`
    user configuration file, and any auxillary files. The output files are written in the same directory 
    by default.
        
    Example usage: :code:`python test/driver.py scenarios/orbitpy_test/`

    """
    start_time = time.process_time()
    
    print('Initializing simulation.')
    simulation = Simulation.from_dir(user_dir)

    print('Start simulation.')
    simulation.run()

    print('Printing Results')
    simulation.print_results()

    print("Time taken to execute in seconds is ", time.process_time() - start_time)


class readable_dir(argparse.Action):
    """Defines a custom argparse Action to identify a readable directory."""
    def __call__(self, parser, namespace, values, option_string=None):
        prospective_dir = values
        if not os.path.isdir(prospective_dir):
            raise argparse.ArgumentTypeError(
                '{0} is not a valid path'.format(prospective_dir)
            )
        if os.access(prospective_dir, os.R_OK):
            setattr(namespace, self.dest, prospective_dir)
        else:
            raise argparse.ArgumentTypeError(
                '{0} is not a readable dir'.format(prospective_dir)
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Run Simulation'
    )
    parser.add_argument(
        'user_dir',
        action=readable_dir,
        help="Directory with user config JSON file, and also to write the results."
    )
    args = parser.parse_args()
    main(args.user_dir)
