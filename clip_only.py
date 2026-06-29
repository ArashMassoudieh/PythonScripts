import os, processing
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

DEM_PATH = os.path.join(ROOT, SITE_DIR, "demlr/cliped_utm.tif")
OUT_DIR  = os.path.join(ROOT, SITE_DIR, "outputs")
os.makedirs(OUT_DIR, exist_ok=True)

# --- shared lock-safe overwrite helper (same one your pipeline uses) ---
import sys as _sys
for _sd in ("C:/Users/arash/Dropbox/Chloeta/NHA/PythonScripts",
            "C:/Users/smnfa/Dropbox/NHA/PythonScripts",
            "/home/arash/Dropbox/Chloeta/NHA/PythonScripts"):
    if os.path.isdir(_sd) and _sd not in _sys.path:
        _sys.path.insert(0, _sd)
from ws3io import release_and_delete

dem = QgsRasterLayer(DEM_PATH, "ref_dem")
if not dem.isValid():
    raise Exception("DEM invalid: " + DEM_PATH)
dem_crs = dem.crs()
e = dem.extent()
extent_str = "%f,%f,%f,%f [%s]" % (e.xMinimum(), e.xMaximum(),
                                   e.yMinimum(), e.yMaximum(), dem_crs.authid())
print("DEM CRS:", dem_crs.authid(), "\n")

# snapshot vector layers up front; skip already-clipped outputs so re-runs
# don't re-clip their own results
vectors = [l for l in QgsProject.instance().mapLayers().values()
           if isinstance(l, QgsVectorLayer) and not l.name().endswith("_clip")]
print("Found %d vector layer(s).\n" % len(vectors))

results = []
to_load = []
for v in vectors:
    name = v.name()
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    out = os.path.join(OUT_DIR, safe + "_clip.gpkg")
    try:
        # release any loaded layer pointing at this output + delete it (lock-safe)
        release_and_delete(out)
        src = v
        reproj = v.crs() != dem_crs
        if reproj:
            src = processing.run("native:reprojectlayer", {
                "INPUT": v, "TARGET_CRS": dem_crs,
                "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
        res = processing.run("native:extractbyextent", {
            "INPUT": src, "EXTENT": extent_str, "CLIP": True, "OUTPUT": out})
        cl = QgsVectorLayer(res["OUTPUT"], name + "_clip", "ogr")
        n = cl.featureCount() if cl.isValid() else -1
        print("  %-30s -> %d features  (%s)" % (name, n,
              "reprojected" if reproj else "CRS ok"))
        results.append((name, n))
        if cl.isValid():
            to_load.append(cl)
    except Exception as ex:
        print("  %-30s -> ERROR: %s" % (name, ex))
        results.append((name, -1))

# add all clipped layers to the project at the end
for cl in to_load:
    QgsProject.instance().addMapLayer(cl)

print("\n--- summary ---")
for n, c in results:
    print("  %-30s %s" % (n, c if c >= 0 else "FAILED"))
print("\nClipped layers written to %s and added to the project." % OUT_DIR)