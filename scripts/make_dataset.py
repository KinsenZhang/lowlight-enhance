"""生成测试数据：从原始素材裁剪出 8 张真值图，再合成低照度图。

仓库里已经附带了生成好的 data/gt 与 data/low，正常情况下不需要重跑；
只有在想换素材或改噪声参数时才需要执行本脚本。

用法：
    python -m scripts.make_dataset --src "C:/Windows/Web"
"""

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dataset import (TARGET_LOW_MEAN, light_field, normalize_exposure,  # noqa: E402
                         synthesize_low_light)

# 素材清单：(编号, 相对路径, 说明)
SOURCES = [
    ("01", "Wallpaper/ThemeC/img28.jpg", "雪山湖面，大面积天空平滑渐变"),
    ("02", "Wallpaper/ThemeC/img29.jpg", "湖岸树林，细碎枝叶纹理"),
    ("03", "Wallpaper/ThemeC/img30.jpg", "日落湖面，暖色高光"),
    ("04", "Wallpaper/ThemeD/img32.jpg", "浅色织物质感，柔和阴影"),
    ("05", "Wallpaper/ThemeD/img33.jpg", "织物褶皱，层叠遮挡"),
    ("06", "Wallpaper/ThemeD/img35.jpg", "织物卷曲，低饱和"),
    ("07", "Screen/img104.jpg", "灰蓝几何，长直线边缘"),
    ("08", "Wallpaper/Spotlight/img14.jpg", "蓝色花瓣，高饱和细节"),
]

# 每张图的色偏设置（夜拍常见偏冷）
CASTS = [
    (1.00, 1.00, 1.10),
    (1.00, 1.00, 1.06),
    (0.99, 1.00, 1.11),
    (1.00, 1.00, 1.04),
    (1.01, 1.00, 1.09),
    (1.00, 1.00, 1.05),
    (1.00, 0.99, 1.12),
    (1.02, 1.00, 1.08),
]

CROP_W, CROP_H = 960, 600
TARGET_LOW_MEAN = 0.22      # 低照度图的平均亮度，约比真值暗 2.5~3 档
SHOT_NOISE = float(os.environ.get("LL_SHOT", 2e-4))
READ_NOISE = float(os.environ.get("LL_READ", 1.5e-4))


def crop_center(im, w, h):
    from PIL import Image
    W, H = im.size
    s = max(w / W, h / H)
    if s > 1:
        im = im.resize((int(round(W * s)), int(round(H * s))), Image.LANCZOS)
    W, H = im.size
    left = (W - w) // 2
    top = (H - h) // 2
    return im.crop((left, top, left + w, top + h))


def solve_exposure(gt, cast, light, target_mean=TARGET_LOW_MEAN):
    """二分搜索曝光系数，使合成图平均亮度接近 target_mean。"""
    lo, hi = 1e-4, 1.0
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        img = synthesize_low_light(gt, exposure=mid, light=light, shot=SHOT_NOISE,
                                   read=READ_NOISE, cast=cast, seed=0)
        if img.mean() < target_mean:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=r"C:/Windows/Web")
    ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()

    from PIL import Image

    gt_dir = os.path.join(args.out, "data", "gt")
    low_dir = os.path.join(args.out, "data", "low")
    os.makedirs(gt_dir, exist_ok=True)
    os.makedirs(low_dir, exist_ok=True)

    rows = []
    for i, (name, rel, note) in enumerate(SOURCES):
        src = os.path.join(args.src, rel.replace("/", os.sep))
        if not os.path.exists(src):
            raise FileNotFoundError(f"找不到素材 {src}")
        im = crop_center(Image.open(src).convert("RGB"), CROP_W, CROP_H)
        gt = np.asarray(im, dtype=np.float64) / 255.0
        gt = normalize_exposure(gt, target=0.50)
        Image.fromarray((gt * 255).round().astype(np.uint8)).save(
            os.path.join(gt_dir, f"{name}.png"))

        cast = CASTS[i]
        light = light_field(CROP_H, CROP_W, seed=int(name))
        exposure = solve_exposure(gt, cast, light)
        low = synthesize_low_light(gt, exposure=exposure, light=light,
                                   shot=SHOT_NOISE, read=READ_NOISE,
                                   cast=cast, seed=int(name))
        Image.fromarray((np.clip(low, 0, 1) * 255).round().astype(np.uint8)).save(
            os.path.join(low_dir, f"{name}.png"))

        rows.append({
            "id": name,
            "source": rel,
            "note": note,
            "exposure": round(exposure, 4),
            "cast_b": cast[2],
            "gt_mean": round(float(gt.mean()), 3),
            "low_mean": round(float(low.mean()), 3),
            "size": f"{CROP_W}x{CROP_H}",
        })
        print(f"[{name}] {rel}  exposure={exposure:.4f} "
              f"gt_mean={gt.mean():.3f} low_mean={low.mean():.3f}")

    with open(os.path.join(args.out, "data", "meta.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"完成，shot={SHOT_NOISE}, read={READ_NOISE}，元数据写入 data/meta.csv")


if __name__ == "__main__":
    main()
