import os

import numpy as np
from sklearn.cluster import KMeans


def compute_superpixel_means(
    image_lab: np.ndarray,
    label_array: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    superpixel_ids = np.unique(label_array)
    mean_colors = np.array([
        image_lab[label_array == sid].mean(axis=0)
        for sid in superpixel_ids
    ])
    return superpixel_ids, mean_colors


def cluster_colors(
    mean_colors_lab: np.ndarray,
    k: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if k is None:
        k = int(os.environ.get("PALETTE_K", 12))
    km = KMeans(n_clusters=k, random_state=42, n_init="auto")
    cluster_labels = km.fit_predict(mean_colors_lab)
    return cluster_labels, km.cluster_centers_


def assign_superpixels(
    label_array: np.ndarray,
    superpixel_ids: np.ndarray,
    cluster_labels: np.ndarray,
) -> np.ndarray:
    mapping = np.zeros(superpixel_ids.max() + 1, dtype=np.int32)
    mapping[superpixel_ids] = cluster_labels
    return mapping[label_array]
