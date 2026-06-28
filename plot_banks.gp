# =============================================================================
# plot_banks.gp  --  one PNG per cross section: profile + thalweg + bank stations
#
# Uses three data files from ras_bank_stations.py (xs_id col 1, offset col 2,
# elev col 3): xs_bank_profiles.dat, xs_bank_thalweg.dat, xs_bank_points.dat
# and xs_bank_ids.txt (space-separated list of XS ids that HAVE data -- no_data
# sections like the confluence are omitted so the loop never hits an empty XS).
#
# Run from outputs_RAS/ :
#   gnuplot plot_banks.gp
# =============================================================================
if (!exists("prof")) prof = "xs_bank_profiles.dat"
if (!exists("thal")) thal = "xs_bank_thalweg.dat"
if (!exists("bank")) bank = "xs_bank_points.dat"
if (!exists("idfile")) idfile = "xs_bank_ids.txt"
if (!exists("outdir")) outdir = "xs_plots"
system(sprintf("mkdir -p %s", outdir))

# read the list of valid XS ids (space-separated) into a string
ids = system(sprintf("cat %s", idfile))
nids = words(ids)

set datafile separator whitespace
set terminal pngcairo size 900,520 enhanced font "Helvetica,11"
set grid
set xlabel "offset from centerline (m)"
set ylabel "elevation (m)"
set xrange [-60:60]
set key top center

do for [k=1:nids] {
    i = int(word(ids, k))
    set output sprintf("%s/xs_bank_%03d.png", outdir, i)
    set title sprintf("AZ12-100  cross section %d  --  thalweg + bank stations", i)
    plot \
        prof using ($1==i ? $2 : 1/0):3 with lines lw 2 lc rgb "#444444" title "ground", \
        thal using ($1==i ? $2 : 1/0):3 with points pt 11 ps 2.4 lc rgb "#1F3864" title "thalweg", \
        bank using ($1==i ? $2 : 1/0):3 with points pt 7 ps 2.0 lc rgb "#C0392B" title "bank stations"
    unset output
}
print sprintf("wrote %d cross-section PNG(s) to %s/", nids, outdir)
