from dataclasses import dataclass

import numpy as np
from skimage.color import lab2rgb, rgb2lab

# Apple Barrel acrylic paint colors: (name, R, G, B)
_APPLE_BARREL_COLORS: list[tuple[str, int, int, int]] = [
    ("White", 255, 255, 255),
    ("Black", 0, 0, 0),
    ("Bright Red", 215, 25, 32),
    ("Bright Blue", 0, 85, 164),
    ("Bright Yellow", 255, 213, 0),
    ("Bright Green", 0, 163, 75),
    ("Orange", 255, 103, 31),
    ("Purple", 130, 0, 122),
    ("Hot Pink", 236, 0, 140),
    ("Navy Blue", 0, 32, 96),
    ("Burnt Sienna", 138, 54, 15),
    ("Raw Sienna", 197, 133, 66),
    ("Tan", 210, 180, 140),
    ("Medium Gray", 128, 128, 128),
    ("Light Gray", 200, 200, 200),
    ("Turquoise", 0, 169, 181),
    ("Lime Green", 120, 198, 0),
    ("Dark Brown", 65, 35, 15),
    ("Lavender", 181, 126, 220),
    ("Coral", 255, 108, 80),
    ("Teal", 0, 128, 128),
    ("Peach", 255, 203, 164),
    ("Leaf Green", 67, 130, 61),
    ("Sky Blue", 135, 206, 235),
    ("Mauve", 189, 141, 174),
    ("Cerulean", 40, 130, 200),
]


@dataclass
class AppleBarrelColor:
    name: str
    rgb: tuple[int, int, int]
    lab: np.ndarray


def _build_table() -> list[AppleBarrelColor]:
    result = []
    for name, r, g, b in _APPLE_BARREL_COLORS:
        rgb_norm = np.array([[[r / 255, g / 255, b / 255]]])
        lab = rgb2lab(rgb_norm)[0, 0]
        result.append(AppleBarrelColor(name=name, rgb=(r, g, b), lab=lab))
    return result


_TABLE = _build_table()


def match_palette(centroids_lab: np.ndarray) -> list[AppleBarrelColor]:
    table_lab = np.array([c.lab for c in _TABLE])
    n = len(centroids_lab)

    # Downweight L (lightness) relative to a*/b* (chroma/hue) so that
    # hue-wrong colors (e.g. Lavender) don't beat hue-correct ones on lightness alone.
    _W = np.array([0.5, 1.5, 1.5])

    # cost[i, j] = weighted LAB distance from cluster i to palette color j
    cost = np.linalg.norm(
        (table_lab[None, :, :] - centroids_lab[:, None, :]) * _W, axis=2
    )

    # Greedy unique assignment: sort all (cluster, color) pairs by distance,
    # assign each cluster to its nearest unassigned palette color.
    pairs = sorted(
        ((cost[ci, pi], ci, pi) for ci in range(n) for pi in range(len(_TABLE))),
        key=lambda x: x[0],
    )

    assignments: list[int] = [-1] * n
    assigned_clusters: set[int] = set()
    used_palette: set[int] = set()

    for _, ci, pi in pairs:
        if ci in assigned_clusters or pi in used_palette:
            continue
        assignments[ci] = pi
        assigned_clusters.add(ci)
        used_palette.add(pi)
        if len(assigned_clusters) == n:
            break

    return [_TABLE[i] for i in assignments]
