import shapefile
import matplotlib.pyplot as plt
import csv
import sys
import os
import numpy as np

# with shapefile.Reader("GRWL_summaryStats.shp") as shp:
#     print(shp)
directory = "./HydroLAKES_points_v10_shp/"

# iterate over files in
# that directory
for filename in os.listdir(directory):
    f = os.path.join(directory, filename)
    # checking if it is a file
    if os.path.isfile(f):
        if ".shp" in f:
            sf = shapefile.Reader(f, encodingErrors="ignore")
            shapes = sf.shapes()
            records = sf.records()
            pops = []
            lats = []
            longs = []
            areas = []
            indices = []
            for i in range(len(shapes)):
                shp = sf.shape(i)
                rec = sf.record(i)
                tup = shp.points
                lat = tup[0][0]
                long = tup[0][1]
                longs.append(tup[0][0])
                lats.append(tup[0][1])
                indices.append(i)
                #pops.append(rec['pop_ct_csu'])
                areas.append(rec['Lake_area'])
            sf.close()
            ninety = np.percentile(areas,90)
            with open(f[:-4]+".csv", 'w', newline='') as csvfile:
                writer = csv.writer(csvfile, quotechar='|', quoting=csv.QUOTE_MINIMAL)
                for i in range(len(lats)):
                    if areas[i] > ninety:
                        writer.writerow([indices[i],lats[i], longs[i], areas[i]])