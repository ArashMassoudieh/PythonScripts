# =============================================================================
# export_osm.py  - same layout as export_final.py but with OpenStreetMap as the
# background instead of the DEM. DPI 150, text north arrow (no SVG).
#
# IMPORTANT before running:
#   1. Frame the canvas on the two sites (same view as the DEM map).
#   2. Turn ON the OpenStreetMap layer and let it FULLY draw in the canvas
#      (no blank/loading tiles) so the layout reuses cached tiles instead of
#      re-fetching a fresh 150-DPI mosaic. This is what prevents the crash.
#   3. Then run:  exec(open(path).read())
#
# If it still hangs >2 min, OSM tiles are being rate-limited; just send the DEM
# map + the satellite aerial instead.
# =============================================================================
import os
from qgis.core import (
    QgsProject, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutPoint,
    QgsLayoutSize, QgsUnitTypes, QgsPrintLayout, QgsLayoutExporter,
    QgsLayoutMeasurement, QgsLayoutItemScaleBar, QgsLayoutItemLegend,
    QgsLayerTree, QgsLegendStyle,
)
from qgis.PyQt.QtGui import QFont, QColor

try:
    ROOT
except NameError:
    ROOT = "C:/Users/smnfa/Dropbox/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/NM15-134"

DPI = 150
PAGE_W_MM, PAGE_H_MM = 297, 210
OSM_LAYER_CANDIDATES = ["OpenStreetMap"]
OVERLAY_LAYERS = ["study_streams", "00_NHA_Structures", "ws3_site_locations", "subwatershed_params"]

proj = QgsProject.instance()
canvas = iface.mapCanvas()
out_dir = os.path.join(ROOT, SITE_DIR, "outputs", "maps")
os.makedirs(out_dir, exist_ok=True)

def by_name(name):
    for l in proj.mapLayers().values():
        if l.name().lower() == name.lower():
            return l
    return None

osm = None
for c in OSM_LAYER_CANDIDATES:
    osm = by_name(c)
    if osm:
        break
if osm is None:
    raise Exception("No OSM layer matched. Names present: %s"
                    % [l.name() for l in proj.mapLayers().values()])
print("Background:", osm.name())

overlays = [by_name(n) for n in OVERLAY_LAYERS]
overlays = [l for l in overlays if l is not None]
def _draw_priority(l):
    n = l.name().lower()
    if "site_locations" in n: return 0
    if "study_streams" in n:  return 1
    if "subwatershed" in n:   return 2
    if "structures" in n:     return 3
    return 2
overlays.sort(key=_draw_priority)
print("Overlays (top->bottom):", [l.name() for l in overlays])

extent = canvas.extent()

layout = QgsPrintLayout(proj)
layout.initializeDefaults()

m = QgsLayoutItemMap(layout)
m.setRect(0, 0, 1, 1)
m.attemptMove(QgsLayoutPoint(8, 22, QgsUnitTypes.LayoutMillimeters))
m.attemptResize(QgsLayoutSize(PAGE_W_MM - 16, PAGE_H_MM - 40, QgsUnitTypes.LayoutMillimeters))
m.setLayers(overlays + [osm])
m.setExtent(extent)
m.setFrameEnabled(True)
m.setFrameStrokeColor(QColor(60, 60, 60))
m.setFrameStrokeWidth(QgsLayoutMeasurement(0.4, QgsUnitTypes.LayoutMillimeters))
layout.addLayoutItem(m)

t = QgsLayoutItemLabel(layout)
t.setText("NHA WS3 - NM15-134 & NM15-135 (Tohajiilee) - OpenStreetMap context")
f = QFont("Arial", 14); f.setBold(True)
t.setFont(f); t.setFontColor(QColor(31, 58, 95))
t.attemptMove(QgsLayoutPoint(8, 8, QgsUnitTypes.LayoutMillimeters))
t.adjustSizeToText()
layout.addLayoutItem(t)

sb = QgsLayoutItemScaleBar(layout)
sb.setStyle("Single Box")
sb.setLinkedMap(m)
sb.setUnits(QgsUnitTypes.DistanceMeters)
sb.setUnitLabel("m")
sb.applyDefaultSize()
sb.setFont(QFont("Arial", 8))
sb.attemptMove(QgsLayoutPoint(12, PAGE_H_MM - 14, QgsUnitTypes.LayoutMillimeters))
layout.addLayoutItem(sb)

leg = QgsLayoutItemLegend(layout)
leg.setTitle("Legend")
leg.setAutoUpdateModel(False)
root = QgsLayerTree()
for l in overlays:
    root.addLayer(l)
leg.model().setRootGroup(root)
leg.setStyleFont(QgsLegendStyle.Title, QFont("Arial", 9, QFont.Bold))
leg.setStyleFont(QgsLegendStyle.SymbolLabel, QFont("Arial", 8))
leg.setBackgroundColor(QColor(255, 255, 255, 220))
leg.setFrameEnabled(True)
leg.setFrameStrokeColor(QColor(120, 120, 120))
leg.attemptMove(QgsLayoutPoint(PAGE_W_MM - 60, 26, QgsUnitTypes.LayoutMillimeters))
leg.attemptResize(QgsLayoutSize(52, 36, QgsUnitTypes.LayoutMillimeters))
layout.addLayoutItem(leg)

na = QgsLayoutItemLabel(layout)
na.setText("N\n^")
naf = QFont("Arial", 14); naf.setBold(True)
na.setFont(naf); na.setFontColor(QColor(40, 40, 40))
na.attemptMove(QgsLayoutPoint(PAGE_W_MM - 16, PAGE_H_MM - 26, QgsUnitTypes.LayoutMillimeters))
na.adjustSizeToText()
layout.addLayoutItem(na)

path = os.path.join(out_dir, "NM15_134_135_OSM.png")
exp = QgsLayoutExporter(layout)
settings = QgsLayoutExporter.ImageExportSettings()
settings.dpi = DPI
print("exporting (may take 30-90s while tiles render)...")
res = exp.exportToImage(path, settings)
print("result:", res, "(0=Success) ->", path if res == 0 else "FAILED")