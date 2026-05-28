"""
score_villages.py
=================
Multi-indicator scoring pipeline to identify economically dynamic villages
in India using GHS Built-up, GHS Population, VIIRS Night-time Lights, and
Facebook Relative Wealth Index.

Methodology reference:
  OECD / JRC Handbook on Constructing Composite Indicators (2008)
  — normalisation, weighting, and sensitivity checks via equal-weights.

Run from the project root:
    python3 code/score_villages.py
"""

from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterstats import zonal_stats

# ---------------------------------------------------------------------------
# Paths — all relative to project root
# ---------------------------------------------------------------------------
ROOT        = Path(__file__).resolve().parent.parent
DATA        = ROOT / "data"
OUTPUT      = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

VILLAGE_GPKG = DATA / "shrug-pc11-village-poly-gpkg" / "village_modified.gpkg"
RWI_DTA      = DATA / "shrug-facebook-rwi-dta"       / "facebook_rwi_shrid.dta"
BUILT_2020   = DATA / "GHS_BUILT_S_2020_India_clean.tif"
BUILT_2025   = DATA / "GHS_BUILT_S_2025_India_clean.tif"
POP_2020     = DATA / "GHS_POP" / "merged" / "GHS_POP_2020_India_clean_merged.tif"
POP_2025     = DATA / "GHS_POP" / "merged" / "GHS_POP_2025_India_clean_merged.tif"
NTL_2021     = DATA / "VIIRS"   / "VIIRS_NTL_2021_India.tif"
NTL_2025     = DATA / "VIIRS"   / "VIIRS_NTL_2025_India.tif"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log_step(msg: str) -> None:
    print(f"\n{'─'*60}\n{msg}\n{'─'*60}")


def minmax(series: pd.Series) -> pd.Series:
    """Min-max normalise to [0, 1]; returns 0 if all values are equal."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (series - mn) / (mx - mn)


def zonal_mean(gdf: gpd.GeoDataFrame,
               tif_path: Path,
               col_name: str,
               batch_size: int = 50_000) -> pd.Series:
    """
    Compute mean raster value over each village polygon using rasterstats,
    processed in batches of `batch_size` to keep memory stable.

    Batching does not change results — it only prevents rasterstats from
    loading the full raster window set for 600k polygons at once.

    nodata: all rasters were exported from GEE without an explicit nodata tag
    (nodata=None). Negative VIIRS values are artefacts; we set them to NaN
    after extraction.
    """
    with rasterio.open(tif_path) as src:
        nodata = src.nodata   # None for all GEE exports

    n       = len(gdf)
    results = []
    n_batches = (n + batch_size - 1) // batch_size

    for i in range(n_batches):
        lo, hi = i * batch_size, min((i + 1) * batch_size, n)
        batch  = gdf.iloc[lo:hi]
        stats  = zonal_stats(batch, str(tif_path),
                             stats=["mean"], nodata=nodata,
                             all_touched=False)
        results.extend([r["mean"] for r in stats])
        print(f"    {col_name}: batch {i+1}/{n_batches}  "
              f"({hi:,}/{n:,} polygons)", flush=True)

    vals = np.array(results, dtype=float)
    vals[~np.isfinite(vals)] = np.nan
    vals[vals < 0]           = np.nan          # clip VIIRS noise artefacts
    return pd.Series(vals, index=gdf.index, name=col_name)


# ===========================================================================
# STEP 1 — Load and clean village polygons
# ===========================================================================
log_step("STEP 1 — Load and clean village polygons")

villages = gpd.read_file(VILLAGE_GPKG)
n_raw = len(villages)
print(f"Loaded {n_raw:,} villages")

# Construct shrid2 — IDs are already zero-padded strings in this file
# (e.g. state='01', district='001', subdistrict='00001', village='000001')
# so simple concatenation matches the '11-01-001-00001-000001' format used
# in all SHRUG tabular datasets.
villages["shrid2"] = (
    "11-"
    + villages["pc11_state_id"] + "-"
    + villages["pc11_district_id"] + "-"
    + villages["pc11_subdistrict_id"] + "-"
    + villages["pc11_town_village_id"]
)

# Drop unnamed villages — they cannot be meaningfully labelled in outputs
villages = villages[villages["town_village_name"].notna()].copy()
print(f"After dropping unnamed villages: {len(villages):,} (dropped {n_raw - len(villages):,})")

# Drop district '000' — these are placeholder / unassigned records
before = len(villages)
villages = villages[villages["pc11_district_id"] != "000"].copy()
print(f"After dropping district=000:     {len(villages):,} (dropped {before - len(villages):,})")

# Ensure EPSG:4326 — required so CRS matches rasters without reprojection
if villages.crs is None or villages.crs.to_epsg() != 4326:
    villages = villages.set_crs("EPSG:4326") if villages.crs is None \
               else villages.to_crs("EPSG:4326")
print(f"CRS: {villages.crs}")

n_after_clean = len(villages)


# ===========================================================================
# STEP 2 — Zonal statistics (mean over village polygon)
# ===========================================================================
log_step("STEP 2 — Zonal statistics (mean over village polygon)")

# All six rasters are EPSG:4326, matching the villages GeoDataFrame.
# Processed in batches of 50k to keep memory stable across 648k polygons.
rasters = [
    (BUILT_2020, "built_2020"),
    (BUILT_2025, "built_2025"),
    (POP_2020,   "pop_2020"),
    (POP_2025,   "pop_2025"),
    (NTL_2021,   "ntl_2021"),
    (NTL_2025,   "ntl_2025"),
]

for tif_path, col_name in rasters:
    print(f"  → {col_name}  ({tif_path.name})")
    villages[col_name] = zonal_mean(villages, tif_path, col_name)

print("\nZonal stats complete. Sample:")
print(villages[["shrid2", "built_2020", "built_2025",
                "pop_2020",   "pop_2025",
                "ntl_2021",   "ntl_2025"]].head(3).to_string())


# ===========================================================================
# STEP 3 — Join Facebook RWI
# ===========================================================================
log_step("STEP 3 — Join Facebook RWI")

rwi = pd.read_stata(RWI_DTA, columns=["shrid2", "facebook_mean_rwi"])
villages = villages.merge(rwi, on="shrid2", how="left")

matched = villages["facebook_mean_rwi"].notna().sum()
print(f"RWI matched: {matched:,} / {len(villages):,} villages "
      f"({matched/len(villages)*100:.1f}%)")


# ===========================================================================
# STEP 4 — Compute log-ratio change signals
# ===========================================================================
log_step("STEP 4 — Compute log-ratio change signals")

# Log-ratio: log1p(y) - log1p(x) is mathematically equivalent to log((y+1)/(x+1)).
# This is strictly bounded regardless of how small the base value is — a village
# with built_2020=0.0001 and built_2025=100 gets log1p(100)-log1p(0.0001) ≈ 4.6,
# not 99,999,900%. No epsilon hacks, no p99 capping needed.
villages["ntl_log_change"]   = np.log1p(villages["ntl_2025"])   - np.log1p(villages["ntl_2021"])
villages["built_log_change"] = np.log1p(villages["built_2025"]) - np.log1p(villages["built_2020"])
villages["pop_log_change"]   = np.log1p(villages["pop_2025"])   - np.log1p(villages["pop_2020"])

print("Log-ratio change signal summary:")
print(villages[["ntl_log_change", "built_log_change", "pop_log_change"]]
      .describe().round(4).to_string())


# ===========================================================================
# STEP 5 — Pre-filter
# ===========================================================================
log_step("STEP 5 — Pre-filter")

n_before = len(villages)

# Filter 1: fully dark — zero NTL in both years contributes no growth signal.
mask_dark = (villages["ntl_2021"].fillna(0) == 0) & (villages["ntl_2025"].fillna(0) == 0)
villages = villages[~mask_dark].copy()
print(f"Dropped fully dark (ntl=0 both years): {mask_dark.sum():,} → {len(villages):,} remain")

# Filter 2: no RWI — welfare dimension is required for composite scoring.
mask_no_rwi = villages["facebook_mean_rwi"].isna()
villages = villages[~mask_no_rwi].copy()
print(f"Dropped no RWI:                        {mask_no_rwi.sum():,} → {len(villages):,} remain")

# Filter 3: all raster values NaN — village has no usable signal at all.
raster_cols = ["built_2020","built_2025","pop_2020","pop_2025","ntl_2021","ntl_2025"]
mask_all_nan = villages[raster_cols].isna().all(axis=1)
villages = villages[~mask_all_nan].copy()
print(f"Dropped all-raster-NaN:                {mask_all_nan.sum():,} → {len(villages):,} remain")

n_after_filter = len(villages)
print(f"\nTotal dropped in pre-filter: {n_before - n_after_filter:,}")


# ===========================================================================
# STEP 6 — Multi-indicator corroboration filter (OECD 2008, §3.3)
# ===========================================================================
log_step("STEP 6 — Multi-indicator corroboration filter")

# Requiring growth in at least 2 of 3 independent indicators reduces the
# risk of selecting a village based on noise in a single sensor.
# Growth is defined as log-ratio > 0, i.e. value increased year-on-year.
villages["ntl_grew"]   = (villages["ntl_log_change"]   > 0).astype(int)
villages["built_grew"] = (villages["built_log_change"]  > 0).astype(int)
villages["pop_grew"]   = (villages["pop_log_change"]    > 0).astype(int)
villages["signals_growing"] = (
    villages["ntl_grew"] + villages["built_grew"] + villages["pop_grew"]
)

# Retain as a quality-flag column for downstream inspection; actual filter
# is applied after scoring (Step 8) so all rows have scores in the full CSV.
n_corroborated = (villages["signals_growing"] >= 2).sum()
print(f"Villages with ≥2 growing signals: {n_corroborated:,} "
      f"({n_corroborated/len(villages)*100:.1f}% of pre-filtered set)")


# ===========================================================================
# STEP 7 — Normalise and score
# ===========================================================================
log_step("STEP 7 — Normalise and score")

# Log-ratio changes are already on a log scale — no further log transform needed.
# Clip negatives to 0: decline treated as neutral, not penalised.
# Min-max normalise directly to [0, 1].
villages["ntl_score"]   = minmax(villages["ntl_log_change"].clip(lower=0))
villages["built_score"] = minmax(villages["built_log_change"].clip(lower=0))
villages["pop_score"]   = minmax(villages["pop_log_change"].clip(lower=0))

# RWI is already on a stable cardinal scale (-∞ to ∞); log-transform would
# distort its meaning, so we normalise directly.
villages["rwi_score"] = minmax(villages["facebook_mean_rwi"])

# --- Primary: weighted composite (reflects data quality hierarchy) ----------
# NTL has finest spatial resolution and best temporal coverage → highest weight.
# Built-up is a direct physical proxy for economic activity → second.
# Population growth is noisier at village level → lower weight.
# RWI is point-in-time, not a change signal → smallest weight.
villages["composite_score"] = (
      0.40 * villages["ntl_score"]
    + 0.35 * villages["built_score"]
    + 0.15 * villages["pop_score"]
    + 0.10 * villages["rwi_score"]
)

# --- Secondary: equal weights (sensitivity check per OECD §6.2) ------------
villages["composite_score_equal"] = (
      0.25 * villages["ntl_score"]
    + 0.25 * villages["built_score"]
    + 0.25 * villages["pop_score"]
    + 0.25 * villages["rwi_score"]
)

print("Composite score summary (all pre-filtered villages):")
print(villages[["composite_score", "composite_score_equal"]].describe().round(4).to_string())


# ===========================================================================
# STEP 8 — State-stratified selection → top 100
# ===========================================================================
log_step("STEP 8 — State-stratified selection")

# Apply the corroboration filter here so the full scored dataset is preserved
# in the CSV output (Step 9) while the selection pool is quality-controlled.
candidates = villages[villages["signals_growing"] >= 2].copy()
print(f"Candidate pool (signals_growing ≥ 2): {len(candidates):,}")

# Take top 5 per state to avoid large-state dominance before the global cut.
# This implements a stratified selection consistent with OECD guidance on
# geographic representativeness in composite indicator frameworks.
top5_per_state = (
    candidates
    .sort_values("composite_score", ascending=False)
    .groupby("pc11_state_id", group_keys=False)
    .head(5)
)
print(f"After top-5-per-state:                {len(top5_per_state):,}")

# Global top 100 from the stratified pool
top100 = (
    top5_per_state
    .sort_values("composite_score", ascending=False)
    .head(100)
    .copy()
)
top100["rank"] = range(1, len(top100) + 1)

# Sensitivity check — which of the top 100 (weighted) also appear in the
# equal-weights top 100?
top100_equal = (
    candidates
    .sort_values("composite_score_equal", ascending=False)
    .groupby("pc11_state_id", group_keys=False)
    .head(5)
    .sort_values("composite_score_equal", ascending=False)
    .head(100)
)
top100_equal_shrids = set(top100_equal["shrid2"])
top100["in_equal_weights_top100"] = top100["shrid2"].isin(top100_equal_shrids)

n_overlap = top100["in_equal_weights_top100"].sum()
n_states  = top100["pc11_state_id"].nunique()

print(f"\nTop 100 results:")
print(f"  States represented:                          {n_states}")
print(f"  Villages in both weighted & equal-wt top100: {n_overlap} / 100")


# ===========================================================================
# STEP 9 — Save outputs
# ===========================================================================
log_step("STEP 9 — Save outputs")

# Full scored dataset — useful for auditing any village's scores
out_cols_full = [
    "shrid2", "town_village_name", "pc11_state_id", "pc11_district_id",
    "pc11_subdistrict_id", "pc11_town_village_id",
    "ntl_2021", "ntl_2025", "built_2020", "built_2025",
    "pop_2020", "pop_2025", "facebook_mean_rwi",
    "ntl_log_change", "built_log_change", "pop_log_change",
    "signals_growing", "ntl_grew", "built_grew", "pop_grew",
    "ntl_score", "built_score", "pop_score", "rwi_score",
    "composite_score", "composite_score_equal",
]
villages[out_cols_full].to_csv(OUTPUT / "all_villages_scored.csv", index=False)
print(f"Saved: output/all_villages_scored.csv  ({len(villages):,} rows)")

# Top 100 CSV — add sensitivity flag
out_cols_top = out_cols_full + ["rank", "in_equal_weights_top100"]
top100[out_cols_top].to_csv(OUTPUT / "top100_villages.csv", index=False)
print(f"Saved: output/top100_villages.csv      ({len(top100)} rows)")

# Top 100 GeoPackage — retains geometry for mapping in QGIS / notebooks
top100.to_file(OUTPUT / "top100_villages.gpkg", driver="GPKG")
print(f"Saved: output/top100_villages.gpkg     ({len(top100)} rows)")


# ===========================================================================
# STEP 10 — Console summary
# ===========================================================================
log_step("STEP 10 — Summary")

print(f"Villages loaded (raw):               {n_raw:,}")
print(f"After name / district-000 filter:    {n_after_clean:,}")
print(f"After pre-filter (dark/RWI/base):    {n_after_filter:,}")
print(f"Candidate pool (≥2 signals growing): {len(candidates):,}")
print(f"After top-5-per-state:               {len(top5_per_state):,}")
print(f"Final top 100:")
print(f"  States represented:                {n_states}")
print(f"  In equal-weights top 100 as well:  {n_overlap} / 100")

print("\nTop 10 villages:")
display_cols = ["rank", "town_village_name", "pc11_state_id",
                "composite_score", "in_equal_weights_top100"]
print(top100[display_cols].head(10).to_string(index=False))
