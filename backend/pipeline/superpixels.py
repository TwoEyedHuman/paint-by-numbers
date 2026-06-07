import os

import numpy as np
from skimage.color import rgb2lab
from skimage.segmentation import slic


def run_slic(
    image_array: np.ndarray,
    n_segments: int | None = None,
    compactness: float | None = None,
) -> np.ndarray:
    if n_segments is None:
        n_segments = int(os.environ.get("SLIC_N_SEGMENTS", 1000))
    if compactness is None:
        compactness = float(os.environ.get("SLIC_COMPACTNESS", 1.0))

    lab = rgb2lab(image_array)
    return slic(lab, n_segments=n_segments, compactness=compactness, channel_axis=-1, convert2lab=False)
