# =============================================================================
# WS3 site -> floodplain distance  (RUN IN QGIS PYTHON CONSOLE)
# =============================================================================
# Reads two layers already loaded in the project:
#   - "ws3_site_locations"  (point layer, your 17 WS3 sites)
#   - "floodplains"         (polygon layer, NHA 1% floodplain)
# For each site computes the minimum distance (meters) to the nearest floodplain
# polygon. Distance 0 means the site is INSIDE a mapped floodplain.
#
# Writes: <OUT_DIR>/ws3_floodplain_distance.csv
#
# Distances are computed in a projected CRS (EPSG:26912, UTM 12N -- the CRS your
# AZ12-100 pipeline already uses) so the numbers are true meters.
# =============================================================================

import os, csv
from qgis.core import (
    QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsGeometry, QgsSpatialIndex, QgsFeatureRequest
)

OUT_DIR = "/home/arash/Dropbox/Chloeta/NHA/WS3_GIS"

SITE_LAYER_NAME = "ws3_site_locations"
FP_LAYER_NAME   = "floodplains"

# Field on the site layer holding the project number (auto-detected if blank)
SITE_ID_FIELD = ""   # e.g. "project_no"; leave "" to auto-detect

# Metric CRS for true-meter distances (UTM Zone 12N, NAD83) -- matches pipeline
METRIC_CRS = "EPSG:26912"
# -----------------------------------------------------------------------------

def get_layer(name):
    lyrs = QgsProject.instance().mapLayersByName(name)
    if not lyrs:
        raise SystemExit(f"Layer '{name}' not found in project. Check the name in the Layers panel.")
    return lyrs[0]

def main():
    sites = get_layer(SITE_LAYER_NAME)
    fp    = get_layer(FP_LAYER_NAME)
    ctx   = QgsProject.instance().transformContext()
    metric = QgsCoordinateReferenceSystem(METRIC_CRS)

    # transforms into the metric CRS
    t_site = QgsCoordinateTransform(sites.crs(), metric, ctx)
    t_fp   = QgsCoordinateTransform(fp.crs(),   metric, ctx)

    # auto-detect a sensible site id field
    sid = SITE_ID_FIELD
    if not sid:
        names = [f.name() for f in sites.fields()]
        for cand in ("project_no","Project_No","PROJECT_NO","site","Site",
                     "name","Name","NUMBER","id","ID"):
            if cand in names:
                sid = cand; break
    print(f"Site id field: {sid or '(using feature id)'}")

    # reproject + index all floodplain polygons into the metric CRS
    fp_geoms = {}
    idx = QgsSpatialIndex()
    fid = 0
    for feat in fp.getFeatures():
        g = QgsGeometry(feat.geometry())
        if g.isEmpty():
            continue
        g.transform(t_fp)
        fp_geoms[fid] = g
        ff = QgsFeatureRequest()  # build a lightweight feature for the index
        from qgis.core import QgsFeature
        nf = QgsFeature(fid)
        nf.setGeometry(g)
        idx.insertFeature(nf)
        fid += 1
    print(f"Floodplain polygons indexed: {len(fp_geoms)}")
    if not fp_geoms:
        raise SystemExit("No floodplain polygons found -- is the 'floodplains' layer the polygon layer?")

    rows = []
    for feat in sites.getFeatures():
        g = QgsGeometry(feat.geometry())
        g.transform(t_site)
        pt = g

        # nearest candidates via spatial index, then exact distance
        cand = idx.nearestNeighbor(pt.asPoint(), 5)
        best = None
        for cid in cand:
            d = pt.distance(fp_geoms[cid])
            if best is None or d < best:
                best = d
        # if index missed (rare), brute force
        if best is None:
            for cid, gg in fp_geoms.items():
                d = pt.distance(gg)
                if best is None or d < best: best = d

        inside = best is not None and best <= 0.5
        sval = feat[sid] if sid else feat.id()
        dist_m = round(best, 1) if best is not None else ""
        # readiness hint
        if inside:
            cls = "INSIDE mapped floodplain -- existing flood data likely usable (assessment/3.8 focus)"
        elif best is not None and best <= 100:
            cls = "Within 100 m of floodplain -- likely flood-affected; verify with WSEL/study"
        elif best is not None and best <= 500:
            cls = "Within 500 m -- check contributing drainage; may need full study"
        else:
            cls = "Far from mapped floodplain -- likely drainage/local-flooding problem, full hydrology if studied"

        rows.append([sval, dist_m, "YES" if inside else "NO", cls])
        print(f"{str(sval):12s} dist={str(dist_m):>9s} m  inside={'YES' if inside else 'NO '}  {cls}")

    out = os.path.join(OUT_DIR, "ws3_floodplain_distance.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["site","dist_to_floodplain_m","inside_floodplain","readiness_hint"])
        w.writerows(rows)
    print(f"\nWrote {out}  ({len(rows)} sites)")

main()
