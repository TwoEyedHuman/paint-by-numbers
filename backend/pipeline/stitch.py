"""Stitch a directory of tune output PNGs into a single grid image.

Usage:
  python pipeline/stitch.py --tmp /app/tmp  --pattern 'seg(\\d+)_k(\\d+)\\.png'      --row-label seg  --col-label k
  python pipeline/stitch.py --tmp /app/tmp2 --pattern 'comp([\\d.]+)_minpx(\\d+)\\.png' --row-label comp --col-label minpx
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument("--tmp",       default="/app/tmp")
parser.add_argument("--pattern",   default=r"seg(\d+)_k(\d+)\.png")
parser.add_argument("--row-label", default="seg")
parser.add_argument("--col-label", default="k")
args = parser.parse_args()

TMP = Path(args.tmp)

entries = []
for f in sorted(TMP.glob("*.png")):
    if f.name == "grid.png":
        continue
    m = re.match(args.pattern, f.name)
    if m:
        entries.append((m.group(1), m.group(2), f))

if not entries:
    raise SystemExit(f"No matching files found in {TMP} for pattern '{args.pattern}'")

def _sort_key(v: str) -> float:
    try:
        return float(v)
    except ValueError:
        return v

row_vals = sorted(set(e[0] for e in entries), key=_sort_key)
col_vals = sorted(set(e[1] for e in entries), key=_sort_key)
lookup   = {(e[0], e[1]): e[2] for e in entries}

THUMB  = 300
LABEL  = 22
PAD    = 3
HDR_W  = 80
HDR_H  = 28
BG     = (40, 40, 40)
HDR_BG = (25, 25, 25)
LBL_FG = (210, 210, 210)
HDR_FG = (255, 200, 80)

cols = len(col_vals)
rows = len(row_vals)

W = HDR_W + cols * (THUMB + PAD) + PAD
H = HDR_H + rows * (THUMB + LABEL + PAD) + PAD

canvas = Image.new("RGB", (W, H), BG)
draw   = ImageDraw.Draw(canvas)

for c, cv in enumerate(col_vals):
    x = HDR_W + PAD + c * (THUMB + PAD)
    draw.rectangle([x, 0, x + THUMB, HDR_H], fill=HDR_BG)
    draw.text((x + 6, 6), f"{args.col_label}={cv}", fill=HDR_FG)

for r, rv in enumerate(row_vals):
    y = HDR_H + PAD + r * (THUMB + LABEL + PAD)
    draw.rectangle([0, y, HDR_W, y + THUMB + LABEL], fill=HDR_BG)
    label = f"{args.row_label}\n={rv}"
    draw.text((4, y + THUMB // 2 - 10), label, fill=HDR_FG)

for r, rv in enumerate(row_vals):
    for c, cv in enumerate(col_vals):
        x = HDR_W + PAD + c * (THUMB + PAD)
        y = HDR_H  + PAD + r * (THUMB + LABEL + PAD)
        path = lookup.get((rv, cv))
        if path:
            img = Image.open(path).resize((THUMB, THUMB), Image.LANCZOS)
            canvas.paste(img, (x, y))
        draw.rectangle([x, y + THUMB, x + THUMB, y + THUMB + LABEL], fill=(20, 20, 20))
        draw.text((x + 4, y + THUMB + 4),
                  f"{args.row_label}={rv}  {args.col_label}={cv}", fill=LBL_FG)

out = TMP / "grid.png"
canvas.save(out)
print(f"Saved {cols}×{rows} grid → {out}")
