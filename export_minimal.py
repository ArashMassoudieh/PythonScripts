# =============================================================================
# export_minimal.py  - bare-bones DEM export to isolate the QGIS crash.
# No OSM, no legend, no north arrow, no scale bar. Just one map item -> PNG.
# Run from QGIS Python Console: exec(open(path).read())
# =============================================================================
import os
from qgis.core import (
    QgsProject, QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize,
    QgsUnitTypes, QgsPrintLayout, QgsLayoutExporter,
)

try:
    ROOT
except NameError:
    ROOT = "C:/Users/smnfa/Dropbox/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/NM15-134"

DPI = 150
DEM_LAYER_CANDIDATES = ["dem_clipped_for_Nathan", "Clipped (extent)", "Merged", "Clipped", "clipped_utm"]

proj = QgsProject.instance()
canvas = iface.mapCanvas()
out_dir = os.path.join(ROOT, SITE_DIR, "outputs", "maps")
os.makedirs(out_dir, exist_ok=True)

# find DEM layer
dem = None
names = {l.name().lower(): l for l in proj.mapLayers().values()}
for c in DEM_LAYER_CANDIDATES:
    if c.lower() in names:
        dem = names[c.lower()]
        break

print("DEM layer:", dem.name() if dem else "*** NONE FOUND ***")
print("Layers in project:", [l.name() for l in proj.mapLayers().values()])
if dem is None:
    raise Exception("No DEM layer matched. Edit DEM_LAYER_CANDIDATES to a name above.")

print("CRS  :", dem.crs().authid())
print("Valid:", dem.isValid())

extent = canvas.extent()
print("Extent:", extent.toString(2))

layout = QgsPrintLayout(proj)
layout.initializeDefaults()

m = QgsLayoutItemMap(layout)
m.setRect(0, 0, 1, 1)
m.attemptMove(QgsLayoutPoint(10, 10, QgsUnitTypes.LayoutMillimeters))
m.attemptResize(QgsLayoutSize(270, 180, QgsUnitTypes.LayoutMillimeters))
m.setLayers([dem])
m.setExtent(extent)
layout.addLayoutItem(m)

path = os.path.join(out_dir, "minimal_DEM.png")
exp = QgsLayoutExporter(layout)
settings = QgsLayoutExporter.ImageExportSettings()
settings.dpi = DPI
res = exp.exportToImage(path, settings)
print("export result:", res, "(0 = Success)")
print("wrote:", path if res == QgsLayoutExporter.Success else "FAILED")