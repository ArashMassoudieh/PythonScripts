#!/usr/bin/env python3
# =============================================================================
# ras_build_g01.py
#
# RAS geometry, step 4: assemble the HEC-RAS .g01 geometry text file from the
# per-section products built in steps 2c-3c. ONE river, ONE reach.
#
# UNIT SYSTEM: US customary (feet). River stations are already in feet; DEM
# elevations are converted m -> ft (x M_TO_FT). The GIS cut-line coordinates
# stay in the projected CRS (EPSG:26912, meters) -- those are map coordinates
# and are independent of the station/elevation unit system.
#
# INPUTS (in <SITE>/outputs_RAS/)
#   xs_profiles_model.csv   xs_id, station_m, river_sta_ft, offset_m, x, y, elev_m, status
#                           (model profiles: interpolated XS substituted, with x,y)
#   bank_stations.csv       xs_id, ..., bank_l_offset_m, bank_r_offset_m, ...
#   manning_n.csv           xs_id, n_lob, n_channel, n_rob, ...
#   reach_lengths.csv       xs_id, len_lob_ft, len_channel_ft, len_rob_ft, ...
#
# OUTPUT (in <SITE>/../../WS3_RAS/<SITE_ID>/)   <- RAS model folder, not GIS
#   <SITE_ID>.g01           HEC-RAS geometry file
#
# Each cross section gets: river station, an optional GIS cut-line (plan x,y),
# the station-elevation table (offset_ft, elev_ft), downstream reach lengths
# (LOB/Channel/ROB), bank stations (in STATION units = offset measured from the
# left end of the cut line), and the three Manning's n values.
#
# IMPORTANT RAS STATION CONVENTION: in the .g01 a cross section's horizontal
# coordinate is the "station" measured from the LEFT end of the cut line,
# increasing to the right -- NOT the signed offset-from-center we carry in the
# CSVs. We convert: station = offset + HALF_LEN_FT, so the left end is 0.
#
# Run: python3 ras_build_g01.py   (or exec in the QGIS Console)
# =============================================================================
import os
import csv
import collections

# --- root / paths ----------------------------------------------------------
try:
    ROOT
except NameError:
    ROOT = "/home/arash/Dropbox/Chloeta/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

SITE_ID = os.path.basename(SITE_DIR.rstrip("/"))        # e.g. "AZ12-100"

OUT_DIR_GIS = os.path.join(ROOT, SITE_DIR, "outputs_RAS")
# RAS model files live in WS3_RAS/<SITE_ID>/, parallel to WS3_GIS
RAS_DIR = os.path.join(ROOT, "WS3_RAS", SITE_ID)

MODEL_CSV = os.path.join(OUT_DIR_GIS, "xs_profiles_model.csv")
BANK_CSV  = os.path.join(OUT_DIR_GIS, "bank_stations.csv")
NCSV      = os.path.join(OUT_DIR_GIS, "manning_n.csv")
LEN_CSV   = os.path.join(OUT_DIR_GIS, "reach_lengths.csv")
G01_OUT   = os.path.join(RAS_DIR, SITE_ID + ".g01")

# --- settings --------------------------------------------------------------
RIVER_NAME = SITE_ID            # RAS river label
REACH_NAME = "Main"             # RAS reach label
M_TO_FT    = 3.280839895
HALF_LEN_M = 200.0              # cut-line half-length (match step 2c HALF_LEN_M)
GEOM_TITLE = SITE_ID + " WS3 1D Geometry"
# ---------------------------------------------------------------------------


def load_csv(path, key="xs_id"):
    if not os.path.isfile(path):
        raise Exception("input not found: " + path)
    rows = list(csv.DictReader(open(path)))
    return rows


def fnum(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def ras_n(v):
    """RAS-style compact n value, right-justified in 8 chars: .045 not 0.045."""
    s = ("%g" % v)
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return "%8s" % s


def main():
    os.makedirs(RAS_DIR, exist_ok=True)

    # --- model profiles: group station-elevation by xs_id -------------------
    prof_rows = load_csv(MODEL_CSV)
    prof = collections.defaultdict(list)     # xs_id -> [(offset_m, elev_m, x, y)]
    rsta = {}                                # xs_id -> river_sta_ft
    for r in prof_rows:
        xi = int(r["xs_id"])
        off = fnum(r["offset_m"])
        el  = fnum(r["elev_m"])
        x   = fnum(r["x"]); y = fnum(r["y"])
        if off is None or el is None:
            continue
        prof[xi].append((off, el, x, y))
        rsta.setdefault(xi, fnum(r["river_sta_ft"]))
    for xi in prof:
        prof[xi].sort(key=lambda t: t[0])    # by offset, left -> right

    # --- banks, n, lengths keyed by xs_id -----------------------------------
    banks = {int(r["xs_id"]): r for r in load_csv(BANK_CSV)}
    nvals = {int(r["xs_id"]): r for r in load_csv(NCSV)}
    lens  = {int(r["xs_id"]): r for r in load_csv(LEN_CSV)}

    # cross sections, ORDERED upstream-most first (descending river station) --
    # RAS lists sections from upstream (high station) to downstream (low).
    xs_ids = sorted(prof.keys(), key=lambda xi: rsta.get(xi, 0), reverse=True)

    half_ft = HALF_LEN_M * M_TO_FT

    # --- reach centerline (the river schematic line) ------------------------
    # RAS needs the reach drawn as a multi-point line following the channel
    # invert; without it the cross sections have nothing to attach to and the
    # River/Reach lists come up empty ("No Data for Plot"). Build it from each
    # section's thalweg point (profile point nearest offset 0), ordered
    # upstream -> downstream to match the cross-section listing.
    centerline = []           # [(x, y)] upstream -> downstream
    for xi in xs_ids:
        pts = prof[xi]
        tp = min(pts, key=lambda t: abs(t[0]))   # nearest offset 0
        centerline.append((tp[2], tp[3]))        # (x, y) projected meters

    all_x = [x for xi in xs_ids for (_, _, x, _) in prof[xi]]
    all_y = [y for xi in xs_ids for (_, _, _, y) in prof[xi]]
    vx0, vx1, vy0, vy1 = min(all_x), max(all_x), min(all_y), max(all_y)

    # =====================================================================
    # write the .g01
    # =====================================================================
    out = []
    out.append("Geom Title=%s" % GEOM_TITLE)
    out.append("Program Version=5.00")
    out.append("Viewing Rectangle= %.4f , %.4f , %.4f , %.4f "
               % (vx0, vx1, vy0, vy1))
    out.append("")
    out.append("River Reach=%-16s,%-16s" % (RIVER_NAME, REACH_NAME))
    out.append("Reach XY= %d " % len(centerline))
    line = ""
    for k, (x, y) in enumerate(centerline):
        line += "%16.4f%16.4f" % (x, y)
        if k % 2 == 1:
            out.append(line); line = ""
    if line:
        out.append(line)
    out.append("Rch Text X Y=%.4f,%.4f" % centerline[0])
    out.append("Reverse River Text= 0 ")
    out.append("")

    for xi in xs_ids:
        pts = prof[xi]
        rs  = rsta.get(xi, 0.0)
        b   = banks.get(xi, {})
        nv  = nvals.get(xi, {})
        ln  = lens.get(xi, {})

        # station-elevation in feet; station = offset + half (left end = 0)
        se = [( (off + HALF_LEN_M) * M_TO_FT, el * M_TO_FT )
              for (off, el, x, y) in pts]
        npts = len(se)
        min_el_ft = min(e for _, e in se)        # invert, for HTab starting elev

        # bank stations -> station units (offset + half), in feet
        bl_off = fnum(b.get("bank_l_offset_m"))
        br_off = fnum(b.get("bank_r_offset_m"))
        bl_sta = (bl_off + HALF_LEN_M) * M_TO_FT if bl_off is not None else half_ft * 0.95
        br_sta = (br_off + HALF_LEN_M) * M_TO_FT if br_off is not None else half_ft * 1.05

        # reach lengths (ft) -- downstream LOB / Channel / ROB
        l_lob = fnum(ln.get("len_lob_ft"), 0.0)
        l_ch  = fnum(ln.get("len_channel_ft"), 0.0)
        l_rob = fnum(ln.get("len_rob_ft"), 0.0)

        # Manning's n
        n_lob = fnum(nv.get("n_lob"), 0.045)
        n_ch  = fnum(nv.get("n_channel"), 0.035)
        n_rob = fnum(nv.get("n_rob"), 0.045)

        # --- cross-section header -------------------------------------------
        out.append("Type RM Length L Ch R = 1 ,%-8.4f,%.4f,%.4f,%.4f"
                   % (rs, l_lob, l_ch, l_rob))

        # --- GIS cut line (plan-view x,y, in projected meters) --------------
        xy = [(x, y) for (off, el, x, y) in pts if x is not None and y is not None]
        if xy:
            out.append("XS GIS Cut Line=%d" % len(xy))
            line = ""
            for k, (x, y) in enumerate(xy):
                line += "%16.2f%16.2f" % (x, y)
                if k % 2 == 1:
                    out.append(line); line = ""
            if line:
                out.append(line)

        # --- station-elevation table (5 pairs per line, 8-wide) -------------
        out.append("#Sta/Elev= %d " % npts)
        line = ""
        for k, (sta, el) in enumerate(se):
            line += "%8.2f%8.2f" % (sta, el)
            if k % 5 == 4:
                out.append(line); line = ""
        if line:
            out.append(line)

        # --- Manning's n: 3 breakpoints, 8-wide fields (sta, n, flag) -------
        # matches the format RAS itself writes: n as compact ".045"
        out.append("#Mann= 3 , 0 , 0 ")
        out.append("%8.2f%s%8s%8.2f%s%8s%8.2f%s%8s"
                   % (0.0,    ras_n(n_lob), "0",
                      bl_sta, ras_n(n_ch),  "0",
                      br_sta, ras_n(n_rob), "0"))

        # --- bank stations + the per-section fields RAS expects -------------
        out.append("Bank Sta=%.2f,%.2f" % (bl_sta, br_sta))
        out.append("XS Rating Curve= 0 ,0")
        out.append("XS HTab Starting El and Incr=%.2f,0.45, 50 " % min_el_ft)
        out.append("XS HTab Horizontal Distribution= 5 , 5 , 5 ")
        out.append("Exp/Cntr=0.3,0.1")
        out.append("")

    # --- geometry file footer (mirrors what RAS writes) ---------------------
    out.append("LCMann Time=Dec/30/1899 00:00:00")
    out.append("LCMann Region Time=Dec/30/1899 00:00:00")
    out.append("LCMann Table=0")
    out.append("Chan Stop Cuts=-1 ")
    out.append("")
    out.append("")
    out.append("Use User Specified Reach Order=0")
    out.append("GIS Ratio Cuts To Invert=-1")
    out.append("GIS Limit At Bridges=0")
    out.append("Composite Channel Slope=5")
    out.append("")

    # CRLF line endings for Windows HEC-RAS
    with open(G01_OUT, "w", newline="") as fh:
        fh.write("\r\n".join(out) + "\r\n")

    # --- summary ------------------------------------------------------------
    print("HEC-RAS geometry written:", G01_OUT)
    print("  river / reach : %s / %s" % (RIVER_NAME, REACH_NAME))
    print("  units         : US customary (feet); elevations converted m->ft")
    print("  cross sections: %d  (river sta %.1f down to %.1f ft)"
          % (len(xs_ids), rsta[xs_ids[0]], rsta[xs_ids[-1]]))
    print("  cut-line CRS  : EPSG:26912 (projected meters, unchanged)")
    # carry through any flagged sections
    flagged = [xi for xi in xs_ids
               if banks.get(xi, {}).get("note", "") not in ("ok", "interp", "")]
    if flagged:
        print("  NOTE flagged sections:", ", ".join("XS %d" % x for x in flagged))
    print("\n  Open in HEC-RAS: add this geometry to a project, then add the")
    print("  culvert/road structure at the crossing manually in the RAS GUI.")


main()
