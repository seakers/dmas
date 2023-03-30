import netCDF4 as nc
import numpy as np
import csv

points = []
with open(self.scenario_dir+'resources/lakeATLAS.csv') as csvfile:
    reader = csv.reader(csvfile)
    count = 0
    for row in reader:
        if count == 0:
            count = 1
            continue
        point = (row[0],row[1])
        points.append(point)
        count = count + 1

fn = './c_gls_LSWT_201109210000_GLOBE_AATSR_v1.0.2.nc'
ds = nc.Dataset(fn)

lats = ds['lat'][:]
lons = ds['lon'][:]
mask = np.ma.getmaskarray(ds['quality_level'][:])
mask = np.squeeze(mask)
latlonpairs = []
for i in range(len(lats)):
    for j in range(len(lons)):
        if not mask[i,j]:
            latlonpairs.append((i,j))

rows = []
for pair in latlonpairs:
    lake_temp = ds['lake_surface_water_temperature'][0,pair[0],pair[1]]
    row = (lats[pair[0]],lons[pair[1]],lake_temp)
    rows.append(row)
lakes = []
for point in points:
    current_lake = point
    lake_temp_sum = 0
    lake_temp_count = 0
    for row in rows:
        if(np.sqrt((current_lake[0]-row[0])**2+(current_lake[1]-row[1])**2) < 1): # within 1 degree lat/lon distance
            lake_temp_sum += row[2]
            lake_temp_count += 1
            rows.remove(row)
    lake = (current_lake[0], current_lake[1], lake_temp_sum/lake_temp_count)
    lakes.append(lake)
with open('laketemps.csv','w') as out:
    csv_out=csv.writer(out)
    csv_out.writerow(['lat','lon','temp'])
    for lake in lakes:
        csv_out.writerow(lake)

