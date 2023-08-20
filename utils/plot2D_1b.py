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
            lats.append(float(points[i][0]))
            lons.append(float(points[i][1]))
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
            lats.append(float(points[i][0]))
            lons.append(float(points[i][1]))
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
    tss_hfs = []
    alt_hfs = []
    tss_floods = []
    alt_floods = []
    tss_all = []
    alt_all = []
    # iterate over files in
    # that directory
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "flood" in f:
                if "Landsat" in f or "Sentinel-2" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            if(float(row[2]) < 86400*4):
                                tss_floods.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            if(float(row[2]) < 86400*4):
                                alt_floods.append((row[0],row[1],row[2]))
            elif "hfs" in f:
                if "Landsat" in f or "Sentinel-2" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            if(float(row[2]) < 86400*4):
                                tss_hfs.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            if(float(row[2]) < 86400*4):
                                alt_hfs.append((row[0],row[1],row[2]))
            else:
                if "Landsat" in f or "Sentinel-2" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            if(float(row[2]) < 86400*4):
                                tss_all.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            if(float(row[2]) < 86400*4):
                                alt_all.append((row[0],row[1],row[2]))
    ground_track_dir = './utils/ground_tracks/arbitrary'
    alt_ground_tracks = []
    tss_ground_tracks = []
    for filename in os.listdir(ground_track_dir):
        f = os.path.join(ground_track_dir, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "Landsat" in f or "imaging" in f or "sentinel" in f:
                print("imaging!")
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i < 5):
                            i = i + 1
                            continue
                        if(float(row[3]) > 180.0):
                            lon = float(row[3]) - 360.0
                        else:
                            lon = float(row[3])
                        tss_ground_tracks.append((float(row[2]),lon,row[0]))
            else:
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i < 5):
                            i = i + 1
                            continue
                        if(float(row[3]) > 180):
                            lon = float(row[3]) - 360.0
                        else:
                            lon = float(row[3])
                        alt_ground_tracks.append((float(row[2]),lon,row[0]))
    if "arbitrary" in ground_track_dir:
        tss_ground_tracks = alt_ground_tracks
    print("Number of floods imaged: "+str(len(time_unique(tss_floods))))
    print("Number of unique floods imaged: "+str(len(unique(tss_floods))))
    print("Number of floods altimetered: "+str(len(time_unique(alt_floods))))
    print("Number of unique floods altimetered: "+str(len(unique(alt_floods))))
    print("Number of high flow events imaged: "+str(len(time_unique(tss_hfs))))
    print("Number of unique high flow events imaged: "+str(len(unique(tss_hfs))))
    print("Number of high flow events altimetered: "+str(len(time_unique(alt_hfs))))
    print("Number of unique high flow events altimetered: "+str(len(unique(alt_hfs))))
    print("Total number of observations: "+str(len(time_unique(tss_all))+len(time_unique(alt_all))))
    coobs_floods = []
    for tss in tss_floods:
        coobs = False
        for alt in alt_floods:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_floods.append(tss)
                coobs = True
                alt_floods.remove(alt)
        if(coobs):
            tss_floods.remove(tss)
    coobs_hfs = []
    for tss in tss_hfs:
        coobs = False
        for alt in alt_hfs:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_hfs.append(tss)
                coobs = True
                alt_hfs.remove(alt)
        if(coobs):
            tss_hfs.remove(tss)
    coobs_all = []
    for tss in tss_all:
        coobs = False
        for alt in alt_all:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_all.append(tss)
                coobs = True
                alt_all.remove(alt)
        if(coobs):
            tss_all.remove(tss)
    #print(coobs_hfs)

    print("Number of flood coobs: "+str(len(time_unique(coobs_floods))))
    print("Number of high flow coobs: "+str(len(time_unique(coobs_hfs))))
    print("Number of all coobs: "+str(len(time_unique(coobs_all))))
    
    print("Number of unique flood coobs: "+str(len(unique(coobs_floods))))
    print("Number of unique high flow coobs: "+str(len(unique(coobs_hfs))))
    #print("Number of unique all coobs: "+str(len(unique(coobs_all))))
    


    flood_points = []
    flood_lats = []
    with open('./scenarios/scenario1b/resources/one_year_floods_multiday.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            if len(flood_points) > 0:
                if line["lat"] not in flood_lats:
                    flood_lats.append(line["lat"])
                    flood_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+60*60))
            else:
                flood_lats.append(line["lat"])
                flood_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+60*60))
    hf_points = []
    hf_lats = []
    with open('./scenarios/scenario1b/resources/flow_events_75_multiday.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            if len(hf_points) > 0:
                hf_lats.append(line["lat"])
                hf_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+86400))
            else:
                hf_lats.append(line["lat"])
                hf_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+86400))
    flood_points = np.asfarray(flood_points)
    hf_points = np.asfarray(hf_points)

    all_floods = []
    for alt in alt_floods:
        all_floods.append((alt[0],alt[1],alt[2],"alt"))
    for tss in tss_floods:
        all_floods.append((tss[0],tss[1],tss[2],"tss"))
    for coobs in coobs_floods:
        all_floods.append((coobs[0],coobs[1],coobs[2],"coobs"))
    all_outliers = np.asarray(all_floods)
    all_outliers = all_outliers[all_outliers[:, 2].argsort()]

    filenames = []
    alt_lats = []
    alt_lons = []
    hfs_alt_lats = []
    hfs_alt_lons = []
    hfs_tss_lats = []
    hfs_tss_lons = []
    tss_gts_lats = []
    tss_gts_lons = []
    alt_gts_lats = []
    alt_gts_lons = []
    tss_lats = []
    tss_lons = []
    coobs_lats = []
    coobs_lons = []
    hfs_coobs_lats = []
    hfs_coobs_lons = []    
    for t in range(0,86400*4,2000):
        hf_lats,hf_lons = get_curr_points(hf_points,t)
        flood_lats, flood_lons = get_curr_points(flood_points,t)
        alt_lats, alt_lons = get_past_points(alt_floods,t)
        tss_lats, tss_lons = get_past_points(tss_floods,t)
        coobs_lats, coobs_lons = get_past_points(coobs_floods,t)
        hfs_alt_lats, hfs_alt_lons = get_past_points(alt_hfs,t)
        hfs_tss_lats, hfs_tss_lons = get_past_points(tss_hfs,t)
        hfs_coobs_lats, hfs_coobs_lons = get_past_points(coobs_hfs,t)
        alt_gts_lats, alt_gts_lons = get_ground_track(alt_ground_tracks,t,3600.0)
        tss_gts_lats, tss_gts_lons = get_ground_track(tss_ground_tracks,t,3600.0)
        
        filename = f'./utils/images/frame_{t}.png'
        filenames.append(filename)
        # last frame of each viz stays longer
        if (t == 86400*4):
            for i in range(5):
                filenames.append(filename)        # save img
        m = Basemap(projection='merc',llcrnrlat=20,urcrnrlat=60,\
                llcrnrlon=-140,urcrnrlon=-60,resolution='c')
        alt_x, alt_y = m(alt_lons,alt_lats)
        tss_x, tss_y = m(tss_lons,tss_lats)
        flood_x, flood_y = m(flood_lons,flood_lats)
        hf_x, hf_y = m(hf_lons,hf_lats)
        hfs_alt_x, hfs_alt_y = m(hfs_alt_lons,hfs_alt_lats)
        hfs_tss_x, hfs_tss_y = m(hfs_tss_lons,hfs_tss_lats)
        tss_x, tss_y = m(tss_lons,tss_lats)
        coobs_x, coobs_y = m(coobs_lons,coobs_lats)
        hfs_coobs_x, hfs_coobs_y = m(hfs_coobs_lons,hfs_coobs_lats)
        alt_gts_x, alt_gts_y = m(alt_gts_lons,alt_gts_lats)
        tss_gts_x, tss_gts_y = m(tss_gts_lons,tss_gts_lats)
        m.drawmapboundary(fill_color='#99ffff')
        m.fillcontinents(color='#cc9966',lake_color='#99ffff')
        m.scatter(alt_gts_x,alt_gts_y,2,marker='o',color='#000000', label='Altimeter ground track')
        m.scatter(tss_gts_x,tss_gts_y,1,marker='o',color='#ffffff', label='Imager ground track')
        m.scatter(hf_x,hf_y,1,marker='o',color='b', label='High flow events')
        m.scatter(flood_x,flood_y,1,marker='o',color='cyan', label='Flood events')
        m.scatter(hfs_alt_x,hfs_alt_y,2,marker='v',color='g', label='Altimetry high flows')
        m.scatter(hfs_tss_x,hfs_tss_y,2,marker='^',color='g', label= 'Imagery high flows')
        m.scatter(alt_x,alt_y,4,marker='v',color='r', label='Altimetry floods')
        m.scatter(tss_x,tss_y,4,marker='^',color='r', label='Imagery floods')
        m.scatter(hfs_coobs_x,hfs_coobs_y,5,marker='s',color='purple', label='High flow coobservations')
        m.scatter(coobs_x,coobs_y,5,marker='s',color='magenta', label='Flood coobservations')
        ax = plt.gca()
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

        # Put a legend to the right of the current axis
        ax.legend(loc='center left', fontsize=5, bbox_to_anchor=(1, 0.5))
        # plt.legend(fontsize=5,loc='upper right')
        plt.title('3D-CHESS observations at time t='+str(np.round(t/86400,2))+' days')
        plt.savefig(filename,dpi=300)
        if (t == 86400*4):
            plt.savefig("final_1b.png",dpi=200)
        plt.close()
    print('Charts saved\n')
    gif_name = 'plot2D_1b_arbitrary'
    # Build GIF
    print('Creating gif\n')
    with imageio.get_writer(f'{gif_name}.gif', mode='I') as writer:
        for filename in filenames:
            image = imageio.imread(filename)
            writer.append_data(image)
    print('Gif saved\n')
    print('Removing Images\n')
    # Remove files
    for filename in set(filenames):
        os.remove(filename)
    print('DONE')