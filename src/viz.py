"""画图工具：拼图、对比图、直方图、条形图、曲线图。

环境里没有 matplotlib，索性用 Pillow 自己画。图都做成白底、细边框、少装饰，
直接贴进报告里也不会显得花哨。
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]

_cache = {}


def font(size):
    if size in _cache:
        return _cache[size]
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            f = ImageFont.truetype(path, size)
            _cache[size] = f
            return f
    f = ImageFont.load_default()
    _cache[size] = f
    return f


def to_image(arr):
    arr = np.clip(np.asarray(arr, dtype=np.float64), 0.0, 1.0)
    return Image.fromarray((arr * 255.0).round().astype(np.uint8))


def fit(im, w, h):
    """等比缩放后居中裁剪到 (w, h)。"""
    sw, sh = im.size
    s = max(w / sw, h / sh)
    if abs(s - 1.0) > 1e-6:
        im = im.resize((max(1, int(round(sw * s))), max(1, int(round(sh * s)))), Image.LANCZOS)
    left = (im.width - w) // 2
    top = (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def grid(tiles, cols, tile_w, tile_h, labels=None, pad=8, label_h=22,
         border=(200, 200, 200), label_size=15, bg="white"):
    """把若干张图拼成网格。tiles 的元素可以是 PIL.Image 或 numpy 数组。"""
    n = len(tiles)
    rows = (n + cols - 1) // cols
    W = cols * tile_w + (cols + 1) * pad
    H = rows * (tile_h + label_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(sheet)

    for i, t in enumerate(tiles):
        im = t if isinstance(t, Image.Image) else to_image(t)
        im = fit(im.convert("RGB"), tile_w, tile_h)
        r, c = divmod(i, cols)
        x = pad + c * (tile_w + pad)
        y = pad + r * (tile_h + label_h + pad)
        sheet.paste(im, (x, y))
        d.rectangle([x - 1, y - 1, x + tile_w, y + tile_h], outline=border)
        if labels:
            text = labels[i]
            tw = d.textlength(text, font=font(label_size))
            d.text((x + (tile_w - tw) / 2, y + tile_h + 4), text, fill=(30, 30, 30),
                   font=font(label_size))
    return sheet


def _axes(d, box, xr, yr, xticks=None, yticks=None, xlabel="", ylabel="", tick_size=13):
    x0, y0, x1, y1 = box
    d.rectangle([x0, y0, x1, y1], outline=(90, 90, 90))
    f = font(tick_size)

    for t in (xticks or []):
        px = x0 + (t - xr[0]) / (xr[1] - xr[0]) * (x1 - x0)
        d.line([px, y1, px, y1 + 4], fill=(90, 90, 90))
        s = f"{t:g}"
        d.text((px - d.textlength(s, font=f) / 2, y1 + 6), s, fill=(40, 40, 40), font=f)
    for t in (yticks or []):
        py = y1 - (t - yr[0]) / (yr[1] - yr[0]) * (y1 - y0)
        d.line([x0 - 4, py, x0, py], fill=(90, 90, 90))
        s = f"{t:g}"
        d.text((x0 - 6 - d.textlength(s, font=f), py - 8), s, fill=(40, 40, 40), font=f)

    if xlabel:
        tw = d.textlength(xlabel, font=f)
        d.text(((x0 + x1 - tw) / 2, y1 + 24), xlabel, fill=(20, 20, 20), font=f)
    if ylabel:
        tw = d.textlength(ylabel, font=f)
        d.text((x0 + (x1 - x0 - tw) / 2, y0 - 24), ylabel, fill=(20, 20, 20), font=f)


def line_plot(series, out_path, size=(560, 340), xr=None, yr=None,
              xlabel="", ylabel="", xticks=None, yticks=None, colors=None,
              legend=None, markers=True):
    """series: [(xs, ys), ...]"""
    W, H = size
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    box = (70, 54, W - 26, H - 56)

    allx = np.concatenate([np.asarray(s[0], float) for s in series])
    ally = np.concatenate([np.asarray(s[1], float) for s in series])
    xr = xr or (float(allx.min()), float(allx.max()))
    if yr is None:
        pad = 0.06 * (ally.max() - ally.min() + 1e-9)
        yr = (float(ally.min() - pad), float(ally.max() + pad))

    _axes(d, box, xr, yr, xticks, yticks, xlabel, ylabel)
    colors = colors or [(40, 90, 170), (200, 90, 40), (60, 140, 80), (120, 80, 160)]
    f = font(13)

    x0, y0, x1, y1 = box
    for k, (xs, ys) in enumerate(series):
        pts = [(x0 + (x - xr[0]) / (xr[1] - xr[0]) * (x1 - x0),
                y1 - (y - yr[0]) / (yr[1] - yr[0]) * (y1 - y0)) for x, y in zip(xs, ys)]
        c = colors[k % len(colors)]
        d.line(pts, fill=c, width=2)
        if markers:
            for px, py in pts:
                d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=c)

    if legend:
        for k, text in enumerate(legend):
            c = colors[k % len(colors)]
            bx = box[0] + 10 + (k % 2) * 150
            by = box[1] + 8 + (k // 2) * 20
            d.line([bx, by + 7, bx + 22, by + 7], fill=c, width=2)
            d.text((bx + 28, by), text, fill=(30, 30, 30), font=f)

    im.save(out_path)
    return out_path


def _nice_ticks(vmax, n=5):
    """挑一组好看的刻度：步长取 1/2/2.5/5 × 10^k。"""
    raw = vmax / n
    mag = 10 ** np.floor(np.log10(max(raw, 1e-9)))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if step >= raw:
            break
    top = step * np.ceil(vmax / step)
    ticks = [round(step * i, 6) for i in range(int(round(top / step)) + 1)]
    return top, ticks


def bar_chart(labels, values, out_path, size=(620, 330), ylabel="", ylim=None,
              fmt="{:.2f}", color=(70, 110, 170), highlight=None):
    """简单柱状图，highlight 指定要高亮的下标（用深色）。"""
    W, H = size
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    box = (66, 50, W - 24, H - 62)
    if ylim is None:
        vmax, ticks = _nice_ticks(max(values) * 1.1)
        vmin = 0.0
    else:
        vmax, vmin = ylim[1], ylim[0]
        ticks = [round(vmin + (vmax - vmin) * i / 4, 3) for i in range(5)]
    _axes(d, box, (0, len(labels)), (vmin, vmax), yticks=ticks, ylabel=ylabel)

    x0, y0, x1, y1 = box
    slot = (x1 - x0) / len(labels)
    bw = slot * 0.55
    f = font(12)
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = x0 + slot * (i + 0.5)
        py = y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)
        c = (40, 60, 90) if (highlight is not None and i == highlight) else color
        d.rectangle([cx - bw / 2, py, cx + bw / 2, y1], fill=c)
        s = fmt.format(v)
        d.text((cx - d.textlength(s, font=f) / 2, py - 16), s, fill=(30, 30, 30), font=f)
        tw = d.textlength(lab, font=f)
        d.text((cx - tw / 2, y1 + 8), lab, fill=(30, 30, 30), font=f)

    im.save(out_path)
    return out_path


def hist_plot(images, labels, out_path, size=(560, 330), bins=64, colors=None):
    """多条亮度直方图叠加对比（归一化到概率密度）。"""
    W, H = size
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    box = (70, 54, W - 26, H - 56)
    _axes(d, box, (0, 1), (0, 1), xticks=[0, 0.25, 0.5, 0.75, 1.0],
          xlabel="亮度", ylabel="")
    colors = colors or [(150, 150, 150), (40, 90, 170), (200, 90, 40), (60, 140, 80)]
    f = font(13)

    curves = []
    for img in images:
        y = 0.299 * img[..., 0] + 0.587 * img[..., 1] + 0.114 * img[..., 2]
        h, _ = np.histogram(y.ravel(), bins=bins, range=(0, 1))
        p = h / h.sum()
        curves.append(p)
    top = max(c.max() for c in curves) * 1.1

    x0, y0, x1, y1 = box
    for k, p in enumerate(curves):
        c = colors[k % len(colors)]
        pts = [(x0 + i / (bins - 1) * (x1 - x0), y1 - p[i] / top * (y1 - y0))
               for i in range(bins)]
        d.line(pts, fill=c, width=2)
    for k, text in enumerate(labels):
        c = colors[k % len(colors)]
        bx = box[0] + 10 + (k % 2) * 130
        by = box[1] + 8 + (k // 2) * 20
        d.line([bx, by + 7, bx + 22, by + 7], fill=c, width=2)
        d.text((bx + 28, by), text, fill=(30, 30, 30), font=f)

    im.save(out_path)
    return out_path
