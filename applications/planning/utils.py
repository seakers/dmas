import os
import shutil


def setup_results_directory(scenario_name) -> str:
    """
    Creates an empty results directory within the current working directory
    """
    results_path = f'{scenario_name}' if './results/' in scenario_name else f'./results/{scenario_name}'

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