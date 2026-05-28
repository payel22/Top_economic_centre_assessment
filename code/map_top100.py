"""
map_top100.py  —  v2
=====================
Spatial maps comparing weighted vs equal-weights top-100 villages.
Villages rendered as buffered polygons (25 km halo) so they are visible
at all-India scale. Tight India bounds, high-contrast colours.

Run from the project root:
    python3 code/map_top100.py
"""

from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from matplotlib.lines import Line2D
import contextily as ctx

ROOT   = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"

# ── India bounds in EPSG:3857 (Web Mercator) ────────────────────────────────
INDIA_XLIM = (7_480_000, 10_500_000)
INDIA_YLIM = (   700_000,  4_550_000)

# ── Colours ──────────────────────────────────────────────────────────────────
C_WEIGHTED = "#D62828"   # vivid red
C_EQUAL    = "#1D3557"   # deep navy
C_BOTH     = "#2A9D8F"   # teal-green
C_EDGE     = "white"

BUFFER_M   = 30_000      # 30 km buffer so polygons are visible at India scale

STATE_NAMES = {
    "01":"J&K","02":"HP","03":"Punjab","04":"Chandigarh","05":"Uttarakhand",
    "06":"Haryana","07":"Delhi","08":"Rajasthan","09":"UP","10":"Bihar",
    "11":"Sikkim","12":"Arunachal","13":"Nagaland","14":"Manipur","15":"Mizoram",
    "16":"Tripura","17":"Meghalaya","18":"Assam","19":"West Bengal",
    "20":"Jharkhand","21":"MP","22":"Chhattisgarh","23":"Odisha","24":"Gujarat",
    "25":"Daman & Diu","26":"D&NH","27":"Maharashtra","28":"AP","29":"Karnataka",
    "30":"Goa","31":"Lakshadweep","32":"Kerala","33":"Tamil Nadu",
    "34":"Puducherry","35":"A&N Islands","36":"Telangana",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_and_prep():
    """Load both top-100 sets, buffer polygons, tag overlap category."""
    w  = gpd.read_file(OUTPUT / "top100_villages.gpkg").to_crs(3857)
    eq = gpd.read_file(OUTPUT / "top100_equal_weights.gpkg").to_crs(3857)

    # Buffer polygons so they are visible at India scale
    w["geometry"]  = w.geometry.buffer(BUFFER_M)
    eq["geometry"] = eq.geometry.buffer(BUFFER_M)

    w_shrids  = set(w["shrid2"])
    eq_shrids = set(eq["shrid2"])

    w["category"]  = w["shrid2"].apply(lambda s: "both" if s in eq_shrids else "weighted_only")
    eq["category"] = eq["shrid2"].apply(lambda s: "both" if s in w_shrids  else "equal_only")
    w["state_label"]  = w["pc11_state_id"].map(STATE_NAMES).fillna(w["pc11_state_id"])
    eq["state_label"] = eq["pc11_state_id"].map(STATE_NAMES).fillna(eq["pc11_state_id"])

    print(f"Weighted top100   : {len(w)}")
    print(f"Equal-wt top100   : {len(eq)}")
    print(f"In both           : {len(w_shrids & eq_shrids)}")
    print(f"Weighted only     : {len(w_shrids - eq_shrids)}")
    print(f"Equal-weights only: {len(eq_shrids - w_shrids)}")
    return w, eq, w_shrids, eq_shrids


def set_india_bounds(ax):
    ax.set_xlim(*INDIA_XLIM)
    ax.set_ylim(*INDIA_YLIM)


def add_basemap(ax, zoom=6):
    try:
        ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=zoom, alpha=0.55)
    except Exception:
        ax.set_facecolor("#f0f0f0")


def label_villages(ax, gdf, col_score, n=12, fontsize=7):
    """Annotate top-n villages by score with name labels."""
    for _, row in gdf.nlargest(n, col_score).iterrows():
        cx = row.geometry.centroid.x
        cy = row.geometry.centroid.y
        ax.annotate(
            row["town_village_name"],
            xy=(cx, cy), xytext=(9, 5), textcoords="offset points",
            fontsize=fontsize, fontweight="bold", color="#111111",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", alpha=0.85,
                      ec="grey", lw=0.4),
            arrowprops=dict(arrowstyle="-", color="grey", lw=0.5),
        )


def style_ax(ax, title, fontsize=13):
    ax.set_axis_off()
    ax.set_title(title, fontsize=fontsize, fontweight="bold", pad=8,
                 color="#1a1a1a")


# ═══════════════════════════════════════════════════════════════════════════
# MAP 1 — Weighted composite top 100
# ═══════════════════════════════════════════════════════════════════════════
def map_weighted(w):
    fig, ax = plt.subplots(figsize=(13, 14), facecolor="white")

    norm  = mcolors.Normalize(vmin=w["composite_score"].min(),
                               vmax=w["composite_score"].max())
    cmap  = cm.YlOrRd
    colors = [cmap(norm(v)) for v in w["composite_score"]]

    w.plot(ax=ax, color=colors, edgecolor="white", linewidth=0.6,
           zorder=3, alpha=0.92)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.022, pad=0.01, shrink=0.6)
    cbar.set_label("Composite score (weighted)", fontsize=10)
    cbar.ax.tick_params(labelsize=9)

    label_villages(ax, w, "composite_score", n=15)
    set_india_bounds(ax)
    add_basemap(ax, zoom=6)
    style_ax(ax, "Top 100 Villages — Weighted Composite\n"
                 "NTL 40%  |  Built-up 35%  |  Pop 15%  |  RWI 10%")

    plt.tight_layout()
    fig.savefig(OUTPUT / "map_01_weighted_top100.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: map_01_weighted_top100.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAP 2 — Equal-weights top 100
# ═══════════════════════════════════════════════════════════════════════════
def map_equal(eq):
    fig, ax = plt.subplots(figsize=(13, 14), facecolor="white")

    norm  = mcolors.Normalize(vmin=eq["composite_score_equal"].min(),
                               vmax=eq["composite_score_equal"].max())
    cmap  = cm.Blues
    colors = [cmap(norm(v)) for v in eq["composite_score_equal"]]

    eq.plot(ax=ax, color=colors, edgecolor="white", linewidth=0.6,
            zorder=3, alpha=0.92)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.022, pad=0.01, shrink=0.6)
    cbar.set_label("Composite score (equal weights)", fontsize=10)
    cbar.ax.tick_params(labelsize=9)

    label_villages(ax, eq, "composite_score_equal", n=15)
    set_india_bounds(ax)
    add_basemap(ax, zoom=6)
    style_ax(ax, "Top 100 Villages — Equal Weights\n"
                 "NTL 25%  |  Built-up 25%  |  Pop 25%  |  RWI 25%")

    plt.tight_layout()
    fig.savefig(OUTPUT / "map_02_equal_weights_top100.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: map_02_equal_weights_top100.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAP 3 — Side-by-side comparison
# ═══════════════════════════════════════════════════════════════════════════
def map_side_by_side(w, eq):
    fig, axes = plt.subplots(1, 2, figsize=(26, 14), facecolor="white")

    for ax, gdf, col, cmap_name, subtitle in [
        (axes[0], w,  "composite_score",      "YlOrRd",
         "Weighted  (NTL 40 | BLT 35 | POP 15 | RWI 10)"),
        (axes[1], eq, "composite_score_equal", "Blues",
         "Equal weights  (25 each)"),
    ]:
        cmap = cm.get_cmap(cmap_name)
        norm = mcolors.Normalize(vmin=gdf[col].min(), vmax=gdf[col].max())
        colors = [cmap(norm(v)) for v in gdf[col]]

        gdf.plot(ax=ax, color=colors, edgecolor="white",
                 linewidth=0.6, zorder=3, alpha=0.92)

        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, fraction=0.022, pad=0.01, shrink=0.55)
        cbar.set_label("Score", fontsize=9)

        label_villages(ax, gdf, col, n=12, fontsize=6.5)
        set_india_bounds(ax)
        add_basemap(ax, zoom=6)
        style_ax(ax, f"Top 100 — {subtitle}", fontsize=11)

    fig.suptitle("Method Comparison: Weighted vs Equal-Weights Scoring",
                 fontsize=15, fontweight="bold", y=1.01, color="#1a1a1a")
    plt.tight_layout()
    fig.savefig(OUTPUT / "map_03_side_by_side.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: map_03_side_by_side.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAP 4 — Overlap / divergence
# ═══════════════════════════════════════════════════════════════════════════
def map_overlap(w, eq, w_shrids, eq_shrids):
    both_mask_w  = w["category"]  == "both"
    w_only       = w[~both_mask_w]
    both_gdf     = w[both_mask_w]
    eq_only      = eq[eq["category"] == "equal_only"]

    n_both    = both_mask_w.sum()
    n_w_only  = (~both_mask_w).sum()
    n_eq_only = len(eq_only)

    fig, ax = plt.subplots(figsize=(13, 14), facecolor="white")

    # Plot in order: equal-only, weighted-only, both (on top)
    if len(eq_only):
        eq_only.plot(ax=ax, color=C_EQUAL,    edgecolor="white",
                     linewidth=0.8, zorder=3, alpha=0.88)
    if len(w_only):
        w_only.plot(ax=ax,  color=C_WEIGHTED, edgecolor="white",
                    linewidth=0.8, zorder=4, alpha=0.88)
    if len(both_gdf):
        both_gdf.plot(ax=ax, color=C_BOTH,   edgecolor="white",
                      linewidth=0.8, zorder=5, alpha=0.92)

    # Label top villages from each category
    for gdf, col, n in [
        (both_gdf, "composite_score",       8),
        (w_only,   "composite_score",       5),
        (eq_only,  "composite_score_equal", 5),
    ]:
        if len(gdf):
            label_villages(ax, gdf, col, n=n, fontsize=6.5)

    legend_elements = [
        mpatches.Patch(facecolor=C_BOTH,     edgecolor="white",
                       label=f"In both top-100s — robust picks ({n_both})"),
        mpatches.Patch(facecolor=C_WEIGHTED, edgecolor="white",
                       label=f"Weighted method only ({n_w_only})"),
        mpatches.Patch(facecolor=C_EQUAL,    edgecolor="white",
                       label=f"Equal-weights method only ({n_eq_only})"),
    ]
    ax.legend(handles=legend_elements, loc="lower left", fontsize=10,
              framealpha=0.95, edgecolor="#cccccc", title="Method membership",
              title_fontsize=10)

    set_india_bounds(ax)
    add_basemap(ax, zoom=6)
    style_ax(ax, "Weighted vs Equal-Weights: Overlap & Divergence\n"
                 "Teal = robust  |  Red = weighted-only  |  Navy = equal-wt-only")

    plt.tight_layout()
    fig.savefig(OUTPUT / "map_04_overlap_divergence.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: map_04_overlap_divergence.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAP 5 — State breakdown bar chart
# ═══════════════════════════════════════════════════════════════════════════
def map_state_breakdown(w, eq):
    w_counts  = w["state_label"].value_counts().rename("Weighted")
    eq_counts = eq["state_label"].value_counts().rename("Equal weights")
    df = pd.concat([w_counts, eq_counts], axis=1).fillna(0).astype(int)
    df = df.sort_values("Weighted", ascending=True)

    fig, ax = plt.subplots(figsize=(10, max(7, len(df) * 0.44)),
                            facecolor="white")
    y = np.arange(len(df))
    h = 0.35

    ax.barh(y + h/2, df["Weighted"],      h, color=C_WEIGHTED,
            alpha=0.85, label="Weighted", edgecolor="white")
    ax.barh(y - h/2, df["Equal weights"], h, color=C_EQUAL,
            alpha=0.85, label="Equal weights", edgecolor="white")

    # Value labels
    for i, (_, row) in enumerate(df.iterrows()):
        if row["Weighted"] > 0:
            ax.text(row["Weighted"] + 0.05, i + h/2, str(int(row["Weighted"])),
                    va="center", fontsize=8, color=C_WEIGHTED, fontweight="bold")
        if row["Equal weights"] > 0:
            ax.text(row["Equal weights"] + 0.05, i - h/2,
                    str(int(row["Equal weights"])),
                    va="center", fontsize=8, color=C_EQUAL, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(df.index, fontsize=9)
    ax.set_xlabel("Number of villages in top 100", fontsize=10)
    ax.set_title("Top-100 representation by state\nWeighted vs Equal Weights",
                 fontsize=12, fontweight="bold", color="#1a1a1a")
    ax.legend(fontsize=10, framealpha=0.9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_xlim(0, df.max().max() + 1.2)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.set_facecolor("white")

    plt.tight_layout()
    fig.savefig(OUTPUT / "map_05_state_breakdown.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: map_05_state_breakdown.png")


# ═══════════════════════════════════════════════════════════════════════════
# MAP 6 — Score scatter: weighted vs equal-weights
# ═══════════════════════════════════════════════════════════════════════════
def map_score_scatter(w, eq, w_shrids, eq_shrids):
    # Build a combined dataframe of all unique villages across both lists
    w_df  = w[["shrid2","town_village_name","composite_score",
                "composite_score_equal","rank"]].copy()
    eq_df = eq[["shrid2","composite_score_equal"]].copy()

    all_df = pd.concat([
        w_df.assign(in_w=True,  in_eq=w_df["shrid2"].isin(eq_shrids)),
        eq_df.assign(in_w=eq_df["shrid2"].isin(w_shrids), in_eq=True,
                     town_village_name=None, composite_score=None, rank=None),
    ]).drop_duplicates("shrid2")

    # Fill composite_score for eq-only from the full CSV
    full = pd.read_csv(ROOT / "output" / "all_villages_scored.csv",
                       usecols=["shrid2","composite_score","composite_score_equal"])
    all_df = all_df.merge(full.rename(columns={
        "composite_score":"cs_full","composite_score_equal":"cse_full"}),
        on="shrid2", how="left")
    all_df["composite_score"]       = all_df["composite_score"].fillna(all_df["cs_full"])
    all_df["composite_score_equal"] = all_df["composite_score_equal"].fillna(all_df["cse_full"])
    all_df = all_df.dropna(subset=["composite_score","composite_score_equal"])

    def cat(row):
        if row["in_w"] and row["in_eq"]: return C_BOTH
        if row["in_w"]:                  return C_WEIGHTED
        return C_EQUAL

    colors = all_df.apply(cat, axis=1)

    fig, ax = plt.subplots(figsize=(10, 9), facecolor="white")

    ax.scatter(
        all_df["composite_score"],
        all_df["composite_score_equal"],
        c=colors, alpha=0.85, s=80,
        edgecolors="white", linewidths=0.5, zorder=3
    )

    # Diagonal line
    lims = [all_df[["composite_score","composite_score_equal"]].min().min() - 0.01,
            all_df[["composite_score","composite_score_equal"]].max().max() + 0.01]
    ax.plot(lims, lims, "--", color="grey", lw=0.9, alpha=0.6, label="y = x  (perfect agreement)")
    ax.set_xlim(lims); ax.set_ylim(lims)

    # Label top 10 by weighted score
    for _, row in w.nlargest(10, "composite_score").iterrows():
        hit = all_df[all_df["shrid2"] == row["shrid2"]]
        if len(hit):
            r = hit.iloc[0]
            ax.annotate(
                row["town_village_name"],
                xy=(r["composite_score"], r["composite_score_equal"]),
                xytext=(7, 3), textcoords="offset points", fontsize=7,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", fc="white",
                          alpha=0.85, ec="grey", lw=0.4),
                arrowprops=dict(arrowstyle="-", color="grey", lw=0.4),
            )

    legend_elements = [
        Line2D([0],[0], marker="o", color="w", markerfacecolor=C_BOTH,
               markersize=10, label=f"In both top-100s ({len(w_shrids & eq_shrids)})"),
        Line2D([0],[0], marker="o", color="w", markerfacecolor=C_WEIGHTED,
               markersize=9,  label=f"Weighted only ({len(w_shrids - eq_shrids)})"),
        Line2D([0],[0], marker="o", color="w", markerfacecolor=C_EQUAL,
               markersize=9,  label=f"Equal-weights only ({len(eq_shrids - w_shrids)})"),
        Line2D([0],[0], linestyle="--", color="grey", lw=1, label="y = x  (perfect agreement)"),
    ]
    ax.legend(handles=legend_elements, fontsize=9, framealpha=0.95,
              edgecolor="#cccccc")
    ax.set_xlabel("Composite score — Weighted  (NTL 40 | BLT 35 | POP 15 | RWI 10)",
                  fontsize=10)
    ax.set_ylabel("Composite score — Equal weights  (25 each)", fontsize=10)
    ax.set_title("Score agreement: Weighted vs Equal-Weights\n"
                 "Points below diagonal → weighted score > equal-weights score",
                 fontsize=12, fontweight="bold", color="#1a1a1a")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_facecolor("white")
    ax.grid(True, alpha=0.25, lw=0.5)

    plt.tight_layout()
    fig.savefig(OUTPUT / "map_06_score_scatter.png", dpi=180,
                bbox_inches="tight", facecolor="white")
    plt.close()
    print("Saved: map_06_score_scatter.png")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Loading data ...")
    w, eq, w_shrids, eq_shrids = load_and_prep()

    print("\nGenerating maps ...")
    map_weighted(w)
    map_equal(eq)
    map_side_by_side(w, eq)
    map_overlap(w, eq, w_shrids, eq_shrids)
    map_state_breakdown(w, eq)
    map_score_scatter(w, eq, w_shrids, eq_shrids)

    print("\nAll maps saved to output/")
