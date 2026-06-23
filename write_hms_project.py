# =============================================================================
# write_hms_project.py (QGIS Python Console)
#
# NHA WS3 -- assemble a ready-to-open HEC-HMS 4.13 project folder from the
# pipeline outputs for one site.
#
# CREATES
#   <HMS_DIR>/<BASIN_NAME>/               HMS project folder
#     <BASIN_NAME>.hms                    project file (references all components)
#     <BASIN_NAME>.basin                  copied from outputs/
#     <BASIN_NAME>.met                    copied from outputs/
#     <BASIN_NAME>_6hr_100yr.control      control spec: 6-hr storm
#     <BASIN_NAME>_24hr_100yr.control     control spec: 24-hr storm
#     <BASIN_NAME>.dss                    empty placeholder (HMS populates on run)
#     data/                               required empty subdirs
#     results/
#     maps/
#     terrain/
#     logs/
#
# The project opens directly in HMS: File -> Open -> <BASIN_NAME>.hms
# Two simulation runs are pre-wired (6-hr and 24-hr, 100-yr) and ready to
# compute with no further configuration.
#
# READS
#   <SITE>/outputs/<BASIN_NAME>.basin     from write_basin.py
#   <SITE>/outputs/<BASIN_NAME>.met       from write_met.py
#
# CONTROL SPEC LOGIC
#   Start date: 01 January 2000 00:00  (arbitrary; only relative timing matters
#                                        for design storm simulations)
#   Storm duration + 50% tail:
#     6-hr storm  -> 9-hr simulation  (360 min storm + 180 min recession)
#     24-hr storm -> 36-hr simulation (1440 min storm + 720 min recession)
#   Time step: 6 minutes (matches hyetograph interval in write_met.py)
#
# TIMEZONE: America/Phoenix (Arizona / Navajo Nation -- no DST)
#           Change TZ_ID below if needed for NM sites.
#
# Run from: QGIS -> Plugins -> Python Console.
# =============================================================================

import os
import shutil
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# --- settings --------------------------------------------------------------
# ---------------------------------------------------------------------------

try:
    ROOT
except NameError:
    ROOT = "/home/arash/Dropbox/Chloeta/NHA/"

try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

# Parent folder where the HMS project folder will be created.
# Default: <ROOT>/WS3_HMS/  (sibling to WS3_GIS/)
try:
    HMS_DIR
except NameError:
    HMS_DIR = os.path.join(ROOT, "WS3_HMS")

# Timezone for the .hms file.
# Arizona (Navajo Nation) does observe DST unlike the rest of AZ,
# so use America/Denver which matches Navajo Nation time.
# Change to "America/Phoenix" (no DST) if preferred.
try:
    TZ_ID
except NameError:
    TZ_ID = "America/Denver"

# ---------------------------------------------------------------------------
# --- derived paths ---------------------------------------------------------
# ---------------------------------------------------------------------------

BASIN_NAME = os.path.basename(os.path.normpath(SITE_DIR))  # e.g. AZ12-100
HMS_NAME   = BASIN_NAME.replace("-", "_")                   # e.g. AZ12_100 (HMS forbids hyphens)
site_path  = os.path.join(ROOT, SITE_DIR)
OUT_DIR    = os.path.join(site_path, "outputs")

basin_src  = os.path.join(OUT_DIR, BASIN_NAME + ".basin")
dss_src    = os.path.join(OUT_DIR, HMS_NAME + ".dss")

# One .met + .gage file per storm
STORMS = [
    ("6hr_100yr",  360),
    ("24hr_100yr", 1440),
]
met_models = []  # list of (model_name, met_src, met_dst, gage_src, gage_dst)
for suffix, _ in STORMS:
    model_name = "%s_%s" % (HMS_NAME, suffix)
    met_models.append((
        model_name,
        os.path.join(OUT_DIR, model_name + ".met"),
        model_name + ".met",
        os.path.join(OUT_DIR, model_name + ".gage"),
        model_name + ".gage",
    ))

proj_dir = os.path.join(HMS_DIR, HMS_NAME)

# Basin destination filename (no hyphens)
basin_dst_name = HMS_NAME + ".basin"
dss_dst_name   = HMS_NAME + ".dss"

CRLF = "\r\n"

# ---------------------------------------------------------------------------
# --- preflight -------------------------------------------------------------
# ---------------------------------------------------------------------------

missing = []
if not os.path.isfile(basin_src):
    missing.append((basin_src, ".basin"))
if not os.path.isfile(dss_src):
    missing.append((dss_src, ".dss"))
for model_name, met_src, _, gage_src, __ in met_models:
    if not os.path.isfile(met_src):
        missing.append((met_src, ".met for %s" % model_name))
    if not os.path.isfile(gage_src):
        missing.append((gage_src, ".gage for %s" % model_name))
if missing:
    msgs = "\n".join("  %s (%s)" % (p, l) for p, l in missing)
    raise Exception(
        "Required file(s) not found:\n%s\n"
        "Run write_basin.py and write_met.py before write_hms_project.py." % msgs)

# ---------------------------------------------------------------------------
# --- helpers ---------------------------------------------------------------
# ---------------------------------------------------------------------------

now  = datetime.now()
DATE = now.strftime("%d %B %Y")   # e.g. "22 June 2026"
TIME = now.strftime("%H:%M")      # e.g. "14:35"  (.hms uses HH:MM, not HH:MM:SS)

def write_crlf(path, content):
    """Write text file with CRLF line endings."""
    with open(path, "w", newline="") as fh:
        fh.write(content)

def fmt_dt(dt):
    """Format datetime for control spec: '01 January 2000', '00:00'."""
    return dt.strftime("%d %B %Y"), dt.strftime("%H:%M")

# ---------------------------------------------------------------------------
# --- create project folder and subdirs -------------------------------------
# ---------------------------------------------------------------------------

SUBDIRS = ["data", "results", "maps", "terrain", "logs",
           "forecast", "ensemble", "montecarlo", "optimizer",
           "frequency", "basinStates", "datavar"]

os.makedirs(proj_dir, exist_ok=True)
for d in SUBDIRS:
    os.makedirs(os.path.join(proj_dir, d), exist_ok=True)

print("Project folder: %s" % proj_dir)

# ---------------------------------------------------------------------------
# --- copy .basin and .met --------------------------------------------------
# ---------------------------------------------------------------------------

basin_dst = os.path.join(proj_dir, basin_dst_name)
shutil.copy2(basin_src, basin_dst)
print("Copied: %s" % basin_dst_name)

# Copy DSS (contains all hyetograph time series)
dss_dst = os.path.join(proj_dir, dss_dst_name)
shutil.copy2(dss_src, dss_dst)
print("Copied: %s" % dss_dst_name)

# Copy per-storm .met files (no longer copying individual .gage files --
# gages are written to the project-level .gage file by write_hms_project.py)
for model_name, met_src, met_dst_name, gage_src, gage_dst_name in met_models:
    shutil.copy2(met_src, os.path.join(proj_dir, met_dst_name))
    print("Copied: %s" % met_dst_name)

# ---------------------------------------------------------------------------
# --- write .control files --------------------------------------------------
#
# HMS .control grammar (4.13):
#
#   Control: <name>
#        Last Modified Date: <DD Month YYYY>
#        Last Modified Time: <HH:MM>
#        Start Date: <DD Month YYYY>
#        Start Time: <HH:MM>
#        End Date: <DD Month YYYY>
#        End Time: <HH:MM>
#        Time Interval: <minutes>
#   End:
# ---------------------------------------------------------------------------

# Anchor start: 01 Jan 2000 00:00 (arbitrary; relative timing is what matters)
START = datetime(2000, 1, 1, 0, 0)

STORMS = [
    # (suffix,  storm_dur_min, tail_factor)
    ("6hr_100yr",  360,   0.5),   # 6 hr storm + 3 hr tail = 9 hr total
    ("24hr_100yr", 1440,  0.5),   # 24 hr storm + 12 hr tail = 36 hr total
]

control_names = []

for suffix, storm_min, tail in STORMS:
    total_min  = int(storm_min * (1 + tail))
    end_dt     = START + timedelta(minutes=total_min)
    ctrl_name  = "%s_%s" % (HMS_NAME, suffix)
    ctrl_file  = os.path.join(proj_dir, ctrl_name + ".control")

    s_date, s_time = fmt_dt(START)
    e_date, e_time = fmt_dt(end_dt)

    content = CRLF.join([
        "Control: " + ctrl_name,
        "     Last Modified Date: " + DATE,
        "     Last Modified Time: " + TIME,
        "     Start Date: " + s_date,
        "     Start Time: " + s_time,
        "     End Date: "   + e_date,
        "     End Time: "   + e_time,
        "     Time Interval: 6",
        "End:",
        "",
    ])

    write_crlf(ctrl_file, content)
    control_names.append((ctrl_name, suffix))
    print("Wrote: %s.control  (%d-min simulation)" % (ctrl_name, total_min))

# ---------------------------------------------------------------------------
# --- write .hms project file -----------------------------------------------
#
# HMS .hms grammar (4.13):
#
#   Project: <name>
#        Description:
#        Version: 4.13
#        Filepath Separator: /
#        DSS File Name: <name>.dss
#        Time Zone ID: <tz>
#   End:
#
#   Basin: <basin_name>
#        Filename: <basin_name>.basin
#        Description:
#        Last Modified Date: ...
#        Last Modified Time: ...
#   End:
#
#   Meteorology: <met_name>
#        Filename: <met_name>.met
#        Description:
#        Last Modified Date: ...
#        Last Modified Time: ...
#   End:
#
#   Control: <ctrl_name>
#        Filename: <ctrl_name>.control
#        Description:
#        Last Modified Date: ...
#        Last Modified Time: ...
#   End:
#
# Note: HMS uses the *basename* of each file with the separator character,
# NOT full paths.  All files must sit in the same folder as the .hms file.
# ---------------------------------------------------------------------------

# met_model_names derived from met_models list
met_model_names = [m[0] for m in met_models]

hms_lines = [
    "Project: " + HMS_NAME,
    "     Description: NHA WS3 -- %s, 100-yr design storm" % BASIN_NAME,
    "     Version: 4.13",
    "     Filepath Separator: /",
    "     DSS File Name: %s.dss" % HMS_NAME,
    "     Time Zone ID: " + TZ_ID,
    "End:",
    "",
]

# Basin block
hms_lines += [
    "Basin: " + HMS_NAME,
    "     Filename: %s" % basin_dst_name,
    "     Description: ",
    "     Last Modified Date: " + DATE,
    "     Last Modified Time: " + TIME,
    "End:",
    "",
]

# Precipitation (met model) blocks -- one per storm
for model_name, _, met_dst_name, __, gage_dst_name in met_models:
    hms_lines += [
        "Precipitation: " + model_name,
        "     Filename: %s" % met_dst_name,
        "     Description: ",
        "     Last Modified Date: " + DATE,
        "     Last Modified Time: " + TIME,
        "End:",
        "",
    ]

# Control blocks
for ctrl_name, _ in control_names:
    hms_lines += [
        "Control: " + ctrl_name,
        "     FileName: %s.control" % ctrl_name,
        "     Description: ",
        "End:",
        "",
    ]

hms_path = os.path.join(proj_dir, HMS_NAME + ".hms")
write_crlf(hms_path, CRLF.join(hms_lines))
print("Wrote: %s.hms" % HMS_NAME)

# ---------------------------------------------------------------------------
# --- write project-level .gage file ----------------------------------------
# All gages live in one <ProjectName>.gage file that HMS finds automatically.
# ---------------------------------------------------------------------------

gage_lines = [
    "Gage Manager: ",
    "     Gage Manager: ",
    "     Version: 4.13",
    "     Filepath Separator: /",
    "End: ",
    "",
]

for model_name, _, __, gage_src, gage_dst_name in met_models:
    gage_name  = model_name + "_Gage"
    dss_pathname = "/%s/%s/PRECIP-INC/01Jan2000/6Minute/ATLAS14/" % (HMS_NAME, gage_name)

    # End time depends on storm duration
    suffix = model_name.split("_")[-2] + "_" + model_name.split("_")[-1]  # e.g. 6hr_100yr
    storm_min = 360 if "6hr" in model_name else 1440
    from datetime import timedelta, datetime as dt
    start = dt(2000, 1, 1, 0, 0)
    end   = start + timedelta(minutes=storm_min)
    end_str = end.strftime("%-d %B %Y, %H:%M")

    gage_lines += [
        "Gage: " + gage_name,
        "     Gage: " + gage_name,
        "     Gage Type: Precipitation",
        "     Description: NOAA Atlas 14, 100-yr",
        "     Last Modified Date: " + DATE,
        "     Last Modified Time: " + TIME,
        "     Latitude Degrees: 0.0",
        "     Longitude Degrees: 0.0",
        "     Reference Height Units: Feet",
        "     Reference Height: 0.0",
        "     Data Source Type: Manual Entry",
        "     Filename: " + HMS_NAME + ".dss",
        "     Pathname: " + dss_pathname,
        "     Variant: Variant-1",
        "       Start Time: 1 January 2000, 00:00",
        "       End Time: " + end_str,
        "     End Variant: Variant-1",
        "End: ",
        "",
    ]

project_gage_path = os.path.join(proj_dir, HMS_NAME + ".gage")
write_crlf(project_gage_path, CRLF.join(gage_lines))
print("Wrote: %s.gage" % HMS_NAME)

# ---------------------------------------------------------------------------
# --- create empty .dss placeholder -----------------------------------------
dss_path = os.path.join(proj_dir, HMS_NAME + ".dss")
if not os.path.exists(dss_path):
    open(dss_path, "wb").close()
    print("Created: %s.dss (empty placeholder)" % HMS_NAME)

# ---------------------------------------------------------------------------
# --- summary ---------------------------------------------------------------
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("HMS PROJECT READY")
print("=" * 60)
print("  Location : %s" % proj_dir)
print("  Open in HMS: File -> Open -> %s.hms" % HMS_NAME)
print("")
print("  Files written:")
for f in os.listdir(proj_dir):
    if os.path.isfile(os.path.join(proj_dir, f)):
        print("    %s" % f)
print("")
print("  To run a simulation:")
print("    Compute -> Simulation Run Manager -> New")
print("    Basin Model   : %s" % BASIN_NAME)
print("    Met Model     : %s_6hr_100yr  (or 24hr)" % BASIN_NAME)
print("    Control Specs : %s_6hr_100yr.control (or 24hr)" % BASIN_NAME)
print("")
print("PRE-SEAL: verify hyetograph shape and peak timing in HMS before sealing.")
