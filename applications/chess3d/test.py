import sys

from applications.planning.utils import setup_results_directory

"""
# TEST WRAPPER

Preliminary wrapper used for debugging purposes
"""
if __name__ == "__main__":
    # read system arguments
    scenario_name = sys.argv[1]
    plot_results = True
    save_plot = False

    # create results directory
    results_path = setup_results_directory(scenario_name)