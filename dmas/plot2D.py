import time, calendar, datetime
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import urllib, os
import csv
import numpy as np
import imageio

landsat_all_filepath = './scenarios/scenario1_nadir/Landsat 9_all.csv'
landsat_all_points = np.zeros(shape=(2000, 3))
with open(landsat_all_filepath) as csvfile:
    reader = csv.reader(csvfile)
    count = 0
    for row in reader:
        if count == 0:
            count = 1
            continue
        landsat_all_points[count-1,:] = [row[0], row[1], row[2]]
        count = count + 1
landsat_all_points = np.asfarray(landsat_all_points)
landsat_all_points = landsat_all_points[~np.all(landsat_all_points == 0, axis=1)]
lats = landsat_all_points[:,0]
lons = landsat_all_points[:,1]
times = landsat_all_points[:,2]

filenames = []
new_lons = []
new_lats = []
for index in np.arange(0, len(landsat_all_points)-1):
    new_lats.append(lats[index])
    new_lons.append(lons[index])
    filename = f'/home/ben/repos/test/dmaspy/dmas/images/frame_{index}.png'
    filenames.append(filename)
    
    # last frame of each viz stays longer
    if (index == len(landsat_all_points)-1):
        for i in range(5):
            filenames.append(filename)        # save img
    m = Basemap(projection='merc',llcrnrlat=-80,urcrnrlat=80,\
            llcrnrlon=-180,urcrnrlon=180,lat_ts=20,resolution='c')
    x, y = m(new_lons,new_lats)
    m.drawmapboundary(fill_color='#99ffff')
    m.fillcontinents(color='#cc9966',lake_color='#99ffff')
    m.scatter(x,y,3,marker='o',color='b')
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