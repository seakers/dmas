import csv
import os
import sys
from collections import Counter


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
    tss_outliers = []
    alt_outliers = []
    alt_all = []
    tss_all = []
    # iterate over files in
    # that directory
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "outliers" in f:
                if "Landsat" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            tss_outliers.append((row[0],row[1]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            alt_outliers.append((row[0],row[1]))
            else:
                if "Landsat" in f or "imaging" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            tss_all.append((row[0],row[1]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            alt_all.append((row[0],row[1]))
    tss_unique = unique(tss_outliers)
    alt_unique = unique(alt_outliers)
    print(f'Number of tss outliers: {len(tss_outliers)}')
    print(f'Number of alt outliers: {len(alt_outliers)}')
    print(f'Number of unique tss outliers: {len(tss_unique)}')
    print(f'Number of unique alt outliers: {len(alt_unique)}')
    tss_unique_all = unique(tss_all)
    alt_unique_all = unique(alt_all)
    print(f'Number of tss all: {len(tss_all)}')
    print(f'Number of alt all: {len(alt_all)}')
    print(f'Number of unique tss all: {len(tss_unique_all)}')
    print(f'Number of unique alt all: {len(alt_unique_all)}')
    coobs_outliers = []
    for tss in tss_unique:
        for alt in alt_unique:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_outliers.append(tss)
    print(f'Number of co-obs outliers: {len(coobs_outliers)}')
    coobs_outliers_all = []
    for tss in tss_unique_all:
        for alt in alt_unique_all:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_outliers_all.append(tss)
    print(f'Number of co-obs all: {len(coobs_outliers_all)}')


    