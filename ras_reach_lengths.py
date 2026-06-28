#!/usr/bin/env python3
# =============================================================================
# ras_reach_lengths.py
#
# RAS geometry, step 3c: the downstream reach lengths (LOB / Channel / ROB)
# between adjacent cross sections.
#
# OPTION A (channel length for all three). The cross sections are placed at
# uniform spacing ALONG the channel centerline (Step 2a), so the channel reach
# length between any two adjacent sections is simply the difference of their
# river stations. For Option A the left-overbank and right-overbank lengths are
# set EQUAL to the channel length -- appropriate for a reach where overbank and
# channel travel nearly the same distance, and a clean first pass that can be
# refined later with offset flow paths (Option B) if the meander warrants it.
#
# RAS convention: each cross section stores the distance DOWNSTREAM to the next
# section. The most-downstream section has no downstream neighbor, so its three
# lengths are 0.
#
# INPUT   <SITE>/outputs_RAS/bank_stations.csv   (xs_id, river_sta_ft, note)
# OUTPUT  <SITE>/outputs_RAS/reach_lengths.csv
#           xs_id, river_sta_ft, len_lob_ft, len_channel_ft, len_rob_ft, note
#
# river_sta_ft increases UPSTREAM (RAS convention). The downstream length for a
# section is its station minus the next-lower station.
#
# Run: python3 ras_reach_lengths.py   (or exec in the QGIS Console)
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
OUT_CSV = os.path.join(OUT_DIR, "reach_lengths.csv")

# Option A: overbank lengths equal the channel length. If a future reach needs
# true offset flow paths, that is Option B (a separate, more involved step).
OVERBANK_EQUALS_CHANNEL = True
# ---------------------------------------------------------------------------


def main():
    if not os.path.isfile(IN_CSV):
        raise Exception("input not found: " + IN_CSV +
                         "\n(run ras_bank_stations.py first)")

    rows = list(csv.DictReader(open(IN_CSV)))
    # collect (xs_id, river_sta_ft, note), sorted by river station DESCENDING
    # (upstream-most first) so the "next downstream" is the following row.
    recs = []
    for r in rows:
        recs.append((int(r["xs_id"]), float(r["river_sta_ft"]), r.get("note", "")))
    recs.sort(key=lambda t: t[1], reverse=True)   # high station (upstream) first

    out_rows = []
    for i, (xi, rs, note) in enumerate(recs):
        # downstream neighbor is the next lower river station
        if i + 1 < len(recs):
            rs_dn = recs[i + 1][1]
            chan = rs - rs_dn                      # ft, channel reach length
        else:
            chan = 0.0                             # most-downstream section
        lob = chan if OVERBANK_EQUALS_CHANNEL else chan
        rob = chan if OVERBANK_EQUALS_CHANNEL else chan
        out_rows.append({
            "xs_id": xi,
            "river_sta_ft": round(rs, 3),
            "len_lob_ft": round(lob, 3),
            "len_channel_ft": round(chan, 3),
            "len_rob_ft": round(rob, 3),
            "note": note,
        })

    # write in river-station order (upstream-most first), matching RAS listing
    cols = ["xs_id", "river_sta_ft", "len_lob_ft", "len_channel_ft",
            "len_rob_ft", "note"]
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    # console summary
    chans = [r["len_channel_ft"] for r in out_rows if r["len_channel_ft"] > 0]
    print("reach lengths written:", OUT_CSV)
    print("  method: Option A (LOB = Channel = ROB)")
    print("  cross sections: %d  (%d reaches)" % (len(out_rows), len(chans)))
    if chans:
        mn, mx = min(chans), max(chans)
        avg = sum(chans) / len(chans)
        print("  channel reach length  min/mean/max = %.2f / %.2f / %.2f ft"
              % (mn, avg, mx))
        if abs(mx - mn) < 0.01:
            print("  (uniform spacing: every reach = %.2f ft = %.1f m)"
                  % (avg, avg / 3.280839895))
    dn = out_rows[-1]
    print("  most-downstream XS %d: lengths 0 (no downstream neighbor)"
          % dn["xs_id"])
    flagged = [r for r in out_rows if r["note"] not in ("ok", "interp", "")]
    if flagged:
        print("  NOTE -- non-standard sections (reach lengths may change when handled):")
        for r in flagged:
            print("    XS %-3s  note=%s" % (r["xs_id"], r["note"]))


main()
