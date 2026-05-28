"""
Merge GEE-exported GHSL tile splits into single GeoTIFFs.

Usage:
    python merge_ghsl.py --input_dir /path/to/downloaded/tiles --output_dir /path/to/output

GEE splits large exports into multiple tiles (e.g. GHS_POP_2020_India_clean-00000...tif).
This script groups tiles by year and product, merges each group, and writes one file per year.
"""

import argparse
import glob
import os
import re
from collections import defaultdict

import rasterio
from rasterio.merge import merge


def find_tile_groups(input_dir, pattern="GHS_*_India_clean-*.tif"):
    """Group tiles by their base name (product + year), ignoring the tile offset suffix."""
    tiles = sorted(glob.glob(os.path.join(input_dir, pattern)))
    groups = defaultdict(list)
    for path in tiles:
        fname = os.path.basename(path)
        # Strip the tile offset suffix: everything after the last '-00000...' block
        base = re.sub(r'-\d{10}-\d{10}\.tif$', '', fname)
        groups[base].append(path)
    return groups


def merge_group(base_name, tile_paths, output_dir):
    output_path = os.path.join(output_dir, f"{base_name}_merged.tif")
    if os.path.exists(output_path):
        print(f"  Skipping {base_name} — merged file already exists.")
        return

    print(f"  Merging {len(tile_paths)} tiles → {os.path.basename(output_path)}")
    datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, transform = merge(datasets)

    profile = datasets[0].profile.copy()
    profile.update({
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": transform,
        "compress": "lzw",   # keeps file size comparable to the split tiles
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    })

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mosaic)

    for ds in datasets:
        ds.close()

    size_mb = os.path.getsize(output_path) / 1e6
    print(f"  Done — {size_mb:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description="Merge GHSL GEE tile exports into single GeoTIFFs.")
    parser.add_argument("--input_dir", required=True, help="Folder containing downloaded GEE tiles")
    parser.add_argument("--output_dir", default=None, help="Output folder (defaults to input_dir/merged)")
    parser.add_argument("--pattern", default="GHS_*_India_clean-*.tif", help="Glob pattern to match tiles")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(args.input_dir, "merged")
    os.makedirs(output_dir, exist_ok=True)

    groups = find_tile_groups(args.input_dir, args.pattern)
    if not groups:
        print(f"No tiles found matching '{args.pattern}' in {args.input_dir}")
        return

    print(f"Found {len(groups)} group(s) to merge:\n")
    for base_name, tile_paths in sorted(groups.items()):
        print(f"[{base_name}]")
        merge_group(base_name, tile_paths, output_dir)

    print(f"\nAll done. Merged files saved to: {output_dir}")


if __name__ == "__main__":
    main()
