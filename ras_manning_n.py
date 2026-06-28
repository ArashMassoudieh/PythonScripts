#!/usr/bin/env python3
# =============================================================================
# ras_manning_n.py
#
# RAS geometry, step 3b: assign Manning's n to each cross section as the three
# standard values -- left overbank (LOB), main channel, right overbank (ROB) --
# keyed to the bank stations from ras_bank_stations.py.
#
# ROUGHNESS BASIS (documented constants -- defensible for the sealed record):
#   * Channel  n = N_CHANNEL  (incised ephemeral sand/gravel wash)
#   * Overbank n = N_OVERBANK (uniform NLCD class 52, Shrub/Scrub, watershed-wide)
#
# The NLCD clip for this watershed is a SINGLE land-cover class (52 Shrub/Scrub)
# everywhere, so a per-section land-cover sample would assign the same overbank
# n to every section. A documented constant is therefore both simpler and more
# transparent than spatially sampling a uniform raster. This uniformity is
# itself a recorded finding: land-cover variation does not drive roughness here;
# soil (HSG) and channel geometry do.
#
# n-values are the HEC-RAS horizontal n breakpoints at the bank stations: n
# applies from the left end to bank_l (LOB), bank_l to bank_r (channel), and
# bank_r to the right end (ROB).
#
# INPUT   <SITE>/outputs_RAS/bank_stations.csv   (xs_id, bank_l_offset_m, ...)
# OUTPUT  <SITE>/outputs_RAS/manning_n.csv
#           xs_id, river_sta_ft,
#           n_lob, n_channel, n_rob,
#           bank_l_offset_m, bank_r_offset_m, note
#
# Cross sections flagged note != ok/interp in bank_stations.csv (e.g. the road/
# culvert section) are written with the same constants but note carried through,
# so they are easy to find and override when the structure is handled.
#
# Run: python3 ras_manning_n.py   (or exec in the QGIS Console)
# =============================================================================
import os
import csv

# --- root / paths (match the rest of the RAS pipeline) ---------------------
try:
    ROOT
except NameError:
    ROOT = "/home/arash/Dropbox/Chloeta/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

OUT_DIR = os.path.join(ROOT, SITE_DIR, "outputs_RAS")
IN_CSV  = os.path.join(OUT_DIR, "bank_stations.csv")
OUT_CSV = os.path.join(OUT_DIR, "manning_n.csv")

# --- Manning's n constants (tune here; these are the sealed-record values) --
N_CHANNEL  = 0.035    # incised ephemeral sand/gravel wash (Chow/USGS)
N_OVERBANK = 0.045    # NLCD 52 Shrub/Scrub, uniform across the watershed
# A note string recorded in the memo / geometry header for provenance:
N_BASIS = ("channel 0.035 (ephemeral sand/gravel wash); overbank 0.045 "
           "(NLCD class 52 Shrub/Scrub, uniform watershed-wide)")
# ---------------------------------------------------------------------------


def main():
    if not os.path.isfile(IN_CSV):
        raise Exception("input not found: " + IN_CSV + "\n(run ras_bank_stations.py first)")

    rows = list(csv.DictReader(open(IN_CSV)))
    out_rows = []
    for r in rows:
        xi = r["xs_id"]
        rs = r.get("river_sta_ft", "")
        note = r.get("note", "")
        bl = r.get("bank_l_offset_m", "")
        br = r.get("bank_r_offset_m", "")
        out_rows.append({
            "xs_id": xi, "river_sta_ft": rs,
            "n_lob": "%.3f" % N_OVERBANK,
            "n_channel": "%.3f" % N_CHANNEL,
            "n_rob": "%.3f" % N_OVERBANK,
            "bank_l_offset_m": bl, "bank_r_offset_m": br,
            "note": note,
        })

    cols = ["xs_id", "river_sta_ft", "n_lob", "n_channel", "n_rob",
            "bank_l_offset_m", "bank_r_offset_m", "note"]
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    # console summary
    print("Manning's n written:", OUT_CSV)
    print("  basis:", N_BASIS)
    print("  cross sections: %d" % len(out_rows))
    print("  n_lob / n_channel / n_rob = %.3f / %.3f / %.3f  (all sections)"
          % (N_OVERBANK, N_CHANNEL, N_OVERBANK))
    # flag any non-ok sections so the road/culvert XS is visible here too
    flagged = [r for r in out_rows if r["note"] not in ("ok", "interp", "")]
    if flagged:
        print("  NOTE -- non-standard sections (override when handled):")
        for r in flagged:
            print("    XS %-3s  note=%s" % (r["xs_id"], r["note"]))


main()
