"""Debug script: runs full paint-by-numbers pipeline and writes preview PNGs to test_assets/."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image
from skimage.color import lab2rgb, rgb2lab
from skimage.segmentation import mark_boundaries

from pipeline.clustering import assign_superpixels, cluster_colors, compute_superpixel_means
from pipeline.downsample import downsample
from pipeline.numbering import place_numbers
from pipeline.palette import match_palette
from pipeline.regions import extract_contours, merge_small_regions, simplify_contours
from pipeline.render import render_png
from pipeline.superpixels import run_slic

ASSETS = Path(__file__).parent.parent / "test_assets"


def main() -> None:
    img = Image.open(ASSETS / "sample.jpg").convert("RGB")
    image_array = np.array(img)

    max_px = int(os.environ.get("DOWNSAMPLE_MAX_PX", 800))
    image_array = downsample(image_array, max_px=max_px)
    h, w = image_array.shape[:2]
    print(f"Downsampled to {w}x{h} (max_px={max_px})")

    n_segments = int(os.environ.get("SLIC_N_SEGMENTS", 1000))
    palette_k = int(os.environ.get("PALETTE_K", 12))
    print(f"Running SLIC: n_segments={n_segments}")

    labels = run_slic(image_array)
    print(f"Produced {labels.max() + 1} superpixels")

    overlay = mark_boundaries(image_array, labels, color=(1, 0, 0), mode="thick")
    overlay_uint8 = (overlay * 255).clip(0, 255).astype("uint8")

    out_path = ASSETS / "output_slic.png"
    Image.fromarray(overlay_uint8).save(out_path)
    print(f"Saved overlay to {out_path}")

    print(f"Running K-Means clustering: k={palette_k}")
    image_lab = rgb2lab(image_array / 255.0)
    superpixel_ids, mean_colors_lab = compute_superpixel_means(image_lab, labels)
    cluster_labels, centroids_lab = cluster_colors(mean_colors_lab, k=palette_k)
    region_map = assign_superpixels(labels, superpixel_ids, cluster_labels)

    palette_colors = match_palette(centroids_lab)
    print(f"Matched {palette_k} clusters to Apple Barrel colors:")
    for i, color in enumerate(palette_colors):
        print(f"  Cluster {i}: {color.name} {color.rgb}")

    # Preview uses raw LAB centroids converted to RGB — palette matching
    # only happens at final render so clustering quality is visible unaltered.
    centroid_rgb = lab2rgb(centroids_lab.reshape(1, -1, 3)).reshape(-1, 3)
    flat_rgb = centroid_rgb[region_map]
    flat_uint8 = (flat_rgb * 255).clip(0, 255).astype("uint8")

    clustered_path = ASSETS / "output_clustered.png"
    Image.fromarray(flat_uint8).save(clustered_path)
    print(f"Saved flat-color preview to {clustered_path}")

    min_px = int(os.environ.get("MIN_REGION_PX", 200))
    print(f"Merging small regions: min_px={min_px}")
    clean_map = merge_small_regions(region_map, min_px=min_px)

    print("Extracting contours")
    contours = extract_contours(clean_map)
    print(f"Found {len(contours)} contours")

    contours = simplify_contours(contours)

    h, w = clean_map.shape
    canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    import cv2 as _cv2
    for c in contours:
        _cv2.drawContours(canvas, [c.points], -1, (0, 0, 0), 1)

    contours_path = ASSETS / "output_contours.png"
    Image.fromarray(canvas).save(contours_path)
    print(f"Saved contours preview to {contours_path}")

    print("Placing region numbers")
    region_labels = list(range(palette_k))
    placements = place_numbers(clean_map, region_labels)
    print(f"Placed numbers on {len(placements)} regions")

    final_path = ASSETS / "output_final.png"
    render_png(contours, placements, palette_colors, final_path, src_shape=clean_map.shape)


if __name__ == "__main__":
    main()
