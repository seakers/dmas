import json
import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

from nodes.science.reqs import *


def plot_2d(scenario_path : str, results_path : str, show_plot : bool = False) -> None:

    # load scenario json file
    scenario_file = open(scenario_path + '/MissionSpecs.json', 'r')
    scenario_dict : dict = json.load(scenario_file)
    scenario_file.close()

    # read agent names
    spacecraft_dict = scenario_dict.get('spacecraft', None)
    uav_dict = scenario_dict.get('uav', None)

    agent_names = []
    if spacecraft_dict:
        for spacecraft in spacecraft_dict:
            agent_names.append(spacecraft['name'])
    if uav_dict:
        for uav in uav_dict:
            agent_names.append(uav['name'])


    # load agent data
    agent_data = {}
    t = None
    for agent_name in agent_names:      
        df = pd.read_csv(f"{results_path}/{agent_name}/states.csv")
        agent_data[agent_name] = df
        if t is None or len(df['t']) < len(t):
            t = df['t']

    # load initial measurement request
    measurement_reqs = []
    df = pd.read_csv(results_path + '/gpRequests.csv')
        
    for _, row in df.iterrows():
        s_max = row['s_max']
        
        measurements_str : str = row['measurements']
        measurements_str = measurements_str.replace('[','')
        measurements_str = measurements_str.replace(']','')
        measurements_str = measurements_str.replace(' ','')
        measurements = measurements_str.split(',')

        t_start = row['t_start']
        t_end = row['t_end']
        t_corr = row['t_corr']

        lat, lon, alt = row.get('lat', None), row.get('lon', None), row.get('alt', None)
        if lat is None and lon is None and alt is None: 
            x_pos, y_pos, z_pos = row.get('x_pos', None), row.get('y_pos', None), row.get('z_pos', None)
            if x_pos is not None and y_pos is not None and z_pos is not None:
                pos = [x_pos, y_pos, z_pos]
                lat, lon, alt = 0.0, 0.0, 0.0
            else:
                raise ValueError('GP Measurement Requests in `gpRequest.csv` must specify a ground position as lat-lon-alt or cartesian coordinates.')
        else:
            pos = None

        lan_lon_pos = [lat, lon, alt]
        req = GroundPointMeasurementRequest(lan_lon_pos, s_max, measurements, t_start, t_end, t_corr, pos=pos)
        measurement_reqs.append(req)

    # initialize plot
    fig, ax = plt.subplots()

    # find bounds
    bounds = [0,0]
    for agent_name in agent_names:
        df = agent_data[agent_name]
        x_min, x_max = min(df['x_pos']), max(df['x_pos'])
        y_min, y_max = min(df['y_pos']), max(df['y_pos'])
        z_min, z_max = min(df['z_pos']), max(df['z_pos'])

        bounds[0] = x_min if x_min < bounds[0] else bounds[0]
        bounds[1] = x_max if x_max > bounds[1] else bounds[1]

        bounds[0] = y_min if y_min < bounds[0] else bounds[0]
        bounds[1] = y_max if y_max > bounds[1] else bounds[1]

        bounds[0] = z_min if z_min < bounds[0] else bounds[0]
        bounds[1] = z_max if z_max > bounds[1] else bounds[1]

    bounds[0] *= 1.10
    bounds[1] *= 1.10

    # plot original agent position
    agent_scats = {}
    agent_lines = {}
    for agent in agent_data:
        x_str, y_str = agent_data[agent]['x_pos'][0], agent_data[agent]['y_pos'][0]

        agent_scats[agent] = ax.scatter([float(x_str)], [float(y_str)], label=f'{agent}')
        agent_lines[agent] = ax.plot([float(x_str)], [float(y_str)])


    # load measurement location
    measurement_data = pd.read_csv(f"{results_path}/ENVIRONMENT/measurements.csv")
    
    # plot task location
    # print('TASK POSITION')
    # print('id, pos, measurements')
    x_tasks = []
    y_tasks = []
    for req in measurement_reqs:
        req : GroundPointMeasurementRequest
        x_i, y_i, _ = req.pos
        x_tasks.append(x_i)
        y_tasks.append(y_i)
        task_id = req.id.split('-')[0]
        # print(f'{task_id},{req.pos},{req.measurements}')

    task_scat = ax.scatter(x_tasks, y_tasks, color='r', marker='*')

    plt.grid(True)
    ax.set(xlim=bounds, ylim=bounds, xlabel='x', ylabel='y')
    ax.legend()

    def update(frame):
        # update agent states
        for agent in agent_data: 
            x = [float(x_str) for x_str in agent_data[agent]['x_pos'][:frame]]
            y = [float(y_str) for y_str in agent_data[agent]['y_pos'][:frame]]

            agent_lines[agent][0].set_xdata(x)
            agent_lines[agent][0].set_ydata(y)
            # agent_lines[agent].set_offsets(data)

            if len(x) > 0:
                x, y = [x[-1]], [y[-1]]
            data = np.stack([x,y]).T
            agent_scats[agent].set_offsets(data)

        # update task status
        x_reqs = []
        y_reqs = []
        if frame > 0:
            t_curr = t[frame]
            t_prev = t[frame-1]
            updated_measurements : pd.DataFrame = measurement_data[measurement_data['t_img'] <= t_curr]
            updated_measurements : pd.DataFrame = updated_measurements[updated_measurements['t_img'] >= t_prev]
            for _, row in updated_measurements.iterrows():
                pos_str : str = row['pos']
                pos_str = pos_str.replace('[','')
                pos_str = pos_str.replace(']','')
                pos_str : list = pos_str.split(',')
                x_str, y_str = float(pos_str[0]), float(pos_str[1])
                x_reqs.append(float(x_str))
                y_reqs.append(float(y_str))

            task_scat = ax.scatter(x_reqs, y_reqs, color='g', marker='*')
        else:
            for req in measurement_reqs:
                req : GroundPointMeasurementRequest
                x_i, y_i, _ = req.pos
                x_reqs.append(x_i)
                y_reqs.append(y_i)
            task_scat = ax.scatter(x_reqs, y_reqs, color='r', marker='*')


        ax.set_title(f't={t[frame]}[s]')
        out = [agent_scats[agent] for agent in agent_scats]
        out.extend([agent_lines[agent][0] for agent in agent_lines])
        out.append(task_scat)

        ax.set_title(f't={t[frame]}[s]')
        return (p for p in out)
    
    anim = animation.FuncAnimation(fig=fig, func=update, frames=len(t), interval=50)
    
    if show_plot:
        plt.show()
    
    return anim

if __name__ == '__main__':
    scenario_name = sys.argv[1]
    scenario_path = f"{scenario_name}" if "./scenarios/" in scenario_name else f'./scenarios/{scenario_name}/'
    results_path = f'{scenario_path}/results/'

    plot_2d(scenario_path, results_path)
    x = 1