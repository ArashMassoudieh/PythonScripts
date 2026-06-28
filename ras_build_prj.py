#!/usr/bin/env python3
# =============================================================================
# ras_build_prj.py
#
# RAS step 5a: write the minimum files needed to OPEN the geometry in HEC-RAS:
#   <SITE_ID>.prj   the project file (this is what you open in HEC-RAS)
#   <SITE_ID>.p01   a plan stub that references the geometry (+ a flow slot)
#
# This gets the 23-section geometry on screen so it can be checked before the
# unsteady flow file and boundary conditions are added (those come next, and
# are easiest finished in the RAS GUI). The plan references a flow file
# <SITE_ID>.u01 that may not exist yet; RAS will open the geometry regardless
# and warn that the flow file is missing -- expected at this stage.
#
# Run AFTER ras_build_g01.py. US customary project.
#
# Run: python3 ras_build_prj.py   (or exec in the QGIS Console)
# =============================================================================
import os

try:
    ROOT
except NameError:
    ROOT = "/home/arash/Dropbox/Chloeta/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

SITE_ID = os.path.basename(SITE_DIR.rstrip("/"))
RAS_DIR = os.path.join(ROOT, "WS3_RAS", SITE_ID)

PRJ_OUT  = os.path.join(RAS_DIR, SITE_ID + ".prj")
PLAN_OUT = os.path.join(RAS_DIR, SITE_ID + ".p01")
G01_NAME = SITE_ID + ".g01"
U01_NAME = SITE_ID + ".u01"        # referenced; created in the next step

TITLE = SITE_ID + " WS3 1D"


def main():
    os.makedirs(RAS_DIR, exist_ok=True)
    if not os.path.isfile(os.path.join(RAS_DIR, G01_NAME)):
        print("WARNING: %s not found in %s -- run ras_build_g01.py first."
              % (G01_NAME, RAS_DIR))

    # --- project file (validated against a real RAS 7.0.1 .prj) -------------
    prj = []
    prj.append("Proj Title=%s" % TITLE)
    prj.append("Current Plan=p01")          # REQUIRED: RAS loads geometry via the current plan
    prj.append("Default Exp/Contr=0.3,0.1")
    prj.append("English Units")             # REQUIRED units declaration
    prj.append("Geom File=g01")
    prj.append("Unsteady File=u01")
    prj.append("Plan File=p01")
    prj.append("Y Axis Title=Elevation")
    prj.append("X Axis Title(PF)=Main Channel Distance")
    prj.append("X Axis Title(XS)=Station")
    prj.append("BEGIN DESCRIPTION:")
    prj.append("  NHA RFP #660 / Chloeta WS3 -- %s 1D unsteady." % SITE_ID)
    prj.append("END DESCRIPTION:")
    prj.append("DSS Start Date=")
    prj.append("DSS Start Time=")
    prj.append("DSS End Date=")
    prj.append("DSS End Time=")
    prj.append("DSS File=dss")
    prj.append("GIS Export Profiles= 0 ")
    with open(PRJ_OUT, "w", newline="") as fh:
        fh.write("\r\n".join(prj) + "\r\n")

    # --- unsteady plan (modeled on a real RAS unsteady .p file) -------------
    plan = []
    plan.append("Plan Title=%s Base Plan" % SITE_ID)
    plan.append("Program Version=5.00")
    plan.append("Short Identifier=Base")
    plan.append("Simulation Date=01JAN2000,0000,02JAN2000,0000")
    plan.append("Geom File=g01")
    plan.append("Flow File=u01")
    plan.append("Subcritical Flow")
    plan.append("Std Step Tol= 0.01 ")
    plan.append("Critical Tol= 0.01 ")
    plan.append("Num of Std Step Trials= 20 ")
    plan.append("Max Error Tol= 0.3 ")
    plan.append("Flow Tol Ratio= 0.001 ")
    plan.append("Friction Slope Method= 1 ")
    plan.append("Unsteady Friction Slope Method= 2 ")
    plan.append("Computation Interval=30SEC")
    plan.append("Output Interval=1HOUR")
    plan.append("Instantaneous Interval=1HOUR")
    plan.append("Mapping Interval=1HOUR")
    plan.append("Run HTab= 1 ")
    plan.append("Run UNet= 1 ")
    plan.append("Run PostProcess= 1 ")
    plan.append("UNET Theta= 1 ")
    plan.append("UNET Use Existing IB Tables= 0 ")
    plan.append("UNET 1D Methodology=Finite Difference")
    plan.append("DSS File=dss")
    with open(PLAN_OUT, "w", newline="") as fh:
        fh.write("\r\n".join(plan) + "\r\n")

    print("HEC-RAS project files written to:", RAS_DIR)
    print("  project:", os.path.basename(PRJ_OUT), "  <- OPEN THIS in HEC-RAS")
    print("  plan   :", os.path.basename(PLAN_OUT))
    print("  geometry referenced:", G01_NAME)
    print("  flow referenced    :", U01_NAME, "(not yet created -- next step)")
    print("\nTo check the geometry now:")
    print("  1. HEC-RAS -> File -> Open Project ->", os.path.basename(PRJ_OUT))
    print("  2. Open the Geometry editor; you should see 23 cross sections.")
    print("  3. RAS will warn the flow file is missing -- expected; ignore for now.")


main()
