import netCDF4 as nc
import numpy as np
import csv
import os

def find_nearest_idx(array, value):
    array = np.asarray(array)
    idx = (np.abs(array - value)).argmin()
    return idx

points = []
with open('./grealm.csv') as csvfile:
    reader = csv.reader(csvfile)
    count = 0
    for row in reader:
        if count == 0:
            count = 1
            continue
        point = (float(row[0]),float(row[1]))
        points.append(point)
        count = count + 1

rows = []
directory = "./laketemps/"
for subdir in os.listdir(directory):
    print(subdir)
    subdirpath = os.path.join(directory, subdir)
    for file in os.listdir(subdirpath):
        # checking if it is a file
        fn = os.path.join(subdirpath,file)
        if os.path.isfile(fn) and ".nc" in fn and file[15:17]=="06":
            ds = nc.Dataset(fn)
            lats = ds['lat'][:]
            lons = ds['lon'][:]
            mask = np.ma.getmaskarray(ds['quality_level'][:])
            mask = np.squeeze(mask)
            latlonpairs = []
            for point in points:
                lat_idx = find_nearest_idx(lats,point[0])
                lon_idx = find_nearest_idx(lons,point[1])
                if not mask[lat_idx,lon_idx]:
                    latlonpairs.append((lat_idx,lon_idx))
            for pair in latlonpairs:
                lake_temp = ds['lake_surface_water_temperature'][0,pair[0],pair[1]]
                row = (lats[pair[0]],lons[pair[1]],lake_temp)
                rows.append(row)
lakes = []
for point in points:
    current_lake = point
    lake_temps = []
    for row in rows:
        if(np.sqrt((current_lake[0]-row[0])**2+(current_lake[1]-row[1])**2) < 1): # within 1 degree lat/lon distance
            lake_temps.append(row[2])
            rows.remove(row)
    if len(lake_temps) == 0:
        continue
    lake = (current_lake[0], current_lake[1], np.average(lake_temps), np.std(lake_temps))
    lakes.append(lake)
with open('laketemps.csv','w') as out:
    csv_out=csv.writer(out)
    csv_out.writerow(['lat','lon','avg','std'])
    for lake in lakes:
        csv_out.writerow(lake)

