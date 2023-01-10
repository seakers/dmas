import time, calendar, datetime
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import urllib, os
import csv
import numpy as np
import imageio
import sys

if __name__=="__main__":
    # assign directory
    directory = sys.argv[1]
    tss_outliers = []
    alt_outliers = []
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
    tss_lats = []
    tss_lons = []
    coobs_lats = []
    coobs_lons = []    
    for index in np.arange(0, len(all_outliers)-1):
        if(all_outliers[index,3]=="alt"):
            alt_lats.append(float(all_outliers[index, 0]))
            alt_lons.append(float(all_outliers[index, 1]))
        elif(all_outliers[index,3]=="tss"):
            tss_lats.append(float(all_outliers[index, 0]))
            tss_lons.append(float(all_outliers[index, 1]))
        elif(all_outliers[index,3]=="coobs"):
            coobs_lats.append(float(all_outliers[index, 0]))
            coobs_lons.append(float(all_outliers[index, 1]))
        filename = f'/home/ben/repos/test/dmaspy/dmas/utils/images/frame_{index}.png'
        filenames.append(filename)
        
        # last frame of each viz stays longer
        if (index == len(all_outliers)-1):
            for i in range(5):
                filenames.append(filename)        # save img
        m = Basemap(projection='merc',llcrnrlat=-80,urcrnrlat=80,\
                llcrnrlon=-180,urcrnrlon=180,lat_ts=20,resolution='c')
        alt_x, alt_y = m(alt_lons,alt_lats)
        tss_x, tss_y = m(tss_lons,tss_lats)
        coobs_x, coobs_y = m(coobs_lons,coobs_lats)
        m.drawmapboundary(fill_color='#99ffff')
        m.fillcontinents(color='#cc9966',lake_color='#99ffff')
        m.scatter(alt_x,alt_y,3,marker='o',color='b')
        m.scatter(tss_x,tss_y,3,marker='s',color='g')
        m.scatter(coobs_x,coobs_y,3,marker='^',color='r')
        plt.savefig(filename)
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