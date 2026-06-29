# =============================================================================
# zonal_cn.py   (QGIS Python Console)
#
# Step 3 of the curve-number workflow: compute the area-weighted mean curve
# number for each subwatershed and write it to a NEW parameters GeoPackage.
#
# Why a new file: subwatersheds.gpkg is the delineation pipeline's output. Re-
# running build_subwatersheds.py would overwrite it and destroy any attributes
# added here. So the hydrologic parameters live in their own file,
# subwatershed_params.gpkg, which this script creates (copying the subwatershed
# geometry + id + area_km2) and which later scripts extend with slope, flow
# length, Tc, etc. The delineation output is never modified.
#
# Method: zonal mean of cn.tif over each subwatershed polygon. Because the CN
# raster is on the DEM's UTM grid (equal-area cells), the unweighted cell mean
# IS the area-weighted CN. Cells that are nodata (255: water-excluded, off-grid,
# or unmatched class/HSG) are ignored by the zonal statistic, so they do not
# drag the average -- the CN is the mean over the classified area only.
#
# Inputs (in <SITE>/outputs/):
#   subwatersheds.gpkg              delineation output (layer 'subwatersheds')
#   clipped/cn.tif                  CN raster from build_cn_raster.py
#
# Output (in <SITE>/outputs/):
#   subwatershed_params.gpkg        polygons with id, area_km2, CN  (+ future cols)
#
# Run from: QGIS -> Plugins -> Python Console.
# =============================================================================
import os
import processing
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsVectorFileWriter,
    QgsCoordinateTransformContext, NULL,
)

# --- settings (set ROOT + SITE_DIR ONCE) -----------------------------------
try:
    ROOT
except NameError:
    ROOT = "C:/Users/smnfa/Dropbox/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

SUBWS_NAME  = "subwatersheds.gpkg"          # delineation output (read-only here)
SUBWS_LAYER = "subwatersheds"
CN_REL      = "clipped/cn.tif"               # CN raster (within outputs/)
OUT_NAME    = "subwatershed_params.gpkg"     # the growing parameters file
OUT_LAYER   = "subwatershed_params"

CN_FIELD    = "CN"                           # field to write (1 decimal)
CN_DECIMALS = 1
ADD_TO_PROJECT = False   # do not auto-load outputs; load manually as needed
# ---------------------------------------------------------------------------

site_path = os.path.join(ROOT, SITE_DIR)
OUT_DIR   = os.path.join(site_path, "outputs")
subws     = os.path.join(OUT_DIR, SUBWS_NAME)
cn_tif    = os.path.join(OUT_DIR, CN_REL)
out_path  = os.path.join(OUT_DIR, OUT_NAME)

print("Site  :", site_path)
print("Zones :", subws, "(layer %s)" % SUBWS_LAYER)
print("CN    :", cn_tif)
print("Out   :", out_path)

# Release any loaded copy of the output up front so it can be overwritten later
# (a loaded subwatershed_params layer holds the GPKG open on Windows).
import sys as _sys
for _sd in ("C:/Users/arash/Dropbox/Chloeta/NHA/PythonScripts",
            "C:/Users/smnfa/Dropbox/NHA/PythonScripts",
            "/home/arash/Dropbox/Chloeta/NHA/PythonScripts"):
    if os.path.isdir(_sd) and _sd not in _sys.path:
        _sys.path.insert(0, _sd)
from ws3io import release_and_delete
release_and_delete(out_path)

for p in (subws, cn_tif):
    if not os.path.isfile(p):
        raise Exception("not found: " + p)

# --- load subwatersheds ----------------------------------------------------
zones = QgsVectorLayer(subws + "|layername=" + SUBWS_LAYER, "zones_src", "ogr")
if not zones.isValid():
    zones = QgsVectorLayer(subws, "zones_src", "ogr")
if not zones.isValid():
    raise Exception("could not open subwatersheds: " + subws)
print("Subwatersheds:", zones.featureCount())

# --- zonal mean of CN over each polygon ------------------------------------
# native:zonalstatisticsfb returns a NEW layer (does not edit the source),
# with the statistic in a prefixed column. We request mean only.
PREFIX = "cn_"
result = processing.run("native:zonalstatisticsfb", {
    "INPUT": zones,
    "INPUT_RASTER": cn_tif,
    "RASTER_BAND": 1,
    "COLUMN_PREFIX": PREFIX,
    "STATISTICS": [2],          # 2 = mean
    "OUTPUT": "memory:zonal",
})
zonal = result["OUTPUT"]
mean_field = PREFIX + "mean"    # native:zonalstatisticsfb names it <prefix>mean

# --- build the output: copy id/area_km2, add CN (rounded) ------------------
from qgis.core import QgsField, QgsFields, QgsFeature
from qgis.PyQt.QtCore import QVariant

fields = QgsFields()
fields.append(QgsField("id", QVariant.Int))
fields.append(QgsField("area_km2", QVariant.Double))
fields.append(QgsField(CN_FIELD, QVariant.Double))

release_and_delete(out_path)              # lock-safe overwrite (layer/Dropbox/GPKG)
opts = QgsVectorFileWriter.SaveVectorOptions()
opts.driverName = "GPKG"
opts.layerName  = OUT_LAYER
writer = QgsVectorFileWriter.create(
    out_path, fields, zones.wkbType(), zones.crs(),
    QgsCoordinateTransformContext(), opts)

n = 0
missing = []

def _null(v):
    return v is None or v == NULL

for ft in zonal.getFeatures():
    mean = ft[mean_field]
    fid  = ft["id"] if "id" in zonal.fields().names() else n + 1
    area = ft["area_km2"] if "area_km2" in zonal.fields().names() else None
    of = QgsFeature(fields)
    of.setGeometry(ft.geometry())
    of["id"] = int(fid) if not _null(fid) else n + 1
    if not _null(area):
        of["area_km2"] = float(area)
    if _null(mean):
        of[CN_FIELD] = None
        missing.append(of["id"])
    else:
        of[CN_FIELD] = round(float(mean), CN_DECIMALS)
    writer.addFeature(of)
    n += 1
del writer

print("\nWrote %d subwatershed(s) -> %s" % (n, OUT_NAME))
print("\n  id    area_km2     CN")
out_lyr = QgsVectorLayer(out_path + "|layername=" + OUT_LAYER, OUT_LAYER, "ogr")

def _isnull(v):
    return v is None or v == NULL

for ft in sorted(out_lyr.getFeatures(),
                 key=lambda f: (_isnull(f["id"]),
                                f["id"] if not _isnull(f["id"]) else -1)):
    a = ft["area_km2"]; cn = ft[CN_FIELD]
    print("  %-4s  %9s  %5s" % (
        ft["id"] if not _isnull(ft["id"]) else "-",
        ("%.4f" % float(a)) if not _isnull(a) else "-",
        ("%.1f" % float(cn)) if not _isnull(cn) else "NULL"))

if missing:
    print("\n*** subwatershed(s) with NULL CN (no classified cells inside):", missing)
    print("    check that cn.tif covers these polygons.")

if ADD_TO_PROJECT and out_lyr.isValid():
    QgsProject.instance().addMapLayer(out_lyr)
    print("\n  added to project:", OUT_LAYER)

print("\nDone.")