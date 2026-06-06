import os
from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage


@dataclass
class Contour:
    label: int
    points: np.ndarray  # shape (N, 1, 2), dtype int32


def merge_small_regions(region_map: np.ndarray, min_px: int | None = None) -> np.ndarray:
    if min_px is None:
        min_px = int(os.environ.get("MIN_REGION_PX", 200))

    result = region_map.copy()
    num_labels = region_map.max() + 1

    for label in range(num_labels):
        mask = result == label
        labeled, n_components = ndimage.label(mask)
        for comp in range(1, n_components + 1):
            component_mask = labeled == comp
            if component_mask.sum() < min_px:
                # find neighbor labels by dilating component and sampling border
                dilated = ndimage.binary_dilation(component_mask, iterations=2)
                border = dilated & ~component_mask
                neighbor_labels = result[border]
                neighbor_labels = neighbor_labels[neighbor_labels != label]
                if len(neighbor_labels) == 0:
                    continue
                # absorb into most common neighbor
                counts = np.bincount(neighbor_labels, minlength=num_labels)
                best = int(counts.argmax())
                result[component_mask] = best

    return result


def extract_contours(region_map: np.ndarray) -> list[Contour]:
    num_labels = region_map.max() + 1
    contours: list[Contour] = []
    for label in range(num_labels):
        mask = (region_map == label).astype(np.uint8) * 255
        found, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for pts in found:
            contours.append(Contour(label=label, points=pts))
    return contours


def simplify_contours(contours: list[Contour], epsilon_factor: float = 0.002) -> list[Contour]:
    simplified: list[Contour] = []
    for c in contours:
        arc = cv2.arcLength(c.points, closed=True)
        epsilon = epsilon_factor * arc
        approx = cv2.approxPolyDP(c.points, epsilon, closed=True)
        simplified.append(Contour(label=c.label, points=approx))
    return simplified
