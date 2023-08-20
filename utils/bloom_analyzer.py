from osgeo import osr, gdal
import re
import numpy as np
import math
import requests
from PIL import Image as im
import os
import csv
import urllib.request
import matplotlib.pyplot as plt


def get_tblr(array,image_size): # returns top bottom left right image dims
    y_pos = math.floor(up_down_frac*array.shape[1])
    x_pos = math.floor(left_right_frac*array.shape[2])
    top = 0
    bottom = array.shape[1]
    left = 0
    right = array.shape[2]
    if y_pos > image_size/2:
        top = math.floor(y_pos - image_size/2)
    if y_pos < array.shape[1]-image_size/2:
        bottom = math.floor(y_pos + image_size/2)
    if x_pos > image_size/2:
        left = math.floor(x_pos - image_size/2)
    if x_pos < array.shape[2]-image_size/2:
        right = math.floor(x_pos + image_size/2)
    return top, bottom, left, right

# assign directory
directory = "./potential_images/"

points = []
with open("./grealm.csv") as csvfile:
    reader = csv.reader(csvfile)
    for row in reader:
        points.append([float(row[0]), float(row[1])])
# iterate over files in
# that directory
file_count = 0
rows = []
good_locations = []
try:
    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            # get the existing coordinate system
            ds = gdal.Open(f)
            footprint_string = ds.GetMetadata()["FOOTPRINT"]
            date = ds.GetMetadata()["DATATAKE_1_DATATAKE_SENSING_START"]
            #print(footprint_string)
            subdatasets = ds.GetSubDatasets()
            mysubdataset_name = subdatasets[0][0] # corresponds to 10m band
            #print(mysubdataset_name)
            mydata = gdal.Open(mysubdataset_name, gdal.GA_ReadOnly)
            mydata = mydata.ReadAsArray()
            #print(mydata.shape)
            #print(subdatasets)
            twenty_meter_data_name = subdatasets[1][0]
            #print(twenty_meter_data_name)
            twenty_meter_data = gdal.Open(twenty_meter_data_name, gdal.GA_ReadOnly)
            twenty_meter_data = twenty_meter_data.ReadAsArray()
            #print(twenty_meter_data.shape)
            res = re.findall("[-+]?[.]?[\d]+(?:,\d\d\d)*[\.]?\d*(?:[eE][-+]?\d+)?", footprint_string)
            ul = (float(res[0]),float(res[1]))
            lr = (float(res[4]),float(res[5]))
            # print(ul)
            # print(lr)
            array = np.asarray(mydata)
            twenty_meter_array = np.asarray(twenty_meter_data)
            blue = array[0,:,:]
            green = array[1,:,:]
            red = array[2,:,:]
            nir = array[3,:,:]
            swir = twenty_meter_array[4,:,:]
            for point in points:
                lat = point[0]
                lon = point[1]
                if(ul[0] < lon < lr[0]):
                    left_right_frac = (ul[0]-lon)/(ul[0]-lr[0])
                else:
                    continue
                if(lr[1] < lat < ul[1]):
                    up_down_frac = (ul[1]-lat)/(ul[1]-lr[1])
                else:
                    continue
                # print(left_right_frac)
                # print(up_down_frac)


                image_size = 512
                top,bottom,left,right = get_tblr(array,image_size)
                ts,bs,ls,rs = get_tblr(twenty_meter_array,256)
                b3 = red[256,256]/10000
                b1 = blue[256,256]/10000
                b2 = green[256,256]/10000
                b4 = nir[256,256]/10000
                b5 = swir[128,128]/10000
                if np.min([b1,b2,b3]) == b1:
                    H = (b2-b1)/(b2+b3-2*b1)
                elif np.min([b1,b2,b3]) == b2:
                    H = (b3-b2)/(b1+b3-2*b2) + 2
                else:
                    H = (b1-b3)/(b1+b2-2*b3) + 1
                if H > 1.6:
                    fg = 0
                else:
                    fg = 1
                B = fg*(b4-1.03*b5)
                print(B)
                row = (date,lat,lon,B)
                rows.append(row)
                print(row)
except Exception as e:
    print(e)

with open("./blooms.csv", 'w', newline='') as csvfile:
    writer = csv.writer(csvfile, quotechar='|', quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        writer.writerow(row)