#!/usr/bin/env python3
"""
WS3 first-pass site classification helper.

Queries each WS3 site coordinate against the NHA/AECOM floodplain study layers
on nhagisportal.com and writes a CSV you can drop straight into the first-pass
classification table.

For each site it reports:
  - in_floodplain : does the site point fall inside a mapped 1% floodplain polygon?
  - floodplain_type : the SFHA/flood-zone attribute(s) found (detailed vs normal)
  - wsel_nearby : is there a Water Surface Elevation feature within BUFFER_M?
  - study_stream_m : distance (m) to the nearest studied stream (AECOM study)
  - prelim_class : a suggested first-pass classification you then confirm by eye

RUN IT ON YOUR MACHINE (Linux or QGIS Python), not in the cloud — the portal
layers require your org token and are not reachable from the sandbox.

USAGE:
  1) Generate a fresh token:
     https://nhagisportal.com/portal/sharing/rest/generateToken
     (Client = "IP Address of this request's origin", expiration 1 day)
  2) Paste it into TOKEN below (or set env var NHA_TOKEN).
  3) python3 ws3_classify_sites.py
  4) Open ws3_site_classification.csv

Dependencies: only the Python standard library. (Works in QGIS Python too.)
"""

import json
import os
import ssl
import csv
import math
import urllib.request
import urllib.parse

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
TOKEN = os.environ.get("NHA_TOKEN", "PASTE_YOUR_FRESH_TOKEN_HERE")

BASE = "https://nhagisportal.com/arcgis/rest/services/Hosted"
LAYERS = {
    "floodplains":   f"{BASE}/Floodplains/FeatureServer/0/query",
    "study_streams": f"{BASE}/Study_Streams_HFS/FeatureServer/0/query",
    "wsel":          f"{BASE}/WSEL_HFS/FeatureServer/0/query",
}

# Buffer for "nearby" WSEL points and for the stream-distance search window (meters)
BUFFER_M = 500
# Larger window used only to measure distance to nearest study stream (meters)
STREAM_SEARCH_M = 3000

# WS3 sites: (project_no, community, lon, lat)
SITES = [
    ("AZ12-100", "Cottonwood, AZ",            -109.886679, 36.071809),
    ("AZ12-116", "Cottonwood, AZ",            -109.887587, 36.071129),
    ("NM15-032", "Ojo Amarillo Modern, NM",   -108.362408, 36.688684),
    ("NM15-134", "Tohajiilee, NM",            -106.984414, 35.062596),
    ("NM15-135", "Tohajiilee, NM",            -106.984427, 35.066195),
    ("AZ12-113", "Kayenta, AZ",               -110.248893, 36.716346),
    ("AZ12-073", "Kayenta, AZ",               -110.245901, 36.718322),
    ("AZ12-139", "Tuba City, AZ",             -111.225696, 36.144348),
    ("AZ12-140", "Tuba City, AZ",             -111.225907, 36.144194),
    ("AZ12-301", "Chilchinbeto, AZ",          -110.072810, 36.520900),
    ("NM15-141", "Coyote Canyon, NM",         -108.659735, 35.763019),
    ("NM15-097", "Coyote Canyon, NM",         -108.711744, 35.763423),
    ("AZ12-069", "Chinle, AZ (65PR)",         -109.580046, 36.164693),
    ("AZ12-086", "Chinle, AZ (50PR)",         -109.577450, 36.163753),
    ("AZ12-087", "Chinle, AZ (50PR)",         -109.576739, 36.161633),
    ("AZ12-080", "Many Farms, AZ (16PR)",     -109.621368, 36.356417),
    ("AZ12-186", "Chinle, AZ (4PR)",          -109.620892, 36.355878),
]

# Cluster assignment (provisional — refine against HUC12 HFS / delineation)
CLUSTER = {
    "AZ12-100": "Cottonwood", "AZ12-116": "Cottonwood",
    "NM15-134": "Tohajiilee", "NM15-135": "Tohajiilee",
    "AZ12-113": "Kayenta", "AZ12-073": "Kayenta",
    "NM15-032": "Ojo Amarillo",
    "AZ12-139": "Tuba City", "AZ12-140": "Tuba City",
    "AZ12-301": "Chilchinbeto",
    "NM15-141": "Coyote Canyon", "NM15-097": "Coyote Canyon",
    "AZ12-069": "Chinle", "AZ12-086": "Chinle", "AZ12-087": "Chinle",
    "AZ12-080": "Many Farms", "AZ12-186": "Many Farms",
}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _post(url, params):
    params = dict(params)
    params.setdefault("f", "json")
    params["token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, context=_ctx, timeout=60) as r:
        return json.loads(r.read().decode())


def _haversine(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def point_geom(lon, lat):
    return json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}})


def envelope(lon, lat, half_m):
    # approximate deg per meter
    dlat = half_m / 111320.0
    dlon = half_m / (111320.0 * math.cos(math.radians(lat)))
    return json.dumps({
        "xmin": lon - dlon, "ymin": lat - dlat,
        "xmax": lon + dlon, "ymax": lat + dlat,
        "spatialReference": {"wkid": 4326},
    })


def query_in_floodplain(lon, lat):
    res = _post(LAYERS["floodplains"], {
        "geometry": point_geom(lon, lat),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
    })
    feats = res.get("features", [])
    if not feats:
        return False, ""
    # try to surface a meaningful zone/type attribute
    attrs = feats[0].get("attributes", {})
    type_keys = [k for k in attrs if any(s in k.lower()
                 for s in ("zone", "type", "sfha", "fld", "class", "detail"))]
    label = "; ".join(f"{k}={attrs[k]}" for k in type_keys if attrs[k] not in (None, "", " "))
    return True, label or "polygon present"


def query_wsel_nearby(lon, lat):
    res = _post(LAYERS["wsel"], {
        "geometry": envelope(lon, lat, BUFFER_M),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnCountOnly": "true",
    })
    return res.get("count", 0) > 0


def query_nearest_stream_m(lon, lat):
    res = _post(LAYERS["study_streams"], {
        "geometry": envelope(lon, lat, STREAM_SEARCH_M),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
    })
    feats = res.get("features", [])
    best = None
    for f in feats:
        g = f.get("geometry", {})
        for path in g.get("paths", []):
            for x, y in path:
                d = _haversine(lon, lat, x, y)
                if best is None or d < best:
                    best = d
    return round(best) if best is not None else None


def classify(in_fp, wsel, stream_m):
    if in_fp and wsel:
        return "Drainage/flooding assessment using existing detailed floodplain data (likely 3.8 focus)"
    if in_fp and not wsel:
        return "In mapped floodplain, WSE not confirmed -- verify DFPS coverage (3.6/3.7 may be needed)"
    if stream_m is not None and stream_m <= 250:
        return "Adjacent to studied stream -- existing study likely usable; confirm extent"
    return "Outside study coverage -- likely full hydrology/hydraulics (3.5-3.7) required"


def main():
    if "PASTE_YOUR_FRESH_TOKEN" in TOKEN:
        raise SystemExit("Set your token: edit TOKEN or run with NHA_TOKEN=... env var")
    rows = []
    for pno, comm, lon, lat in SITES:
        try:
            in_fp, fp_type = query_in_floodplain(lon, lat)
            wsel = query_wsel_nearby(lon, lat)
            stream_m = query_nearest_stream_m(lon, lat)
            prelim = classify(in_fp, wsel, stream_m)
        except Exception as e:
            in_fp, fp_type, wsel, stream_m, prelim = "ERR", str(e), "ERR", "ERR", "query failed"
        rows.append({
            "project_no": pno,
            "cluster": CLUSTER.get(pno, ""),
            "community": comm,
            "in_floodplain": in_fp,
            "floodplain_type": fp_type,
            "wsel_nearby": wsel,
            "nearest_study_stream_m": stream_m,
            "prelim_classification": prelim,
        })
        print(f"{pno:9s} {CLUSTER.get(pno,''):13s} in_fp={in_fp!s:5} wsel={wsel!s:5} "
              f"stream={stream_m!s:>6} m  -> {prelim}")

    out = "ws3_site_classification.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out} ({len(rows)} sites)")


if __name__ == "__main__":
    main()
