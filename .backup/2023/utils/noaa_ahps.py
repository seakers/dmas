# first import the functions for downloading data from NWIS
import shapefile

sf = shapefile.Reader("./utils/ahps/national_shapefile_obs.shp")

print(sf.fields)
rec = sf.record(3)
print(rec['GaugeLID'])
print(rec['Observed'])
print(rec['Status'])
print(rec['LowThresh'])
print(rec['Moderate'])
print(rec['Major'])
print(rec['Waterbody'])
print(rec['Latitude'])
print(rec['Longitude'])
