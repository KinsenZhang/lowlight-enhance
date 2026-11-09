"""跑完整实验：四个方法 + 消融，输出 CSV 与终端表格。

用法：
    python -m scripts.run_benchmark              # 主实验
    python -m scripts.run_benchmark --ablation   # 额外跑消融
"""

import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baselines import clahe, gamma_correction, msrcr      # noqa: E402
from src.dataset import (IMAGE_NAMES, ideal_restore, load_pairs, light_field,
                         vignette_field)                       # noqa: E402
from src.enhance import ABLATIONS, enhance                     # noqa: E402
from src.color import luminance                                  # noqa: E402
from src.metrics import (delta_e, match_brightness, measure_time,  # noqa: E402
                         no_reference_scores, psnr, region_psnr,
                         shadow_noise, ssim)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 方法名 -> 函数
METHODS = {
    "Gamma 2.2": lambda im: gamma_correction(im, 1.0 / 2.2),
    "CLAHE": lambda im: clahe(im),
    "MSRCR": lambda im: msrcr(im),
    "Ours": lambda im: enhance(im),
}

# 用于分区评价：按输入亮度分成暗部/亮部
SHADOW_Q = 0.35
HIGHLIGHT_Q = 0.35


def read_meta():
    path = os.path.join(ROOT, "data", "meta.csv")
    with open(path, encoding="utf-8-sig") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def eval_one(name, gt, low, meta_row):
    """对一张图算所有方法的全部指标。"""
    y = luminance(low)
    thr_lo = np.quantile(y, SHADOW_Q)
    thr_hi = np.quantile(y, 1.0 - HIGHLIGHT_Q)
    m_shadow = y <= thr_lo
    m_bright = y >= thr_hi

    rows = []
    for label, fn in METHODS.items():
        out = fn(low)
        nr = no_reference_scores(out)
        rows.append({
            "image": name,
            "method": label,
            "psnr": psnr(gt, out),
            "ssim": ssim(gt, out),
            "delta_e": delta_e(gt, out),
            "psnr_match": psnr(gt, match_brightness(out)),
            "ssim_match": ssim(gt, match_brightness(out)),
            "psnr_dark": region_psnr(gt, out, m_shadow),
            "psnr_bright": region_psnr(gt, out, m_bright),
            "shadow_noise": shadow_noise(out, m_shadow),
            "brightness": nr["brightness"],
            "contrast": nr["contrast"],
            "entropy": nr["entropy"],
            "avg_grad": nr["avg_grad"],
            "colorfulness": nr["colorfulness"],
            "dead_black": nr["dead_black"],
            "overexposed": nr["overexposed"],
        })
    return rows


def eval_ablation(name, gt, low):
    rows = []
    for label, kw in ABLATIONS.items():
        out = enhance(low, **kw)
        rows.append({
            "image": name,
            "variant": label,
            "psnr": psnr(gt, out),
            "ssim": ssim(gt, out),
            "delta_e": delta_e(gt, out),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ablation", action="store_true", help="同时跑消融实验")
    ap.add_argument("--timing", action="store_true", help="统计平均耗时")
    ap.add_argument("--scaling", action="store_true",
                    help="测窗口半径与图像分辨率对耗时的影响")
    args = ap.parse_args()

    meta = read_meta()
    pairs = load_pairs(ROOT)

    all_rows = []
    for name, gt, low in pairs:
        all_rows.extend(eval_one(name, gt, low, meta[name]))
        print(f"  {name} 完成", flush=True)

    field_names = list(all_rows[0].keys())
    out_csv = os.path.join(ROOT, "results", "metrics.csv")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=field_names)
        w.writeheader()
        w.writerows(all_rows)

    # 汇总
    print("\n方法        PSNR   SSIM   ΔE    匹配PSNR 匹配SSIM 暗部 亮部 阴影噪声 熵    梯度   色彩  耗时")
    summary = []
    for label in METHODS:
        sel = [r for r in all_rows if r["method"] == label]
        agg = {k: float(np.mean([r[k] for r in sel])) for k in
               ("psnr", "ssim", "delta_e", "psnr_match", "ssim_match", "psnr_dark",
                "psnr_bright", "shadow_noise", "entropy", "avg_grad", "colorfulness")}
        t = float("nan")
        if args.timing:
            t = measure_time(METHODS[label], pairs[0][2], repeat=3)
        agg.update({"method": label, "time": t})
        summary.append(agg)
        print(f"{label:<11s} {agg['psnr']:5.2f}  {agg['ssim']:.3f}  {agg['delta_e']:5.2f}  "
              f"{agg['psnr_match']:6.2f}  {agg['ssim_match']:.3f}   "
              f"{agg['psnr_dark']:5.2f} {agg['psnr_bright']:5.2f} {agg['shadow_noise']:.4f}  "
              f"{agg['entropy']:.3f} {agg['avg_grad']:.4f} {agg['colorfulness']:6.2f} {t:6.3f}")

    # 理想反解作为上界参考
    ideal_rows = []
    for name, gt, low in pairs:
        row = meta[name]
        light = light_field(gt.shape[0], gt.shape[1], seed=int(name))
        out = ideal_restore(low, float(row["exposure"]), light,
                            cast=(1.0, 1.0, float(row["cast_b"])))
        ideal_rows.append((psnr(gt, out), ssim(gt, out), delta_e(gt, out)))
    print(f"{'(理想反解)':<12s} {np.mean([r[0] for r in ideal_rows]):5.2f}  "
          f"{np.mean([r[1] for r in ideal_rows]):.3f}  "
          f"{np.mean([r[2] for r in ideal_rows]):4.2f}  —— 仅作噪声上限参考")

    with open(os.path.join(ROOT, "results", "summary.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    if args.ablation:
        abl = []
        for name, gt, low in pairs:
            abl.extend(eval_ablation(name, gt, low))
        with open(os.path.join(ROOT, "results", "ablation.csv"), "w", newline="",
                  encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(abl[0].keys()))
            w.writeheader()
            w.writerows(abl)

        print("\n消融           PSNR   SSIM   ΔE")
        for label in ABLATIONS:
            sel = [r for r in abl if r["variant"] == label]
            print(f"{label:<20s} {np.mean([r['psnr'] for r in sel]):5.2f}  "
                  f"{np.mean([r['ssim'] for r in sel]):.3f}  "
                  f"{np.mean([r['delta_e'] for r in sel]):4.2f}")

    print(f"\n结果写入 {out_csv}")

    if args.scaling:
        run_scaling(pairs[0][2])


def run_scaling(img):
    """窗口半径和分辨率对耗时的影响，用来支撑"与半径无关、随像素数线性"的说法。"""
    import time

    from src.filters import resize_bilinear

    print("\n窗口半径对耗时的影响（960x600）")
    rows = []
    for r in (8, 16, 32, 64, 128):
        enhance(img, radius=r)
        t0 = time.perf_counter()
        for _ in range(3):
            enhance(img, radius=r)
        t = (time.perf_counter() - t0) / 3
        rows.append((r, t))
        print(f"  r={r:<4d} {t:.3f} s")

    print("\n分辨率对耗时的影响（r=32）")
    for scale in (0.5, 1.0, 1.5, 2.0):
        h, w = int(600 * scale), int(960 * scale)
        big = resize_bilinear(img, h, w)
        enhance(big, radius=32)
        t0 = time.perf_counter()
        for _ in range(2):
            enhance(big, radius=32)
        t = (time.perf_counter() - t0) / 2
        print(f"  {w}x{h}  {t:.3f} s")

    with open(os.path.join(ROOT, "results", "scaling.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["radius", "seconds"])
        for r, t in rows:
            w.writerow([r, round(t, 4)])


if __name__ == "__main__":
    main()
