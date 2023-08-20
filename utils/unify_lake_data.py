import csv
import numpy as np

june_points = []
values = []
with open("./blooms.csv") as csvfile:
    reader = csv.reader(csvfile)
    next(reader)
    for row in reader:
        june_points.append([row[0], float(row[1]), float(row[2]), float(row[3])])
        if(abs(float(row[3])) > 0):
            values.append(float(row[3]))

points = []
with open("./grealm.csv") as csvfile:
    reader = csv.reader(csvfile)
    next(reader)
    for row in reader:
        points.append([float(row[0]), float(row[1]), float(row[2]), float(row[3])])

avg = np.average(values)
std = np.std(values)
rows = []
for jp in june_points:
    dateraw = jp[0]
    year = dateraw[0:4]
    month = dateraw[5:7]
    day = dateraw[8:10]
    date = year+month+day
    row = [jp[1],jp[2],avg,std,date,jp[3]]
    rows.append(row)
with open('blooms_unified.csv','w') as out:
    csv_out=csv.writer(out)
    csv_out.writerow(['lat','lon','avg','std', 'date', 'value'])
    for row in rows:
        csv_out.writerow(row)