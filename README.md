# Top Economic Centre Assessment
Finding India's top economically growing villages using multi-indicator remote sensing and socioeconomic data.

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

| File | Description |
|---|---|
| `output/all_villages_scored.csv` | All 585,257 villages with raster extractions, log-change values, corroboration flags, and normalised scores |
| `output/top100_villages.csv` | Top 100 villages with all score components, ranks, and equal-weights sensitivity flag |
| `output/top100_villages.gpkg` | Top 100 with original polygon geometry for mapping |
