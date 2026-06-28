# =============================================================================
# WS3 site -> study stream (+ WSEL) distance   (RUN IN QGIS PYTHON CONSOLE)
# =============================================================================
# Reads layers already loaded in the project:
#   - "ws3_site_locations"   (points)
#   - "study_streams"        (lines: NHA/AECOM studied streams)
#   - "WSEL_HFS"             (optional, points/lines: water surface elevations)
# Computes min distance (m) from each site to study streams, and to WSEL if loaded.
# Writes <OUT_DIR>/ws3_stream_wsel_distance.csv
# Distances in EPSG:26912 (UTM 12N) -> true meters.
# =============================================================================

import os, csv
from qgis.core import (
    QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsSpatialIndex, QgsFeature
)

OUT_DIR = "/home/arash/Dropbox/Chloeta/NHA/WS3_GIS"
SITE_LAYER = "ws3_site_locations"
STREAM_LAYER = "study_streams"
WSEL_LAYER = "WSEL_HFS"          # optional; script skips if not loaded
SITE_ID_FIELD = ""               # auto-detect if blank
METRIC = "EPSG:26912"
# -----------------------------------------------------------------------------

def lyr(name, required=True):
    found = QgsProject.instance().mapLayersByName(name)
    if not found:
        if required: raise SystemExit(f"Layer '{name}' not found.")
        return None
    return found[0]

def build_index(layer, metric, ctx):
    """Reproject all features to metric CRS, return (geoms dict, spatial index)."""
    tr = QgsCoordinateTransform(layer.crs(), metric, ctx)
    geoms = {}; idx = QgsSpatialIndex(); i = 0
    for feat in layer.getFeatures():
        g = QgsGeometry(feat.geometry())
        if g.isEmpty(): continue
        g.transform(tr)
        geoms[i] = g
        nf = QgsFeature(i); nf.setGeometry(g); idx.insertFeature(nf)
        i += 1
    return geoms, idx

def nearest_dist(pt, geoms, idx):
    if not geoms: return None
    cand = idx.nearestNeighbor(pt.asPoint(), 5)
    best = None
    for c in cand:
        d = pt.distance(geoms[c])
        if best is None or d < best: best = d
    if best is None:
        for g in geoms.values():
            d = pt.distance(g)
            if best is None or d < best: best = d
    return best

def main():
    sites = lyr(SITE_LAYER)
    streams = lyr(STREAM_LAYER)
    wsel = lyr(WSEL_LAYER, required=False)
    ctx = QgsProject.instance().transformContext()
    metric = QgsCoordinateReferenceSystem(METRIC)

    sid = SITE_ID_FIELD
    if not sid:
        names = [f.name() for f in sites.fields()]
        for c in ("project_no","Project_No","PROJECT_NO","site","Site","name","Name","id","ID"):
            if c in names: sid = c; break
    print(f"Site id field: {sid or '(feature id)'}")

    sg, si = build_index(streams, metric, ctx)
    print(f"Study-stream features indexed: {len(sg)}")
    wg = wi = None
    if wsel is not None:
        wg, wi = build_index(wsel, metric, ctx)
        print(f"WSEL features indexed: {len(wg)}")
    else:
        print("WSEL_HFS not loaded -- skipping WSEL column.")

    t_site = QgsCoordinateTransform(sites.crs(), metric, ctx)
    rows = []
    for feat in sites.getFeatures():
        g = QgsGeometry(feat.geometry()); g.transform(t_site)
        ds = nearest_dist(g, sg, si)
        dw = nearest_dist(g, wg, wi) if wg else None
        sval = feat[sid] if sid else feat.id()
        ds_r = round(ds,1) if ds is not None else ""
        dw_r = round(dw,1) if dw is not None else ""
        rows.append([sval, ds_r, dw_r])
        line = f"{str(sval):12s} stream={str(ds_r):>9s} m"
        if wg: line += f"  wsel={str(dw_r):>9s} m"
        print(line)

    out = os.path.join(OUT_DIR, "ws3_stream_wsel_distance.csv")
    with open(out,"w",newline="") as fh:
        w = csv.writer(fh)
        hdr = ["site","dist_to_study_stream_m"]
        if wg: hdr.append("dist_to_wsel_m")
        else:  hdr.append("dist_to_wsel_m")  # keep column for merge consistency
        w.writerow(hdr)
        w.writerows(rows)
    print(f"\nWrote {out}  ({len(rows)} sites)")

main()
