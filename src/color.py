"""颜色空间相关的小工具：sRGB 线性化、亮度、色度、饱和度、色调映射。

低照度增强里很多问题出在"在 sRGB 域里直接乘系数"——那样会破坏线性关系，
放大器噪声、把颜色推到色域外。所以这里的转换都严格按 IEC 61966-2-1 来做。
"""

import numpy as np


def srgb_to_linear(img):
    """sRGB [0,1] -> 线性光。"""
    img = np.asarray(img, dtype=np.float64)
    return np.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(img):
    """线性光 -> sRGB [0,1]（不裁剪）。"""
    img = np.asarray(img, dtype=np.float64)
    img = np.maximum(img, 0.0)
    return np.where(img <= 0.0031308, img * 12.92, 1.055 * img ** (1 / 2.4) - 0.055)


def luminance(img):
    """Rec.601 亮度，返回单通道。"""
    img = np.asarray(img, dtype=np.float64)
    return 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]


def v_max(img):
    """max-RGB：三通道最大值。用它当光照图初值可以避免引入色彩偏移。"""
    return np.max(np.asarray(img, dtype=np.float64), axis=-1)


def saturation(img):
    """HSV 中的饱和度 S = (max - min) / max。"""
    img = np.asarray(img, dtype=np.float64)
    mx = np.max(img, axis=-1)
    mn = np.min(img, axis=-1)
    return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)


def adjust_saturation(img, factor):
    """保持亮度的饱和度调整：向灰度插值 / 背离灰度插值。"""
    img = np.asarray(img, dtype=np.float64)
    gray = luminance(img)[..., None]
    return np.clip(gray + (img - gray) * factor, 0.0, None)


def soft_clip(img, knee=0.85):
    """高光软压缩。

    超过 knee 的部分不再线性截断，而是用 1-exp 曲线压进 [knee, 1]，
    这样亮部不会出现成片的纯白死区。
    """
    img = np.asarray(img, dtype=np.float64)
    span = 1.0 - knee
    over = img > knee
    out = img.copy()
    x = (img[over] - knee) / span
    out[over] = knee + span * (1.0 - np.exp(-x))
    return np.clip(out, 0.0, 1.0)


def percentile_stretch(img, low=1.0, high=99.0):
    """按分位数把图拉回 [0,1]，MSRCR 一类算法的收尾常用做法。"""
    img = np.asarray(img, dtype=np.float64)
    lo = np.percentile(img, low)
    hi = np.percentile(img, high)
    if hi - lo < 1e-8:
        return np.clip(img, 0.0, 1.0)
    return np.clip((img - lo) / (hi - lo), 0.0, 1.0)
