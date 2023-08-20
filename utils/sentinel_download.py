from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
from datetime import date
import os

# assign directory
directory = './lake_geojsons'
api = SentinelAPI('bgorr480', 'kirichu98', 'https://scihub.copernicus.eu/dhus')

# iterate over files in
# that directory
products = []
for filename in os.listdir(directory):
    f = os.path.join(directory, filename)
    # checking if it is a file
    if os.path.isfile(f):
        footprint = geojson_to_wkt(read_geojson(f))
        product_list = api.query(footprint,
                             date=('20220601', date(2022, 6, 30)),
                             platformname='Sentinel-2',
                             producttype='S2MSI1C',
                             cloudcoverpercentage=(0, 20),limit=1)
        for product in product_list:
            print(product)
            products.append(product)
products = [*set(products)]
api.download_all(products,directory_path="./potential_images/")