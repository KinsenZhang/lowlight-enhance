"""本文方法：引导滤波光照估计 + 光照归一化映射 + 噪声感知细节重建。

Retinex 的基本假设是 I = L ∘ R：观测图等于光照与反射（本征颜色）的乘积。
做法是先估计光照 L，把图像除回去得到反射 R，再把光照按一条"归一化幂律曲线"
重新配光，最后乘回反射。和 MSRCR 相比一共改了四处，每处都能单独关掉：

    M1  光照图用引导滤波估计（替代三尺度高斯模糊），亮暗交界处不出晕圈
    M2  光照按 τ·(L/L̄)^p 重新配光（替代固定伽马），亮度和局部明暗自动适配
    M3  反射层按放大倍数做收缩与增益，暗部不跟着放大噪声
    M4  色度保持的软限幅与饱和度补偿（替代逐通道拉伸）

其中 M2 的 (L/L̄) 归一化是让不同暗度的图都能落到同一目标亮度的关键，
p 越小越接近"完全去掉光照"，p=1 则退化为只调曝光的全局伽马。
"""

import numpy as np

from .color import adjust_saturation, soft_clip, v_max
from .filters import box_filter, gaussian_blur, guided_filter

# 默认参数，报告 4.4 节给了一组参数扫描结果
DEFAULT_PARAMS = {
    "radius": 32,        # 引导滤波窗口半径
    "eps": 3e-3,         # 引导滤波正则项
    "target": 0.50,      # 配光后的目标平均亮度
    "p": 0.60,           # 光照压缩指数，越小越"平"
    "k_ref": 3.0,        # 增益归一化尺度
    "alpha_max": 0.85,   # 反射层向局部均值收缩的最大比例
    "beta_min": 0.70,    # 细节增益下界
    "beta_max": 1.00,    # 细节增益上界
    "tau": 1.8,          # 细节增益随增益衰减的时间常数
    "sat_gain": 1.00,    # 饱和度补偿系数
    "knee": 0.85,        # 高光软压缩拐点
    "box_r": 3,          # 反射层收缩所用的局部均值窗口半径
}


def enhance(img,
            radius=32,
            eps=3e-3,
            target=0.50,
            p=0.60,
            k_ref=3.0,
            alpha_max=0.85,
            beta_min=0.70,
            beta_max=1.00,
            tau=1.8,
            sat_gain=1.00,
            knee=0.85,
            box_r=3,
            fixed_gamma=1.8,
            use_guided=True,
            use_adaptive_gamma=True,
            use_noise_aware=True,
            use_color=True):
    """低照度图像增强。

    开关参数 use_guided / use_adaptive_gamma / use_noise_aware / use_color
    分别对应 M1~M4，用于消融实验。
    """
    img = np.clip(np.asarray(img, dtype=np.float64), 1e-4, 1.0)

    # ---- M1：光照图 ------------------------------------------------------
    v = v_max(img)
    if use_guided:
        light = guided_filter(v, v, radius, eps)
    else:
        # 消融：退回 MSRCR 的三尺度高斯式光照估计（这里用单尺度，等价于最粗那一层）
        light = gaussian_blur(v, sigma=radius)
    light = np.maximum(light, 1e-4)

    # ---- M2：重新配光 ----------------------------------------------------
    if use_adaptive_gamma:
        l_bar = max(float(np.mean(light)), 1e-4)
        # 先按均值归一化，再压指数 p：p 越小，明暗差被抹得越平
        light_new = (light / l_bar) ** p
        gain = light_new / light          # 暗处远大于 1，是噪声被放大的直接原因
    else:
        # 消融：固定指数的全局伽马，不知道这幅图到底有多暗，只能赌一个平均情况
        light_new = light ** (1.0 / fixed_gamma)
        gain = light_new / light

    # ---- M3：反射层 ------------------------------------------------------
    refl = img / light[..., None]
    if use_noise_aware:
        alpha = np.clip((gain - 1.0) / k_ref, 0.0, alpha_max)
        local_mean = np.stack([box_filter(refl[..., c], box_r) for c in range(3)], axis=-1)
        refl = refl + alpha[..., None] * (local_mean - refl)
        beta = beta_min + (beta_max - beta_min) * np.exp(-((gain - 1.0) / tau) ** 2)
    else:
        # 消融：反射层原样放大，不做任何收缩，暗部噪声会跟着翻上去
        beta = np.ones_like(gain)

    refl = np.clip(refl, 1e-4, 8.0)
    out = light_new[..., None] * refl ** beta[..., None]

    # M2 的后半段：整体配光，把平均亮度对到目标值
    if use_adaptive_gamma:
        out = out * _solve_gain(out, target)

    # ---- M4：颜色 --------------------------------------------------------
    if use_color:
        out = soft_clip(out, knee=knee)
        out = adjust_saturation(out, sat_gain)
        out = np.clip(out, 0.0, 1.0)
    else:
        # 消融：逐通道分位拉伸，颜色会发灰/偏色
        lo = np.percentile(out, 1.0)
        hi = np.percentile(out, 99.0)
        out = np.clip((out - lo) / max(hi - lo, 1e-6), 0.0, 1.0)

    return out


def _solve_gain(img, target, lo=0.02, hi=60.0, iters=16, step=4):
    """二分求整体曝光系数，使输出平均亮度等于 target。

    只在 1/4 分辨率的缩略图上搜索，单次搜索不到 1 ms。
    """
    small = np.mean(img[::step, ::step])
    if small < 1e-8:
        return 1.0
    for _ in range(iters):
        mid = np.sqrt(lo * hi)
        if small * mid < target:
            lo = mid
        else:
            hi = mid
    return float(np.sqrt(lo * hi))


def alpha_map(gain, k_ref=3.0, alpha_max=0.85):
    """把收缩系数单独暴露出来，方便画图分析。"""
    return np.clip((gain - 1.0) / k_ref, 0.0, alpha_max)


# 消融实验的预设，键名直接对应报告中的表格行
ABLATIONS = {
    "Ours (full)": dict(),
    "w/o M1 (Gauss)": dict(use_guided=False),
    "w/o M2 (fixed γ)": dict(use_adaptive_gamma=False),
    "w/o M3 (no shrink)": dict(use_noise_aware=False),
    "w/o M4 (per-channel)": dict(use_color=False),
}
