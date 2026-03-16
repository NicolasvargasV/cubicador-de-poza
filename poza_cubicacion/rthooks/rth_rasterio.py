import os, sys

base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))

gdal_data = os.path.join(base, "rasterio", "gdal_data")
proj_data = os.path.join(base, "rasterio", "proj_data")

if os.path.isdir(gdal_data):
    os.environ["GDAL_DATA"] = gdal_data

if os.path.isdir(proj_data):
    os.environ["PROJ_LIB"] = proj_data
