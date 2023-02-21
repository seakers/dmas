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
    # iterate over files in
    # that directory
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "outliers" in f:
                if "imaging" in f:
                    print(f)
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            tss_outliers.append((row[0],row[1]))
                else:
                    print(f)
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        for row in csv_reader:
                            print(row)
                            alt_outliers.append((row[0],row[1]))
    print(alt_outliers)
    tss_unique = unique(tss_outliers)
    alt_unique = unique(alt_outliers)
    print(f'Number of tss outliers: {len(tss_outliers)}')
    print(f'Number of alt outliers: {len(alt_outliers)}')
    print(f'Number of unique tss outliers: {len(tss_unique)}')
    print(f'Number of unique alt outliers: {len(alt_unique)}')
    coobs_outliers = []
    for tss in tss_unique:
        for alt in alt_unique:
            if tss[0] == alt[0] and tss[1] == alt[1]:
                coobs_outliers.append(tss)
    print(f'Number of co-obs outliers: {len(coobs_outliers)}')


    