import time, calendar, datetime
from mpl_toolkits.basemap import Basemap
import matplotlib.pyplot as plt
import urllib, os
import csv
import numpy as np
import imageio
import sys

def unique(lakes):
    lakes = np.asarray(lakes)[:,0:1]
    return np.unique(lakes,axis=0)

def time_unique(lakes):
    lakes = np.asarray(lakes)
    return np.unique(lakes,axis=0)

def get_past_points(points, curr_time):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        if(float(points[i][2]) < curr_time):
            lats.append(float(points[i][0]))
            lons.append(float(points[i][1]))
        else:
            break
        i = i+1
    return lats, lons

def get_curr_points(points, curr_time):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        if(float(points[i][2]) < curr_time < float(points[i][3])):
            lats.append(float(points[i][0]))
            lons.append(float(points[i][1]))
        i = i+1
    return lats, lons

def get_points(points, curr_time):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        lats.append(float(points[i][0]))
        lons.append(float(points[i][1]))
        i = i+1
    return lats, lons

def get_ground_track(points, curr_time, window):
    lats = []
    lons = []
    i = 0
    while i < len(points):
        if((curr_time - window) < float(points[i][2]) < curr_time):
            lats.append(float(points[i][0]))
            lons.append(float(points[i][1]))
        i = i+1
    return lats, lons

if __name__=="__main__":
    # assign directory
    directory = sys.argv[1]
    lake_droughts = []
    lake_floods = []
    hot_lakes = []
    cold_lakes = []
    blooms = []
    all_temps = []
    all_levels = []
    all_images = []
    # iterate over files in
    # that directory

    with open(directory+'../../resources/blooms.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            blooms.append((line["lat"],line["lon"]))

    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "lakes" in f:
                if "cold" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            cold_lakes.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            hot_lakes.append((row[0],row[1],row[2]))
            elif "lake" in f:
                if "drought" in f:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            lake_droughts.append((row[0],row[1],row[2]))
                else:
                    with open(f) as csv_file:
                        csv_reader = csv.reader(csv_file, delimiter=',')
                        i = 0
                        for row in csv_reader:
                            if(i == 0):
                                i = 1
                                continue
                            lake_floods.append((row[0],row[1],row[2]))
            # elif "bloom" in f:
            #     with open(f) as csv_file:
            #         csv_reader = csv.reader(csv_file, delimiter=',')
            #         i = 0
            #         for row in csv_reader:
            #             if(i == 0):
            #                 i = 1
            #                 continue
            #             #print(row)
            #             blooms.append((row[0],row[1],row[2]))
            elif "all" in f and ("vnirtir" in f or "Landsat" in f or "Sentinel-2" in f):
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i == 0):
                            i = 1
                            continue
                        all_temps.append((row[0],row[1],row[2]))
                        all_images.append((row[0],row[1],row[2]))
            elif "all" in f and ("vnir_sat" in f or "Landsat" in f or "Sentinel-2" in f):
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i == 0):
                            i = 1
                            continue
                        all_images.append((row[0],row[1],row[2]))
            elif "all" in f and ("tir_sat" in f or "Landsat" in f or "Sentinel-2" in f):
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i == 0):
                            i = 1
                            continue
                        all_temps.append((row[0],row[1],row[2]))
            elif "all" in f and ("alt_sat" in f or "Cryo" in f or "Jason" in f or "SWOT" in f or "Sentinel-6" in f):
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i == 0):
                            i = 1
                            continue
                        all_levels.append((row[0],row[1],row[2]))
    ground_track_dir = './utils/ground_tracks/scenario2'
    vnirtir_ground_tracks = []
    tir_ground_tracks = []
    alt_ground_tracks = []
    vnir_ground_tracks = []
    for filename in os.listdir(ground_track_dir):
        f = os.path.join(ground_track_dir, filename)
        # checking if it is a file
        if os.path.isfile(f):
            if "vnirtir" in f:
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i < 5):
                            i = i + 1
                            continue
                        if(float(row[3]) > 180.0):
                            lon = float(row[3]) - 360.0
                        else:
                            lon = float(row[3])
                        vnirtir_ground_tracks.append((float(row[2]),lon,float(row[0])*10))
            elif "alt" in f:
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i < 5):
                            i = i + 1
                            continue
                        if(float(row[3]) > 180):
                            lon = float(row[3]) - 360.0
                        else:
                            lon = float(row[3])
                        alt_ground_tracks.append((float(row[2]),lon,float(row[0])*10))
            elif "tir" in f:
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i < 5):
                            i = i + 1
                            continue
                        if(float(row[3]) > 180):
                            lon = float(row[3]) - 360.0
                        else:
                            lon = float(row[3])
                        tir_ground_tracks.append((float(row[2]),lon,float(row[0])*10))
            else:
                with open(f) as csv_file:
                    csv_reader = csv.reader(csv_file, delimiter=',')
                    i = 0
                    for row in csv_reader:
                        if(i < 5):
                            i = i + 1
                            continue
                        if(float(row[3]) > 180):
                            lon = float(row[3]) - 360.0
                        else:
                            lon = float(row[3])
                        vnir_ground_tracks.append((float(row[2]),lon,float(row[0])*10))

    # coobs_lakes = []
    # for image in all_images:
    #     coobs = False
    #     for alt in lake_floods:
    #         if image[0] == alt[0] and image[1] == alt[1]:
    #             for temp in all_temps:
    #                 if temp[0] == alt[0] and temp[1] == alt[1]:
    #                     if np.max([np.abs(float(temp[2])-float(alt[2])),np.abs(float(temp[2])-float(image[2])),np.abs(float(image[2])-float(alt[2]))]) < 86400:
    #                         coobs_lakes.append(image)
    #                         coobs = True
    #                 if coobs:
    #                     break
    #         if coobs:
    #             break
    
    # bloom_lats = [56.4716520000001,
    #             52.1125980000001,
    #             -28.504996,
    #             44.1850160000001,
    #             -38.6902729999999,
    #             43.23425,
    #             58.3827590000001,
    #             50.677083,
    #             57.3356810000001,
    #             53.8435430000001,
    #             -0.0385909999999399]
    obs_blooms = []
    for image in all_images:
        for bloom in blooms:
            if np.abs(float(image[0]) - float(bloom[0])) < 0.00001:
                obs_blooms.append(image)
    coobs_lakes = []
    print(len(all_temps))
    print(len(all_levels))
    print(len(all_images))
    #print(obs_blooms)
    for image in obs_blooms:
        coobs = False
        for alt in all_levels:
            if image[0] == alt[0] and image[1] == alt[1]:
                for temp in all_temps:
                    if temp[0] == alt[0] and temp[1] == alt[1]:
                        if np.max([np.abs(float(temp[2])-float(alt[2])),np.abs(float(temp[2])-float(image[2])),np.abs(float(image[2])-float(alt[2]))]) < 14400:
                            coobs_lakes.append(image)
                            coobs = True
                    if coobs:
                        break
            if coobs:
                break
    bloom_sighting_counts= []
    bloom_revisits = []
    for bloom in blooms:
        bloom_visit_times = []
        bloom_sightings = []
        for image in all_images:
            if image[0] == bloom[0] and image[1] == bloom[1]:
                bloom_visit_times.append(float(image[2]))
                bloom_sightings.append(bloom)
        for level in all_levels:
            if level[0] == bloom[0] and level[1] == bloom[1]:
                bloom_visit_times.append(float(level[2]))
                bloom_sightings.append(bloom)
        for temp in all_temps:
            if temp[0] == bloom[0] and temp[1] == bloom[1]:
                bloom_visit_times.append(float(temp[2]))
                bloom_sightings.append(bloom)
        gaps = []
        #bloom_visit_times.append(0)
        #bloom_visit_times.append(86400*30)
        bloom_visit_times = np.sort(bloom_visit_times)
        bloom_visit_times = np.unique(bloom_visit_times)
        for i in range(1,len(bloom_visit_times)):
            gaps.append(bloom_visit_times[i]-bloom_visit_times[i-1])
        if len(gaps) > 0:
            #print(gaps)
            bloom_revisits.append(np.average(gaps))
        bloom_sighting_counts.append(len(bloom_sightings))
    print(np.average(bloom_revisits)/86400)
    #print(np.average(bloom_sighting_counts))
    # print("Cold lakes: "+str(len(unique(cold_lakes))))
    # print("Hot lakes: "+str(len(unique(hot_lakes))))
    # print("Lake floods seen: "+str(len(unique(lake_floods))))
    # print("Lake droughts seen: "+str(len(unique(lake_droughts))))
    print("Co-obs blooms seen: "+str(len(unique(coobs_lakes))))
    # if(len(blooms) > 0):
    #     print("Blooms seen: "+str(len(unique(blooms))))
    # print("Lakes altimetered: "+str(len(unique(all_levels))))
    # print("Lakes imaged: "+str(len(unique(all_images))))
    # print("Lakes thermally imaged: "+str(len(unique(all_temps))))

    # print("Cold lakes all: "+str(len(time_unique(cold_lakes))))
    # print("Hot lakes all: "+str(len(time_unique(hot_lakes))))
    # print("Lake floods all: "+str(len(time_unique(lake_floods))))
    # print("Lake droughts all: "+str(len(time_unique(lake_droughts))))
    print("Co-obs blooms all: "+str(len(time_unique(coobs_lakes))))
    # if(len(blooms) > 0):
    #     print("Blooms all: "+str(len(time_unique(blooms))))
    # print("Lakes altimetered all: "+str(len(time_unique(all_levels))))
    # print("Lakes imaged all: "+str(len(time_unique(all_images))))
    # print("Lakes thermally all: "+str(len(time_unique(all_temps))))

    
    lake_points = []
    with open(directory+'../../resources/grealm.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            lake_points.append((line["lat"],line["lon"]))
    with open(directory+'../../resources/laketemps.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            lake_points.append((line["lat"],line["lon"]))
    with open(directory+'../../resources/laketemps.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            lake_points.append((line["lat"],line["lon"]))
    with open(directory+'../../resources/extralakes.csv', 'r') as f:
        d_reader = csv.DictReader(f)
        for line in d_reader:
            lake_points.append((line["lat"],line["lon"]))

    # flood_points = []
    # flood_lats = []
    # with open('./scenarios/scenario1b/resources/one_year_floods_multiday.csv', 'r') as f:
    #     d_reader = csv.DictReader(f)
    #     for line in d_reader:
    #         if len(flood_points) > 0:
    #             if line["lat"] not in flood_lats:
    #                 flood_lats.append(line["lat"])
    #                 flood_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+60*60))
    #         else:
    #             flood_lats.append(line["lat"])
    #             flood_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+60*60))
    # hf_points = []
    # hf_lats = []
    # with open('./scenarios/scenario1b/resources/flow_events_75_multiday.csv', 'r') as f:
    #     d_reader = csv.DictReader(f)
    #     for line in d_reader:
    #         if len(hf_points) > 0:
    #             hf_lats.append(line["lat"])
    #             hf_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+86400))
    #         else:
    #             hf_lats.append(line["lat"])
    #             hf_points.append((line["lat"],line["lon"],line["time"],float(line["time"])+86400))
    # flood_points = np.asfarray(flood_points)
    # hf_points = np.asfarray(hf_points)

    # all_floods = []
    # for alt in alt_floods:
    #     all_floods.append((alt[0],alt[1],alt[2],"alt"))
    # for tss in tss_floods:
    #     all_floods.append((tss[0],tss[1],tss[2],"tss"))
    # for coobs in coobs_floods:
    #     all_floods.append((coobs[0],coobs[1],coobs[2],"coobs"))
    # all_outliers = np.asarray(all_floods)
    # all_outliers = all_outliers[all_outliers[:, 2].argsort()]

    filenames = []
    alt_lats = []
    alt_lons = []
    lake_droughts_lats = []
    lake_droughts_lons = []
    lake_floods_lats = []
    lake_floods_lons = []
    cold_lakes_lats = []
    cold_lakes_lons = []
    hot_lakes_lats = []
    hot_lakes_lons = []
    #tss_lats = []
    #tss_lons = []
    coobs_lats = []
    coobs_lons = []
    images_lats = []
    images_lons = []
    alt_lats = []
    alt_lons = []
    therm_lats = []
    therm_lons = []
    #hfs_coobs_lats = []
    #hfs_coobs_lons = []
    duration = 86400*30
    for t in range(200000,duration,5184*4):
        #hf_lats,hf_lons = get_curr_points(hf_points,t)
        lake_lats, lake_lons = get_points(lake_points,t)
        #alt_lats, alt_lons = get_past_points(alt_floods,t)
        #tss_lats, tss_lons = get_past_points(tss_floods,t)
        coobs_lats, coobs_lons = get_past_points(coobs_lakes,t)
        images_lats, images_lons = get_past_points(all_images,t)
        therm_lats, therm_lons = get_past_points(all_temps,t)
        alt_lats, alt_lons = get_past_points(all_levels,t)
        lake_droughts_lats, lake_droughts_lons = get_past_points(lake_droughts,t)
        lake_floods_lats, lake_floods_lons = get_past_points(lake_floods,t)
        cold_lakes_lats, cold_lakes_lons = get_past_points(cold_lakes,t)
        hot_lakes_lats, hot_lakes_lons = get_past_points(hot_lakes,t)
        blooms_lats, blooms_lons = get_past_points(blooms,t)
        #hfs_tss_lats, hfs_tss_lons = get_past_points(tss_hfs,t)
        #hfs_coobs_lats, hfs_coobs_lons = get_past_points(coobs_hfs,t)
        alt_gts_lats, alt_gts_lons = get_ground_track(alt_ground_tracks,t,6000.0)
        vnir_gts_lats, vnir_gts_lons = get_ground_track(vnir_ground_tracks,t,6000.0)
        vnirtir_gts_lats, vnirtir_gts_lons = get_ground_track(vnirtir_ground_tracks,t,6000.0)
        tir_gts_lats, tir_gts_lons = get_ground_track(tir_ground_tracks,t,6000.0)
        
        filename = f'./utils/images_a/frame_{t}.png'
        filenames.append(filename)
        # last frame of each viz stays longer
        if (t == duration):
            for i in range(5):
                filenames.append(filename)        # save img
        m = Basemap(projection='merc',llcrnrlat=-70,urcrnrlat=70,\
                llcrnrlon=-180,urcrnrlon=180,resolution='c')
        #alt_x, alt_y = m(alt_lons,alt_lats)
        #tss_x, tss_y = m(tss_lons,tss_lats)
        lake_x, lake_y = m(lake_lons,lake_lats)
        img_x, img_y = m(images_lons,images_lats)
        alt_x, alt_y = m(alt_lons,alt_lats)
        therm_x, therm_y = m(therm_lons,therm_lats)
        #hf_x, hf_y = m(hf_lons,hf_lats)
        lake_droughts_x, lake_droughts_y = m(lake_droughts_lats, lake_droughts_lons)
        lake_floods_x, lake_floods_y = m(lake_floods_lons,lake_floods_lats)
        #tss_x, tss_y = m(tss_lons,tss_lats)
        coobs_x, coobs_y = m(coobs_lons,coobs_lats)
        cold_lakes_x, cold_lakes_y = m(cold_lakes_lons,cold_lakes_lats)
        hot_lakes_x, hot_lakes_y = m(hot_lakes_lons,hot_lakes_lats)
        blooms_x, blooms_y = m(blooms_lons,blooms_lats)
        alt_gts_x, alt_gts_y = m(alt_gts_lons,alt_gts_lats)
        vnir_gts_x, vnir_gts_y = m(vnir_gts_lons,vnir_gts_lats)
        vnirtir_gts_x, vnirtir_gts_y = m(vnirtir_gts_lons,vnirtir_gts_lats)
        tir_gts_x, tir_gts_y = m(tir_gts_lons,tir_gts_lats)
        m.drawmapboundary(fill_color='#99ffff')
        m.fillcontinents(color='#cc9966',lake_color='#99ffff')
        m.scatter(alt_gts_x,alt_gts_y,0.25,marker='o',color='#000000', label='Altimeter ground track')
        m.scatter(vnir_gts_x,vnir_gts_y,0.25,marker='o',color='#ffffff', label='VNIR ground track')
        m.scatter(vnirtir_gts_x,vnirtir_gts_y,0.25,marker='o',color='yellow', label='VNIR+TIR ground track')
        m.scatter(tir_gts_x,tir_gts_y,0.25,marker='o',color='orange', label='TIR ground track')
        #m.scatter(hf_x,hf_y,1,marker='o',color='b', label='High flow events')
        m.scatter(lake_x,lake_y,0.25,marker='o',color='cyan', label='Lakes')
        m.scatter(img_x,img_y,2,marker='o',color='yellow', label='Imagery')
        m.scatter(alt_x,alt_y,1.5,marker='o',color='black', label='Altimetry')
        m.scatter(therm_x,therm_y,1,marker='o',color='orange', label='Thermals')
        m.scatter(coobs_x,coobs_y,4,marker='s',color='magenta', label='Co-observations')
        m.scatter(lake_droughts_x,lake_droughts_y,4,marker='v',color='brown', label='Lake droughts')
        m.scatter(lake_floods_x,lake_floods_y,4,marker='^',color='purple', label= 'Lake floods')
        m.scatter(cold_lakes_x,cold_lakes_y,4,marker='v',color='blue', label='Cold lakes')
        m.scatter(hot_lakes_x,hot_lakes_y,4,marker='^',color='red', label='Hot lakes')
        m.scatter(blooms_x,blooms_y,6,marker='o',color='green', label='Blooms')
        #m.scatter(hfs_coobs_x,hfs_coobs_y,5,marker='s',color='purple', label='High flow coobservations')
        ax = plt.gca()
        box = ax.get_position()
        ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])

        # Put a legend to the right of the current axis
        ax.legend(loc='center left', fontsize=5, bbox_to_anchor=(1, 0.5))
        # plt.legend(fontsize=5,loc='upper right')
        plt.title('3D-CHESS observations at time t='+str(np.round(t/86400,2))+' days')
        plt.savefig(filename,dpi=300)
        if (t == duration):
            plt.savefig("final_2_existing.png",dpi=300)
        plt.close()
    print('Charts saved\n')
    gif_name = 'plot2D_2_a'
    # Build GIF
    print('Creating gif\n')
    with imageio.get_writer(f'{gif_name}.gif', mode='I') as writer:
        for filename in filenames:
            image = imageio.imread(filename)
            writer.append_data(image)
    print('Gif saved\n')
    print('Removing Images\n')
    # Remove files
    for filename in set(filenames):
        os.remove(filename)
    print('DONE')