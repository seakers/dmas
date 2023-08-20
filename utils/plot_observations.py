import time, calendar, datetime
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import urllib, os
import csv
import numpy as np
import imageio
import sys

def unique(lakes):
    lakes = np.asarray(lakes)[:,0:1]
    return np.unique(lakes,axis=0)

def time_unique(lakes):
    lakes = np.asarray(lakes)
    return np.unique(lakes,axis=0)

def get_past_points(points, curr_time):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        if(float(points[i][2]) < curr_time):
            lats.append(float(points[i][0])*180/np.pi)
            lons.append(float(points[i][1])*180/np.pi)
        else:
            break
        i = i+1
    return lats, lons

def get_curr_points(points, curr_time):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        if(float(points[i][2]) < curr_time < float(points[i][3])):
            lats.append(float(points[i][0])*180/np.pi)
            lons.append(float(points[i][1])*180/np.pi)
        i = i+1
    return lats, lons

def get_ground_track(points, curr_time, window):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        if((curr_time - window) < float(points[i][2]) < curr_time):
            lats.append(float(points[i][0]))
            lons.append(float(points[i][1]))
        i = i+1
    return lats, lons

if __name__=="__main__":
    # assign directory
    directory = sys.argv[1]
    satellites = ["smallsat00","smallsat01","smallsat02","smallsat03","smallsat04"]
    observations_by_sat = {}
    # iterate over files in
    # that directory
    all_observations = []
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            with open(f) as csv_file:
                csv_reader = csv.reader(csv_file, delimiter=',')
                i = 0
                for row in csv_reader:
                    if(i == 0):
                        i = 1
                        continue
                    all_observations.append((row[0],row[1],row[2],row[3]))
    for sat in satellites:
        observations = []
        for obs in all_observations:
            if(obs[0]==sat):
                observations.append(obs[1:])
        observations_by_sat[sat] = observations
    # ground_track_dir = './utils/ground_tracks/chrissi'
    # ground_tracks = []
    # for filename in os.listdir(ground_track_dir):
    #     f = os.path.join(ground_track_dir, filename)
    #     # checking if it is a file
    #     if os.path.isfile(f):
    #         with open(f) as csv_file:
    #             csv_reader = csv.reader(csv_file, delimiter=',')
    #             i = 0
    #             for row in csv_reader:
    #                 if(i < 5):
    #                     i = i + 1
    #                     continue
    #                 if(float(row[3]) > 180.0):
    #                     lon = float(row[3]) - 360.0
    #                 else:
    #                     lon = float(row[3])
    #                 ground_tracks.append((float(row[2]),lon,row[0]))

    filenames = []   
    #gts_lats, gts_lons = get_ground_track(ground_tracks,t,3600.0)
    m = Basemap(projection='merc',llcrnrlat=-60,urcrnrlat=80,\
            llcrnrlon=-180,urcrnrlon=180,resolution='c')
    
    #gts_x, gts_y = m(gts_lons,gts_lats)
    m.drawmapboundary(fill_color='#99ffff')
    m.fillcontinents(color='#cc9966',lake_color='#99ffff')
    #m.scatter(gts_x,gts_y,2,marker='o',color='#000000', label='Ground tracks')
    i = 0
    colors = ["blue","yellow","green","red","orange"]
    for sat in satellites:
        obs_lats, obs_lons = get_past_points(observations_by_sat[sat],86400)
        obs_x, obs_y = m(obs_lons,obs_lats)
        m.scatter(obs_x,obs_y,5-i,marker='o',color=colors[i], label = sat)
        i = i+1
    ax = plt.gca()
    box = ax.get_position()
    ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

    # Put a legend to the right of the current axis
    ax.legend(loc='center left', fontsize=5, bbox_to_anchor=(1, 0.5))
    # plt.legend(fontsize=5,loc='upper right')
    plt.title('Observations')
    plt.savefig("final_obs_greedy.png",dpi=300)
    plt.close()
    print('Charts saved\n')