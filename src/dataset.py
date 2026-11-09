"""测试数据的构造。

真值取 8 张 1920x1200 的公开图像素材，中心裁剪到 960x600，并统一曝光到平均亮度 0.50。
低照度图按一个简化的相机成像模型合成：

    线性光 -> 乘以空间不均的光照场 S(x,y) 与曝光系数 a -> 加镜头暗角
            -> 加散粒噪声与读出噪声 -> 乘白平衡偏移 -> sRGB 编码

其中 S 由两团低频光斑加一块软边矩形（模拟路灯、窗光）组成，是低照度场景里
最难处理的部分：整幅图局部亮、局部黑，全局伽马没法同时照顾好两头。
"""

import os

import numpy as np

from .color import linear_to_srgb, srgb_to_linear

# 8 张图的编号
IMAGE_NAMES = ["01", "02", "03", "04", "05", "06", "07", "08"]

TARGET_GT_MEAN = 0.50
TARGET_LOW_MEAN = 0.22


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def light_field(h, w, seed=0):
    """生成 [0.45, 1] 范围内的低频光照场，带一两处软边。

    两团高斯光斑负责整体的明暗过渡，软边矩形负责出现"亮暗交界"，
    后者正是高斯光照估计（MSRCR）容易出晕圈、引导滤波能保住边缘的地方。
    """
    rng = np.random.default_rng(seed * 7 + 1)
    yy = (np.arange(h) - (h - 1) / 2) / (h / 2)
    xx = (np.arange(w) - (w - 1) / 2) / (w / 2)
    Y, X = np.meshgrid(yy, xx, indexing="ij")

    field = np.zeros((h, w), dtype=np.float64)
    for _ in range(2):
        cy = rng.uniform(-0.7, 0.7)
        cx = rng.uniform(-0.8, 0.8)
        s = rng.uniform(0.45, 0.85)
        field += rng.uniform(0.30, 0.50) * np.exp(
            -((Y - cy) ** 2 + (X - cx) ** 2) / (2.0 * s * s))

    ry = rng.uniform(0.55, 1.10)
    rx = rng.uniform(0.45, 1.10)
    soft = rng.uniform(0.045, 0.085)
    rect = _sigmoid((ry - np.abs(Y)) / soft) * _sigmoid((rx - np.abs(X)) / soft)
    field += rng.uniform(0.35, 0.55) * rect

    lo, hi = float(field.min()), float(field.max())
    return 0.45 + 0.55 * (field - lo) / max(hi - lo, 1e-6)


def vignette_field(h, w, strength=0.15):
    """镜头暗角，中心为 1，四角略暗。"""
    yy = (np.arange(h) - (h - 1) / 2) / (h / 2)
    xx = (np.arange(w) - (w - 1) / 2) / (w / 2)
    r2 = yy[:, None] ** 2 + xx[None, :] ** 2
    return np.clip(1.0 - strength * r2 / 2.0, 0.6, 1.0)


def normalize_exposure(gt, target=TARGET_GT_MEAN, iters=18):
    """把真值的平均亮度归一到 target（sRGB 域）。

    不同素材本身曝光不同，直接混在一起会让 PSNR 被整体亮度差主导，
    所以在线性域乘一个全局增益统一曝光——相当于调曝光，不改变结构内容。
    """
    gt = np.asarray(gt, dtype=np.float64)
    lin0 = srgb_to_linear(gt)
    y0 = 0.299 * lin0[..., 0] + 0.587 * lin0[..., 1] + 0.114 * lin0[..., 2]
    step = 2  # 二分搜索在 1/2 分辨率上做，精度足够
    y_s = y0[::step, ::step]

    def mean_srgb(gain):
        return float(np.mean(linear_to_srgb(np.clip(y_s * gain, 0.0, 1.0))))

    lo, hi = 1e-3, 1e3
    for _ in range(iters):
        mid = np.sqrt(lo * hi)
        if mean_srgb(mid) < target:
            lo = mid
        else:
            hi = mid
    gain = np.sqrt(lo * hi)
    return np.clip(linear_to_srgb(np.clip(lin0 * gain, 0.0, 1.0)), 0.0, 1.0)


def synthesize_low_light(gt, exposure=0.2, light=None, vignette_strength=0.15,
                         shot=1.2e-3, read=6e-4, cast=(1.0, 1.0, 1.08), seed=0):
    """由真值合成低照度图像。

    exposure  : 线性域曝光系数
    light     : 光照场，None 表示均匀光照
    shot      : 散粒噪声系数，方差 = shot * 光照强度
    read      : 读出噪声标准差（线性域）
    cast      : 三通道轻微白平衡偏移（夜拍常见的偏蓝）
    """
    rng = np.random.default_rng(seed)
    gt = np.asarray(gt, dtype=np.float64)
    h, w = gt.shape[:2]

    lin = srgb_to_linear(gt)
    e = exposure * lin
    if light is not None:
        e = e * np.asarray(light, dtype=np.float64)[..., None]
    e = e * vignette_field(h, w, vignette_strength)[..., None]

    noisy = e + rng.normal(0.0, 1.0, e.shape) * np.sqrt(np.maximum(shot * e, 0.0))
    noisy = noisy + rng.normal(0.0, read, e.shape)
    noisy = noisy * np.asarray(cast, dtype=np.float64)[None, None, :]

    low = linear_to_srgb(np.clip(noisy, 0.0, 1.0))
    return np.clip(low, 0.0, 1.0)


def ideal_restore(low, exposure, light=None, vignette_strength=0.15,
                  cast=(1.0, 1.0, 1.0)):
    """理想反解：假定已知曝光、光照场、暗角与白平衡，直接除回去。

    这不是一个可比的方法，只是给出"在同样的噪声下能达到的最好效果"，
    用来说明各方法的差距里有多少来自噪声、有多少来自光照估计。
    """
    low = np.asarray(low, dtype=np.float64)
    h, w = low.shape[:2]
    lin = srgb_to_linear(low)
    lin = lin / np.asarray(cast, dtype=np.float64)[None, None, :]
    denom = exposure * vignette_field(h, w, vignette_strength)
    if light is not None:
        denom = denom * np.asarray(light, dtype=np.float64)
    return np.clip(linear_to_srgb(np.clip(lin / denom[..., None], 0.0, 1.0)), 0.0, 1.0)


def load_pairs(root):
    """读取 data/gt 与 data/low 下的图像对，返回 [(name, gt, low), ...]。"""
    from PIL import Image

    gt_dir = os.path.join(root, "data", "gt")
    low_dir = os.path.join(root, "data", "low")

    pairs = []
    for name in IMAGE_NAMES:
        gt_path = os.path.join(gt_dir, f"{name}.png")
        low_path = os.path.join(low_dir, f"{name}.png")
        if not (os.path.exists(gt_path) and os.path.exists(low_path)):
            raise FileNotFoundError(f"缺少图像对 {name}")
        gt = np.asarray(Image.open(gt_path).convert("RGB"), dtype=np.float64) / 255.0
        low = np.asarray(Image.open(low_path).convert("RGB"), dtype=np.float64) / 255.0
        pairs.append((name, gt, low))
    return pairs
