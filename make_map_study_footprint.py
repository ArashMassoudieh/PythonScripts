# =============================================================================
# make_map_study_footprint.py   (QGIS Python Console)
#
# NHA WS3 -- report figure showing the AECOM study footprint vs. the WS3 sites.
# Renders four layers already loaded in the project:
#     HUC12_HSF        (watershed mesh, light outline -- the full region)
#     study_streams    (studied reaches -- highlighted)
#     wsel             (water surface elevation features -- highlighted)
#     ws3_site_locations (the WS3 sites, labeled)
# Assembles a print layout with subtitle, legend, north arrow, and scale bar,
# then exports a 300-dpi PNG.
#
# The point of the figure: the HUC12 mesh blankets the whole Navajo Nation, but
# study_streams + wsel only appear in a few subwatersheds -- so most WS3 sites
# fall OUTSIDE the detailed AECOM study footprint.
#
# USAGE (QGIS Python Console):
#   exec(open("/home/arash/Dropbox/Chloeta/NHA/PythonScripts/make_map_study_footprint.py").read())
#
# Layers are read from the project by name; nothing is downloaded.
# =============================================================================

import os
from qgis.core import (
    QgsProject, QgsRectangle, QgsVectorLayer,
    QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
    QgsLayoutItemScaleBar, QgsLayoutItemLabel, QgsLayoutItemPicture,
    QgsLayoutItemPolygon, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutExporter, QgsLayerTree, QgsLayoutItemMapGrid,
    QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont, QPolygonF
from qgis.PyQt.QtCore import QPointF

# ---------------------------------------------------------------------------
# --- settings --------------------------------------------------------------
# ---------------------------------------------------------------------------
try:
    ROOT
except NameError:
    ROOT = "/home/arash/Dropbox/Chloeta/NHA"

# Layer names as they appear in the Layers panel (edit if yours differ).
L_HUC12   = "HUD12_HSF"          # note: panel showed "HUD12_HSF"
L_STREAMS = "study_streams"
L_WSEL    = "wsel"
L_SITES   = "ws3_site_locations"

# Field on the site layer holding the label (auto-detect if blank)
SITE_LABEL_FIELD = ""

OUT_PNG  = os.path.join(ROOT, "WS3_GIS", "figures", "WS3_Study_Footprint.png")
SUBTITLE = ("NHA WS3 -- AECOM Detailed Study Footprint vs. WS3 Sites   "
            "(HUC-12 mesh = full region; studied streams / WSEL = detailed study extent)")
DPI         = 300
MARGIN_FRAC = 0.04
PAGE_W_MM   = 279.4    # 11 in landscape
PAGE_H_MM   = 150.0    # trimmed height to remove bottom whitespace
# ---------------------------------------------------------------------------

os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
proj = QgsProject.instance()

def get(name, *keywords):
    """Find a layer by exact name, else by any keyword (case-insensitive substring).
    Robust to prior renames (e.g. a previous run that relabeled layers)."""
    found = proj.mapLayersByName(name)
    if found:
        return found[0]
    allnames = {l.name(): l for l in proj.mapLayers().values()}
    # try keyword substring match
    for kw in keywords:
        for n, l in allnames.items():
            if kw.lower() in n.lower():
                return l
    raise Exception("Layer not found. Looked for '%s' (and keywords %s). "
                    "Layers present: %s" % (name, list(keywords), list(allnames)))

huc   = get(L_HUC12,   "huc", "hud", "watershed")
strm  = get(L_STREAMS, "stud", "stream")
wsel  = get(L_WSEL,    "wsel", "water surface")
sites = get(L_SITES,   "ws3", "site", "location")

# ---------------------------------------------------------------------------
# --- styling ---------------------------------------------------------------
# ---------------------------------------------------------------------------

# HUC12: light grey hairline outline, no fill -> the "everything" backdrop
huc_sym = QgsFillSymbol.createSimple({
    "color": "0,0,0,0",
    "outline_color": "170,185,205,160",   # pale steel-blue
    "outline_width": "0.12",
    "outline_style": "solid",
})
huc.renderer().setSymbol(huc_sym)
huc.setName("HUC-12 watersheds (region)")
huc.triggerRepaint()

# study streams: strong blue line -> the studied reaches
strm_sym = QgsLineSymbol.createSimple({
    "color": "20,90,170,255",
    "width": "0.6",
})
strm.renderer().setSymbol(strm_sym)
strm.setName("Studied streams (AECOM study)")
strm.triggerRepaint()

# WSEL: warm highlight so detailed-results areas stand out from streams
# (handle point or line geometry)
from qgis.core import QgsWkbTypes
if QgsWkbTypes.geometryType(wsel.wkbType()) == QgsWkbTypes.PointGeometry:
    wsel_sym = QgsMarkerSymbol.createSimple({
        "name": "circle", "color": "200,60,30,255",
        "outline_color": "120,30,15,255", "size": "1.4",
    })
else:
    wsel_sym = QgsLineSymbol.createSimple({"color": "200,60,30,255", "width": "0.9"})
wsel.renderer().setSymbol(wsel_sym)
wsel.setName("WSEL -- detailed water surface elevations")
wsel.triggerRepaint()

# sites: bold yellow circles with dark outline
site_sym = QgsMarkerSymbol.createSimple({
    "name": "circle", "color": "255,210,0,255",
    "outline_color": "30,30,30,255", "outline_width": "0.3", "size": "2.0",
})
sites.renderer().setSymbol(site_sym)
sites.setName("WS3 sites")
sites.triggerRepaint()

# site labels
sid = SITE_LABEL_FIELD
if not sid:
    names = [f.name() for f in sites.fields()]
    for c in ("project_no","Project_No","PROJECT_NO","site","Site","name","Name","id","ID"):
        if c in names:
            sid = c; break
if sid:
    pal = QgsPalLayerSettings()
    pal.fieldName = sid
    pal.enabled = True
    tf = QgsTextFormat()
    f = QFont("Arial"); f.setPointSize(8); f.setBold(True)
    tf.setFont(f); tf.setSize(8)
    tf.setColor(QColor(20, 20, 20))
    buf = QgsTextBufferSettings(); buf.setEnabled(True); buf.setSize(0.8)
    buf.setColor(QColor(255, 255, 255)); tf.setBuffer(buf)
    pal.setFormat(tf)
    try:
        pal.placement = QgsPalLayerSettings.OverPoint
        pal.yOffset = 2.0
    except Exception:
        pass
    sites.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    sites.setLabelsEnabled(True)
    sites.triggerRepaint()

# ---------------------------------------------------------------------------
# --- extent: full region (HUC12) so the footprint contrast is visible ------
# ---------------------------------------------------------------------------
ext = huc.extent()
dx, dy = ext.width() * MARGIN_FRAC, ext.height() * MARGIN_FRAC
map_ext = QgsRectangle(ext.xMinimum()-dx, ext.yMinimum()-dy,
                       ext.xMaximum()+dx, ext.yMaximum()+dy)

# ---------------------------------------------------------------------------
# --- print layout ----------------------------------------------------------
# ---------------------------------------------------------------------------
mgr = proj.layoutManager()
lname = "WS3_Study_Footprint"
for lay in mgr.printLayouts():
    if lay.name() == lname:
        mgr.removeLayout(lay)

layout = QgsPrintLayout(proj)
layout.initializeDefaults()
layout.setName(lname)
page = layout.pageCollection().pages()[0]
page.setPageSize(QgsLayoutSize(PAGE_W_MM, PAGE_H_MM, QgsUnitTypes.LayoutMillimeters))
mgr.addLayout(layout)

# map item sized to region aspect ratio
AVAIL_X, AVAIL_Y = 8, 18
AVAIL_W, AVAIL_H = 195, 112
aspect = (map_ext.width()/map_ext.height()) if map_ext.height() else 1.0
if AVAIL_W/AVAIL_H > aspect:
    map_h = AVAIL_H; map_w = map_h*aspect
else:
    map_w = AVAIL_W; map_h = map_w/aspect

m = QgsLayoutItemMap(layout)
m.setBackgroundColor(QColor(255,255,255))
layout.addLayoutItem(m)
m.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
m.attemptMove(QgsLayoutPoint(AVAIL_X, AVAIL_Y, QgsUnitTypes.LayoutMillimeters))
m.setExtent(map_ext); m.zoomToExtent(map_ext)
# draw order: sites on top, then wsel, streams, huc backdrop
m.setLayers([sites, wsel, strm, huc])
m.setKeepLayerSet(True)

# light grid annotations
grid = m.grid()
grid.setEnabled(True)
grid.setIntervalX(map_ext.width()/4.0)
grid.setIntervalY(map_ext.height()/4.0)
grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly)
grid.setAnnotationEnabled(True)
grid.setAnnotationPrecision(0)
grid.setAnnotationFontColor(QColor(0,0,0))
grid.setAnnotationFrameDistance(1.0)
grid.setFrameStyle(QgsLayoutItemMapGrid.NoFrame)
try:
    grid.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, QgsLayoutItemMapGrid.Top)
    grid.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, QgsLayoutItemMapGrid.Left)
    grid.setAnnotationDisplay(QgsLayoutItemMapGrid.HideAll, QgsLayoutItemMapGrid.Right)
    grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, QgsLayoutItemMapGrid.Bottom)
except Exception as e:
    print("  (grid side-control skipped: %s)" % e)

# subtitle
sub = QgsLayoutItemLabel(layout)
sub.setText(SUBTITLE)
fs = QFont(); fs.setPointSize(9)
sub.setFont(fs); sub.setFontColor(QColor(70,70,70))
layout.addLayoutItem(sub)
sub.attemptMove(QgsLayoutPoint(8, 11, QgsUnitTypes.LayoutMillimeters))
sub.attemptResize(QgsLayoutSize(260, 8, QgsUnitTypes.LayoutMillimeters))

# legend restricted to the four map layers
leg = QgsLayoutItemLegend(layout)
leg.setTitle("Legend")
leg.setLinkedMap(m)
leg.setAutoUpdateModel(False)
leg.setLegendFilterByMapEnabled(True)
root = QgsLayerTree()
root.addLayer(sites)
root.addLayer(wsel)
root.addLayer(strm)
root.addLayer(huc)
leg.model().setRootGroup(root)
# smaller legend fonts
try:
    from qgis.core import QgsLegendStyle
    f_title = QFont("Arial"); f_title.setPointSize(9); f_title.setBold(True)
    f_item  = QFont("Arial"); f_item.setPointSize(7)
    leg.setStyleFont(QgsLegendStyle.Title, f_title)
    leg.setStyleFont(QgsLegendStyle.SymbolLabel, f_item)
    leg.setSymbolHeight(3.5)
    leg.setSymbolWidth(5.0)
except Exception as e:
    print("  (legend font control skipped: %s)" % e)
leg.adjustBoxSize()
layout.addLayoutItem(leg)
leg_x = min(AVAIL_X + map_w + 4, PAGE_W_MM - 62)
leg.attemptMove(QgsLayoutPoint(leg_x, AVAIL_Y + 6, QgsUnitTypes.LayoutMillimeters))
leg.setBackgroundColor(QColor(255,255,255))

# scale bar -- fixed number of segments with an explicit unit-per-segment so the
# scalebar over a large region cannot blow up to an enormous width
sb = QgsLayoutItemScaleBar(layout)
sb.setStyle("Single Box")
sb.setLinkedMap(m)
sb.setUnits(QgsUnitTypes.DistanceMiles)
sb.setUnitLabel("mi")
try:
    sb.setUnitsPerSegment(30)        # 30 mi per box
    sb.setNumberOfSegments(4)
    sb.setNumberOfSegmentsLeft(0)
    sf = QFont("Arial"); sf.setPointSize(7)
    try:
        from qgis.core import QgsTextFormat as _TF
        _tf = _TF(); _tf.setFont(sf); _tf.setSize(7); sb.setTextFormat(_tf)
    except Exception:
        sb.setFont(sf)
    sb.setHeight(2.5)
    sb.update()
except Exception as e:
    print("  (scalebar segment control fallback: %s)" % e)
    sb.applyDefaultSize()
layout.addLayoutItem(sb)
sb.attemptResize(QgsLayoutSize(55, 8, QgsUnitTypes.LayoutMillimeters))
sb.attemptMove(QgsLayoutPoint(AVAIL_X + 2, AVAIL_Y + map_h + 3, QgsUnitTypes.LayoutMillimeters))

# north arrow (SVG with drawn fallback)
north = QgsLayoutItemPicture(layout)
svg = []
try:
    from qgis.core import QgsApplication
    pkg = QgsApplication.pkgDataPath()
    for rel in ("svg/arrows/NorthArrow_02.svg","svg/arrows/NorthArrow_01.svg"):
        p = os.path.join(pkg, rel)
        if os.path.isfile(p): svg.append(p)
except Exception:
    pass
if svg:
    north.setPicturePath(svg[0]); layout.addLayoutItem(north)
    north.attemptMove(QgsLayoutPoint(leg_x + 4, AVAIL_Y + 70, QgsUnitTypes.LayoutMillimeters))
    north.attemptResize(QgsLayoutSize(11, 14, QgsUnitTypes.LayoutMillimeters))
else:
    nx, ny = leg_x + 8, AVAIL_Y + 70
    tri = QgsLayoutItemPolygon(layout)
    tri.setNodes(QPolygonF([QPointF(nx,ny),QPointF(nx-5,ny+12),QPointF(nx+5,ny+12)]))
    tri.setSymbol(QgsFillSymbol.createSimple({"color":"20,20,20,255","outline_color":"20,20,20,255"}))
    layout.addLayoutItem(tri)
    nlab = QgsLayoutItemLabel(layout); nlab.setText("N")
    nf = QFont(); nf.setPointSize(14); nf.setBold(True)
    nlab.setFont(nf); nlab.adjustSizeToText(); layout.addLayoutItem(nlab)
    nlab.attemptMove(QgsLayoutPoint(nx-2, ny+12, QgsUnitTypes.LayoutMillimeters))

# --- export ---
exporter = QgsLayoutExporter(layout)
settings = QgsLayoutExporter.ImageExportSettings()
settings.dpi = DPI
# IMPORTANT: keep the page fixed (11x8.5 in). cropToContents can blow the canvas
# up to hundreds of thousands of pixels if any item (e.g. the scalebar) renders
# off-page or oversized, producing a "corrupted"-looking ultra-wide PNG.
settings.cropToContents = False
res = exporter.exportToImage(OUT_PNG, settings)
if res == QgsLayoutExporter.Success:
    print("Wrote PNG:", OUT_PNG)
else:
    print("PNG EXPORT FAILED, code:", res)

# also export PDF
OUT_PDF = os.path.splitext(OUT_PNG)[0] + ".pdf"
pdf_settings = QgsLayoutExporter.PdfExportSettings()
pdf_settings.dpi = DPI
try:
    pdf_settings.rasterizeWholeImage = False
except Exception:
    pass
res_pdf = exporter.exportToPdf(OUT_PDF, pdf_settings)
if res_pdf == QgsLayoutExporter.Success:
    print("Wrote PDF:", OUT_PDF)
else:
    print("PDF EXPORT FAILED, code:", res_pdf)

print("  extent: %.0f x %.0f m" % (map_ext.width(), map_ext.height()))
print("  dpi   :", DPI)