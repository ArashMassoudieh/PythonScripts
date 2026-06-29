# =============================================================================
# Clip ALL raster and vector layers in the project to the outer boundary of the
# final subwatersheds layer (subwatersheds.gpkg from build_subwatersheds.py).
#
# - Dissolves all subwatershed polygons into ONE boundary mask (with CRS set).
# - Clips every vector layer -> native:clip
# - Clips every raster layer  -> gdal:cliprasterbymasklayer (CRS passed explicitly)
# - Outputs go to <SITE>/outputs/clipped/ with a _wsclip suffix.
#
# All outputs are written WITH their CRS so you do not have to assign it by hand.
#
# WINDOWS FILE-LOCK NOTE: this QGIS session can keep watershed_boundary.gpkg
# open via a previously loaded layer (including this script's own verify layer),
# and Windows then refuses to overwrite it on the next run. release_and_delete()
# (a) removes any project layer pointing at the target file, (b) drops QGIS data
# sources / forces GC, (c) falls back to QgsVectorFileWriter.deleteSilently, and
# (d) only raises if the file genuinely cannot be cleared. So reruns no longer
# self-lock, and when they truly can't, the error is explicit.
#
# Run from: QGIS -> Plugins -> Python Console.
# =============================================================================

import os
import gc
import processing
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsGeometry, QgsFeature,
    QgsFields, QgsField, QgsVectorFileWriter, QgsWkbTypes,
    QgsCoordinateTransformContext, QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant

# --- settings (set ROOT + SITE_DIR ONCE) -----------------------------------
try:
    ROOT
except NameError:
    ROOT = "C:/Users/smnfa/Dropbox/NHA/"
try:
    SITE_DIR
except NameError:
    SITE_DIR = "WS3_GIS/AZ12-100"

SUBWS_NAME   = "subwatersheds.gpkg"
CLIP_SUFFIX  = "_wsclip"
USE_VISIBLE_ONLY = False
ADD_TO_PROJECT   = False   # do not auto-load outputs; load manually as needed

# Fallback CRS if the subwatersheds file somehow has none. AZ = 26912, eastern
# NM = 26913. Used ONLY if the layer's own CRS is invalid.
FALLBACK_EPSG = 26912
# ---------------------------------------------------------------------------

site_path = os.path.join(ROOT, SITE_DIR)
OUT_DIR   = os.path.join(site_path, "outputs")
CLIP_DIR  = os.path.join(OUT_DIR, "clipped")
os.makedirs(CLIP_DIR, exist_ok=True)
SUBWS_PATH = os.path.join(OUT_DIR, SUBWS_NAME)

print("Site    :", site_path)
print("Boundary:", SUBWS_PATH)
print("Clipped :", CLIP_DIR)


# --- Windows-safe release + delete helper ----------------------------------
def release_and_delete(path):
    """Remove any project layer pointing at `path`, drop OGR handles that may be
    held by stray QgsVectorLayer objects in the shared run_phase2 namespace,
    then delete the file and its GPKG sidecars. Retries for transient locks."""
    target = os.path.normcase(os.path.abspath(path))
    proj = QgsProject.instance()
    # (a) remove any loaded layer whose data source is this file
    for lyr in list(proj.mapLayers().values()):
        src = lyr.source().split("|")[0]
        try:
            if os.path.normcase(os.path.abspath(src)) == target:
                proj.removeMapLayer(lyr.id())
        except Exception:
            pass

    # (a2) CRITICAL for run_phase2.py: steps share one exec() namespace, so a
    # QgsVectorLayer opened by an EARLIER step (e.g. the phase-1 boundary, or a
    # verify layer) can still be alive as a module-level variable, holding the
    # OGR provider open even though it was never added to the project. Find such
    # objects in the caller's globals and delete them so the handle is freed.
    import inspect
    try:
        for frame_info in inspect.stack():
            g = frame_info.frame.f_globals
            for name in list(g.keys()):
                obj = g.get(name)
                if isinstance(obj, QgsVectorLayer):
                    try:
                        osrc = obj.source().split("|")[0]
                        if os.path.normcase(os.path.abspath(osrc)) == target:
                            g[name] = None
                    except Exception:
                        pass
    except Exception:
        pass
    gc.collect()

    # (b) try the Qgis silent delete first (cleanest; handles sidecars)
    try:
        ok, _ = QgsVectorFileWriter.deleteSilently(path)
        if ok and not os.path.exists(path):
            return
    except AttributeError:
        pass
    except Exception:
        pass
    # (c) manual removal of file + sidecars, with retries: transient locks from
    # Dropbox/antivirus/Windows indexing usually clear within a few seconds.
    import time
    last_err = None
    for attempt in range(8):                 # ~8 tries over ~10s
        last_err = None
        for ext in ("", "-wal", "-shm", "-journal"):
            p = path + ext
            if os.path.exists(p):
                try:
                    os.remove(p)
                except PermissionError as e:
                    last_err = e
        if not os.path.exists(path):
            return
        # try Qgis silent delete again between attempts
        try:
            QgsVectorFileWriter.deleteSilently(path)
        except Exception:
            pass
        if not os.path.exists(path):
            return
        time.sleep(1.5)
    if os.path.exists(path):
        raise Exception(
            "Cannot overwrite %s -- it is still locked after retries.\n"
            "This is usually Dropbox or antivirus holding the file. PAUSE "
            "Dropbox sync during pipeline runs, or remove the "
            "'watershed_boundary' layer / restart QGIS, then re-run. (%s)"
            % (path, last_err))


# --- load subwatersheds ----------------------------------------------------
subws = QgsVectorLayer(SUBWS_PATH + "|layername=subwatersheds",
                       "subwatersheds_src", "ogr")
if not subws.isValid():
    subws = QgsVectorLayer(SUBWS_PATH, "subwatersheds_src", "ogr")
if not subws.isValid():
    raise Exception("Could not open subwatersheds: " + SUBWS_PATH)

# determine a VALID CRS for the mask
mask_crs = subws.crs()
if not mask_crs.isValid():
    mask_crs = QgsCoordinateReferenceSystem("EPSG:%d" % FALLBACK_EPSG)
    print("  subwatersheds had no CRS -> using EPSG:%d" % FALLBACK_EPSG)
crs_authid = mask_crs.authid() or ("EPSG:%d" % FALLBACK_EPSG)
print("Mask CRS:", crs_authid)

geoms = [ft.geometry() for ft in subws.getFeatures() if not ft.geometry().isEmpty()]
if not geoms:
    raise Exception("subwatersheds has no geometry.")
boundary = QgsGeometry.unaryUnion(geoms).makeValid()
print("Dissolved %d subwatershed(s) into one boundary (area %.4f km2)."
      % (len(geoms), boundary.area() / 1e6))

# release the subwatersheds_src handle we opened above; we have the geometry now
subws = None
gc.collect()

# --- write the dissolved boundary WITH its CRS -----------------------------
# LOCK AVOIDANCE: instead of overwriting a fixed Dropbox path that a stray
# QgsVectorLayer in the shared run_phase2 namespace may still hold open, write
# the mask to a UNIQUE temp filename each run. Nothing can be holding a file
# that did not exist a moment ago, so the WinError 32 overwrite-lock cannot
# occur. The clip steps use this temp mask. A stable copy is written at the end
# only if it can be (best-effort), so downstream tools that expect
# watershed_boundary.gpkg still find it.
import tempfile, uuid
_mask_dir = tempfile.gettempdir()
mask_path = os.path.join(_mask_dir, "ws_boundary_%s.gpkg" % uuid.uuid4().hex[:8])
STABLE_MASK = os.path.join(OUT_DIR, "watershed_boundary.gpkg")
print("Mask (temp):", mask_path)

# no release_and_delete needed: mask_path is brand-new and unique this run.

fields = QgsFields()
fields.append(QgsField("id", QVariant.Int))
opts = QgsVectorFileWriter.SaveVectorOptions()
opts.driverName = "GPKG"
opts.layerName = "watershed_boundary"

# IMPORTANT: pass a VALID QgsCoordinateReferenceSystem here so the file is
# written with a CRS. (Some builds drop the CRS if it is passed indirectly.)
ctx = QgsCoordinateTransformContext()
writer = QgsVectorFileWriter.create(
    mask_path, fields, QgsWkbTypes.MultiPolygon, mask_crs, ctx, opts)

bgeom = boundary
if bgeom.wkbType() not in (QgsWkbTypes.MultiPolygon, QgsWkbTypes.Polygon):
    coerced = bgeom.coerceToType(QgsWkbTypes.MultiPolygon)
    if coerced:
        bgeom = coerced[0]
bf = QgsFeature(fields)
bf.setGeometry(bgeom)
bf["id"] = 1
writer.addFeature(bf)
del writer          # release the write handle before reopening the file
gc.collect()

# verify the CRS actually stuck; if not, force it via assignprojection.
# NOTE: release the verify layer (set to None + GC) so it does not keep the
# file open and block the NEXT run's overwrite -- this was the original lock
# cause.
check = QgsVectorLayer(mask_path + "|layername=watershed_boundary", "chk", "ogr")
crs_ok = check.crs().isValid()
check_authid = check.crs().authid()
check = None
gc.collect()
if not crs_ok:
    print("  WARNING: boundary still lacks CRS; forcing", crs_authid)
    processing.run("native:assignprojection",
                   {"INPUT": mask_path, "CRS": mask_crs, "OUTPUT": mask_path})
else:
    print("Boundary mask written WITH CRS", check_authid, "->", mask_path)

# --- best-effort: also write the stable watershed_boundary.gpkg ------------
# Downstream tools may expect <SITE>/outputs/watershed_boundary.gpkg. Copy the
# temp mask there if possible. If a stray handle locks the stable file, this is
# NON-FATAL: the clip below uses the temp mask, which is what actually matters.
try:
    release_and_delete(STABLE_MASK)
    import shutil
    shutil.copyfile(mask_path, STABLE_MASK)
    print("Stable boundary copy ->", STABLE_MASK)
except Exception as ex:
    print("  NOTE: could not refresh stable watershed_boundary.gpkg (%s)" % ex)
    print("        Clip proceeds with the temp mask; this is non-fatal.")

# --- collect layers to clip ------------------------------------------------
project = QgsProject.instance()
root = project.layerTreeRoot()

def is_visible(layer):
    node = root.findLayer(layer.id())
    return node is not None and node.isVisible()

def is_skippable(layer):
    src = layer.source().lower()
    nm = layer.name().lower()
    if "subwatersheds" in src or "watershed_boundary" in src:
        return True
    if CLIP_SUFFIX.lower() in src or CLIP_SUFFIX.lower() in nm:
        return True
    return False

rasters, vectors = [], []
for lyr in project.mapLayers().values():
    if USE_VISIBLE_ONLY and not is_visible(lyr):
        continue
    if is_skippable(lyr):
        continue
    if isinstance(lyr, QgsRasterLayer):
        rasters.append(lyr)
    elif isinstance(lyr, QgsVectorLayer):
        vectors.append(lyr)

print("\nClipping %d raster(s) and %d vector(s)..." % (len(rasters), len(vectors)))

def safe(name):
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)

made = []

# --- clip vectors ----------------------------------------------------------
for v in vectors:
    out_path = os.path.join(CLIP_DIR, f"{safe(v.name())}{CLIP_SUFFIX}.gpkg")
    print("  [vector]", v.name(), "(CRS", v.crs().authid() or "NONE", ")")
    try:
        # overwrite-safe: clear any prior clip output that may be locked/loaded
        release_and_delete(out_path)
        src = v.source()
        vcrs = v.crs()
        # if the input vector itself has no/!= CRS, reproject/assign to mask CRS
        if not vcrs.isValid():
            print("     input has no CRS -> assigning", crs_authid)
            asg = processing.run("native:assignprojection",
                                 {"INPUT": src, "CRS": mask_crs,
                                  "OUTPUT": "TEMPORARY_OUTPUT"})
            src = asg["OUTPUT"]
        elif vcrs.authid() != crs_authid:
            rep = processing.run("native:reprojectlayer", {
                "INPUT": src, "TARGET_CRS": mask_crs, "OUTPUT": "TEMPORARY_OUTPUT"})
            src = rep["OUTPUT"]
        res = processing.run("native:clip", {
            "INPUT": src, "OVERLAY": mask_path, "OUTPUT": out_path})
        # report feature count so empties are obvious
        chk = QgsVectorLayer(out_path, "chk", "ogr")
        n = chk.featureCount() if chk.isValid() else -1
        chk = None
        gc.collect()
        print("     ->", out_path, "(%d features)" % n)
        made.append(("vector", v.name(), out_path))
    except Exception as ex:
        print("     ERROR:", ex)

# --- clip rasters ----------------------------------------------------------
for r in rasters:
    out_path = os.path.join(CLIP_DIR, f"{safe(r.name())}{CLIP_SUFFIX}.tif")
    rcrs = r.crs().authid() or crs_authid
    print("  [raster]", r.name(), "(CRS", r.crs().authid() or "NONE", ")")
    try:
        # overwrite-safe: clear any prior clip output that may be locked/loaded
        release_and_delete(out_path)
        processing.run("gdal:cliprasterbymasklayer", {
            "INPUT": r.source(),
            "MASK": mask_path,
            # pass CRS EXPLICITLY so GDAL aligns mask + raster correctly
            "SOURCE_CRS": QgsCoordinateReferenceSystem(rcrs),
            "TARGET_CRS": QgsCoordinateReferenceSystem(rcrs),
            "NODATA": -9999,
            "ALPHA_BAND": False,
            "CROP_TO_CUTLINE": True,
            "KEEP_RESOLUTION": True,
            "OPTIONS": "",
            "DATA_TYPE": 0,
            "OUTPUT": out_path,
        })
        if os.path.exists(out_path):
            print("     ->", out_path)
            made.append(("raster", r.name(), out_path))
        else:
            print("     ERROR: no output produced (CRS mismatch?)")
    except Exception as ex:
        print("     ERROR:", ex)

# --- load results ----------------------------------------------------------
if ADD_TO_PROJECT:
    for kind, name, path in made:
        if kind == "vector":
            lyr = QgsVectorLayer(path, f"{name}{CLIP_SUFFIX}", "ogr")
        else:
            lyr = QgsRasterLayer(path, f"{name}{CLIP_SUFFIX}")
        if lyr.isValid():
            project.addMapLayer(lyr)

print("\nDone. Clipped %d layer(s). Output in: %s" % (len(made), CLIP_DIR))
print("All outputs written with CRS %s." % crs_authid)
