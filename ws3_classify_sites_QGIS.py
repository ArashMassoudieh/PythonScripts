# =============================================================================
# WS3 first-pass site classification  --  RUN IN QGIS PYTHON CONSOLE
# =============================================================================
# Uses QGIS's authenticated connection to nhagisportal.com (no tokens/cookies).
# For each WS3 site it reports:
#   in_floodplain    : site point falls inside a Floodplain Boundaries polygon
#   floodplain_attr  : attributes of that polygon (detailed vs normal 1% area)
#   wsel_within_m    : nearest WSEL feature distance (m), or blank if none in window
#   stream_within_m  : nearest Study Stream distance (m)
#   prelim_class     : suggested first-pass classification (confirm by eye)
#
# Writes: <OUT_DIR>/ws3_site_classification.csv
#
# PREREQ: you are signed in to the NHA portal in QGIS (Browser panel shows the
#         ArcGIS REST / portal connection). pyproj ships with QGIS.
# =============================================================================

import os, csv, math
from qgis.core import (
    QgsVectorLayer, QgsPointXY, QgsGeometry, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsProject, QgsFeatureRequest, QgsRectangle
)

# ---- EDIT THIS: where to write the CSV --------------------------------------
OUT_DIR = r"C:/Users/smnfa/Dropbox/NHA"          # Windows (Samaneh)
# OUT_DIR = "/home/arash/Dropbox/Chloeta/NHA"    # Linux (Arash)

# ---- Service endpoints (FeatureServer roots) --------------------------------
# The script auto-detects the correct sublayer index from each service.
SERVICES = {
    "floodplains":  "https://nhagisportal.com/arcgis/rest/services/Hosted/Floodplains/FeatureServer",
    "wsel":         "https://nhagisportal.com/arcgis/rest/services/Hosted/WSEL_HFS/FeatureServer",
    "streams":      "https://nhagisportal.com/arcgis/rest/services/Hosted/Study_Streams_HFS/FeatureServer",
}

WSEL_WINDOW_M   = 500      # search radius for "WSE available near site"
STREAM_WINDOW_M = 3000     # search radius for nearest studied stream

# ---- WS3 sites: (project_no, cluster, community, lon, lat) -------------------
SITES = [
    ("AZ12-100","Cottonwood","Cottonwood, AZ",          -109.886679,36.071809),
    ("AZ12-116","Cottonwood","Cottonwood, AZ",          -109.887587,36.071129),
    ("NM15-032","Ojo Amarillo","Ojo Amarillo Modern, NM",-108.362408,36.688684),
    ("NM15-134","Tohajiilee","Tohajiilee, NM",          -106.984414,35.062596),
    ("NM15-135","Tohajiilee","Tohajiilee, NM",          -106.984427,35.066195),
    ("AZ12-113","Kayenta","Kayenta, AZ",                -110.248893,36.716346),
    ("AZ12-073","Kayenta","Kayenta, AZ",                -110.245901,36.718322),
    ("AZ12-139","Tuba City","Tuba City, AZ",            -111.225696,36.144348),
    ("AZ12-140","Tuba City","Tuba City, AZ",            -111.225907,36.144194),
    ("AZ12-301","Chilchinbeto","Chilchinbeto, AZ",      -110.072810,36.520900),
    ("NM15-141","Coyote Canyon","Coyote Canyon, NM",    -108.659735,35.763019),
    ("NM15-097","Coyote Canyon","Coyote Canyon, NM",    -108.711744,35.763423),
    ("AZ12-069","Chinle","Chinle, AZ (65PR)",           -109.580046,36.164693),
    ("AZ12-086","Chinle","Chinle, AZ (50PR)",           -109.577450,36.163753),
    ("AZ12-087","Chinle","Chinle, AZ (50PR)",           -109.576739,36.161633),
    ("AZ12-080","Many Farms","Many Farms, AZ (16PR)",   -109.621368,36.356417),
    ("AZ12-186","Many Farms","Chinle, AZ (4PR)",        -109.620892,36.355878),
]

# NHA Stereographic Double (from the FeatureServer WKT)
NHA_WKT = (
 'PROJCS["NHA Stereographic Double",GEOGCS["GCS_North_American_1983",'
 'DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],'
 'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
 'PROJECTION["Double_Stereographic"],PARAMETER["False_Easting",1500000.0],'
 'PARAMETER["False_Northing",500000.0],PARAMETER["Central_Meridian",-109.5],'
 'PARAMETER["Scale_Factor",1.0002],PARAMETER["Latitude_Of_Origin",36.25],'
 'UNIT["Meter",1.0]]'
)

# -----------------------------------------------------------------------------
def load_service_layer(name, fs_url):
    """Load the first queryable Feature Layer sublayer of a FeatureServer."""
    # QGIS ArcGIS REST provider: type=arcgisfeatureserver, url=<sublayer url>
    # Try to discover sublayer ids by probing common indices + known ones.
    candidate_ids = list(range(0, 12))
    for lid in candidate_ids:
        url = f"{fs_url}/{lid}"
        uri = f"crs='EPSG:4326' url='{url}'"
        lyr = QgsVectorLayer(uri, f"{name}_{lid}", "arcgisfeatureserver")
        if lyr.isValid() and lyr.featureCount() != 0:
            print(f"  [{name}] using sublayer {lid}: {lyr.name()}  "
                  f"({lyr.featureCount()} features, crs={lyr.crs().authid() or lyr.crs().description()})")
            return lyr
    print(f"  [{name}] WARNING: no valid sublayer found under {fs_url}")
    return None

def main():
    # CRS + transforms
    crs_wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    crs_nha = QgsCoordinateReferenceSystem.fromWkt(NHA_WKT)
    if not crs_nha.isValid():
        print("ERROR: could not build NHA CRS from WKT"); return
    tr_ctx = QgsProject.instance().transformContext()
    to_nha = QgsCoordinateTransform(crs_wgs, crs_nha, tr_ctx)

    print("Loading services (using your QGIS portal authentication)...")
    layers = {k: load_service_layer(k, u) for k, u in SERVICES.items()}
    fp = layers.get("floodplains")
    wsel = layers.get("wsel")
    streams = layers.get("streams")
    if fp is None:
        print("ERROR: Floodplains layer failed to load. Are you signed in to the "
              "NHA portal in QGIS? Try adding the layer manually from the Browser "
              "panel first, then re-run."); return

    # Determine each layer's CRS for distance math (they're in NHA meters)
    def layer_crs_tr(lyr):
        return QgsCoordinateTransform(crs_wgs, lyr.crs(), tr_ctx)

    rows = []
    for pno, cluster, comm, lon, lat in SITES:
        pt_wgs = QgsPointXY(lon, lat)

        # --- in floodplain? (point-in-polygon) ---
        in_fp, fp_attr = False, ""
        tr_fp = layer_crs_tr(fp)
        p_fp = tr_fp.transform(pt_wgs)
        g_fp = QgsGeometry.fromPointXY(p_fp)
        req = QgsFeatureRequest().setFilterRect(
            QgsRectangle(p_fp.x()-1, p_fp.y()-1, p_fp.x()+1, p_fp.y()+1))
        for feat in fp.getFeatures(req):
            if feat.geometry().contains(g_fp):
                in_fp = True
                a = feat.attributes()
                names = [f.name() for f in fp.fields()]
                keep = {n: v for n, v in zip(names, a)
                        if any(s in n.lower() for s in
                               ("zone","type","sfha","fld","class","detail","name"))}
                fp_attr = "; ".join(f"{n}={v}" for n, v in keep.items() if v not in (None,""))
                break

        # --- nearest WSEL within window ---
        wsel_m = ""
        if wsel is not None:
            tr = layer_crs_tr(wsel); p = tr.transform(pt_wgs)
            rect = QgsRectangle(p.x()-WSEL_WINDOW_M, p.y()-WSEL_WINDOW_M,
                                p.x()+WSEL_WINDOW_M, p.y()+WSEL_WINDOW_M)
            gp = QgsGeometry.fromPointXY(p); best=None
            for feat in wsel.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
                d = feat.geometry().distance(gp)
                if best is None or d < best: best = d
            if best is not None: wsel_m = round(best)

        # --- nearest study stream within window ---
        stream_m = ""
        if streams is not None:
            tr = layer_crs_tr(streams); p = tr.transform(pt_wgs)
            rect = QgsRectangle(p.x()-STREAM_WINDOW_M, p.y()-STREAM_WINDOW_M,
                                p.x()+STREAM_WINDOW_M, p.y()+STREAM_WINDOW_M)
            gp = QgsGeometry.fromPointXY(p); best=None
            for feat in streams.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
                d = feat.geometry().distance(gp)
                if best is None or d < best: best = d
            if best is not None: stream_m = round(best)

        # --- preliminary classification ---
        if in_fp and wsel_m != "":
            prelim = "Existing detailed floodplain data (WSE present) -- assessment + mitigation focus (3.8)"
        elif in_fp:
            prelim = "In mapped floodplain, WSE not confirmed -- verify DFPS (3.6/3.7 may apply)"
        elif stream_m != "" and stream_m <= 250:
            prelim = "Adjacent to studied stream -- existing study likely usable; confirm"
        else:
            prelim = "Outside study coverage -- full hydrology/hydraulics (3.5-3.7) likely required"

        rows.append([pno, cluster, comm, in_fp, fp_attr, wsel_m, stream_m, prelim])
        print(f"{pno:9s} {cluster:13s} in_fp={str(in_fp):5s} wsel={str(wsel_m):>6s} "
              f"stream={str(stream_m):>6s}  -> {prelim}")

    out = os.path.join(OUT_DIR, "ws3_site_classification.csv")
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["project_no","cluster","community","in_floodplain",
                    "floodplain_attr","wsel_within_m","stream_within_m",
                    "prelim_classification"])
        w.writerows(rows)
    print(f"\nWrote {out}  ({len(rows)} sites)")

main()
