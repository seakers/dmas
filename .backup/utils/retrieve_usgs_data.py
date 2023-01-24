# first import the functions for downloading data from NWIS
import dataretrieval.nwis as nwis
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import numpy as np
import csv

# get water quality samples (qwdata)
turbidity_df = nwis.get_record(stateCd='tx', parameterCd=['00060','63680'], service='dv', start='2020-01-01', end='2020-12-31')

df, md = nwis.what_sites(stateCd='TX', parameterCd='63680')
print(df)
usgs_dir = './utils/usgs_data/'
sites = []
for site, new_df in turbidity_df.groupby(level=0):
    site_info = nwis.get_record(sites=site,service='site')
    sites.append((site,site_info.iloc[0]['station_nm'],site_info.iloc[0]['dec_lat_va'],site_info.iloc[0]['dec_long_va']))
    new_df = new_df.droplevel(0)
    times = []
    for date in new_df.index:
        times.append(date)
    water_levels = new_df['00060_Mean'].values
    turbidity_levels = new_df['63680_Mean'].values
    if(np.max(water_levels) > 1.0 and not np.isnan(turbidity_levels).all()):
        # Plot water levels
        
        ax1 = plt.gca()
        ax1.plot(times, water_levels, 'b-')
        plt.xlabel('Time')
        ax1.set_ylabel('Discharge [cfs]', color='b')
        plt.title(site_info.iloc[0]['station_nm']+' at latitude : '+str(site_info.iloc[0]['dec_lat_va'])+', longitude: '+str(site_info.iloc[0]['dec_long_va']))
        date_form = DateFormatter("%b-%d")
        ax1.xaxis.set_major_formatter(date_form)
        # Plot turbidity
        
        ax2 = ax1.twinx()
        ax2.plot(times, turbidity_levels, 'g-')
        plt.xlabel('Time')
        ax2.set_ylabel('Turbidity [mg/L]', color='g')
        date_form = DateFormatter("%b-%d")
        ax2.xaxis.set_major_formatter(date_form)
        with open(usgs_dir+site+'.csv','w') as out:
            csv_out=csv.writer(out)
            csv_out.writerow(['date','discharge [cfs]','turbidity [mg/L]'])
            for i in range(len(water_levels)):
                csv_out.writerow((times[i],water_levels[i],turbidity_levels[i]))
        plt.savefig(usgs_dir+site+'.png')
        plt.show()
with open(usgs_dir+'sites.csv','w') as out:
    csv_out=csv.writer(out)
    csv_out.writerow(['id','name','lat','lon'])
    for row in sites:
        csv_out.writerow(row)