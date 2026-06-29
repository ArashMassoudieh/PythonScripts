import os
from qgis.core import (
    QgsProject, QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutPoint,
    QgsLayoutSize, QgsUnitTypes, QgsPrintLayout, QgsLayoutExporter,
    QgsLayoutMeasurement, QgsLayoutItemScaleBar, QgsLayoutItemLegend,
    QgsLayerTree, QgsLegendStyle, QgsRectangle,
)
from qgis.PyQt.QtGui import QFont, QColor

# ---- session paths (this project = AZ12-069 / Chinle C2) ----
try: ROOT
except NameError: ROOT = "/home/arash/Dropbox/Chloeta/NHA/"
try: SITE_DIR
except NameError: SITE_DIR = "WS3_GIS/AZ12-069"

DPI = 150
PAGE_W_MM, PAGE_H_MM = 297, 210
DEM_NAME = "cliped_utm"
OSM_NAME = "OpenStreetMap"
TITLE = "NHA WS3 - AZ12-069 / 086 / 087 (Chinle, C2)"
OVERLAY_LAYERS = ["C2_points", "study_streams_clip", "floodplains_clip",
                  "WSEL_HFS_clip", "NHDFlowline_clip"]

proj = QgsProject.instance()
out_dir = os.path.join(ROOT, SITE_DIR, "outputs", "maps")
os.makedirs(out_dir, exist_ok=True)

def by_name(name):
    for l in proj.mapLayers().values():
        if l.name().lower() == name.lower():
            return l
    return None

dem = by_name(DEM_NAME)
if dem is None:
    raise Exception("DEM layer '%s' not loaded. Present: %s"
                    % (DEM_NAME, [l.name() for l in proj.mapLayers().values()]))

# --- frame to the DEM extent, with a small margin so edges aren't flush ---
e = dem.extent()
mx, my = e.width() * 0.04, e.height() * 0.04
extent = QgsRectangle(e.xMinimum()-mx, e.yMinimum()-my,
                      e.xMaximum()+mx, e.yMaximum()+my)
print("Framing to DEM extent:", extent.toString(1))

overlays = [by_name(n) for n in OVERLAY_LAYERS]
overlays = [l for l in overlays if l is not None]
def _pri(l):
    n = l.name().lower()
    if "point" in n or "site" in n: return 0
    if "stream" in n:               return 1
    if "flowline" in n:             return 2
    if "wsel" in n:                 return 3
    if "floodplain" in n:           return 4
    return 3
overlays.sort(key=_pri)
print("Overlays (top->bottom):", [l.name() for l in overlays])

def build_and_export(background, title_suffix, fname):
    layout = QgsPrintLayout(proj)
    layout.initializeDefaults()

    m = QgsLayoutItemMap(layout)
    m.setRect(0, 0, 1, 1)
    m.attemptMove(QgsLayoutPoint(8, 22, QgsUnitTypes.LayoutMillimeters))
    m.attemptResize(QgsLayoutSize(PAGE_W_MM-16, PAGE_H_MM-40, QgsUnitTypes.LayoutMillimeters))
    m.setLayers(overlays + [background])
    m.setExtent(extent)
    m.setFrameEnabled(True)
    m.setFrameStrokeColor(QColor(60, 60, 60))
    m.setFrameStrokeWidth(QgsLayoutMeasurement(0.4, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(m)

    t = QgsLayoutItemLabel(layout)
    t.setText(TITLE + " - " + title_suffix)
    f = QFont("Arial", 14); f.setBold(True)
    t.setFont(f); t.setFontColor(QColor(31, 58, 95))
    t.attemptMove(QgsLayoutPoint(8, 8, QgsUnitTypes.LayoutMillimeters))
    t.adjustSizeToText()
    layout.addLayoutItem(t)

    sb = QgsLayoutItemScaleBar(layout)
    sb.setStyle("Single Box"); sb.setLinkedMap(m)
    sb.setUnits(QgsUnitTypes.DistanceMeters); sb.setUnitLabel("m")
    sb.applyDefaultSize(); sb.setFont(QFont("Arial", 8))
    sb.attemptMove(QgsLayoutPoint(12, PAGE_H_MM-14, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(sb)

    leg = QgsLayoutItemLegend(layout)
    leg.setTitle("Legend"); leg.setAutoUpdateModel(False)
    rt = QgsLayerTree()
    for l in overlays:
        rt.addLayer(l)
    leg.model().setRootGroup(rt)
    leg.setStyleFont(QgsLegendStyle.Title, QFont("Arial", 9, QFont.Bold))
    leg.setStyleFont(QgsLegendStyle.SymbolLabel, QFont("Arial", 8))
    leg.setBackgroundColor(QColor(255, 255, 255, 220))
    leg.setFrameEnabled(True); leg.setFrameStrokeColor(QColor(120, 120, 120))
    leg.attemptMove(QgsLayoutPoint(PAGE_W_MM-60, 26, QgsUnitTypes.LayoutMillimeters))
    leg.attemptResize(QgsLayoutSize(52, 36, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(leg)

    na = QgsLayoutItemLabel(layout)
    na.setText("N\n^")
    naf = QFont("Arial", 14); naf.setBold(True)
    na.setFont(naf); na.setFontColor(QColor(40, 40, 40))
    na.attemptMove(QgsLayoutPoint(PAGE_W_MM-16, PAGE_H_MM-26, QgsUnitTypes.LayoutMillimeters))
    na.adjustSizeToText()
    layout.addLayoutItem(na)

    path = os.path.join(out_dir, fname)
    exp = QgsLayoutExporter(layout)
    st = QgsLayoutExporter.ImageExportSettings(); st.dpi = DPI
    print("exporting %s ..." % fname)
    res = exp.exportToImage(path, st)
    print("  result:", res, "(0=Success) ->", path if res == 0 else "FAILED")

# --- map 1: DEM background ---
build_and_export(dem, "DEM", "AZ12-069_DEM.png")

# --- map 2: OSM context (only if OSM is loaded and drawn) ---
osm = by_name(OSM_NAME)
if osm is not None:
    build_and_export(osm, "OpenStreetMap context", "AZ12-069_OSM.png")
else:
    print("OSM layer not loaded; skipped OSM map. (DEM map still produced.)")