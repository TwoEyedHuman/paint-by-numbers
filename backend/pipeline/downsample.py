import os

import numpy as np
from PIL import Image


def downsample(image_array: np.ndarray, max_px: int | None = None) -> np.ndarray:
    if max_px is None:
        max_px = int(os.environ.get("DOWNSAMPLE_MAX_PX", 800))

    h, w = image_array.shape[:2]
    longest = max(h, w)
    if longest <= max_px:
        return image_array

    scale = max_px / longest
    new_w = round(w * scale)
    new_h = round(h * scale)
    img = Image.fromarray(image_array)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    return np.array(img)
