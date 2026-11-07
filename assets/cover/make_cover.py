# -*- coding: utf-8 -*-
"""生成公众号封面图（横屏 2.35:1 + 方形 1:1）。

风格：深墨绿底 + 纯白手绘线条 + 白色色块（块内反白深色字）。
底图由 AI 生成纯白线稿，本脚本负责：抹水印、抠掉底色与画布融合、
排中文标题、画手绘装饰线、导出多尺寸。
"""
import os
import math
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'art-linework.png')

FONT_BOLD = 'C:/Windows/Fonts/msyhbd.ttc'
FONT_HEI = 'C:/Windows/Fonts/simhei.ttf'
FONT_KAI = 'C:/Windows/Fonts/simkai.ttf'

INK = (13, 25, 22)          # 画布深底
WHITE = (255, 255, 255)


# ---------------------------------------------------------------- 工具
def font(path, size):
    return ImageFont.truetype(path, size)


def text_size(draw, s, f):
    box = draw.textbbox((0, 0), s, font=f)
    return box[2] - box[0], box[3] - box[1]


def rough_line(draw, pts, width, color, seed=0, wobble=2.2, passes=2):
    """手绘感线条：同一条路径多遍叠加 + 随机抖动，边缘像马克笔。"""
    rnd = random.Random(seed)
    for k in range(passes):
        jitter = wobble if k == 0 else wobble * 0.5
        pts2 = [(x + rnd.uniform(-jitter, jitter), y + rnd.uniform(-jitter, jitter))
                for x, y in pts]
        draw.line(pts2, fill=color, width=width, joint='curve')
        r = width / 2.0
        for x, y in pts2:
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def sketchy_box(draw, xy, radius, width, color, seed=0, wobble=1.6):
    """手绘圆角矩形边框（边缘带轻微抖动）。"""
    x0, y0, x1, y1 = xy
    rnd = random.Random(seed)
    pts = []
    corners = [(x1 - radius, y0 + radius, -90, 0),
               (x1 - radius, y1 - radius, 0, 90),
               (x0 + radius, y1 - radius, 90, 180),
               (x0 + radius, y0 + radius, 180, 270)]
    for cx, cy, a0, a1 in corners:
        for a in range(a0, a1 + 1, 6):
            r = math.radians(a)
            pts.append((cx + radius * math.cos(r), cy + radius * math.sin(r)))
    # 描边顺序需要连续，重新按边界排
    pts = []
    def arc(cx, cy, a0, a1, n=14):
        out = []
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            out.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
        return out
    pts = (arc(x1 - radius, y0 + radius, -90, 0)
           + arc(x1 - radius, y1 - radius, 0, 90)
           + arc(x0 + radius, y1 - radius, 90, 180)
           + arc(x0 + radius, y0 + radius, 180, 270))
    pts = [(x + rnd.uniform(-wobble, wobble), y + rnd.uniform(-wobble, wobble))
           for x, y in pts]
    draw.line(pts + [pts[0]], fill=color, width=width, joint='curve')
    r = width / 2.0
    for x, y in pts:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


# ---------------------------------------------------------------- 底图处理
def load_art(crop_subject=False):
    """抹掉 AI 水印，并把深色背景抠成透明，便于与画布无缝融合。

    crop_subject=True 时只保留右侧主体（显示器+人物+机器人），去掉左侧空白。
    """
    im = Image.open(SRC).convert('RGB')
    w, h = im.size
    px = im.load()

    # 1) 抹水印：右下角用邻域背景色覆盖
    bg_sample = px[30, 30]
    for y in range(int(h * 0.90), h):
        for x in range(int(w * 0.84), w):
            px[x, y] = bg_sample

    # 2) 按亮度抠底：亮线条保留，暗底变透明（中间过渡做软边）
    alpha = Image.new('L', (w, h), 0)
    ap = alpha.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            lum = max(r, g, b)
            if lum <= 58:
                a = 0
            elif lum >= 96:
                a = 255
            else:
                a = int((lum - 58) / 38 * 255)
            ap[x, y] = a
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    art = im.convert('RGBA')
    art.putalpha(alpha)

    if crop_subject:
        # 只取右侧主体区域（去掉左侧 40% 空白）
        art = art.crop((int(w * 0.40), 0, w, h))
    return art, bg_sample


def paste_art(canvas, art, box, focus=(0.60, 0.42)):
    """把线稿放进右侧区域，按 focus 指定主体在框内的位置。"""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    ar = art.width / art.height
    if bw / bh > ar:                      # 框更宽 → 按高缩放
        nh = bh
        nw = int(bh * ar)
    else:
        nw = bw
        nh = int(bw / ar)
    art2 = art.resize((nw, nh), Image.LANCZOS)
    ox = int(x0 + (bw - nw) * focus[0])
    oy = int(y0 + (bh - nh) * focus[1])
    canvas.alpha_composite(art2, (ox, oy))


# ---------------------------------------------------------------- 版式
def _text_block(d, left, top, scale=1.0, arrow_to=None, show_handwriting=True):
    """排版左侧文字区，返回 (副标题右边界x, 底部y)。"""
    S = scale

    # 标签：白色色块 + 深色字
    chip_txt = '小白姐姐工作室 · AI 实操教程'
    f_chip = font(FONT_BOLD, int(40 * S))
    cw, ch = text_size(d, chip_txt, f_chip)
    chip_h = int(76 * S)
    d.rounded_rectangle((left, top, left + cw + int(56 * S), top + chip_h),
                        radius=chip_h // 2, fill=WHITE)
    d.text((left + int(28 * S), top + int(12 * S)), chip_txt, font=f_chip, fill=INK + (255,))

    # 主标题 第一行
    y = top + int(114 * S)
    f_t1 = font(FONT_BOLD, int(100 * S))
    d.text((left - int(4 * S), y), '0 基础也能做出', font=f_t1, fill=WHITE + (255,))

    # 主标题 第二行：白色色块 + 反白深色字
    y2 = y + int(132 * S)
    f_t2 = font(FONT_BOLD, int(124 * S))
    t2 = '知识动画'
    w2, h2 = text_size(d, t2, f_t2)
    bx0, by0 = left - int(14 * S), y2 - int(6 * S)
    bx1, by1 = left + w2 + int(34 * S), y2 + h2 + int(18 * S)
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=int(16 * S), fill=WHITE)
    d.text((left + int(4 * S), y2), t2, font=f_t2, fill=INK + (255,))

    # 手绘下划线（色块下方）
    rough_line(d, [(bx0 + 6, by1 + int(30 * S)), (bx1 - int(30 * S), by1 + int(24 * S))],
               max(3, int(7 * S)), WHITE + (230,), seed=3, wobble=2.4)

    # 副标题
    y3 = by1 + int(62 * S)
    f_s = font(FONT_BOLD, int(46 * S))
    sub = '6 套模板风格 · 3 步装好 · 附完整教程'
    d.text((left, y3), sub, font=f_s, fill=(228, 238, 233, 255))
    sw, sh = text_size(d, sub, f_s)

    # 底部手写体 + 手绘下划线
    y4 = y3 + int(84 * S)
    if show_handwriting:
        f_b = font(FONT_KAI, int(42 * S))
        bt = '改几个词就是你自己的'
        d.text((left, y4), bt, font=f_b, fill=(196, 213, 205, 255))
        bw, bh = text_size(d, bt, f_b)
        rough_line(d, [(left + 6, y4 + bh + int(16 * S)),
                       (left + bw - 14, y4 + bh + int(11 * S))],
                   max(2, int(5 * S)), (196, 213, 205, 190), seed=11, wobble=1.6)
    else:
        bh = 0

    # 指引虚线 + 箭头（指向右侧插画）
    if arrow_to is not None:
        ay = y3 + int(10 * S)
        x0 = left + sw + int(40 * S)
        for i in range(7):
            x = x0 + i * int(26 * S)
            r = max(2, int(4 * S))
            d.ellipse((x, ay, x + r * 2, ay + r * 2), fill=WHITE + (110,))
        ax = x0 + 7 * int(26 * S) + int(14 * S)
        s = int(26 * S)
        d.polygon([(ax, ay - int(4 * S)), (ax + s, ay + int(4 * S)), (ax, ay + int(12 * S))],
                  fill=WHITE + (150,))

    return left + sw, y4 + bh


def _deco_dots(d, x, y, S=1.0):
    """三个递减白点 + 手绘曲线。"""
    for i, r in enumerate((13, 9, 6)):
        cx = x + int(i * 34 * S)
        rr = int(r * S)
        d.ellipse((cx, y, cx + rr * 2, y + rr * 2), fill=WHITE + (230 - i * 60,))
    curve = []
    for i in range(26):
        t = i / 25.0
        curve.append((x + int(128 * S) + t * int(190 * S),
                      y + int(12 * S) - math.sin(t * math.pi * 1.6) * int(26 * S)))
    for i in range(0, len(curve) - 1, 2):
        d.line([curve[i], curve[i + 1]], fill=(255, 255, 255, 150), width=max(2, int(5 * S)))


def build_cover(W=1800, H=766, art=None, bg_sample=None):
    """横屏 2.35:1 封面。"""
    canvas = Image.new('RGBA', (W, H), INK + (255,))
    d = ImageDraw.Draw(canvas)

    # 背景辉光（右侧，呼应插画）
    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy = int(W * 0.78), int(H * 0.5)
    for i in range(26, 0, -1):
        r = int(H * 0.10 * i / 4)
        a = int(9 * (1 - i / 26))
        gd.ellipse((gx - r, gy - r, gx + r, gy + r), fill=(80, 170, 130, a))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28)))

    # 手绘边框（漫画分格感）
    sketchy_box(d, (26, 26, W - 26, H - 26), 30, 5, WHITE + (150,), seed=7, wobble=2.0)

    # 插画：往左靠 + 放大，压缩文字区与插画之间的空档
    if art is not None:
        paste_art(canvas, art, (int(W * 0.40), int(H * 0.03),
                                W + 90, H - 6), focus=(0.66, 0.0))

    left = 118
    _text_block(d, left, 96, scale=1.0, arrow_to=True)
    _deco_dots(d, left, H - 108, S=1.0)
    return canvas.convert('RGB')


def build_square(W=1080, H=1080, art=None, bg_sample=None):
    """方形封面：插画缩到右下角，文字整体上移，互不遮挡。"""
    canvas = Image.new('RGBA', (W, H), INK + (255,))
    d = ImageDraw.Draw(canvas)

    glow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gx, gy = int(W * 0.74), int(H * 0.72)
    for i in range(26, 0, -1):
        r = int(H * 0.11 * i / 4)
        a = int(9 * (1 - i / 26))
        gd.ellipse((gx - r, gy - r, gx + r, gy + r), fill=(80, 170, 130, a))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28)))

    sketchy_box(d, (24, 24, W - 24, H - 24), 28, 5, WHITE + (150,), seed=7, wobble=2.0)

    # 插画：右下角，缩小，只露出主体（顶部留出文字空间）
    if art is not None:
        paste_art(canvas, art, (int(W * 0.30), int(H * 0.50),
                                int(W * 1.06), int(H * 1.04)), focus=(0.60, 0.0))

    left = 84
    _text_block(d, left, 84, scale=0.86, arrow_to=None, show_handwriting=False)
    _deco_dots(d, left, H - 92, S=0.86)
    return canvas.convert('RGB')


def main():
    art, bg = load_art(crop_subject=True)

    # 横屏大图 2.35:1（公众号首条封面比例 900×383）
    big = build_cover(1800, 766, art, bg)
    big = big.resize((900, 383), Image.LANCZOS)
    out1 = os.path.join(HERE, 'cover-900x383.jpg')
    big.save(out1, quality=94, subsampling=0)

    # 高清版（备用，印刷/大屏）
    hd = build_cover(2400, 1022, art, bg)
    hd = hd.resize((1800, 766), Image.LANCZOS)
    out2 = os.path.join(HERE, 'cover-1800x766.jpg')
    hd.save(out2, quality=93, subsampling=0)

    # 方形（公众号次条 / 分享卡片 1:1）
    sq = build_square(1080, 1080, art, bg)
    sq = sq.resize((800, 800), Image.LANCZOS)
    out3 = os.path.join(HERE, 'cover-800x800.jpg')
    sq.save(out3, quality=93, subsampling=0)

    for p in (out1, out2, out3):
        print('written: %s (%d bytes)' % (p, os.path.getsize(p)))


if __name__ == '__main__':
    main()
