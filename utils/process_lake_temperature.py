import netCDF4 as nc
import numpy as np
import csv

fn = './c_gls_LSWT_201109210000_GLOBE_AATSR_v1.0.2.nc'
ds = nc.Dataset(fn)

lats = ds['lat'][:]
lons = ds['lon'][:]
print(len(ds['quality_level'][:].compressed()))
mask = np.ma.getmaskarray(ds['quality_level'][:])
mask = np.squeeze(mask)
print(np.shape(mask))
latlonpairs = []
for i in range(len(lats)):
    for j in range(len(lons)):
        if not mask[i,j]:
            print(f'Unmasked element at {lats[i]}, {lons[j]}')
            latlonpairs.append((i,j))

rows = []
for pair in latlonpairs:
    lake_temp = ds['lake_surface_water_temperature'][0,pair[0],pair[1]]
    print(f'Temp at {lats[pair[0]]}, {lons[pair[1]]}: {lake_temp}')
    row = (lats[pair[0]],lons[pair[1]],lake_temp)
    rows.append(row)
with open('laketemps.csv','w') as out:
    csv_out=csv.writer(out)
    csv_out.writerow(['lat','lon','temp'])
    for row in rows:
        csv_out.writerow(row)

