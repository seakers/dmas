import os, shutil

def setup_results_directory(scenario_name) -> str:
    """
    Creates an empty results directory within the `mccbba` directory
    """
    results_path = f'./{scenario_name}'

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

def create_tasks():
    pass

if __name__ == '__main__':
    """
    Wrapper for asynchronous MCCBBA simulation using DMAS
    """    
    # create 
    scenario_name = 'TEST'
    results_path = setup_results_directory(scenario_name)
    
    # define simulation config

    # create simulation manager and monitor
    monitor = 0

    # create simulation environment

    # create simulation agents

    # run simulation

    # compile results from monitor

    # print results

