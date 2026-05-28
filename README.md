# Top Economic Centre Assessment
Finding India's top economically growing villages using multi-indicator remote sensing and socioeconomic data.

---

## Code

| File | Description |
|---|---|
| `code/score_villages.py` | Main scoring pipeline. Loads village polygons, runs batched zonal statistics across 6 rasters, joins Facebook RWI, computes log-ratio change signals, applies pre-filters and corroboration filter, normalises and scores with both weighted and equal-weight composites, applies state-stratified selection, and saves all outputs. Run from the project root: `python3 code/score_villages.py` |
| `code/map_top100.py` | Spatial mapping script. Reads the top 100 outputs and generates 6 maps comparing the weighted and equal-weights scoring methods, including side-by-side India maps, overlap/divergence map, state breakdown bar chart, and score scatter plot. Uses contextily (CartoDB Positron basemap) and 30km polygon buffers for visibility at India scale. Run from the project root: `python3 code/map_top100.py` |
| `code/visualise_join_data.ipynb` | Exploratory data analysis notebook. Contains EDA sections for all five datasets: Facebook RWI (distributions, violin, error, cell counts), GHS-POP 2020 & 2025 (maps, change maps, distributions), GHS Built-up 2020 & 2025, VIIRS NTL 2021 & 2025, and Antyodaya (521k rows, 169 columns). All figures are saved to `output/`. |
| `code/gee_ghsl.ipynb` | Google Earth Engine notebook used to download and export the GHS-BUILT-S and GHS-POP rasters for India, clipped and exported as GeoTIFFs to Google Drive. |
| `code/merge_ghsl.py` | Utility script to merge GEE-exported GHS tile splits (each raster is exported by GEE as multiple tile files) into single merged GeoTIFFs using rasterio. Run once after downloading tiles from Google Drive. |

---

## Methodology: Identifying Emerging Economic Centres in Rural India

### Data Sources

| Dataset | Source | Resolution | Years |
|---|---|---|---|
| Village polygons | SHRUG PC11 village boundaries (v2.1, Development Data Lab) | Village-level | 2011 census boundaries |
| Built-up surface area | GHS-BUILT-S (Global Human Settlement Layer, JRC) | 100m, EPSG:4326 | 2020, 2025 |
| Population | GHS-POP (Global Human Settlement Layer, JRC) | 100m, EPSG:4326 | 2020, 2025 |
| Nighttime lights | VIIRS Annual VNL v2.2 (Earth Observation Group) | 500m, EPSG:4326 | 2021, 2025 |
| Relative Wealth Index | Facebook/Meta RWI (SHRUG shrid-level tabular, Development Data Lab) | Subvillage grid cells | ~2021 |

---

### Step 1 — Village Geometry

Village polygons were loaded from the SHRUG PC11 village GeoPackage (`village_modified.gpkg`, 648,012 polygons). Each village carries a unique `shrid2` identifier in the format `11-{state}-{district}-{subdistrict}-{village}` (all components zero-padded), used as the join key throughout. Two cleaning filters were applied upfront: villages with no name were dropped, and records with `district_id = "000"` (placeholder/unassigned) were removed.

---

### Step 2 — Raster Extraction (Zonal Statistics)

For each of the six rasters, the mean pixel value within each village polygon was extracted using `rasterstats.zonal_stats()` with `stats=["mean"]` and `all_touched=False`. Due to memory constraints, polygons were processed in batches of 50,000. Pixels with `nodata` values were excluded. Any extracted value that was non-finite or negative was set to `NaN`.

This yields six village-level columns: `built_2020`, `built_2025`, `pop_2020`, `pop_2025`, `ntl_2021`, `ntl_2025`.

---

### Step 3 — Facebook RWI Join

The Facebook Relative Wealth Index was aggregated to village level by computing the mean RWI across all grid cells within each village polygon, joined on the `shrid2` key. The resulting column is `facebook_mean_rwi`.

---

### Step 4 — Change Signals (Log-Ratio)

Percentage-change is inappropriate when base values are near zero (it produces extreme or undefined values). Instead, change was computed as the log-ratio:

```
change = log(1 + value_end) − log(1 + value_start)
```

This is symmetric, defined at zero, and naturally compresses extreme outliers. Three change columns were produced: `ntl_log_change`, `built_log_change`, `pop_log_change`.

---

### Step 5 — Pre-filters

Three filters were applied to remove uninformative villages before scoring:

1. **Persistently dark** — villages where `ntl_2021 = 0` and `ntl_2025 = 0`
2. **No RWI** — villages with no Facebook RWI coverage
3. **All rasters NaN** — villages where all six raster extractions returned `NaN`

---

### Step 6 — Multi-Indicator Corroboration Filter *(OECD 2008, §3.3)*

For each village, a binary growth indicator was computed for each of the three raster signals (growth defined as log-ratio > 0):

```
signals_growing = ntl_grew + built_grew + pop_grew   (range: 0–3)
```

This corroboration count is retained as a quality flag in the output. It is applied as a **hard filter at selection time (Step 8)**: only villages with `signals_growing ≥ 2` enter the top 100 candidate pool. This guards against selecting a village on the basis of a strong signal in a single noisy sensor — a genuine emerging centre should show coordinated growth across multiple independent data sources.

---

### Step 7 — Normalisation and Scoring

Negative log-change values (decline) were clipped to zero — decline is treated as neutral, not penalised. Each dimension was then min-max normalised to [0, 1] across all pre-filtered villages (OECD Handbook on Composite Indicators, 2008):

```
score_i = (x_i − min(x)) / (max(x) − min(x))
```

**Weighted composite** (theory-driven weights):

| Indicator | Weight | Rationale |
|---|---|---|
| Nighttime lights change | 40% | Strongest proxy for economic activity |
| Built-up surface change | 35% | Direct measure of physical development |
| Population change | 15% | Demand-side growth signal |
| Relative Wealth Index | 10% | Baseline wealth context (not a change signal) |

**Equal-weights composite** (sensitivity check, OECD §6.2): each dimension weighted 25%.

---

### Step 8 — State-Stratified Selection

Selection proceeded in two stages:

1. Filter to villages with `signals_growing ≥ 2` (corroboration requirement)
2. Within each state, retain the **top 5** by weighted composite score
3. From this stratified pool, take the **global top 100** by score

Step 2 prevents large states (Uttar Pradesh, Madhya Pradesh, Rajasthan) from monopolising the national list while still ranking entirely by economic signal strength.

---

### Outputs

#### Data files

| File | Description |
|---|---|
| `output/all_villages_scored.csv.gz` | All 585,257 villages with raster extractions, log-change values, corroboration flags, and normalised scores (gzip-compressed) |
| `output/top100_villages.csv` | Top 100 villages with all score components, ranks, and equal-weights sensitivity flag |
| `output/top100_villages.gpkg` | Top 100 with original polygon geometry for mapping (weighted composite) |
| `output/top100_equal_weights.gpkg` | Top 100 with original polygon geometry for mapping (equal-weights composite) |

#### Maps — Top 100 spatial comparison

| File | Description |
|---|---|
| `output/map_01_weighted_top100.png` | India map: top 100 villages by weighted composite score |
| `output/map_02_equal_weights_top100.png` | India map: top 100 villages by equal-weights composite score |
| `output/map_03_side_by_side.png` | Side-by-side comparison of both scoring methods |
| `output/map_04_overlap_divergence.png` | Villages unique to each method vs. overlap between both |
| `output/map_05_state_breakdown.png` | Bar chart of top 100 villages per state by method |
| `output/map_06_score_scatter.png` | Scatter plot of weighted vs. equal-weight scores |

#### EDA plots — Nighttime Lights (VIIRS)

| File | Description |
|---|---|
| `output/ntl_01_maps_2021_2025.png` | Side-by-side India maps of NTL 2021 and 2025 |
| `output/ntl_02_change_absolute.png` | Absolute change in NTL (2021–2025) |
| `output/ntl_03_change_pct.png` | Percentage change in NTL (2021–2025) |
| `output/ntl_04_shrid_distribution.png` | Distribution of shrid-level NTL values |
| `output/ntl_05_cdf_scatter.png` | CDF and scatter of NTL values |

#### EDA plots — GHS Built-up Surface

| File | Description |
|---|---|
| `output/blt_01_maps_2020_2025.png` | Side-by-side India maps of built-up area 2020 and 2025 |
| `output/blt_02_change_absolute.png` | Absolute change in built-up surface (2020–2025) |
| `output/blt_03_change_pct.png` | Percentage change in built-up surface (2020–2025) |
| `output/blt_04_distribution.png` | Distribution of built-up values |

#### EDA plots — GHS Population

| File | Description |
|---|---|
| `output/pop_01_maps_2020_2025.png` | Side-by-side India maps of population 2020 and 2025 |
| `output/pop_02_change_absolute.png` | Absolute change in population (2020–2025) |
| `output/pop_03_change_pct.png` | Percentage change in population (2020–2025) |
| `output/pop_04_distributions.png` | Distribution of population values |
| `output/pop_05_overlay.png` | Population overlay on India basemap |

#### EDA plots — Facebook Relative Wealth Index

| File | Description |
|---|---|
| `output/rwi_01_mean_distribution.png` | Distribution of mean RWI values across villages |
| `output/rwi_02_range.png` | Range of RWI values per village |
| `output/rwi_03_violin.png` | Violin plot of RWI by state |
| `output/rwi_04_error.png` | RWI uncertainty / error distribution |
| `output/rwi_05_num_cells.png` | Number of RWI grid cells per village |
| `output/village_01_rwi_choropleth.png` | Choropleth map of village-level mean RWI across India |
| `output/village_02_rwi_distribution.png` | Distribution of village-level RWI |

#### EDA plots — Antyodaya (SHRUG socioeconomic dataset)

| File | Description |
|---|---|
| `output/anty_01_missing.png` | Missing data overview across Antyodaya variables |
| `output/anty_02_demographics.png` | Demographic indicators distribution |
| `output/anty_03_agriculture.png` | Agricultural indicators distribution |
| `output/anty_04_infrastructure.png` | Infrastructure indicators distribution |
| `output/anty_05_education.png` | Education indicators distribution |
| `output/anty_06_health.png` | Health indicators distribution |
| `output/anty_07_welfare.png` | Welfare indicators distribution |
| `output/anty_08_correlation.png` | Correlation matrix across Antyodaya indicators |
