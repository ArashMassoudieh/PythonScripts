#!/usr/bin/env python3
"""
WS3 endpoint probe — run BEFORE trusting the classifier.

Discovers, for each candidate layer:
  - whether the FeatureServer/sublayer exists and responds
  - its true spatialReference (wkid) and extent
  - total feature count
  - field names
  - one sample feature's attributes

This tells us why the classifier returned all-False (almost certainly a
spatial-reference mismatch: the NHA layers use a custom "NHA Stereographic
Double" projection, not lat/lon).

Run:  NHA_TOKEN='...' python3 ws3_probe.py
"""

import json, os, ssl, urllib.request, urllib.parse

TOKEN = os.environ.get("NHA_TOKEN", "PASTE_TOKEN")
BASE = "https://nhagisportal.com/arcgis/rest/services/Hosted"

# Try the FeatureServer root (metadata) and sublayers 0..3 for each service
SERVICES = {
    "Floodplains":   f"{BASE}/Floodplains/FeatureServer",
    "Study_Streams": f"{BASE}/Study_Streams_HFS/FeatureServer",
    "WSEL":          f"{BASE}/WSEL_HFS/FeatureServer",
    "HUC12":         f"{BASE}/HUC12__HFS_/FeatureServer",
}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def get(url, params=None):
    params = dict(params or {})
    params.setdefault("f", "json")
    params["token"] = TOKEN
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full, context=_ctx, timeout=60) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_http_error": str(e)}


def probe_service(name, url):
    print(f"\n===== {name}  {url} =====")
    meta = get(url)
    if "_http_error" in meta:
        print("  service metadata error:", meta["_http_error"]); return
    if "error" in meta:
        print("  service error:", meta["error"]); return
    layers = meta.get("layers", [])
    print("  sublayers:", [(l.get("id"), l.get("name")) for l in layers] or "none listed")
    # probe each sublayer 0..3
    for idx in range(max(4, len(layers))):
        q = get(f"{url}/{idx}/query", {
            "where": "1=1",
            "returnCountOnly": "true",
        })
        if "error" in q:
            continue
        cnt = q.get("count")
        if cnt is None:
            continue
        # get one sample feature + SR
        samp = get(f"{url}/{idx}/query", {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "resultRecordCount": "1",
        })
        sr = samp.get("spatialReference", {})
        feats = samp.get("features", [])
        fields = [f.get("name") for f in samp.get("fields", [])]
        print(f"  /{idx}/  count={cnt}  SR={sr}")
        print(f"        fields: {fields}")
        if feats:
            g = feats[0].get("geometry", {})
            gkeys = list(g.keys())
            # show a coord sample to reveal coordinate magnitude (deg vs projected)
            sample_xy = None
            if "x" in g: sample_xy = (g["x"], g["y"])
            elif "paths" in g and g["paths"]: sample_xy = g["paths"][0][0]
            elif "rings" in g and g["rings"]: sample_xy = g["rings"][0][0]
            print(f"        geom keys={gkeys}  sample_xy={sample_xy}")


def main():
    if "PASTE_TOKEN" in TOKEN:
        raise SystemExit("Set NHA_TOKEN env var first.")
    for name, url in SERVICES.items():
        probe_service(name, url)
    print("\nDone. Paste this whole output back.")


if __name__ == "__main__":
    main()
