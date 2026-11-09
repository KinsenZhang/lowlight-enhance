"""单张图演示：输入一张偏暗的图，输出增强结果与并排对比图。

    python scripts/demo.py data/low/02.png -o results/demo.png
    python scripts/demo.py myphoto.jpg --compare
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baselines import gamma_correction, msrcr        # noqa: E402
from src.enhance import enhance                          # noqa: E402
from src.viz import grid, to_image                       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="输入图像路径")
    ap.add_argument("-o", "--out", default="results/demo.png", help="输出路径")
    ap.add_argument("--compare", action="store_true", help="同时输出并排对比图")
    args = ap.parse_args()

    img = np.asarray(Image.open(args.input).convert("RGB"), dtype=np.float64) / 255.0
    out = enhance(img)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    Image.fromarray((out * 255).round().astype(np.uint8)).save(args.out)

    print(f"输入 {args.input}  {img.shape[1]}x{img.shape[0]}")
    print(f"平均亮度 {img.mean():.3f} -> {out.mean():.3f}")
    print(f"结果写入 {args.out}")

    if args.compare:
        stem, _ = os.path.splitext(args.out)
        tiles = [img, out, gamma_correction(img, 1 / 2.2), msrcr(img)]
        labels = ["输入", "本文方法", "Gamma 2.2", "MSRCR"]
        grid(tiles, cols=2, tile_w=420, tile_h=262, labels=labels).save(stem + "_compare.png")
        print(f"对比图写入 {stem}_compare.png")


if __name__ == "__main__":
    main()
