import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pipeline.numbering import NumberPlacement
from pipeline.palette import AppleBarrelColor
from pipeline.regions import Contour

_SERIF_CANDIDATES = [
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _SERIF_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_png(
    contours: list[Contour],
    number_placements: list[NumberPlacement],
    palette_colors: list[AppleBarrelColor],
    output_path: str | Path,
    src_shape: tuple[int, int] | None = None,
) -> None:
    dpi = int(os.environ.get("OUTPUT_DPI", 300))
    width_in = float(os.environ.get("OUTPUT_WIDTH_IN", 8))
    height_in = float(os.environ.get("OUTPUT_HEIGHT_IN", 10))
    out_w = int(dpi * width_in)
    out_h = int(dpi * height_in)

    k = len(palette_colors)
    legend_cols = min(k, 4)
    legend_rows = math.ceil(k / legend_cols)
    legend_row_h = max(40, out_w // 50)
    legend_h = legend_rows * legend_row_h + legend_row_h // 2

    paint_h = out_h - legend_h

    if src_shape is not None:
        src_h, src_w = src_shape
    elif contours:
        all_pts = np.vstack([c.points.reshape(-1, 2) for c in contours if len(c.points) > 0])
        src_w = int(all_pts[:, 0].max()) + 1
        src_h = int(all_pts[:, 1].max()) + 1
    else:
        src_w, src_h = out_w, paint_h

    scale_x = out_w / src_w
    scale_y = paint_h / src_h

    canvas = Image.new("RGB", (out_w, out_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    for c in contours:
        if len(c.points) < 2:
            continue
        pts = c.points.reshape(-1, 2)
        scaled = [(int(p[0] * scale_x), int(p[1] * scale_y)) for p in pts]
        if len(scaled) >= 2:
            draw.polygon(scaled, outline=(0, 0, 0))

    if number_placements:
        max_area = max(p.area for p in number_placements)
        min_fs = max(10, out_w // 300)
        max_fs = max(36, out_w // 70)

        for placement in number_placements:
            sx = int(placement.x * scale_x)
            sy = int(placement.y * scale_y)
            ratio = math.sqrt(placement.area / max_area)
            font_size = int(min_fs + ratio * (max_fs - min_fs))
            font = _load_font(font_size)
            text = str(placement.label + 1)
            draw.text((sx, sy), text, fill=(30, 30, 30), font=font, anchor="mm")

    swatch = int(legend_row_h * 0.65)
    col_w = out_w // legend_cols
    legend_font = _load_font(max(14, legend_row_h // 3))
    legend_y0 = paint_h + legend_row_h // 4

    for i, color in enumerate(palette_colors):
        row = i // legend_cols
        col = i % legend_cols
        x0 = col * col_w + 6
        y0 = legend_y0 + row * legend_row_h + (legend_row_h - swatch) // 2
        draw.rectangle([x0, y0, x0 + swatch, y0 + swatch], fill=color.rgb, outline=(0, 0, 0))
        tx = x0 + swatch + 8
        ty = legend_y0 + row * legend_row_h + legend_row_h // 2
        draw.text((tx, ty), f"{i + 1}  {color.name}", fill=(0, 0, 0), font=legend_font, anchor="lm")

    canvas.save(str(output_path))
    print(f"Saved final render to {output_path}  ({out_w}×{out_h} px)")
