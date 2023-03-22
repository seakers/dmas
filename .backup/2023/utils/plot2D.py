import time, calendar, datetime
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import urllib, os
import csv
import numpy as np
import imageio
import sys

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
    tss_outliers = []
    alt_outliers = []
    tss_all = []
    alt_all = []
    # iterate over files in
    # that directory
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "outliers" in f:
                if "Landsat" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            tss_outliers.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            alt_outliers.append((row[0],row[1],row[2]))
            else:
                if "Landsat" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            tss_all.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            alt_all.append((row[0],row[1],row[2]))
    ground_track_dir = './utils/ground_tracks/'
    alt_ground_tracks = []
    tss_ground_tracks = []
    for filename in os.listdir(ground_track_dir):
        f = os.path.join(ground_track_dir, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "landsat" in f:
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
    coobs_outliers = []
    for tss in tss_outliers:
        coobs = False
        for alt in alt_outliers:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_outliers.append(tss)
                coobs = True
                alt_outliers.remove(alt)
        if(coobs):
            tss_outliers.remove(tss)
    


    # landsat_all_filepath = './scenarios/scenario1_nadir/Landsat 9_all.csv'
    # landsat_all_points = np.zeros(shape=(2000, 3))
    # with open(landsat_all_filepath) as csvfile:
    #     reader = csv.reader(csvfile)
    #     count = 0
    #     for row in reader:
    #         if count == 0:
    #             count = 1
    #             continue
    #         landsat_all_points[count-1,:] = [row[0], row[1], row[2]]
    #         count = count + 1
    # landsat_all_points = np.asfarray(landsat_all_points)
    # landsat_all_points = landsat_all_points[~np.all(landsat_all_points == 0, axis=1)]
    all_outliers = []
    for alt in alt_outliers:
        all_outliers.append((alt[0],alt[1],alt[2],"alt"))
    for tss in tss_outliers:
        all_outliers.append((tss[0],tss[1],tss[2],"tss"))
    for coobs in coobs_outliers:
        all_outliers.append((coobs[0],coobs[1],coobs[2],"coobs"))
    all_outliers = np.asarray(all_outliers)
    all_outliers = all_outliers[all_outliers[:, 2].argsort()]

    filenames = []
    alt_lats = []
    alt_lons = []
    all_alt_lats = []
    all_alt_lons = []
    all_tss_lats = []
    all_tss_lons = []
    tss_gts_lats = []
    tss_gts_lons = []
    alt_gts_lats = []
    alt_gts_lons = []
    tss_lats = []
    tss_lons = []
    coobs_lats = []
    coobs_lons = []    
    for t in range(0,86400,100):
        alt_lats, alt_lons = get_past_points(alt_outliers,t)
        tss_lats, tss_lons = get_past_points(tss_outliers,t)
        coobs_lats, coobs_lons = get_past_points(coobs_outliers,t)
        all_alt_lats, all_alt_lons = get_past_points(alt_all,t)
        all_tss_lats, all_tss_lons = get_past_points(tss_all,t)
        alt_gts_lats, alt_gts_lons = get_ground_track(alt_ground_tracks,t,3600.0)
        tss_gts_lats, tss_gts_lons = get_ground_track(tss_ground_tracks,t,3600.0)
        
        filename = f'/home/ben/repos/test/dmaspy/utils/images/frame_{t}.png'
        filenames.append(filename)
        # last frame of each viz stays longer
        if (t == 86400):
            for i in range(5):
                filenames.append(filename)        # save img
        m = Basemap(projection='merc',llcrnrlat=30,urcrnrlat=70,\
                llcrnrlon=-140,urcrnrlon=-70,resolution='c')
        alt_x, alt_y = m(alt_lons,alt_lats)
        tss_x, tss_y = m(tss_lons,tss_lats)
        all_alt_x, all_alt_y = m(all_alt_lons,all_alt_lats)
        all_tss_x, all_tss_y = m(all_tss_lons,all_tss_lats)
        tss_x, tss_y = m(tss_lons,tss_lats)
        coobs_x, coobs_y = m(coobs_lons,coobs_lats)
        alt_gts_x, alt_gts_y = m(alt_gts_lons,alt_gts_lats)
        tss_gts_x, tss_gts_y = m(tss_gts_lons,tss_gts_lats)
        m.drawmapboundary(fill_color='#99ffff')
        m.fillcontinents(color='#cc9966',lake_color='#99ffff')
        m.scatter(alt_gts_x,alt_gts_y,2,marker='o',color='#000000', label='Altimeter ground track')
        m.scatter(tss_gts_x,tss_gts_y,2,marker='o',color='#ffffff', label='Imager ground track')
        m.scatter(alt_x,alt_y,5,marker='^',color='b', label='Altimetry floods')
        m.scatter(tss_x,tss_y,5,marker='^',color='g', label='Imagery floods')
        m.scatter(all_alt_x,all_alt_y,1,marker='o',color='b', label='Normal altimetry obs')
        m.scatter(all_tss_x,all_tss_y,1,marker='o',color='g', label= 'Normal imagery obs')
        m.scatter(coobs_x,coobs_y,4,marker='^',color='r', label='Coobservation')
        plt.legend(fontsize=5)
        plt.title('3D-CHESS observations at time t='+str(t)+' s')
        plt.savefig(filename,dpi=200)
        plt.close()
    print('Charts saved\n')
    gif_name = 'plot2D'
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