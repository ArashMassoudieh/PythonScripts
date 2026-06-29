# =============================================================================
# longest_flow_path.py   (QGIS Python Console)
#
# Adds the LONGEST FLOW PATH and its derived parameters to each subwatershed in
# subwatershed_params.gpkg, and writes a flow-path line layer for inspection.
#
# For each subwatershed it finds the hydraulically most distant cell and traces
# downstream (along the GRASS r.watershed flow-direction grid) to that
# subwatershed's outlet, giving the longest flow path. From that path:
#   flow_len_ft   path length (feet)              -- the L in every Tc equation
#   elev_max_ft   elevation at the distant point  (feet)
#   elev_min_ft   elevation at the outlet         (feet)
#   slope_lfp     straight rise/run over the path (ft/ft)  -- 2nd slope definition
#   slope_1085    drop between 10% and 85% points (ft/ft)  -- damps end anomalies
#
# Grids (note: NOT the 30 m CN grid -- these are the native ~9.34 m delineation
# grid, which is finer and better for tracing; lengths are in meters internally
# then converted to feet):
#   flow_dir.tif    GRASS r.watershed direction, 1-8 CCW from east, |v| used,
#                   negative = drains off-region. ~9.34 m, UTM.
#   dem_carved.tif  same grid; elevations sampled here (the surface routing used).
# Outlets: pour_points_snapped.gpkg, each point matched to the subwatershed that
#          contains it. Masking: each trace is confined to its subwatershed polygon.
#
# Appends columns to subwatershed_params.gpkg IN PLACE (CN, slope_pct preserved)
# and writes longest_flow_paths.gpkg (one line per subwatershed).
#
# Run from: QGIS -> Plugins -> Python Console.
# =============================================================================
import os, math, struct, time
import numpy as np
from osgeo import gdal, ogr
from qgis.core import (QgsProject, QgsVectorLayer, QgsField, QgsFields,
                       QgsFeature, QgsGeometry, QgsPointXY, QgsVectorFileWriter,
                       QgsCoordinateTransformContext, QgsWkbTypes, NULL)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QApplication
gdal.UseExceptions()

# treat Python None and QGIS QVariant-null alike
def _null(v):
    return v is None or v == NULL

# --- time / cancel guards ----------------------------------------------------
# MAX_TOTAL_SEC: whole-script budget; MAX_PER_SW_SEC: per-subwatershed budget.
# Either being exceeded makes the script give up GRACEFULLY (writes whatever it
# finished, marks the rest NULL) instead of hanging. Set to None to disable.
MAX_TOTAL_SEC  = 600     # 10 min for the whole site; raise for very large sites
MAX_PER_SW_SEC = 90      # 90 s per subwatershed before it bails on that one

class _Timeout(Exception):
    pass

def _check_stop(stop_file, counter, t_start_total, t_start_sw, every=2000):
    """Pump events (keeps QGIS responsive + stop button alive), honour the STOP
    file, and enforce the time budgets. Raises _Timeout/Exception to unwind."""
    if counter % every:
        return
    QApplication.processEvents()
    if os.path.exists(stop_file):
        raise Exception("Aborted by STOP file (%s). Delete it to re-run." % stop_file)
    now = time.time()
    if MAX_TOTAL_SEC is not None and (now - t_start_total) > MAX_TOTAL_SEC:
        raise Exception("Total time budget (%ss) exceeded; giving up." % MAX_TOTAL_SEC)
    if MAX_PER_SW_SEC is not None and (now - t_start_sw) > MAX_PER_SW_SEC:
        raise _Timeout()    # per-subwatershed only: skip this one, keep going

# --- settings (set ROOT + SITE_DIR ONCE) -----------------------------------
try:
    ROOT
except NameError:
    ROOT = "C:/Users/smnfa/Dropbox/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

FLOWDIR_NAME = "flow_dir.tif"
DEM_NAME     = "dem_carved.tif"
SUBWS_NAME   = "subwatersheds.gpkg";          SUBWS_LAYER  = "subwatersheds"
POUR_NAME    = "pour_points_snapped.gpkg"     # snapped outlets
PARAMS_NAME  = "subwatershed_params.gpkg";    PARAMS_LAYER = "subwatershed_params"
LFP_NAME     = "longest_flow_paths.gpkg";     LFP_LAYER    = "longest_flow_paths"

M_TO_FT = 3.280839895
ADD_TO_PROJECT = False   # do not auto-load outputs; load manually as needed
# ---------------------------------------------------------------------------

# GRASS r.watershed direction -> (drow, dcol). Row increases southward.
# 1=NE,2=N,3=NW,4=W,5=SW,6=S,7=SE,8=E  (counterclockwise from east)
GRASS_OFF = {1:(-1, 1), 2:(-1, 0), 3:(-1,-1), 4:(0,-1),
             5:( 1,-1), 6:( 1, 0), 7:( 1, 1), 8:(0, 1)}

site = os.path.join(ROOT, SITE_DIR); OUT = os.path.join(site, "outputs")
fd_path   = os.path.join(OUT, FLOWDIR_NAME)
dem_path  = os.path.join(OUT, DEM_NAME)
subws_path= os.path.join(OUT, SUBWS_NAME)
pour_path = os.path.join(OUT, POUR_NAME)
params    = os.path.join(OUT, PARAMS_NAME)
lfp_path  = os.path.join(OUT, LFP_NAME)

print("Site :", site)
for p in (fd_path, dem_path, subws_path, pour_path, params):
    if not os.path.isfile(p):
        raise Exception("not found: " + p)

# --- read flow_dir + dem as numpy arrays, capture geotransform ------------
fdds = gdal.Open(fd_path); fdb = fdds.GetRasterBand(1)
gt = fdds.GetGeoTransform(); proj = fdds.GetProjection()
NX, NY = fdds.RasterXSize, fdds.RasterYSize
px, py = gt[1], -gt[5]                      # pixel sizes (m), py>0
FD = fdb.ReadAsArray().astype(np.int16)     # FD[r, c]
demds = gdal.Open(dem_path); demb = demds.GetRasterBand(1)
DEM = demb.ReadAsArray().astype(np.float64) # DEM[r, c]
print("Grid : %d x %d  pixel %.3f m" % (NX, NY, px))

STOP_FILE = os.path.join(OUT, "STOP")
if os.path.exists(STOP_FILE):
    os.remove(STOP_FILE)                    # clear any stale stop file

ortho = (px + py) / 2.0
diag  = ortho * math.sqrt(2)

def to_rc(x, y):
    c = int((x - gt[0]) / gt[1]); r = int((y - gt[3]) / gt[5])
    return r, c

def to_xy(r, c):                            # cell center
    x = gt[0] + (c + 0.5) * gt[1]; y = gt[3] + (r + 0.5) * gt[5]
    return x, y

def trace(r, c):
    """downstream path (list of (r,c)) following GRASS flow dir, until edge/sink."""
    path = [(r, c)]; seen = set(); steps = 0
    while True:
        if (r, c) in seen:                  # guard against loops
            break
        seen.add((r, c))
        code = abs(FD[r][c])
        if code not in GRASS_OFF:
            break
        dr, dc = GRASS_OFF[code]; nr, nc = r + dr, c + dc
        if not (0 <= nr < NY and 0 <= nc < NX):
            break
        path.append((nr, nc)); r, c = nr, nc; steps += 1
        if steps > NX * NY:
            break
    return path


def longest_path_to_outlet(in_sw, o_r, o_c):
    """Fast longest-flow-path within a subwatershed mask `in_sw` (bool array),
    draining to outlet (o_r,o_c).

    Strategy: for every in-mask cell, walk downstream (confined to the mask)
    until we reach the outlet, accumulating distance -- but MEMOIZE the
    distance-to-outlet so each cell is resolved once (near-linear overall).
    The path-length to outlet is then known for all cells; the longest flow
    path starts at the cell with the greatest distance-to-outlet. We trace that
    single cell to build the geometry. No per-headwater tracing, no list scans.
    """
    DIST = {}                        # (r,c) -> distance downstream to outlet (m)
    NEXT = {}                        # (r,c) -> next downstream (r,c) or None
    outlet = (o_r, o_c)

    def step(r, c):
        code = abs(int(FD[r][c]))
        off = GRASS_OFF.get(code)
        if off is None:
            return None
        nr, nc = r + off[0], c + off[1]
        if not (0 <= nr < NY and 0 <= nc < NX):
            return None
        if not in_sw[nr, nc]:        # leaving the subwatershed
            return None
        seg = diag if (off[0] != 0 and off[1] != 0) else ortho
        return nr, nc, seg

    def dist_to_outlet(r, c):
        # iterative walk with on-stack cycle guard; memoized.
        stack = []
        cur = (r, c)
        guard = set()
        while cur not in DIST:
            if cur == outlet:
                DIST[cur] = 0.0
                break
            if cur in guard:         # routing loop -> treat as unreachable
                for s in stack:
                    DIST[s] = None
                DIST[cur] = None
                break
            guard.add(cur)
            s = step(*cur)
            if s is None:            # ran off mask/edge before hitting outlet
                DIST[cur] = None     # this cell does not drain to the outlet
                break
            nr, nc, seg = s
            NEXT[cur] = (nr, nc, seg)
            stack.append(cur)
            cur = (nr, nc)
        # unwind the stack, assigning cumulative distances
        base = DIST.get(cur)
        while stack:
            s = stack.pop()
            nxt = NEXT.get(s)
            if base is None or nxt is None:
                DIST[s] = None
                base = None
            else:
                base = base + nxt[2]
                DIST[s] = base
        return DIST[(r, c)]

    rs, cs = np.where(in_sw)
    best_d = -1.0; best_cell = None
    cnt = 0
    for r, c in zip(rs.tolist(), cs.tolist()):
        cnt += 1
        _check_stop(STOP_FILE, cnt, _t_total_ref[0], _t_sw_ref[0], every=20000)
        d = dist_to_outlet(r, c)
        if d is not None and d > best_d:
            best_d = d; best_cell = (r, c)

    if best_cell is None or best_d <= 0:
        return None, 0.0
    # build the path geometry by walking from best_cell to outlet
    path = [best_cell]
    cur = best_cell
    while cur != outlet:
        nxt = NEXT.get(cur)
        if nxt is None:
            break
        cur = (nxt[0], nxt[1])
        path.append(cur)
    return path, best_d

def cumdist(path):
    d = [0.0]
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        d.append(d[-1] + (diag if (r0 != r1 and c0 != c1) else ortho))
    return d

def slope_1085(path, dd):
    L = dd[-1]
    if L <= 0:
        return 0.0
    def elev_at(frac):
        t = frac * L
        for i in range(len(dd) - 1):
            if dd[i] <= t <= dd[i + 1]:
                r, c = path[i]; return DEM[r][c]
        r, c = path[-1]; return DEM[r][c]
    return abs(elev_at(0.85) - elev_at(0.10)) / (0.75 * L)

# --- load subwatersheds + snapped pour points ------------------------------
subws = QgsVectorLayer(subws_path + "|layername=" + SUBWS_LAYER, "sw", "ogr")
if not subws.isValid():
    subws = QgsVectorLayer(subws_path, "sw", "ogr")
pour = QgsVectorLayer(pour_path, "pp", "ogr")
if not (subws.isValid() and pour.isValid()):
    raise Exception("could not open subwatersheds or pour points")

pour_pts = [f.geometry().asPoint() for f in pour.getFeatures()
            if not f.geometry().isEmpty()]

# --- rasterize subwatershed ids onto the flow-dir grid (one GEOS pass, not
# millions). ID[r,c] = subwatershed id, or -1 outside. Replaces the per-cell
# geom.contains() that made this O(cells x boundary-complexity). --------------
_mem = gdal.GetDriverByName("MEM").Create("", NX, NY, 1, gdal.GDT_Int32)
_mem.SetGeoTransform(gt); _mem.SetProjection(proj)
_mb = _mem.GetRasterBand(1); _mb.SetNoDataValue(-1); _mb.Fill(-1)
_ogr = ogr.Open(subws_path)
_olyr = _ogr.GetLayerByName(SUBWS_LAYER) if _ogr.GetLayerByName(SUBWS_LAYER) else _ogr.GetLayer(0)
gdal.RasterizeLayer(_mem, [1], _olyr, options=["ATTRIBUTE=id"])
ID = _mb.ReadAsArray()
_mem = None; _ogr = None
print("Rasterized subwatershed mask:", int((ID >= 0).sum()), "cells inside basins")

# --- precompute headwater cells: a cell is a headwater if NO in-mask neighbor
# drains INTO it. The longest path to an outlet always starts at a headwater,
# so we trace only from these (orders of magnitude fewer starts than all cells).
# Build "drains-into" by walking each cell's downstream neighbor and marking it.
has_upstream = np.zeros((NY, NX), dtype=bool)
for code, (dr, dc) in GRASS_OFF.items():
    # cells whose FD == code send flow to (r+dr, c+dc); mark those targets
    src = (np.abs(FD) == code)
    if not src.any():
        continue
    rs, cs = np.where(src)
    tr, tc = rs + dr, cs + dc
    valid = (tr >= 0) & (tr < NY) & (tc >= 0) & (tc < NX)
    has_upstream[tr[valid], tc[valid]] = True
IS_HEADWATER = ~has_upstream

# --- per-subwatershed longest flow path ------------------------------------
results = {}            # id -> dict of params
lines   = {}            # id -> list of (x,y) for the path line

_t_total = time.time()
_t_total_ref = [_t_total]     # mutable holders so _check_stop sees them
_t_sw_ref = [time.time()]
_timed_out_ids = []
_total_budget_hit = False

for sw in subws.getFeatures():
    sid = int(sw["id"])
    _t_sw_ref[0] = time.time()
    try:
        geom = sw.geometry()
        # outlet = the snapped pour point inside this subwatershed
        outlet = None
        for p in pour_pts:
            if geom.contains(QgsGeometry.fromPointXY(p)):
                outlet = p; break
        if outlet is None:                       # fallback: nearest pour point
            outlet = min(pour_pts, key=lambda p: geom.distance(QgsGeometry.fromPointXY(p)))
        o_r, o_c = to_rc(outlet.x(), outlet.y())

        in_sw = (ID == sid)
        # snap outlet to nearest in-mask cell if it landed just outside
        if not (0 <= o_r < NY and 0 <= o_c < NX) or not in_sw[o_r, o_c]:
            rs_, cs_ = np.where(in_sw)
            if len(rs_):
                k = int(np.argmin((rs_ - o_r) ** 2 + (cs_ - o_c) ** 2))
                o_r, o_c = int(rs_[k]), int(cs_[k])

        best_path, best_len = longest_path_to_outlet(in_sw, o_r, o_c)

    except _Timeout:
        print("  id %s: per-subwatershed time budget hit -> NULL, skipping." % sid)
        _timed_out_ids.append(sid)
        results[sid] = dict(flow_len_ft=None, elev_max_ft=None, elev_min_ft=None,
                            slope_lfp=None, slope_1085=None)
        continue
    except Exception as ex:
        print("  STOPPING:", ex)
        _total_budget_hit = True
        break

    except _Timeout:
        # this subwatershed took too long: record NULL, move on to the next.
        print("  id %s: per-subwatershed time budget hit -> NULL, skipping." % sid)
        _timed_out_ids.append(sid)
        results[sid] = dict(flow_len_ft=None, elev_max_ft=None, elev_min_ft=None,
                            slope_lfp=None, slope_1085=None)
        continue
    except Exception as ex:
        # total budget or STOP file: stop processing further subwatersheds but
        # keep what we have and fall through to writing outputs.
        print("  STOPPING:", ex)
        _total_budget_hit = True
        break

    if not best_path or best_len <= 0:
        results[sid] = dict(flow_len_ft=None, elev_max_ft=None, elev_min_ft=None,
                            slope_lfp=None, slope_1085=None)
        continue

    dd = cumdist(best_path)
    rs, cs = best_path[0]; re_, ce = best_path[-1]
    emax, emin = DEM[rs][cs], DEM[re_][ce]
    L_ft = best_len * M_TO_FT
    slp  = abs(emax - emin) / best_len if best_len else 0.0
    s1085 = slope_1085(best_path, dd)
    results[sid] = dict(
        flow_len_ft=round(L_ft, 1),
        elev_max_ft=round(emax * M_TO_FT, 1),
        elev_min_ft=round(emin * M_TO_FT, 1),
        slope_lfp=round(slp, 5),
        slope_1085=round(s1085, 5))
    lines[sid] = [to_xy(r, c) for (r, c) in best_path]
    print("  id %s: L=%.0f ft  slope_lfp=%.2f%%  s1085=%.2f%%" %
          (sid, L_ft, 100 * slp, 100 * s1085))

# --- write the flow-path line layer ----------------------------------------
if _total_budget_hit:
    print("\n*** Stopped early (total budget or STOP). Writing partial results. ***")
if _timed_out_ids:
    print("*** Subwatershed(s) skipped on per-sw timeout (NULL):", _timed_out_ids, "***")
    print("    Raise MAX_PER_SW_SEC, or check these for a routing/loop problem.")
flds = QgsFields(); flds.append(QgsField("id", QVariant.Int))
flds.append(QgsField("flow_len_ft", QVariant.Double))
if os.path.exists(lfp_path):
    os.remove(lfp_path)
opts = QgsVectorFileWriter.SaveVectorOptions()
opts.driverName = "GPKG"; opts.layerName = LFP_LAYER
w = QgsVectorFileWriter.create(lfp_path, flds, QgsWkbTypes.LineString,
                               subws.crs(), QgsCoordinateTransformContext(), opts)
for sid, pts in lines.items():
    f = QgsFeature(flds)
    f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in pts]))
    f["id"] = int(sid); f["flow_len_ft"] = results[sid]["flow_len_ft"]
    w.addFeature(f)
del w

# --- append columns to params gpkg in place --------------------------------
pl = QgsVectorLayer(params + "|layername=" + PARAMS_LAYER, PARAMS_LAYER, "ogr")
pl.startEditing()
newcols = ["flow_len_ft", "elev_max_ft", "elev_min_ft", "slope_lfp", "slope_1085"]
have = [f.name() for f in pl.fields()]
for col in newcols:
    if col not in have:
        pl.dataProvider().addAttributes([QgsField(col, QVariant.Double)])
pl.updateFields()
idx = {col: pl.fields().indexFromName(col) for col in newcols}
for ft in pl.getFeatures():
    res = results.get(int(ft["id"]) if not _null(ft["id"]) else None)
    if not res:
        continue
    for col in newcols:
        pl.changeAttributeValue(ft.id(), idx[col], res[col])
pl.commitChanges()

print("\nWrote %s and updated %s." % (LFP_NAME, PARAMS_NAME))
if ADD_TO_PROJECT:
    for path, lyr, nm in [(lfp_path, LFP_LAYER, LFP_LAYER),
                          (params, PARAMS_LAYER, PARAMS_LAYER)]:
        v = QgsVectorLayer(path + "|layername=" + lyr, nm, "ogr")
        if v.isValid():
            QgsProject.instance().addMapLayer(v)
print("\nDone.")
