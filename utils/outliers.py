import csv
import os
import sys
from collections import Counter
import numpy as np


def unique(list1):

	# initialize a null list
	unique_list = []

	# traverse for all elements
	for x in list1:
		# check if exists in unique_list or not
		if x not in unique_list:
			unique_list.append(x)
	return unique_list



if __name__=="__main__":
    # assign directory
    directory = sys.argv[1]
    tss_floods = []
    tss_hfs = []
    alt_floods = []
    alt_hfs = []
    # iterate over files in
    # that directory
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "hfs" in f:
                if "Landsat" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            tss_hfs.append((row[0],row[1]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            alt_hfs.append((row[0],row[1]))
            else:
                if "Landsat" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            tss_floods.append((row[0],row[1]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            alt_floods.append((row[0],row[1]))
    tss_unique = unique(tss_floods)
    alt_unique = unique(alt_floods)
    print(f'Number of tss floods: {len(tss_floods)}')
    print(f'Number of alt floods: {len(alt_floods)}')
    print(f'Number of unique tss floods: {len(tss_unique)}')
    print(f'Number of unique alt floods: {len(alt_unique)}')
    tss_unique_hfs = unique(tss_hfs)
    alt_unique_hfs = unique(alt_hfs)
    print(f'Number of tss hfs: {len(tss_hfs)}')
    print(f'Number of alt hfs: {len(alt_hfs)}')
    print(f'Number of unique tss hfs: {len(tss_unique_hfs)}')
    print(f'Number of unique alt hfs: {len(alt_unique_hfs)}')
    coobs_floods = []
    for tss in tss_unique:
        for alt in alt_unique:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_floods.append(tss)
    print(f'Number of co-obs floods: {len(coobs_floods)}')
    coobs_hfs = []
    for tss in tss_unique_hfs:
        for alt in alt_unique_hfs:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_hfs.append(tss)
    print(f'Number of co-obs hfs: {len(coobs_hfs)}')

    flood_points = []
    flood_lats = []
    with open('./scenarios/scenario1b/resources/one_year_floods_multiday.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            if len(flood_points) > 0:
                flood_lats.append(line["lat"])
                flood_points.append((line["lat"],line["lon"]))
            else:
                flood_lats.append(line["lat"])
                flood_points.append((line["lat"],line["lon"]))
    hf_points = []
    hf_lats = []
    with open('./scenarios/scenario1b/resources/flow_events_75_multiday.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            if len(hf_points) > 0:
                hf_lats.append(line["lat"])
                hf_points.append((line["lat"],line["lon"]))
            else:
                hf_lats.append(line["lat"])
                hf_points.append((line["lat"],line["lon"]))
    flood_points = np.asfarray(flood_points)
    hf_points = np.asfarray(hf_points)
    print(f'Number of flood locations: {len(flood_points)}')
    print(f'Number of high flow locations: {len(hf_points)}')
    print(f'Number of unique flood locations: {len(unique(flood_points[:,0]))}')
    print(f'Number of unique high flow locations: {len(unique(hf_points[:,0]))}')

    