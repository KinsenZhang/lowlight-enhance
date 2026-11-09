"""评价指标。

有参考指标（和真值比）：PSNR、SSIM；
无参考指标（只看增强结果本身）：亮度均值、对比度、信息熵、平均梯度、色彩丰富度、
死黑比例、过曝比例。低照度增强的实际应用中一般拿不到真值，所以两套指标都算。
"""

import time

import numpy as np

from .color import luminance
from .filters import conv1d, gaussian_kernel


def psnr(gt, pred):
    """峰值信噪比，按 [0,255] 计算。"""
    gt = np.asarray(gt, dtype=np.float64)
    pred = np.asarray(pred, dtype=np.float64)
    mse = np.mean((gt * 255.0 - pred * 255.0) ** 2)
    if mse < 1e-12:
        return float("inf")
    return float(10.0 * np.log10(255.0 ** 2 / mse))


def ssim(gt, pred):
    """结构相似度，标准 11x11 高斯窗、sigma=1.5，在亮度通道上计算。"""
    x = luminance(np.asarray(gt, dtype=np.float64)) * 255.0
    y = luminance(np.asarray(pred, dtype=np.float64)) * 255.0

    k = gaussian_kernel(1.5)
    mu_x = conv1d(conv1d(x, k, 0), k, 1)
    mu_y = conv1d(conv1d(y, k, 0), k, 1)

    xx = conv1d(conv1d(x * x, k, 0), k, 1)
    yy = conv1d(conv1d(y * y, k, 0), k, 1)
    xy = conv1d(conv1d(x * y, k, 0), k, 1)

    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2

    sig_x2 = xx - mu_x * mu_x
    sig_y2 = yy - mu_y * mu_y
    sig_xy = xy - mu_x * mu_y

    num = (2 * mu_x * mu_y + c1) * (2 * sig_xy + c2)
    den = (mu_x ** 2 + mu_y ** 2 + c1) * (sig_x2 + sig_y2 + c2)
    return float(np.mean(num / den))


def mean_brightness(img):
    return float(np.mean(img))


def contrast(img):
    """全局标准差，反映整体对比度。"""
    return float(np.std(luminance(np.asarray(img, dtype=np.float64))))


def entropy(img):
    """灰度直方图的信息熵，单位 bit，最大 8。"""
    y = luminance(np.asarray(img, dtype=np.float64))
    q = np.clip((y * 255.0).round(), 0, 255).astype(np.uint8)
    hist = np.bincount(q.ravel(), minlength=256).astype(np.float64)
    p = hist / hist.sum()
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def average_gradient(img):
    """平均梯度：相邻像素差的均值，衡量清晰度/边缘强度。"""
    y = luminance(np.asarray(img, dtype=np.float64))
    dh = np.abs(np.diff(y, axis=1)).mean()
    dw = np.abs(np.diff(y, axis=0)).mean()
    return float((dh + dw) / 2.0)


def colorfulness(img):
    """Hasler 与 Süsstrunk 的色彩丰富度指标 M。"""
    img = np.asarray(img, dtype=np.float64) * 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    std = np.sqrt(rg.std() ** 2 + yb.std() ** 2)
    mean = np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    return float(std + 0.3 * mean)


def dead_black_ratio(img, thresh=16 / 255.0):
    """三通道同时小于阈值的像素比例，反映暗部是否"糊成一片黑"。"""
    img = np.asarray(img, dtype=np.float64)
    return float(np.mean(np.max(img, axis=-1) < thresh))


def _srgb_to_lab(img):
    """sRGB [0,1] -> CIE Lab（D65）。"""
    from .color import srgb_to_linear

    lin = srgb_to_linear(np.clip(np.asarray(img, dtype=np.float64), 0.0, 1.0))
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T
    white = np.array([0.95047, 1.0, 1.08883])

    def f(t):
        d = 6.0 / 29.0
        return np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4.0 / 29.0)

    fx, fy, fz = f(xyz[..., 0] / white[0]), f(xyz[..., 1] / white[1]), f(xyz[..., 2] / white[2])
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def delta_e(gt, pred):
    """平均色差 ΔE*ab（CIE76），越小越接近真值颜色。"""
    a = _srgb_to_lab(gt)
    b = _srgb_to_lab(pred)
    return float(np.mean(np.sqrt(np.sum((a - b) ** 2, axis=-1))))


def shadow_noise(img, mask, r=1):
    """阴影区的噪声水平。

    mask 为 True 的像素（一般取低照度图里最暗的那部分）统计高频残差的标准差，
    数值越小说明暗部越干净。
    """
    y = luminance(np.asarray(img, dtype=np.float64))
    from .filters import box_filter
    hp = y - box_filter(y, r)
    return float(np.std(hp[np.asarray(mask, dtype=bool)]))


def region_psnr(gt, pred, mask):
    """只在掩膜区域内算 PSNR，用来分别评价亮部与暗部。"""
    m = np.asarray(mask, dtype=bool)
    if m.sum() == 0:
        return float("nan")
    g = np.asarray(gt, dtype=np.float64)[m] * 255.0
    p = np.asarray(pred, dtype=np.float64)[m] * 255.0
    mse = np.mean((g - p) ** 2)
    if mse < 1e-12:
        return float("inf")
    return float(10.0 * np.log10(255.0 ** 2 / mse))


def overexposed_ratio(img, thresh=240 / 255.0):
    """至少一个通道接近饱和的像素比例。"""
    img = np.asarray(img, dtype=np.float64)
    return float(np.mean(np.max(img, axis=-1) > thresh))


def no_reference_scores(img):
    """打包一组无参考指标。"""
    return {
        "brightness": mean_brightness(img),
        "contrast": contrast(img),
        "entropy": entropy(img),
        "avg_grad": average_gradient(img),
        "colorfulness": colorfulness(img),
        "dead_black": dead_black_ratio(img),
        "overexposed": overexposed_ratio(img),
    }


def match_brightness(img, target=0.50):
    """把图像整体线性缩放到平均亮度 target。

    只用于补充实验：给 CLAHE、MSRCR 这类不带自动配光的方法"补一个自动曝光"，
    看看在同样亮度下它们的结构指标能到多少，避免把差距全算在曝光头上。
    """
    img = np.asarray(img, dtype=np.float64)
    m = float(np.mean(img))
    if m < 1e-6:
        return img.copy()
    return np.clip(img * (target / m), 0.0, 1.0)


def measure_time(fn, img, repeat=3):
    """跑 repeat 次取平均耗时（秒）。第一次作为预热不计入。"""
    fn(img)
    ts = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn(img)
        ts.append(time.perf_counter() - t0)
    return float(np.mean(ts))
