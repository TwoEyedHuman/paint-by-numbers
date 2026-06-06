"""Runs SLIC on test_assets/sample.jpg and writes a labeled overlay to test_assets/output_slic.png."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from PIL import Image
from skimage.segmentation import mark_boundaries

from pipeline.superpixels import run_slic

ASSETS = Path(__file__).parent.parent / "test_assets"


def main() -> None:
    img = Image.open(ASSETS / "sample.jpg").convert("RGB")
    image_array = np.array(img)

    n_segments = int(os.environ.get("SLIC_N_SEGMENTS", 1000))
    print(f"Running SLIC: n_segments={n_segments}")

    labels = run_slic(image_array)
    print(f"Produced {labels.max() + 1} superpixels")

    overlay = mark_boundaries(image_array, labels, color=(1, 0, 0), mode="thick")
    overlay_uint8 = (overlay * 255).clip(0, 255).astype("uint8")

    out_path = ASSETS / "output_slic.png"
    Image.fromarray(overlay_uint8).save(out_path)
    print(f"Saved overlay to {out_path}")


if __name__ == "__main__":
    main()
