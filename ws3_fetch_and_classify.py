#!/usr/bin/env python3
# =============================================================================
# WS3 study-layer downloader + site classifier  (ONE SCRIPT)
# =============================================================================
# The NHA federated server only accepts BROWSER SESSION auth (every token path
# returns 498/499). So this script authenticates with your browser's session
# cookie -- you paste it once below.
#
# It will:
#   1. Download each Hosted study layer as GeoJSON (lat/lon) into OUT_DIR,
#      paginating past the 2000-record cap automatically.
#   2. Classify all 17 WS3 sites against the local GeoJSON (no projection math --
#      everything is requested in EPSG:4326).
#   3. Write ws3_site_classification.csv into OUT_DIR.
#
# HOW TO GET THE COOKIE (Chrome, while logged in to nhagisportal.com):
#   F12 -> Application tab -> Storage -> Cookies -> https://nhagisportal.com
#   Copy the VALUE of the session cookie (often "agstoken" or ".AspNet..."; if
#   unsure, copy ALL cookies: in DevTools Console run:  document.cookie
#   and paste the whole string).
#
# Then paste it into COOKIE below and run:  python3 ws3_fetch_and_classify.py
# Dependencies: requests, shapely  (pip install requests shapely)
# =============================================================================

import os, json, csv, time

# ---- PASTE YOUR BROWSER COOKIE STRING HERE ----------------------------------
# Easiest: open DevTools Console on nhagisportal.com, run  document.cookie
# copy the whole output, paste between the quotes.
COOKIE = "PASTE_FULL_document.cookie_STRING_HERE"

OUT_DIR = "/home/arash/Dropbox/Chloeta/NHA/WS3_GIS/dwelling_unit_inventory"

# ---- Layers to download: name -> (service path, layer index) ----------------
LAYERS = {
    "floodplains":   ("Hosted/Floodplains",        7),
    "wsel":          ("Hosted/WSEL_HFS",            0),
    "study_streams": ("Hosted/Study_Streams_HFS",   0),
    "huc12":         ("Hosted/HUC12__HFS_",         0),
}
BASE = "https://nhagisportal.com/arcgis/rest/services"

WSEL_WINDOW_M   = 500
STREAM_WINDOW_M = 3000

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

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests shapely")
try:
    from shapely.geometry import shape, Point
    from shapely.ops import nearest_points
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False
    print("WARNING: shapely not installed -> distances/point-in-polygon limited. "
          "pip install shapely  for full results.")

import math
def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def session():
    s = requests.Session()
    s.headers.update({"Cookie": COOKIE,
                      "Referer": "https://nhagisportal.com/arcgis/rest/services",
                      "User-Agent": "Mozilla/5.0"})
    return s

def download_layer(s, name, svc_path, idx):
    """Download all features of a layer as GeoJSON, paginating past the cap."""
    url = f"{BASE}/{svc_path}/FeatureServer/{idx}/query"
    all_feats = []
    offset = 0
    page = 2000
    while True:
        params = {
            "where": "1=1", "outFields": "*", "outSR": "4326",
            "f": "geojson", "resultOffset": offset, "resultRecordCount": page,
            "returnGeometry": "true",
        }
        r = s.get(url, params=params, timeout=120)
        if r.status_code != 200:
            raise SystemExit(f"[{name}] HTTP {r.status_code}: {r.text[:200]}")
        try:
            gj = r.json()
        except Exception:
            raise SystemExit(f"[{name}] non-JSON response (auth/cookie issue?): {r.text[:200]}")
        if "error" in gj:
            raise SystemExit(f"[{name}] server error: {gj['error']}  "
                             f"(cookie likely expired -- refresh document.cookie)")
        feats = gj.get("features", [])
        all_feats.extend(feats)
        if len(feats) < page:
            break
        offset += page
        time.sleep(0.2)
    out = {"type": "FeatureCollection", "features": all_feats}
    path = os.path.join(OUT_DIR, f"{name}.geojson")
    with open(path, "w") as fh:
        json.dump(out, fh)
    print(f"  [{name}] {len(all_feats)} features -> {path}")
    return out

def load_geoms(gj):
    if not HAVE_SHAPELY: return []
    geoms = []
    for f in gj.get("features", []):
        g = f.get("geometry")
        if g:
            try: geoms.append((shape(g), f.get("properties", {})))
            except Exception: pass
    return geoms

def main():
    if "PASTE_FULL" in COOKIE:
        raise SystemExit("Set COOKIE first (run document.cookie in the browser console).")
    os.makedirs(OUT_DIR, exist_ok=True)
    s = session()

    print("Downloading study layers (browser-cookie auth)...")
    data = {}
    for name,(svc,idx) in LAYERS.items():
        data[name] = download_layer(s, name, svc, idx)

    fp_geoms     = load_geoms(data["floodplains"])
    wsel_geoms   = load_geoms(data["wsel"])
    stream_geoms = load_geoms(data["study_streams"])

    print("\nClassifying sites...")
    rows = []
    for pno, cluster, comm, lon, lat in SITES:
        pt = Point(lon, lat) if HAVE_SHAPELY else None
        in_fp, fp_attr, wsel_m, stream_m = False, "", "", ""

        if HAVE_SHAPELY:
            for geom, props in fp_geoms:
                if geom.contains(pt):
                    in_fp = True
                    keep = {k:v for k,v in props.items()
                            if any(t in k.lower() for t in
                                   ("zone","type","sfha","fld","class","detail","name"))}
                    fp_attr = "; ".join(f"{k}={v}" for k,v in keep.items() if v not in (None,""))
                    break
            # nearest wsel (deg -> approx m via haversine on nearest vertex)
            best=None
            for geom,_ in wsel_geoms:
                np1,_=nearest_points(geom, pt)
                d=haversine_m(lon,lat,np1.x,np1.y)
                if best is None or d<best: best=d
            if best is not None and best<=WSEL_WINDOW_M: wsel_m=round(best)
            # nearest study stream
            best=None
            for geom,_ in stream_geoms:
                np1,_=nearest_points(geom, pt)
                d=haversine_m(lon,lat,np1.x,np1.y)
                if best is None or d<best: best=d
            if best is not None and best<=STREAM_WINDOW_M: stream_m=round(best)

        if in_fp and wsel_m!="":
            prelim="Existing detailed floodplain data (WSE present) -- assessment + mitigation (3.8)"
        elif in_fp:
            prelim="In mapped floodplain, WSE not confirmed -- verify DFPS (3.6/3.7 may apply)"
        elif stream_m!="" and stream_m<=250:
            prelim="Adjacent to studied stream -- existing study likely usable; confirm"
        else:
            prelim="Outside study coverage -- full hydrology/hydraulics (3.5-3.7) likely required"

        rows.append([pno,cluster,comm,in_fp,fp_attr,wsel_m,stream_m,prelim])
        print(f"{pno:9s} {cluster:13s} in_fp={str(in_fp):5s} wsel={str(wsel_m):>6s} "
              f"stream={str(stream_m):>6s}  -> {prelim}")

    out = os.path.join(OUT_DIR, "ws3_site_classification.csv")
    with open(out,"w",newline="") as fh:
        w=csv.writer(fh)
        w.writerow(["project_no","cluster","community","in_floodplain",
                    "floodplain_attr","wsel_within_m","stream_within_m",
                    "prelim_classification"])
        w.writerows(rows)
    print(f"\nWrote {out}  ({len(rows)} sites)")

if __name__ == "__main__":
    main()
