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

    lakes_lats = []
    lakes_lons = []
    rivers_lats = []
    rivers_lons = []

    with open('./hydrolakes.csv') as csvfile:
        reader = csv.reader(csvfile)
        count = 0
        for row in reader:
            if count == 0:
                count = 1
                continue
            lakes_lats.append(float(row[0]))
            lakes_lons.append(float(row[1]))
            if(count > 100):
                break
            count = count + 1
    with open('./grwl_river_output.csv') as csvfile:
        reader = csv.reader(csvfile)
        count = 0
        for row in reader:
            if count == 0:
                count = 1
                continue
            rivers_lats.append(float(row[1]))
            rivers_lons.append(float(row[0]))
            if(count > 100):
                break
            count = count + 1

    filename = f'/home/ben/repos/test/dmaspy/utils/images/xgrants.png'
    m = Basemap(projection='merc',llcrnrlat=-60,urcrnrlat=80,\
            llcrnrlon=-180,urcrnrlon=180,resolution='c')
    lakes_x, lakes_y = m(lakes_lons,lakes_lats)
    rivers_x, rivers_y = m(rivers_lons,rivers_lats)
    m.drawmapboundary(fill_color='#99ffff')
    m.fillcontinents(color='#cc9966',lake_color='#99ffff')
    m.scatter(lakes_x,lakes_y,2,marker='o',color='green', label='Lakes')
    m.scatter(rivers_x,rivers_y,2,marker='o',color='blue', label='Rivers')

    plt.legend(fontsize=5)
    plt.savefig(filename,dpi=200,bbox_inches="tight")
    plt.close()