import csv
import numpy as np
import datetime as dt

points = []
with open('./grealm_unified.csv', 'r') as f:
    d_reader = csv.DictReader(f)
    for line in d_reader:
        points.append((line["lat"],line["lon"],line["avg"],line["std"],line["date"],line["value"],0))



req_points = []
for point in points:
    if float(point[5]) > (float(point[2])+float(point[3])) or float(point[5]) < (float(point[2])-float(point[3])):
        req_points.append(point)



with open("./gpRequests.csv", 'w', newline='') as csvfile:
    writer = csv.writer(csvfile, quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(['lat','lon','alt','s_max','measurements','t_start','t_end','t_corr'])
    for point in req_points:
        start_date = dt.datetime(2022,6,1,0,0,0)
        date = str(point[4])
        obs_date = dt.datetime(2022,int(date[4:6]),int(date[6:8]),0,0,0)
        obs_time = (obs_date-start_date).total_seconds()
        writer.writerow([point[0], point[1], 0.0, 100, '[OLI,POSEIDON-3BAltimeter,ThermalCamera]', obs_time, obs_time+86400, 86400])


