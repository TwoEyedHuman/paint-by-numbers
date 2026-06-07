import os
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt, label as nd_label


@dataclass
class NumberPlacement:
    label: int
    x: int  # column in region_map pixel coords
    y: int  # row in region_map pixel coords
    area: int


def place_numbers(
    region_map: np.ndarray,
    region_labels: list[int],
    min_label_px: int | None = None,
) -> list[NumberPlacement]:
    if min_label_px is None:
        min_label_px = int(os.environ.get("MIN_LABEL_PX", 500))

    placements: list[NumberPlacement] = []
    for label in region_labels:
        mask = region_map == label
        if not mask.any():
            continue

        components, n = nd_label(mask)
        for comp in range(1, n + 1):
            comp_mask = components == comp
            area = int(comp_mask.sum())
            if area < min_label_px:
                continue

            rows, cols = np.where(comp_mask)
            cy = int(rows.mean())
            cx = int(cols.mean())

            if comp_mask[cy, cx]:
                placements.append(NumberPlacement(label=label, x=cx, y=cy, area=area))
            else:
                dist = distance_transform_edt(comp_mask)
                best_idx = int(np.argmax(dist))
                by, bx = np.unravel_index(best_idx, dist.shape)
                placements.append(NumberPlacement(label=label, x=int(bx), y=int(by), area=area))

    return placements
