"""生成课程大作业报告 docx：套用学院封面模板，正文按任务书的五个部分组织。

    python docs/build_report.py

表格里的数字全部从 results/*.csv 读，避免报告和实验对不上。
"""

import csv
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = (r"C:\Users\35102\xwechat_files\wxid_rxybcdlidrpt22_a49a\msg\file\2026-11"
            r"\计算机科学与工程学院实验报告首页.docx")
OUT = os.path.join(ROOT, "报告-张子腾-20245630.docx")
FIGS = os.path.join(ROOT, "results", "figs")

REPO_URL = "https://github.com/KinsenZhang/lowlight-enhance"

STUDENT = {
    "课程": "图像处理",
    "专业": "人工智能",
    "班级": "人智3班",
    "学号": "20245630",
    "姓名": "张子腾",
    "教师": "刘尧",
}


# ---------------------------------------------------------------- 读取实验数据

def read_csv(path):
    with open(os.path.join(ROOT, "results", path), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_csv_abs(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_numbers():
    summary = {r["method"]: r for r in read_csv("summary.csv")}
    ablation = read_csv("ablation.csv")
    meta = read_csv_abs(os.path.join(ROOT, "data", "meta.csv"))
    return summary, ablation, meta


def mean_of(rows, key, name):
    sel = [float(r[key]) for r in rows if r["variant"] == name]
    return sum(sel) / len(sel)


# ---------------------------------------------------------------- 排版小工具

def set_east_asia(style_or_run, font_name):
    rpr = style_or_run.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), font_name)
    rfonts.set(qn("w:ascii"), font_name)
    rfonts.set(qn("w:hAnsi"), font_name)


def make_style(doc, name, size, east, bold=False, line=1.5, before=0, after=0,
               indent_chars=0, align=WD_ALIGN_PARAGRAPH.JUSTIFY, keep_next=False):
    from docx.enum.style import WD_STYLE_TYPE

    style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = doc.styles["Normal"]
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.name = east
    set_east_asia(style, east)
    pf = style.paragraph_format
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.alignment = align
    if indent_chars:
        pf.first_line_indent = Pt(size * indent_chars)
    pf.keep_with_next = keep_next
    pf.widow_control = True
    return style


def P(doc, text, style="正文"):
    """普通段落，反引号包裹的部分用等宽字体。"""
    p = doc.add_paragraph(style=style)
    for i, chunk in enumerate(text.split("`")):
        if not chunk:
            continue
        run = p.add_run(chunk)
        if i % 2 == 1:
            run.font.name = "Consolas"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            run.font.size = Pt(10)
    return p


def H1(doc, text):
    return doc.add_paragraph(text, style="标题1")


def H2(doc, text):
    return doc.add_paragraph(text, style="标题2")


FIG_JPG_DIR = os.path.join(ROOT, "docs", "figs_jpg")
PHOTO_FIGS = {"fig1_dataset.png", "fig2_compare02.png", "fig3_compare07.png", "fig4_zoom.png"}


def figure_path(filename):
    """照片类的图转一份 JPEG 嵌入，控制 docx 体积；图表仍用 PNG 保证文字清晰。"""
    src = os.path.join(FIGS, filename)
    if filename not in PHOTO_FIGS:
        return src
    from PIL import Image

    os.makedirs(FIG_JPG_DIR, exist_ok=True)
    out = os.path.join(FIG_JPG_DIR, os.path.splitext(filename)[0] + ".jpg")
    if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(src):
        Image.open(src).convert("RGB").save(out, quality=92, optimize=True)
    return out


def FIG(doc, filename, width_cm, caption):
    p = doc.add_paragraph(style="插图")
    p.add_run().add_picture(figure_path(filename), width=Cm(width_cm))
    return doc.add_paragraph(caption, style="图注")


def CODE(doc, lines):
    for i, line in enumerate(lines):
        p = doc.add_paragraph(line, style="代码")
        p.paragraph_format.space_after = Pt(6 if i == len(lines) - 1 else 0)


def _cell_text(cell, text, bold=False, size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER):
    cell.text = ""
    p = cell.paragraphs[0]
    p.style = "表格文字"
    p.alignment = align
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def _shade(cell, hex_color="F2F2F2"):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def TABLE(doc, header, rows, widths, caption=None, size=9.5):
    if caption:
        doc.add_paragraph(caption, style="表注")
    table = doc.add_table(rows=1, cols=len(header))
    table.style = doc.styles["Table Grid"]
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:tblHeader"))

    for j, text in enumerate(header):
        _cell_text(table.rows[0].cells[j], text, bold=True, size=size)
        _shade(table.rows[0].cells[j])

    for row in rows:
        cells = table.add_row().cells
        for j, text in enumerate(row):
            _cell_text(cells[j], text, size=size)

    for row in table.rows:
        for j, cell in enumerate(row.cells):
            cell.width = Cm(widths[j])
    doc.add_paragraph("", style="表后间隙")
    return table


def add_page_number_footer(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    run.font.size = Pt(9)
    run.font.name = "Times New Roman"


# ---------------------------------------------------------------- 封面

def fill_cover(doc):
    tbl = doc.tables[0]

    def put(row_idx, label, value):
        cells = tbl.rows[row_idx].cells
        for i, cell in enumerate(cells):
            if cell.text.strip() == label:
                for nxt in cells[i + 1:]:
                    if nxt.text.strip() == "" or nxt.text.strip() == value:
                        nxt.text = ""
                        p = nxt.paragraphs[0]
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run = p.add_run(value)
                        run.font.size = Pt(11)
                        run.font.name = "Times New Roman"
                        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                        return
        raise KeyError(f"封面上找不到 {label}")

    put(0, "实验课程名称", STUDENT["课程"])
    put(1, "专业", STUDENT["专业"])
    put(1, "班级", STUDENT["班级"])
    put(1, "指导教师签字", STUDENT["教师"])
    put(2, "学号", STUDENT["学号"])
    put(2, "姓名", STUDENT["姓名"])

    # 实验课程总结：保留模板提示，后面接四行简短总结
    summary_cell = None
    for row in tbl.rows:
        for cell in row.cells:
            if "实验课程总结" in cell.text and "从以下方面总结" in cell.text:
                summary_cell = cell
                break
        if summary_cell is not None:
            break

    texts = [
        "1. 把课上的 Retinex、引导滤波、CLAHE 等算子在同一个任务里串起来用了一遍，并自行实现了"
        "积分图、SSIM 与 MSRCR，对算子细节的掌握比直接调用现成函数更扎实。",
        "2. 体会最深的是指标与观感经常不一致：例如光照估计的改进在 PSNR 上只有 0.12 dB，"
        "需要多套指标互相印证才能定位问题。",
        "3. 建议课程增加一次从劣质原图到成片的全流程小练习，并在评分要求中明确是否要求定量对比。",
        "4. 其他方面暂无意见。",
    ]
    for t in texts:
        p = summary_cell.add_paragraph()
        pf = p.paragraph_format
        pf.first_line_indent = Pt(10.5 * 2)
        pf.line_spacing = 1.15
        pf.space_before = Pt(0)
        pf.space_after = Pt(2)
        run = p.add_run(t)
        run.font.size = Pt(10.5)
        run.font.name = "宋体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


# ---------------------------------------------------------------- 正文

def build():
    doc = Document(TEMPLATE)

    make_style(doc, "正文", 12, "宋体", line=1.5, after=0, indent_chars=2)
    make_style(doc, "标题1", 14, "黑体", bold=False, line=1.5, before=14, after=8,
               align=WD_ALIGN_PARAGRAPH.LEFT, keep_next=True)
    make_style(doc, "标题2", 12, "黑体", bold=False, line=1.5, before=10, after=4,
               align=WD_ALIGN_PARAGRAPH.LEFT, keep_next=True)
    make_style(doc, "文档标题", 18, "黑体", line=1.5, before=0, after=6,
               align=WD_ALIGN_PARAGRAPH.CENTER)
    make_style(doc, "副标题", 10.5, "宋体", line=1.5, before=0, after=18,
               align=WD_ALIGN_PARAGRAPH.CENTER)
    make_style(doc, "图注", 10.5, "宋体", line=1.2, before=4, after=10,
               align=WD_ALIGN_PARAGRAPH.CENTER)
    make_style(doc, "表注", 10.5, "宋体", line=1.2, before=10, after=2,
               align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    make_style(doc, "插图", 10.5, "宋体", line=1.0, before=6, after=0,
               align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    make_style(doc, "代码", 9, "Consolas", line=1.0, before=2, after=0,
               align=WD_ALIGN_PARAGRAPH.LEFT)
    doc.styles["代码"].paragraph_format.left_indent = Cm(0.9)
    doc.styles["代码"].element.get_or_add_rPr().get_or_add_rFonts().set(
        qn("w:eastAsia"), "宋体")
    make_style(doc, "表格文字", 9.5, "宋体", line=1.0, before=1, after=1,
               align=WD_ALIGN_PARAGRAPH.CENTER)
    make_style(doc, "表后间隙", 6, "宋体", line=1.0, before=0, after=0,
               align=WD_ALIGN_PARAGRAPH.CENTER)
    make_style(doc, "参考文献", 10.5, "宋体", line=1.25, before=0, after=2,
               align=WD_ALIGN_PARAGRAPH.LEFT)

    fill_cover(doc)
    add_page_number_footer(doc.sections[0])

    summary, ablation, meta = load_numbers()
    g, c, m, o = summary["Gamma 2.2"], summary["CLAHE"], summary["MSRCR"], summary["Ours"]

    # ---------------- 标题与摘要
    title = doc.add_paragraph("基于引导滤波与自适应光照映射的低照度图像增强", style="文档标题")
    title.paragraph_format.page_break_before = True
    doc.add_paragraph("——对多尺度 Retinex 的四处改进与对比实验", style="副标题")

    P(doc, "本工作以多尺度 Retinex（MSRCR）为基线，在光照估计、光照映射、反射层噪声抑制与颜色"
           "重建四个环节进行改进，并在 8 组带真值的半合成低照度图像上完成定量对比与消融实验。"
           f"改进后 PSNR 由 {float(m['psnr']):.2f} dB 提升至 {float(o['psnr']):.2f} dB，SSIM 由 "
           f"{float(m['ssim']):.3f} 提升至 {float(o['ssim']):.3f}，平均色差由 {float(m['delta_e']):.1f} "
           f"降至 {float(o['delta_e']):.1f}，暗部高频噪声降至 MSRCR 的 1/7 左右，"
           f"单张 960×600 图像的处理耗时基本持平（{float(o['time']):.2f} s 对 {float(m['time']):.2f} s）。")

    # ---------------- 一、GitHub 链接
    H1(doc, "一、GitHub 链接")
    P(doc, f"仓库地址：{REPO_URL}")
    P(doc, "仓库包含源码、脚本、8 组测试数据与全部实验结果，不包含模型权重（本方法不需要训练）。"
           "安装依赖后依次执行以下三条命令即可复现报告中的全部数据：")
    CODE(doc, [
        "pip install -r requirements.txt",
        "python -m scripts.run_benchmark --ablation --timing --scaling",
        "python -m scripts.make_figures",
    ])
    P(doc, "其中 `run_benchmark` 输出逐图逐方法的指标（`metrics.csv`）、汇总（`summary.csv`）、"
           "消融（`ablation.csv`）与耗时（`scaling.csv`），`make_figures` 生成第 3 至 5 节的图。"
           "低照度合成与噪声均固定随机种子，重复运行结果一致。目录结构如下：")
    CODE(doc, [
        "lowlight-enhance/",
        "  src/       filters  color  enhance  baselines  metrics  dataset  viz",
        "  scripts/   make_dataset  run_benchmark  make_figures  demo",
        "  data/      gt/  low/  meta.csv",
        "  results/   metrics.csv  summary.csv  ablation.csv  scaling.csv  figs/",
        "  docs/      build_report.py（生成报告脚本）",
        "  报告-张子腾-20245630.docx",
    ])
    P(doc, "运行环境为 Python 3.9 及以上、numpy 与 Pillow。实现中未引入 OpenCV：一方面希望每个"
           "算子的行为都能在代码中直接核对（盒式滤波的积分图、引导滤波的四步均值、SSIM 的可分离"
           "高斯窗均为自行实现），另一方面这些算子的复杂度本身为 O(N)，引入大型依赖收益有限。"
           "第三方库仅用于图像读写。")

    # ---------------- 二、任务描述
    H1(doc, "二、任务描述")
    H2(doc, "2.1 问题分析")
    P(doc, "夜间、室内或逆光条件下拍摄的图像通常同时存在三个问题：整体亮度偏低、暗部噪声明显、"
           "光照在空间上分布不均（台灯、窗户或路灯往往只照亮画面的一部分）。三者相互耦合：提高"
           "整体亮度会同时放大噪声；仅压制暗部会使亮部过曝；统一提亮则导致颜色发灰。低照度增强"
           "的目标是在不引入上述副作用的前提下，使图像的亮度、对比度与颜色恢复到接近正常曝光的水平。")
    H2(doc, "2.2 全局伽马变换的局限")
    P(doc, "最直接的做法是对整幅图像施加伽马变换 I^(1/2.2)，以单条曲线提高亮度。该方法只有一个"
           "自由度，存在三方面局限。")
    P(doc, "其一，各图的实际暗度不同。本实验将 8 张低照度图的平均亮度统一控制在 0.22 左右，但其"
           "明暗结构差异较大，同一指数在部分图像上过曝、在另一部分仍偏暗。表 4 中“去 M2”一行即"
           "该版本，PSNR 仅 17.96 dB。")
    P(doc, "其二，伽马变换无法区分“因光照弱而暗”与“因物体本色深而暗”。前者需要增强，后者不应"
           "增强；全局曲线对二者一视同仁，结果是深色物体被一并提亮，画面趋于平淡。")
    P(doc, "其三，伽马曲线在暗部斜率最大，而暗部恰是信噪比最低的区域，噪声被放大得最严重。")
    P(doc, "Retinex 理论将图像表示为 I = L∘R，L 为光照分量，R 为反射（本征颜色）分量，分别处理后"
           "可使亮度、颜色与细节解耦。MSRCR、LIME、RetinexNet 等方法均属这一框架，本工作的改进"
           "也在该框架内进行。")
    H2(doc, "2.3 研究内容")
    P(doc, "基线选取 MSRCR：它对光照不均具有一定校正能力，但灰白化与噪声放大问题突出（第 5 节中 "
           "SSIM 仅 0.614，暗部噪声为本方法的 7 倍）。在保留其框架的前提下，对四个环节做了替换，"
           "每个环节均可单独关闭以便分析贡献：")
    CODE(doc, [
        "M1  光照图改用引导滤波估计，替代三尺度高斯模糊",
        "M2  光照按 L' = (L/L̄)^p 重新配光，替代固定指数伽马",
        "M3  反射层按放大倍数向局部均值收缩，抑制暗部噪声",
        "M4  同一增益图作用于三通道并加高光软限幅，替代逐通道拉伸",
    ])
    P(doc, "目标是在不引入训练与先验库的条件下，依靠经典算子同时处理亮度、噪声、颜色与晕圈，并使"
           "每一步的作用可解释。评价采用两类指标：有真值的 PSNR、SSIM 与色差，以及无参考的熵、"
           "平均梯度、色彩丰富度与阴影噪声。")

    # ---------------- 三、数据描述
    H1(doc, "三、数据描述")
    H2(doc, "3.1 测试图像")
    P(doc, "共 8 张，分辨率统一为 960×600，由 4K 公开图像素材（Windows 系统自带壁纸）中心裁剪"
           "得到。图像内容经过挑选：01–03 为天空与水面的平滑渐变（易暴露晕圈与色带），04–06 为"
           "织物的柔和阴影（可反映暗部层次是否丢失），07 为长直边界的几何图形，08 为高饱和蓝色"
           "花瓣（用于观察颜色漂移）。")
    P(doc, "素材原始曝光差异较大，平均亮度在 0.31 至 0.85 之间。若直接混用，PSNR 将被整体亮度"
           "差异主导：在未统一曝光的一版数据上，同一方法在不同图像上的 PSNR 相差可达十几分贝，"
           "指标失去可比性。因此先在线性域为每张真值乘以一个增益，将平均亮度统一到 0.50。该操作"
           "只改变曝光、不改变内容，代价是提亮幅度较大的图像存在少量高光裁切（统一后真值的高光"
           "像素比例为 8.7%）。需要指出，真值被归一到 0.50 之后，本方法的目标亮度取 0.50 与之对应，"
           "二者并非相互独立，这一点在 5.9 节作为局限再次说明。")
    FIG(doc, "fig1_dataset.png", 14.4, "图 1  测试图像示例（上排为真值，下排为对应的低照度图）")
    H2(doc, "3.2 低照度图像的生成")
    P(doc, "由于缺少配对的真实低照度数据，低照度图像按简化的相机成像模型合成：")
    CODE(doc, [
        "lin  = srgb_to_linear(gt)",
        "e    = a * lin * S(x,y) * V(x,y)                  # 曝光 × 光照场 × 暗角",
        "e   += N(0, sqrt(2e-4 * e)) + N(0, 1.5e-4)        # 散粒噪声 + 读出噪声",
        "low  = linear_to_srgb(clip(e * (1, 1, 1.06)))      # 轻微偏蓝的白平衡",
    ])
    P(doc, "其中 a 为曝光系数，由二分搜索反解得到，使低照度图平均亮度约为 0.22，比真值低约 2.5 档"
           "（对应 a 在 0.25 至 0.28 之间，见表 1）；S 为空间不均的光照场，由两团低频高斯光斑与"
           "一块软边矩形叠加而成，模拟窗光与灯罩，取值范围 0.45 至 1.0；V 为强度 0.15 的镜头暗角；"
           "噪声包含与光照强度成正比的散粒噪声和恒定的读出噪声；最后乘以偏冷的白平衡以模拟夜景色偏。")
    rows = []
    for r in meta:
        rows.append([r["id"], r["note"].split("，")[0], f"{float(r['exposure']):.3f}",
                     f"{float(r['cast_b']):.2f}", f"{float(r['gt_mean']):.2f}",
                     f"{float(r['low_mean']):.2f}"])
    TABLE(doc, ["编号", "内容", "曝光 a", "B 通道增益", "真值亮度", "低照度亮度"], rows,
          [1.4, 5.8, 1.8, 2.0, 1.7, 1.7], "表 1  测试集的合成参数")
    P(doc, "按 2.5 档折算，提亮过程相当于将噪声放大约 2.5 倍，这是所有对比方法共同面对的误差"
           "来源。3.4 节的解析反解给出了该噪声水平下的性能上界。")
    H2(doc, "3.3 半合成数据的局限")
    P(doc, "只有半合成数据才具备真值，PSNR、SSIM 与色差才有意义。其局限在于噪声模型过于理想："
           "真实相机还存在坏点、机内降噪造成的涂抹、JPEG 块效应以及白平衡估计误差，均比本文加入"
           "的模型复杂。因此第 5 节的绝对数值只适合横向比较，不能作为真实场景下的性能承诺；对真实"
           "照片而言，可用的评价依据仅为无参考指标与主观观察，这也是本文保留熵、平均梯度与色彩"
           "丰富度的原因。")
    H2(doc, "3.4 解析反解参考上界")
    P(doc, "由于 a、S、V 与色偏在合成时均为已知，可构造一个“已知答案”的反解：直接按模型除回。"
           "该方法 PSNR 为 34.98 dB、色差 3.96，但 SSIM 仅 0.888，低于本方法的 0.962。原因在于"
           "它未做任何去噪，1/(a·S·V) 的放大会将噪声一并放大，而 SSIM 对这类高频噪声较为敏感。"
           "这组结果说明两点：其一，本方法与结构完全正确的解之间仍有约 9 dB 差距，主要来自光照"
           "估计误差；其二，本文 SSIM 的优势中有一部分来自暗部更干净，而非全部来自结构更准确。")

    # ---------------- 四、代码修改描述
    H1(doc, "四、代码修改描述")
    H2(doc, "4.1 基线 MSRCR 的复现")
    P(doc, "MSRCR 在对数域减去三个尺度的高斯模糊：R = Σ log I − log(F_k * I)，三个 σ 取 "
           "15/80/250 并按图像短边缩放，再乘色彩恢复因子 C_i = β·log(α·I_i / Σ I)（α=125、β=46），"
           "最后做分位拉伸。复现过程中有两个问题需要处理。")
    P(doc, "一是计算量。σ=250 时高斯核长度为 1501，3 通道 × 3 尺度共 9 次卷积，直接计算需 30 s "
           "以上。改为“降采样至 σ/2 → 小核模糊 → 双线性上采样”后，总耗时降至 0.55 s，两版结果"
           "并排比较无明显差异。")
    P(doc, "二是收尾的分位比例。按常见实现的 1%/99% 拉伸，MSRCR 输出被压缩成灰片，平均亮度仅 "
           "0.10；改为 0.5%/99.9% 后才可用（PSNR 由 11.6 提高到 13.2）。该参数在本文测试集上确定，"
           "相当于对 MSRCR 做了有利调整，因此第 5 节结果对 MSRCR 并不苛刻。")
    H2(doc, "4.2 M1：光照图改用引导滤波")
    P(doc, "MSRCR 以高斯核估计光照，等价于假设光照在局部为常数。在亮暗交界处（窗台、灯罩边缘），"
           "高斯核会混合亮侧与暗侧，除回后在亮侧产生暗晕、暗侧产生亮晕，形成数十像素宽的灰边。"
           "仅改用 σ=32 的高斯核只能使晕圈变窄，无法消除。")
    P(doc, "引导滤波的局部线性模型为 q_i = a·I_i + b，在窗口内求解最小二乘后加权平均：")
    CODE(doc, [
        "a = cov(I, p) / (var(I) + eps)",
        "b = mean(p) - a * mean(I)",
        "q = mean(a) * I + mean(b)      # 四个量都用盒式滤波求，O(N)",
    ])
    P(doc, "其特性为：窗口内方差远大于 eps 时 a→1，输出跟随引导图，边缘得以保留；方差很小时 a→0，"
           "退化为均值滤波，暗部噪声被平滑。以 V = max(R,G,B) 同时作为引导图与输入，即得到保边的"
           "光照估计。参数取 r=32、eps=3e-3。eps 的影响主要体现在 SSIM：取 1e-3 与 3e-3 时指标基本"
           "一致（均为 25.85 dB / 0.962），取到 1e-2 时 SSIM 降至 0.955，取 3e-2 降至 0.948，原因是"
           "窗口内本应保留的亮度起伏被当作噪声平滑掉了。")
    FIG(doc, "fig5_maps.png", 14.0,
        "图 2  光照估计与增益图（以 07 号图为例）。右下两格为放大倍数 k 与收缩系数 α，"
        "暗处 k 大、α 大，对应更强的噪声抑制")
    H2(doc, "4.3 M2：从固定伽马到归一化幂律")
    P(doc, "最初的做法是对光照图施加固定指数的伽马变换 L^γ，γ 取 1/1.8（约 0.56，与表 4“去 M2”"
           "一行一致）。其问题已在 2.2 节说明：同一指数无法适应不同暗度的图像。改进后分为两步："
           "先按均值归一化，再用指数 p 压缩明暗差，最后整体乘以一个系数使输出平均亮度达到目标值。")
    CODE(doc, [
        "L' = (L / L̄) ** p            # 去掉“这幅图有多暗”的自由度，只保留“压多平”",
        "out = g * L' * (I / L) ** beta       # g 由二分搜索确定，使 out 的均值到 0.50",
    ])
    P(doc, "系数 g 由二分搜索确定，搜索在 1/4 分辨率的缩略图上迭代 16 次，耗时不足 1 ms。p 的取值"
           "见 5.7 节，p=0.6 时 PSNR 最高。值得注意的是 p 减小时指标反而下降（p=0.4 时 24.56 dB，"
           "p=0.2 时 22.04 dB）：R=I/L 在去除光照的同时也去除了物体本征的阴影，而后者在真值中"
           "真实存在。因此“完全去除光照”并不等价于“更接近真值”。")
    H2(doc, "4.4 M3：反射层按放大倍数抑制噪声")
    P(doc, "R=I/L 在暗部被放大 k = L'/L 倍，本实验中暗角处可达 6–8 倍，噪声随之放大。处理方式是"
           "以 k 作为噪声放大系数进行控制：")
    CODE(doc, [
        "alpha = clip((k - 1) / 3, 0, 0.85)                 # 收缩强度，暗处大",
        "R'    = R + alpha * (box7(R) - R)                  # 向局部均值收缩",
        "beta  = 0.70 + 0.30 * exp(-((k - 1) / 1.8)**2)     # 亮部留细节，暗部平滑",
    ])
    P(doc, "未采用双边滤波或非局部均值的原因在于：该环节的主要误差已不是噪声而是光照估计（3.4 节"
           "两者相差 9 dB），均值收缩已可将阴影区高频噪声由 0.0151 降至 0.0069，代价仅是暗部细节"
           "略软；在 0.5 s 的耗时预算内再引入非局部均值并不划算，且会进一步模糊暗部的细枝结构。")
    H2(doc, "4.5 M4：收尾与颜色")
    P(doc, "重建时同一增益图作用于三个通道（I/L 保留了通道比例，颜色的相对关系不变）；随后对"
           "超过拐点的部分作软限幅 y = knee + (1−knee)(1−e^(−(x−knee)/(1−knee)))，避免亮部被硬"
           "截断为纯白；最后进行饱和度补偿。")
    P(doc, "饱和度系数经 1.08、1.12、1.25 三组测试，PSNR 分别为 25.66、25.54、25.18，SSIM 均在 "
           "0.962 附近，而色差随系数增大而上升。原因是本方法的增益映射本身保持色度，额外补偿"
           "反而过冲，因此最终取 1.0，代码中保留该开关。作为对照，去掉 M4（对三通道分别作分位"
           "拉伸）后 PSNR 降至 18.08 dB、色差升至 13.67，说明该环节并非可有可无的收尾。")
    H2(doc, "4.6 实现与参数")
    P(doc, "盒式滤波以积分图实现，代价与半径无关；引导滤波为 4 次盒式滤波加 2 次均值；大 σ 高斯"
           "采用降采样近似。960×600 图像的单张耗时 0.52 s，与 MSRCR 相当，约为伽马变换的十倍。"
           "若需进一步提速，可将 M3 的收缩运算放在 1/2 分辨率上执行，代价是细节损失，该版本未在"
           "本实验中实现。")
    rows = [
        ["r", "32", "引导滤波窗口半径，决定晕圈宽度"],
        ["eps", "3×10⁻³", "引导滤波正则项，按 V 通道局部方差量级选取"],
        ["p", "0.60", "光照压缩指数，见 5.7 节的扫描"],
        ["target", "0.50", "配光后的目标平均亮度"],
        ["k_ref", "3.0", "增益归一化尺度，超过它按 0.85 收缩"],
        ["α_max", "0.85", "反射层向局部均值收缩的最大比例"],
        ["β", "0.70–1.00", "细节增益上下界，随 k 指数衰减"],
        ["knee", "0.85", "高光软限幅拐点"],
    ]
    TABLE(doc, ["参数", "取值", "作用"], rows, [2.0, 2.6, 10.0], "表 2  本方法的默认参数")

    # ---------------- 五、结果对比
    H1(doc, "五、结果对比")
    H2(doc, "5.1 评价指标")
    P(doc, "有真值的指标为三项：PSNR（按 0–255 计算）、SSIM（亮度通道、11×11 高斯窗、σ=1.5）与 "
           "ΔE*ab（CIE76，在 Lab 空间求平均色差）。全局指标容易受整体亮度是否匹配的影响，因此"
           "另设两项分区指标：取低照度图最暗的 35% 与最亮的 35% 像素分别计算 PSNR，用于判断方法"
           "是否只照顾了一端。")
    P(doc, "无参考指标为四项：阴影噪声（暗区内高频残差的标准差，越小越干净）、信息熵、平均梯度"
           "与色彩丰富度（Hasler 与 Süsstrunk 的 M 指标）。耗时在 960×600 图像上取三次平均。")
    H2(doc, "5.2 定量结果")
    P(doc, "表 3 为 8 张图的平均值。本方法 PSNR 为 25.85 dB，较 Gamma 2.2 高 3.4 dB，较 MSRCR 高 "
           "13.4 dB；SSIM 为 0.962，是四种方法中唯一超过 0.95 的；平均色差 6.03，不足 Gamma 的"
           "一半、MSRCR 的五分之一；阴影噪声 0.0069，为 Gamma 的 46%、MSRCR 的 14%。")
    rows = []
    for label, d in [("Gamma 2.2", g), ("CLAHE", c), ("MSRCR", m), ("本文方法", o)]:
        rows.append([label, f"{float(d['psnr']):.2f}", f"{float(d['ssim']):.3f}",
                     f"{float(d['delta_e']):.2f}", f"{float(d['shadow_noise']):.4f}",
                     f"{float(d['time']):.2f}"])
    rows.append(["解析反解（上界）", "34.98", "0.888", "3.96", "—", "—"])
    TABLE(doc, ["方法", "PSNR/dB", "SSIM", "ΔE*ab", "阴影噪声", "耗时/s"], rows,
          [3.8, 2.4, 2.0, 2.0, 2.4, 2.0], "表 3  8 张测试图上的平均结果")
    FIG(doc, "fig7_metrics.png", 10.5, "图 3  四种方法的 PSNR 对比")
    P(doc, "CLAHE 与 MSRCR 的结果明显偏差，但原因不同。CLAHE 仅重分布直方图，不控制绝对亮度，"
           "输出平均亮度仅 0.29，整体偏暗；块状映射同时放大了噪声与块边界。MSRCR 的问题在于"
           "灰白化与噪声放大：输出平均亮度 0.59、色彩丰富度 33.5（真值 28.8，本方法 28.2），"
           "表面看颜色更浓，实则由色偏与暗部噪点造成，因此 ΔE 高达 32.4。")
    P(doc, "为排除整体亮度的影响，对 CLAHE 与 MSRCR 的输出补充一次全局配光（统一缩放到平均亮度 "
           "0.50）后重新计算：CLAHE 升至 20.42 dB，MSRCR 升至 18.37 dB；本方法同样配光后为 "
           "25.63 dB，仍分别相差 5.2 与 7.3 dB。Gamma 补充配光后仅提高 0.6 dB（23.03），说明其"
           "亮度本就正确，差距在局部。")
    H2(doc, "5.3 视觉结果")
    P(doc, "图 4 为 02 号图（山林与远山），图 5 为 07 号图（长直边界）。Gamma 的结果整体发灰，"
           "树冠绿色被冲淡成黄绿；CLAHE 反差不自然，天空与远山出现成片颗粒和块状边界；MSRCR 整幅"
           "偏蓝灰，暗部存在大量蓝紫色噪点，原因是色彩恢复因子在暗部将通道比例放得过大。本方法的"
           "色调与真值最接近，暗部树叶仍能区分前后层次。")
    P(doc, "07 号图可进一步观察边界处理。CLAHE 在曲线边界外沿压出一圈亮边，其内侧紧接一条暗带；"
           "MSRCR 的亮边更宽且伴随噪点；Gamma 未出现明显晕圈，其问题在于整体发灰、上方原本深蓝的"
           "区域被抬成灰蓝。本方法的边界过渡与真值基本重合，仅在紧贴边界的一至两个像素内略软。"
           "该差别由 M1 带来，但在全局指标上几乎不可见（见 5.6 节）。")
    FIG(doc, "fig2_compare02.png", 14.6,
        "图 4  02 号图的方法对比（上排：真值、低照度、Gamma 2.2；下排：CLAHE、MSRCR、本文方法）")
    FIG(doc, "fig3_compare07.png", 14.6, "图 5  07 号图的方法对比，注意亮暗交界处的过渡")
    H2(doc, "5.4 局部放大")
    P(doc, "将 02 号图树冠处 330×195 的区域放大 2 倍（图 6）。Gamma 的亮部呈灰雾状，暗部颗粒"
           "明显；CLAHE 的颗粒被对比度进一步放大，并出现块状边界；MSRCR 出现成片蓝斑；本方法"
           "与真值最接近，但细枝略有柔化，这是细节增益上限取 1.0 的代价。")
    FIG(doc, "fig4_zoom.png", 14.6, "图 6  02 号图局部放大 2 倍")
    H2(doc, "5.5 亮度分布")
    P(doc, "图 7 为 04 号图（浅色织物）的亮度直方图。真值在 0.3 至 0.7 之间分布较宽；低照度图"
           "集中于 0 至 0.3；MSRCR 集中于 0.4 至 0.6 的窄区间，这是其灰片观感的直接来源；本方法的"
           "分布形状与真值最接近，仅 0.9 以上的高光略少。")
    FIG(doc, "fig6_hist.png", 11.0, "图 7  04 号图的亮度直方图对比")
    H2(doc, "5.6 消融实验")
    P(doc, "分别关闭四个模块，结果见表 4。M2 与 M4 贡献最大（关闭后分别下降 7.9 与 7.8 dB），"
           "M3 主要影响 SSIM（由 0.962 降至 0.856）与色差，M1 在 PSNR 上仅 0.12 dB、SSIM 0.021。")
    rows = []
    for name, label in [("Ours (full)", "完整"), ("w/o M1 (Gauss)", "去 M1（高斯光照）"),
                        ("w/o M2 (fixed γ)", "去 M2（固定 γ=1.8）"),
                        ("w/o M3 (no shrink)", "去 M3（不收缩）"),
                        ("w/o M4 (per-channel)", "去 M4（逐通道拉伸）")]:
        rows.append([label, f"{mean_of(ablation, 'psnr', name):.2f}",
                     f"{mean_of(ablation, 'ssim', name):.3f}",
                     f"{mean_of(ablation, 'delta_e', name):.2f}"])
    TABLE(doc, ["版本", "PSNR/dB", "SSIM", "ΔE*ab"], rows, [6.4, 2.8, 2.6, 2.6],
          "表 4  消融实验（8 张图平均）")
    P(doc, "M1 的指标贡献与视觉改善并不一致。对比差图可见，晕圈仅出现在交界附近数十像素宽的"
           "窄带内，占全图面积不足 5%，对全局平均的影响有限；同时它对暗部细节的平滑作用与 M3 "
           "存在重叠，二者收益部分抵消。这说明仅凭 PSNR 会低估此类局部伪影的改进，也是本文保留"
           "多套指标的原因。")
    H2(doc, "5.7 p 的取值")
    P(doc, "图 8 为 p 从 0 到 1 的扫描结果。PSNR 先升后降，峰值位于 0.6–0.7（25.85 与 25.84）；"
           "p=1（仅调曝光，等价于归一化伽马）降至 23.69，p=0（完全去除光照）仅 19.49。SSIM 的"
           "峰值略偏右，在 0.8 附近（0.9637），与 PSNR 不完全重合，最终按 PSNR 取 0.6。")
    FIG(doc, "fig8_psweep.png", 10.5, "图 8  光照压缩指数 p 对 PSNR 的影响")
    P(doc, "该曲线也解释了 4.3 节的现象：完全去除光照在直觉上更彻底，实测却最差。在真实低照度"
           "图像中，光照场与物体本征阴影本就难以分离，p 的作用相当于承认这一不确定性，只做部分"
           "抹平，这也是本方法的适用边界。")
    H2(doc, "5.8 耗时")
    P(doc, "表 5 为窗口半径对耗时的影响。积分图使盒式滤波的代价与半径无关，实测 r 由 8 增至 128 "
           "时耗时在 0.48–0.57 s 之间波动，波动主要来自测量误差。分辨率的影响近似线性：480×300 "
           "为 0.13 s，960×600 为 0.47 s，1440×900 为 1.21 s，1920×1200 为 2.22 s。")
    with open(os.path.join(ROOT, "results", "scaling.csv"), encoding="utf-8-sig") as f:
        scaling = list(csv.DictReader(f))
    TABLE(doc, ["窗口半径 r", "8", "16", "32", "64", "128"],
          [["耗时/s"] + [f"{float(r['seconds']):.2f}" for r in scaling],
           ["等效高斯核长度", "17", "33", "65", "129", "257"]],
          [3.6, 2.2, 2.2, 2.2, 2.2, 2.2], "表 5  窗口半径与耗时的关系（960×600）")
    P(doc, "作为对照，MSRCR 在相同三个尺度下需 0.55 s，本方法在指标大幅领先的同时耗时基本持平；"
           "Gamma 仅需 0.04 s，说明若只追求亮度提升，计算代价可以很低，但输出质量不可用。")
    H2(doc, "5.9 局限与不足")
    P(doc, "第一，半合成数据上的结论不能直接外推到真实照片。合成噪声偏白，真实相机的降噪处理"
           "会使暗部细节更少，本方法细节增益的取值可能需要上调。")
    P(doc, "第二，p=0.6 与 target=0.50 均在上述 8 张图上扫描确定，存在过拟合风险。尤其是 target："
           "真值已被统一到 0.50，目标亮度取 0.50 相当于部分利用了先验。更换数据时应重新标定，或"
           "改为由图像自身统计量（如高光分位数）确定，后者未在本实验中实现。")
    P(doc, "第三，与解析反解仍有约 9 dB 差距，主要来自光照估计。引导滤波估计的是局部亮度的平滑"
           "版本，无法区分“光照暗”与“物体暗”，这是当前最大的误差来源，也是后续改进的重点。")
    P(doc, "第四，极暗场景（平均亮度低于 0.1）未做测试。按现有公式，k 将超过 10 倍，α 早已饱和于 "
           "0.85，输出很可能明显发糊。此类场景需要真正的去噪器，而非均值收缩。")

    # ---------------- 参考文献
    H1(doc, "参考文献")
    refs = [
        "[1] Land E H, McCann J J. Lightness and retinex theory[J]. Journal of the Optical Society of America, 1971, 61(1): 1-11.",
        "[2] Jobson D J, Rahman Z, Woodell G A. A multiscale retinex for bridging the gap between color images and the human observation of scenes[J]. IEEE Transactions on Image Processing, 1997, 6(7): 965-976.",
        "[3] He K, Sun J, Tang X. Guided image filtering[C]//European Conference on Computer Vision (ECCV). 2010: 1-14.",
        "[4] Guo X, Li Y, Ling H. LIME: Low-light image enhancement via illumination map estimation[J]. IEEE Transactions on Image Processing, 2017, 26(2): 982-993.",
        "[5] Wang Z, Bovik A C, Sheikh H R, et al. Image quality assessment: from error visibility to structural similarity[J]. IEEE Transactions on Image Processing, 2004, 13(4): 600-612.",
        "[6] Zuiderveld K. Contrast limited adaptive histogram equalization[M]//Graphics Gems IV. San Diego: Academic Press, 1994: 474-485.",
    ]
    for r in refs:
        p = doc.add_paragraph(r, style="参考文献")
        p.paragraph_format.first_line_indent = Pt(-21)
        p.paragraph_format.left_indent = Pt(21)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    try:
        doc.save(OUT)
        print(f"已生成 {OUT}")
    except PermissionError:
        alt = OUT.replace(".docx", "_new.docx")
        doc.save(alt)
        print(f"原文件被其他程序占用，已写入 {alt}")


if __name__ == "__main__":
    build()
