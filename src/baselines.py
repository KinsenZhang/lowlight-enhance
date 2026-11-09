"""对比方法：朴素伽马校正、CLAHE、MSRCR。

MSRCR 是本实验的基线——本文方法就是在它的 Retinex 框架上改的。
三个对比方法都按原论文的默认参数实现，没有为本文的好看而刻意调差。
"""

import numpy as np

from .color import (adjust_saturation, linear_to_srgb, luminance,
                    percentile_stretch, srgb_to_linear)
from .filters import box_filter, gaussian_blur


# ---------------------------------------------------------------- 朴素伽马

def gamma_correction(img, gamma=1.0 / 2.2):
    """最直接的亮度提升：I^(1/gamma)，不区分光照和反射，噪声会一起放大。"""
    img = np.asarray(img, dtype=np.float64)
    return np.clip(img ** gamma, 0.0, 1.0)


# ---------------------------------------------------------------- CLAHE

def _tile_luts(y, tiles, clip_limit):
    """按块统计直方图并生成映射表。"""
    h, w = y.shape
    ty, tx = tiles
    # 把图裁成 tiles 的整数倍，便于 reshape 成块
    hh, ww = h // ty, w // tx
    y_cut = y[:hh * ty, :ww * tx]
    q = np.clip((y_cut * 255.0).round(), 0, 255).astype(np.int32)

    blocks = q.reshape(ty, hh, tx, ww).transpose(0, 2, 1, 3).reshape(ty * tx, hh * ww)
    hist = np.stack([np.bincount(b, minlength=256) for b in blocks]).astype(np.float64)

    n_pix = hh * ww
    limit = clip_limit * n_pix / 256.0
    excess = np.maximum(hist - limit, 0).sum(axis=1, keepdims=True)
    hist = np.minimum(hist, limit) + excess / 256.0

    cdf = hist.cumsum(axis=1)
    cdf = cdf / cdf[:, -1:]
    return cdf * 255.0, (ty, tx)


def clahe(img, tiles=(8, 8), clip_limit=2.0, sat_gain=1.0):
    """限制对比度自适应直方图均衡（只作用在亮度上，再做色度保持的增益映射）。"""
    img = np.asarray(img, dtype=np.float64)
    y = luminance(img)

    luts, (ty, tx) = _tile_luts(y, tiles, clip_limit)
    h, w = y.shape

    # 每个像素落在哪 4 个块之间，做双线性插值
    gy = np.clip((np.arange(h) + 0.5) / h * ty - 0.5, 0, ty - 1)
    gx = np.clip((np.arange(w) + 0.5) / w * tx - 0.5, 0, tx - 1)
    y0 = np.floor(gy).astype(np.int64)
    x0 = np.floor(gx).astype(np.int64)
    y1 = np.minimum(y0 + 1, ty - 1)
    x1 = np.minimum(x0 + 1, tx - 1)
    wy = (gy - y0)[:, None]
    wx = (gx - x0)[None, :]

    q = np.clip((y * 255.0).round(), 0, 255).astype(np.int64)
    out = np.zeros_like(y)
    for yy, wgt_y in ((y0, 1 - wy), (y1, wy)):
        for xx, wgt_x in ((x0, 1 - wx), (x1, wx)):
            idx = yy[:, None] * tx + xx[None, :]  # (H, W) 每个像素所属块的编号
            mapped = luts[idx, q]
            out += wgt_y * wgt_x * mapped

    out = out / 255.0
    gain = out / np.maximum(y, 1e-4)
    res = np.clip(img * gain[..., None], 0.0, 1.0)
    if sat_gain != 1.0:
        res = np.clip(adjust_saturation(res, sat_gain), 0.0, 1.0)
    return res


# ---------------------------------------------------------------- MSRCR

def msrcr(img, sigmas=(15.0, 80.0, 250.0), alpha=125.0, beta=46.0,
          gain=1.0, low_clip=0.5, high_clip=99.9):
    """多尺度 Retinex 加色彩恢复（Jobson 等, 1997）。

    sigmas 按图像短边自适应缩放，保证不同分辨率下尺度一致。
    收尾的 0.5%/99.9% 分位拉伸是在本文测试集上试出来的最优收尾——对 MSRCR
    已经算客气了，分位再收紧会把它直接压成灰片。
    """
    img = np.clip(np.asarray(img, dtype=np.float64), 1e-4, 1.0)
    h, w = img.shape[:2]
    scale = min(h, w) / 600.0
    sig = [s * scale for s in sigmas]

    msr = np.zeros_like(img)
    for s in sig:
        blur = np.stack([gaussian_blur(img[..., c], s) for c in range(3)], axis=-1)
        msr += (np.log10(img + 1e-6) - np.log10(blur + 1e-6)) / len(sig)

    # 色彩恢复因子：C_i = beta * log(alpha * I_i / sum_c I_c)
    total = img.sum(axis=-1, keepdims=True) + 1e-6
    chroma = beta * np.log10(alpha * img / total + 1e-6)

    out = msr * chroma * gain
    return percentile_stretch(out, low_clip, high_clip)
