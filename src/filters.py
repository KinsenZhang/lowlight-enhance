"""基础滤波算子。

全部只用 numpy 实现，不依赖 OpenCV。为了在纯 CPU 上处理百万像素级图像，
盒式滤波用积分图、高斯模糊用"降采样-小核模糊-上采样"的近似，整体保持 O(N)。

图像一律用 float64、形状 (H, W) 或 (H, W, C)，取值范围 [0, 1]。
"""

import numpy as np


# ---------------------------------------------------------------- 盒式滤波

def _integral_image(img):
    """二维前缀和，返回 (H+1, W+1) 的数组。"""
    h, w = img.shape
    ii = np.zeros((h + 1, w + 1), dtype=np.float64)
    ii[1:, 1:] = img.cumsum(axis=0).cumsum(axis=1)
    return ii


def box_filter(img, r):
    """半径为 r 的均值滤波，边界按 reflect 复制。复杂度 O(N)，与 r 无关。"""
    img = np.asarray(img, dtype=np.float64)
    if r <= 0:
        return img.copy()
    h, w = img.shape
    k = 2 * r + 1
    p = np.pad(img, r, mode="reflect")
    ii = _integral_image(p)
    s = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return s / (k * k)


# ---------------------------------------------------------------- 引导滤波

def guided_filter(guide, src, r, eps):
    """He 等人 2010 年的引导滤波（单通道版）。

    guide 为引导图，src 为待滤波图。当 src is guide 时退化为保边平滑，
    正是本文用它估计光照图的用法。复杂度 O(N)，与窗口半径无关。
    """
    guide = np.asarray(guide, dtype=np.float64)
    src = np.asarray(src, dtype=np.float64)

    mean_g = box_filter(guide, r)
    mean_s = box_filter(src, r)
    corr_gg = box_filter(guide * guide, r)
    corr_gs = box_filter(guide * src, r)

    var_g = corr_gg - mean_g * mean_g
    cov_gs = corr_gs - mean_g * mean_s

    a = cov_gs / (var_g + eps)
    b = mean_s - a * mean_g
    mean_a = box_filter(a, r)
    mean_b = box_filter(b, r)
    return mean_a * guide + mean_b


# ---------------------------------------------------------------- 卷积 / 高斯

def conv1d(img, kernel, axis):
    """沿指定轴做一维卷积，边界 reflect。"""
    kernel = np.asarray(kernel, dtype=np.float64)
    r = len(kernel) // 2
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r, r)
    p = np.pad(np.asarray(img, dtype=np.float64), pad, mode="reflect")

    out = np.zeros(img.shape, dtype=np.float64)
    n = img.shape[axis]
    for i, kv in enumerate(kernel):
        sl = [slice(None)] * img.ndim
        sl[axis] = slice(i, i + n)
        out += kv * p[tuple(sl)]
    return out


def gaussian_kernel(sigma):
    r = max(1, int(np.ceil(3.0 * sigma)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return k / k.sum()


def resize_bilinear(img, out_h, out_w):
    """双线性缩放，返回 float64。"""
    img = np.asarray(img, dtype=np.float64)
    h, w = img.shape[:2]
    if (h, w) == (out_h, out_w):
        return img.copy()

    ys = (np.arange(out_h) + 0.5) * (h / out_h) - 0.5
    xs = (np.arange(out_w) + 0.5) * (w / out_w) - 0.5
    ys = np.clip(ys, 0, h - 1)
    xs = np.clip(xs, 0, w - 1)

    y0 = np.floor(ys).astype(np.int64)
    x0 = np.floor(xs).astype(np.int64)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)
    wy = (ys - y0)[:, None]
    wx = (xs - x0)[None, :]

    if img.ndim == 3:
        wy = wy[:, :, None]
        wx = wx[:, :, None]
        top = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
        bot = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    else:
        top = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
        bot = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return top * (1 - wy) + bot * wy


def gaussian_blur(img, sigma):
    """高斯模糊。大 sigma 时先降采样再模糊再放大，避免卷积核过长拖慢速度。"""
    img = np.asarray(img, dtype=np.float64)
    if sigma < 0.4:
        return img.copy()

    h, w = img.shape[:2]
    # 核半径超过图像尺寸一半时，高斯核在边界内几乎是个常数，直接截断
    sigma = min(sigma, 0.5 * min(h, w))

    # 降采样倍数取 sigma/2 与"最短边至少留 8 个像素"的较小值
    factor = int(round(sigma / 2.0))
    factor = max(1, min(factor, min(h, w) // 8))
    if factor <= 1:
        k = gaussian_kernel(sigma)
        out = conv1d(img, k, 0)
        return conv1d(out, k, 1)

    small_h, small_w = max(8, h // factor), max(8, w // factor)
    small = resize_bilinear(img, small_h, small_w)
    k = gaussian_kernel(sigma / factor)
    small = conv1d(small, k, 0)
    small = conv1d(small, k, 1)
    return resize_bilinear(small, h, w)


def local_std(img, r):
    """局部标准差，用积分图算 (E[x^2] - E[x]^2)，用于估计噪声强度。"""
    img = np.asarray(img, dtype=np.float64)
    m = box_filter(img, r)
    m2 = box_filter(img * img, r)
    return np.sqrt(np.maximum(m2 - m * m, 0.0))
