"""生成报告和 README 用的图。

    python -m scripts.make_figures

所有图输出到 results/figs/。图的版式按报告里 14.6 cm 的正文宽度设计，
每格保持 16:10，贴进 Word 后不需要再缩放。
"""

import csv
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baselines import clahe, gamma_correction, msrcr          # noqa: E402
from src.color import v_max                                        # noqa: E402
from src.dataset import load_pairs                                 # noqa: E402
from src.enhance import enhance                                    # noqa: E402
from src.filters import gaussian_blur, guided_filter                # noqa: E402
from src.metrics import psnr, ssim                                 # noqa: E402
from src.viz import (bar_chart, font, grid, hist_plot, line_plot,  # noqa: E402
                     to_image)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIGS = os.path.join(ROOT, "results", "figs")

LABELS = ["真值", "低照度", "Gamma 2.2", "CLAHE", "MSRCR", "本文方法"]


def load_summary():
    with open(os.path.join(ROOT, "results", "summary.csv"), encoding="utf-8-sig") as f:
        return {r["method"]: r for r in csv.DictReader(f)}


def fig_dataset(pairs):
    """数据集概览：上排真值，下排对应的低照度图。"""
    sel = [pairs[0], pairs[1], pairs[5], pairs[7]]
    tiles, labels = [], []
    for name, gt, low in sel:
        tiles.append(gt)
        labels.append(f"({name}) 真值")
    for name, gt, low in sel:
        tiles.append(low)
        labels.append(f"({name}) 低照度")
    grid(tiles, cols=4, tile_w=330, tile_h=206, labels=labels, pad=7).save(
        os.path.join(FIGS, "fig1_dataset.png"))


def _six_panel(name, gt, low, tile_w=330, tile_h=206):
    outs = [gt, low, gamma_correction(low, 1 / 2.2), clahe(low), msrcr(low), enhance(low)]
    return grid(outs, cols=3, tile_w=tile_w, tile_h=tile_h, labels=LABELS, pad=7)


def fig_compare(pairs, name, out):
    _, gt, low = [p for p in pairs if p[0] == name][0]
    _six_panel(name, gt, low).save(os.path.join(FIGS, out))


def fig_zoom(pairs, name="02", box=(470, 250, 800, 445), scale=2.0):
    """局部放大：看噪声、色偏和边缘过渡。"""
    _, gt, low = [p for p in pairs if p[0] == name][0]
    outs = [gt, low, gamma_correction(low, 1 / 2.2), clahe(low), msrcr(low), enhance(low)]
    w, h = int((box[2] - box[0]) * scale), int((box[3] - box[1]) * scale)
    crops = [to_image(im).crop(box).resize((w, h), Image.LANCZOS) for im in outs]
    grid(crops, cols=3, tile_w=w, tile_h=h, labels=LABELS, pad=7).save(
        os.path.join(FIGS, "fig4_zoom.png"))


def fig_maps(pairs, name="07"):
    """光照图与增益图：M1 和 M3 到底在做什么。"""
    _, gt, low = [p for p in pairs if p[0] == name][0]
    v = v_max(low)
    l_gf = guided_filter(v, v, 32, 3e-3)
    l_gs = gaussian_blur(v, 32)

    l_bar = float(np.mean(l_gf))
    gain = (l_gf / l_bar) ** 0.60 / l_gf
    alpha = np.clip((gain - 1.0) / 3.0, 0.0, 0.85)

    def norm(x):
        lo, hi = np.percentile(x, 1), np.percentile(x, 99)
        return np.clip((x - lo) / max(hi - lo, 1e-6), 0, 1)

    show = [low, np.repeat(v[..., None], 3, -1), np.repeat(l_gf[..., None], 3, -1),
            np.repeat(l_gs[..., None], 3, -1), np.repeat(norm(gain)[..., None], 3, -1),
            np.repeat(norm(alpha)[..., None], 3, -1)]
    labels = ["输入", "V = max(R, G, B)", "M1 引导滤波光照",
              "高斯光照（对照）", "放大倍数 k", "收缩系数 α"]
    grid(show, cols=3, tile_w=310, tile_h=194, labels=labels, pad=7).save(
        os.path.join(FIGS, "fig5_maps.png"))


def fig_hist(pairs, name="04"):
    _, gt, low = [p for p in pairs if p[0] == name][0]
    imgs = [gt, low, msrcr(low), enhance(low)]
    hist_plot(imgs, ["真值", "低照度", "MSRCR", "本文方法"],
              os.path.join(FIGS, "fig6_hist.png"))


def _stack(paths, out, gap=10):
    ims = [Image.open(p) for p in paths]
    W = max(i.width for i in ims)
    H = sum(i.height for i in ims) + gap * (len(ims) - 1)
    sheet = Image.new("RGB", (W, H), "white")
    y = 0
    for im in ims:
        sheet.paste(im, (0, y))
        y += im.height + gap
    sheet.save(out)


def fig_metrics(summary):
    methods = ["Gamma 2.2", "CLAHE", "MSRCR", "Ours"]
    short = ["Gamma", "CLAHE", "MSRCR", "本文"]
    vals = [float(summary[m]["psnr"]) for m in methods]
    bar_chart(short, vals, os.path.join(FIGS, "fig7_metrics.png"),
              ylabel="PSNR / dB", fmt="{:.1f}", highlight=3, size=(520, 280))


def fig_psweep(pairs):
    ps = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    psnr_curve, ssim_curve = [], []
    for p in ps:
        psnr_curve.append(float(np.mean([psnr(gt, enhance(low, p=p)) for _, gt, low in pairs])))
        ssim_curve.append(float(np.mean([ssim(gt, enhance(low, p=p)) for _, gt, low in pairs])))
        print(f"  p={p:.1f} PSNR={psnr_curve[-1]:.2f} SSIM={ssim_curve[-1]:.3f}", flush=True)
    line_plot([(ps, psnr_curve)], os.path.join(FIGS, "fig8_psweep.png"),
              xlabel="光照压缩指数 p", ylabel="PSNR / dB", xticks=ps, size=(520, 300))
    with open(os.path.join(ROOT, "results", "psweep.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["p", "psnr", "ssim"])
        for p, a, b in zip(ps, psnr_curve, ssim_curve):
            w.writerow([p, round(a, 3), round(b, 4)])


def fig_ablation():
    path = os.path.join(ROOT, "results", "ablation.csv")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    order = ["Ours (full)", "w/o M1 (Gauss)", "w/o M2 (fixed γ)",
             "w/o M3 (no shrink)", "w/o M4 (per-channel)"]
    short = ["完整", "去M1", "去M2", "去M3", "去M4"]
    vals = [float(np.mean([float(r["psnr"]) for r in rows if r["variant"] == v]))
            for v in order]
    bar_chart(short, vals, os.path.join(FIGS, "fig9_ablation.png"),
              ylabel="PSNR / dB", fmt="{:.1f}", highlight=0, size=(520, 300))


def main():
    os.makedirs(FIGS, exist_ok=True)
    pairs = load_pairs(ROOT)
    print("图 1 数据集…", flush=True)
    fig_dataset(pairs)
    print("图 2/3 方法对比…", flush=True)
    fig_compare(pairs, "02", "fig2_compare02.png")
    fig_compare(pairs, "07", "fig3_compare07.png")
    print("图 4 局部放大…", flush=True)
    fig_zoom(pairs)
    print("图 5 光照/增益…", flush=True)
    fig_maps(pairs)
    print("图 6 直方图…", flush=True)
    fig_hist(pairs)
    print("图 7 指标柱状图…", flush=True)
    fig_metrics(load_summary())
    print("图 8 p 敏感性…", flush=True)
    fig_psweep(pairs)
    print("图 9 消融…", flush=True)
    fig_ablation()
    print("完成，图在 results/figs/")


if __name__ == "__main__":
    main()
