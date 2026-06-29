# =============================================================================
# ws3_io.py  -- shared I/O helpers for the NHA WS3 QGIS pipeline.
#
# Import from any pipeline script run in the QGIS Python Console:
#     from ws3_io import release_and_delete, isnull
#
# Centralizes the two bugs that recurred across every script and machine:
#   1. Windows file locks (WinError 32) when overwriting a fixed-path output
#      that QGIS still holds open (a loaded layer) or Dropbox is syncing.
#   2. QVariant-null vs Python None when reading attribute values back from a
#      GPKG / memory layer ("%.1f" % cn crashing on a QVariant).
#
# Fix once here; every script benefits. Works identically on Linux and Windows.
# =============================================================================
import os
import time

try:
    from qgis.core import QgsProject, QgsVectorFileWriter, NULL
except Exception:
    QgsProject = None
    QgsVectorFileWriter = None
    NULL = None


def isnull(v):
    """True if v is a Python None OR a QGIS QVariant-null. Use this instead of
    'v is None' for any value read from a QGIS feature/attribute, then it is
    safe to float()/round()/format it in the else branch."""
    if v is None:
        return True
    if NULL is not None and v == NULL:
        return True
    return False


def _remove_project_layers_for(path):
    """Drop any loaded QGIS layer whose data source is `path` (releases the
    handle that otherwise locks the file on Windows)."""
    if QgsProject is None:
        return
    target = os.path.normcase(os.path.abspath(path))
    proj = QgsProject.instance()
    for lyr in list(proj.mapLayers().values()):
        try:
            src = lyr.source().split("|")[0]
            if os.path.normcase(os.path.abspath(src)) == target:
                proj.removeMapLayer(lyr.id())
        except Exception:
            pass


def release_and_delete(path, retries=8, sleep_s=1.0, layer_hint="this output"):
    """Make `path` safe to overwrite: remove any project layer holding it, then
    delete the file (+ GPKG sidecars), retrying for transient Dropbox/AV locks.
    Raises with a clear, actionable message only if it truly cannot be cleared.

    Works for both rasters (.tif) and vectors (.gpkg/.shp). Safe no-op if the
    file does not exist."""
    _remove_project_layers_for(path)

    # Prefer QGIS's silent vector delete (handles GPKG sidecars) when available.
    if QgsVectorFileWriter is not None and path.lower().endswith(".gpkg"):
        try:
            ok, _ = QgsVectorFileWriter.deleteSilently(path)
            if ok and not os.path.exists(path):
                return
        except Exception:
            pass

    sidecars = ("", "-wal", "-shm", "-journal",        # GPKG
                ".aux.xml", ".ovr")                     # raster sidecars
    for _ in range(max(1, retries)):
        # delete the main file + any sidecars present
        for ext in sidecars:
            p = path + ext if ext.startswith(("-", ".")) else path
            if os.path.exists(p):
                try:
                    os.remove(p)
                except PermissionError:
                    pass
        if not os.path.exists(path):
            return
        time.sleep(sleep_s)

    if os.path.exists(path):
        raise Exception(
            "Cannot overwrite %s -- it is still locked.\n"
            "Remove %s from the QGIS Layers panel (or restart QGIS), and pause "
            "Dropbox sync during pipeline runs, then re-run." % (path, layer_hint))