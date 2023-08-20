import csv
import numpy as np
import os

points = []
with open('./lakeATLAS.csv') as csvfile:
    reader = csv.reader(csvfile)
    count = 0
    for row in reader:
        if count == 0:
            count = 1
            continue
        point = (float(row[1]),float(row[2]))
        points.append(point)
        count = count + 1
directory = "./grealm/"

# iterate over files in
# that directory
lats = []
lons = []
avgs = []
stds = []
vals = []
dates = []
for filename in os.listdir(directory):
    f = os.path.join(directory, filename)
    # checking if it is a file
    if os.path.isfile(f):
        with open(f) as txt_file:
            lines = txt_file.readlines()
        levels = []
        for i in range(len(lines)):
            if i == 2:
                tokens = lines[i].split(" ")
                tokens = [i for i in tokens if i != '']
                lat = float(tokens[0])
                lon = float(tokens[1])
                if lon > 180:
                    lon = lon - 360
            if i >= 15:
                tokens = lines[i].split(" ")
                tokens = [i for i in tokens if i != '']
                year = tokens[0][0:4]
                month = tokens[0][4:6]
                if tokens[3] != "999.99" and month == "06" and year == "2022":
                    val = float(tokens[3])
                    dates.append(tokens[0])
                    lats.append(lat)
                    lons.append(lon)
                    vals.append(val)


with open("./grealm_june.csv", 'w', newline='') as csvfile:
    writer = csv.writer(csvfile, quotechar='|', quoting=csv.QUOTE_MINIMAL)
    for i in range(len(lats)):
        closest_point_lat = None
        closest_point_lon = None
        closest_dist = 1000000
        for point in points:
            dist = np.sqrt((point[0]-lats[i])**2+(point[1]-lons[i])**2)
            #print(dist)
            if dist < 1:
                if closest_point_lat is None:
                    closest_point_lat = point[0]
                    closest_point_lon = point[1]
                    closest_dist = dist
                else:
                    if dist < closest_dist:
                        closest_point_lat = point[0]
                        closest_point_lon = point[1]
                        closest_dist = dist
        if closest_point_lat is not None:
            writer.writerow([closest_point_lat, closest_point_lon, dates[i], vals[i]])