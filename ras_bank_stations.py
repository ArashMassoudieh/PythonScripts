#!/usr/bin/env python3
# =============================================================================
# ras_bank_stations.py
#
# RAS geometry, step 3a: detect LEFT and RIGHT bank stations for each cross
# section from the recentered station-elevation profiles. The thalweg sits at
# offset ~0 (recentering already done); banks are found by walking OUTWARD from
# the thalweg on each side and placing the bank at the channel-wall -> floodplain
# transition.
#
# METHOD (slope-break hybrid with a height cap):
#   Walk outward from the thalweg. Track the running rise above the thalweg.
#   A bank is placed at the first offset where BOTH:
#     (a) the ground has risen at least MIN_BANK_RISE_M above the thalweg
#         (so we clear the channel bed and are genuinely on the wall), AND
#     (b) the local cross-slope has dropped below SLOPE_BREAK (the wall has
#         rolled over toward the flatter floodplain),
#   OR, failing a clean slope-break, at the offset where the rise first reaches
#   HEIGHT_CAP_M (so a bank is never pushed indefinitely up a continuous wall).
#   Whichever condition triggers first (going outward) sets the bank.
#
# This keeps each bank on an identifiable terrain feature (defensible for the
# sealed record) while the height cap prevents a runaway placement on a tall
# continuous wall or a distant terrace.
#
# INPUT   <SITE>/outputs_RAS/xs_profiles_recentered.csv
#         cols: xs_id, station_m, river_sta_ft, offset_m, x, y, elev_m, status
# OUTPUT  <SITE>/outputs_RAS/bank_stations.csv
#           xs_id, river_sta_ft, thalweg_offset_m,
#           bank_l_offset_m, bank_r_offset_m,
#           bank_l_elev_m, bank_r_elev_m, channel_width_m, method_l, method_r, note
#         <SITE>/outputs_RAS/xs_banks.gp.dat   (gnuplot: profile + bank markers)
#
# Non-'ok' profile points are skipped. A cross section with no usable points
# (e.g. the confluence XS) is written with empty banks and note='no_data'.
#
# Run: python3 ras_bank_stations.py
# =============================================================================
import os
import csv
import collections

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
IN_CSV  = os.path.join(OUT_DIR, "xs_profiles_recentered.csv")
OUT_CSV = os.path.join(OUT_DIR, "bank_stations.csv")

# --- detection parameters (tune on AZ12-100, then lock for the template) ----
MIN_BANK_RISE_M = 0.6    # must clear at least this much above thalweg first
SLOPE_BREAK     = 0.08   # m/m; wall considered "rolled over" below this local slope
HEIGHT_CAP_M    = 3.0    # hard cap: bank no higher than this above thalweg
SLOPE_WIN_M     = 3.0    # window (m) over which local cross-slope is measured
SMOOTH_WIN_M    = 2.0    # +/- smoothing half-window (m) applied to elevations
OFFCENTER_TOL_M = 10.0   # flag a XS as suspect if its thalweg is > this from center
# ---------------------------------------------------------------------------


def load_profiles(path):
    rows = list(csv.DictReader(open(path)))
    byxs = collections.defaultdict(list)
    rsta = {}
    for r in rows:
        if r.get("status") not in ("ok", "interp"):
            continue
        xi = int(r["xs_id"])
        byxs[xi].append((float(r["offset_m"]), float(r["elev_m"])))
        rsta.setdefault(xi, float(r["river_sta_ft"]))
    for xi in byxs:
        byxs[xi].sort()
    # also capture every xs_id seen (even all-bad ones) so we can emit no_data
    all_ids = sorted({int(r["xs_id"]) for r in rows})
    rsta_all = {}
    for r in rows:
        rsta_all.setdefault(int(r["xs_id"]), float(r["river_sta_ft"]))
    return byxs, rsta_all, all_ids


def smooth(pts, half_m):
    """Box-smooth elevations over +/- half_m in offset units (1 m spacing)."""
    if half_m <= 0 or len(pts) < 3:
        return pts
    offs = [p[0] for p in pts]
    els  = [p[1] for p in pts]
    out = []
    n = len(pts)
    for i in range(n):
        o0 = offs[i] - half_m
        o1 = offs[i] + half_m
        lo = i
        while lo > 0 and offs[lo - 1] >= o0:
            lo -= 1
        hi = i
        while hi < n - 1 and offs[hi + 1] <= o1:
            hi += 1
        out.append((offs[i], sum(els[lo:hi + 1]) / (hi - lo + 1)))
    return out


def thalweg_index(pts):
    return min(range(len(pts)), key=lambda k: pts[k][1])


def find_bank(pts, t_idx, direction):
    """Walk outward from thalweg (direction -1 = left, +1 = right).
    Returns (offset, elev, method)."""
    n = len(pts)
    t_off, t_el = pts[t_idx]
    step = 1
    i = t_idx
    cap_hit = None
    while True:
        i += direction * step
        if i < 0 or i >= n:
            # ran off the end -> use the last valid point as the bank
            j = max(0, min(n - 1, i - direction * step))
            return pts[j][0], pts[j][1], "edge"
        off, el = pts[i]
        rise = el - t_el
        # remember where we first reach the height cap, as a fallback
        if cap_hit is None and rise >= HEIGHT_CAP_M:
            cap_hit = (off, el)
        # local slope over SLOPE_WIN_M, measured outward
        k = i
        target = off + direction * SLOPE_WIN_M
        while 0 <= k + direction < n and \
                ((direction > 0 and pts[k + direction][0] <= target) or
                 (direction < 0 and pts[k + direction][0] >= target)):
            k += direction
        d_off = abs(pts[k][0] - off)
        d_el  = pts[k][1] - el
        local_slope = (d_el / d_off) if d_off > 0 else 0.0
        # slope-break: risen enough AND wall has flattened
        if rise >= MIN_BANK_RISE_M and local_slope < SLOPE_BREAK:
            return off, el, "slope_break"
        # height cap reached before any slope break
        if cap_hit is not None and rise >= HEIGHT_CAP_M:
            return cap_hit[0], cap_hit[1], "height_cap"


def main():
    if not os.path.isfile(IN_CSV):
        raise Exception("input not found: " + IN_CSV)
    byxs, rsta, all_ids = load_profiles(IN_CSV)

    out_rows = []
    prof_rows = []
    thal_rows = []
    bank_rows = []
    for xi in all_ids:
        pts = byxs.get(xi, [])
        rs = rsta.get(xi, float("nan"))
        if len(pts) < 5:
            out_rows.append(dict(
                xs_id=xi, river_sta_ft=round(rs, 3), thalweg_offset_m="",
                bank_l_offset_m="", bank_r_offset_m="",
                bank_l_elev_m="", bank_r_elev_m="", channel_width_m="",
                method_l="", method_r="", note="no_data"))
            continue
        spts = smooth(pts, SMOOTH_WIN_M)
        t_idx = thalweg_index(spts)
        t_off, t_el = spts[t_idx]
        lo_off, lo_el, lm = find_bank(spts, t_idx, -1)
        ro_off, ro_el, rm = find_bank(spts, t_idx, +1)
        width = ro_off - lo_off
        out_rows.append(dict(
            xs_id=xi, river_sta_ft=round(rs, 3),
            thalweg_offset_m=round(t_off, 2),
            bank_l_offset_m=round(lo_off, 2), bank_r_offset_m=round(ro_off, 2),
            bank_l_elev_m=round(lo_el, 3), bank_r_elev_m=round(ro_el, 3),
            channel_width_m=round(width, 2),
            method_l=lm, method_r=rm, note="ok"))

        # three clean per-purpose tables (xs_id is column 1) -- far more robust
        # for gnuplot than mixed single/double blank separators
        for off, el in pts:
            prof_rows.append("%d %.3f %.4f" % (xi, off, el))
        prof_rows.append("")            # double blank -> one index block per XS
        prof_rows.append("")
        thal_rows.append("%d %.3f %.4f" % (xi, t_off, t_el))
        bank_rows.append("%d %.3f %.4f" % (xi, lo_off, lo_el))
        bank_rows.append("%d %.3f %.4f" % (xi, ro_off, ro_el))

    # write CSV
    cols = ["xs_id", "river_sta_ft", "thalweg_offset_m",
            "bank_l_offset_m", "bank_r_offset_m",
            "bank_l_elev_m", "bank_r_elev_m", "channel_width_m",
            "method_l", "method_r", "note"]
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    # three clean gnuplot data files
    prof_path = os.path.join(OUT_DIR, "xs_bank_profiles.dat")
    thal_path = os.path.join(OUT_DIR, "xs_bank_thalweg.dat")
    bank_path = os.path.join(OUT_DIR, "xs_bank_points.dat")
    with open(prof_path, "w") as fh:
        fh.write("\n".join(prof_rows))
    with open(thal_path, "w") as fh:
        fh.write("\n".join(thal_rows))
    with open(bank_path, "w") as fh:
        fh.write("\n".join(bank_rows))

    # list of XS ids that actually have profile data (skips no_data sections);
    # the gnuplot plotter loops over THIS list so it never hits an empty index.
    valid_ids = [r["xs_id"] for r in out_rows if r["note"] == "ok"]
    with open(os.path.join(OUT_DIR, "xs_bank_ids.txt"), "w") as fh:
        fh.write(" ".join(str(i) for i in valid_ids))

    # console summary
    ok = [r for r in out_rows if r["note"] == "ok"]
    nd = [r for r in out_rows if r["note"] == "no_data"]
    print("bank stations written:", OUT_CSV)
    print("  cross sections: %d  (%d with banks, %d no_data)"
          % (len(out_rows), len(ok), len(nd)))
    if ok:
        widths = [r["channel_width_m"] for r in ok]
        print("  channel width  min/mean/max = %.1f / %.1f / %.1f m"
              % (min(widths), sum(widths) / len(widths), max(widths)))
        mflags = collections.Counter([r["method_l"] for r in ok]
                                     + [r["method_r"] for r in ok])
        print("  bank method counts:", dict(mflags))
    if nd:
        print("  no_data XS:", ", ".join(str(r["xs_id"]) for r in nd))

    # --- off-center / suspect-XS diagnostic --------------------------------
    # Flag cross sections that likely need a recentering or cut-line review:
    #   * thalweg offset far from 0 (channel not centered on the cut line)
    #   * both banks on the same side of center (channel entirely off-center)
    #   * channel width hitting the search edge (no real banks found)
    suspect = []
    for r in ok:
        toff = float(r["thalweg_offset_m"])
        bl, br = float(r["bank_l_offset_m"]), float(r["bank_r_offset_m"])
        reasons = []
        if abs(toff) > OFFCENTER_TOL_M:
            reasons.append("thalweg off-center %.0f m" % toff)
        if (bl < 0) == (br < 0):
            reasons.append("both banks same side")
        if r["method_l"] == "edge" or r["method_r"] == "edge":
            reasons.append("bank at search edge")
        if reasons:
            suspect.append((r["xs_id"], "; ".join(reasons)))
    if suspect:
        print("\n  SUSPECT cross sections (review recentering / cut line):")
        for xi, why in suspect:
            print("    XS %-3d  %s" % (xi, why))
    else:
        print("\n  no suspect cross sections (all thalwegs centered).")

    print("\ngnuplot data files:")
    print("  ", prof_path)
    print("  ", thal_path)
    print("  ", bank_path)


main()
