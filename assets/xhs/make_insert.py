# -*- coding: utf-8 -*-
"""从公众号封面的手绘线稿里抠出人物+屏幕部分，做成透明 PNG，给小红书卡片当装饰。

线稿原图是"深绿底 + 白线"，这里按亮度抠掉绿底保留白线（带 alpha），
裁掉右下角 AI 水印区域。
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'cover', 'art-linework.png')
OUT = os.path.join(HERE, 'art-person.png')

im = Image.open(SRC).convert('RGB')
W, H = im.size

# 裁掉右下角水印 + 只取右侧人物/屏幕/装饰段
CROP = (1130, 0, 1780, 900)
im = im.crop(CROP)
w, h = im.size

px = im.load()
out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
op = out.load()

for y in range(h):
    for x in range(w):
        r, g, b = px[x, y]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        # 绿底 lum ~25-40；白线 lum ~200+
        a = int(max(0, min(255, (lum - 55) / 45 * 255)))
        if a > 0:
            # 线稿本体是白的，保留一点点原色偏暖
            op[x, y] = (255, 255, 255, a)

out.save(OUT)
print('saved', OUT, out.size)
