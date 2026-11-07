#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成「公众号粘贴版」HTML。

公众号（微信公众平台图文编辑器）粘贴网页内容时会：
  - 剥离 <script> / <style>  →  复制按钮失效、整页样式丢失
  - 只认内联 style 属性
  - 不支持 grid 布局、不支持内部锚点跳转、非白名单外链点不动
  - 只加载公网图片，本地相对路径全部 404

所以这里做一次转换：
  1. 把 <style> 里的规则全部内联到元素的 style 属性（按源码顺序，后者覆盖前者）
  2. 媒体查询只保留手机断点（max-width:560px 生效，min-width:561px 丢弃）
  3. :before 伪元素换成真实的 <span>，避免 list 圆点丢失
  4. grid 布局改写成 flex
  5. 绝对定位的编号圆点改成 flex 排布（公众号里 absolute 会错位）
  6. 去掉 <script>、<button> 改 <span>、内部锚点改 <span>
  7. 图片 src 加 --base 公网前缀

用法：
    python make-wechat.py                      # 本地相对路径，浏览器打开人工核对
    python make-wechat.py --base https://xxx   # 图片指向公网，可直接粘贴进公众号
"""
import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

HERE = Path(__file__).resolve().parent
SRC = HERE / 'index.html'
OUT = HERE / 'wechat.html'


# ---------------------------------------------------------------- CSS parsing
def strip_comments(css):
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def parse_rules(css):
    """Return list of (media, selector, declarations-string)."""
    rules = []
    i, n = 0, len(css)
    while i < n:
        # find the next '{'
        brace = css.find('{', i)
        if brace == -1:
            break
        prelude = css[i:brace].strip()
        # matching close brace
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == '{':
                depth += 1
            elif css[j] == '}':
                depth -= 1
            j += 1
        body = css[brace + 1:j - 1]

        if prelude.startswith('@media'):
            cond = prelude[len('@media'):].strip()
            inner = parse_rules(body)
            for m, sel, decl in inner:
                rules.append((cond, sel, decl))
        elif prelude.startswith('@'):
            pass  # @keyframes etc. — skip
        else:
            for sel in prelude.split(','):
                sel = sel.strip()
                if sel:
                    rules.append(('', sel, body))
        i = j
    return rules


def decls_to_dict(decl_str):
    out = {}
    for piece in decl_str.split(';'):
        if ':' not in piece:
            continue
        k, v = piece.split(':', 1)
        out[k.strip().lower()] = v.strip()
    return out


# ---------------------------------------------------------------- inlining
PSEUDO_SPAN = ('<span style="position:absolute;left:4px;top:11px;width:7px;'
               'height:7px;border-radius:50%;background:#4da783"></span>')


def make_pseudo_span():
    """Build a real element (NavigableString would escape it as plain text)."""
    return BeautifulSoup(PSEUDO_SPAN, 'lxml').span


def inline_styles(soup):
    style_tags = soup.find_all('style')
    css = '\n'.join(t.get_text() for t in style_tags)
    for t in style_tags:
        t.decompose()
    css = strip_comments(css)

    for media, sel, decl in parse_rules(css):
        # 公众号只有手机宽度：保留 max-width 断点，丢弃 min-width 断点
        if media and 'min-width' in media:
            continue
        if ':' in sel and not sel.endswith(':before'):
            continue  # 伪类/伪元素（除 :before）无法内联
        is_before = sel.endswith(':before')
        base_sel = sel[:-7].strip() if is_before else sel
        try:
            targets = soup.select(base_sel)
        except Exception:
            continue
        props = decls_to_dict(decl)
        for el in targets:
            if is_before:
                if base_sel == 'ul.fit li':
                    el.insert(0, make_pseudo_span())
                continue
            cur = el.get('style', '')
            merged = decls_to_dict(cur)
            merged.update(props)
            el['style'] = '; '.join(f'{k}: {v}' for k, v in merged.items())


# ---------------------------------------------------------------- rewrites
GRID_TO_FLEX = {
    '.flow-links': 'display:flex;flex-wrap:wrap;gap:9px;',
    '.flow-links > *': 'flex:1 1 46%;min-width:0;',
    '.types': 'display:flex;flex-wrap:wrap;gap:10px;',
    '.types > *': 'flex:1 1 46%;min-width:0;',
    '.follow-duo': 'display:flex;flex-wrap:wrap;gap:16px;align-items:center;',
    # basis 200px：手机 375px 排不满两个 → 单列；PC 微信 677px 正好三栏
    '.follow-duo > *': 'flex:1 1 180px;min-width:0;',
}


def merge_style(cur, extra):
    """Append declarations safely — a missing ';' silently swallows the next rule."""
    cur = (cur or '').strip().rstrip(';')
    extra = (extra or '').strip().rstrip(';')
    if not cur:
        return extra
    if not extra:
        return cur
    return cur + '; ' + extra


def rewrite(soup):
    # 1) grid → flex
    for sel, style in GRID_TO_FLEX.items():
        try:
            targets = soup.select(sel)
        except Exception:
            continue
        for tag in targets:
            cur = tag.get('style', '')
            cur = re.sub(r'display:\s*grid[^;]*;?', '', cur)
            cur = re.sub(r'grid-template-columns:[^;]*;?', '', cur)
            cur = re.sub(r'gap:\s*[^;]*;?', '', cur) if sel.endswith('> *') else cur
            tag['style'] = merge_style(cur, style)

    # 1b) 长 URL 必须允许断行（<wbr> 在公众号会被剥离）
    for a in soup.select('.site a'):
        a['style'] = merge_style(a.get('style', ''), 'word-break:break-all')
    for wbr in soup.find_all('wbr'):
        wbr.decompose()

    # 2) 编号圆点保持 absolute：祖先 li / .sub-head 有 position:relative，定位不会错位。
    #    （早期版本误改成 flex，反而把步骤项的每个子元素挤成并排多列，已回退。）

    # 3) 内部锚点去掉 href，但保留 <a> 标签 —— 否则 .site a / .flow-links a 等
    #    选择器全部失配，卡片样式会丢
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if href.startswith('#'):
            del a['href']
        else:
            a.attrs.pop('target', None)
            a.attrs.pop('rel', None)

    # 4) button → span（公众号会剥离 button 的交互属性）
    for b in soup.find_all('button'):
        b.name = 'span'
        b.attrs.pop('type', None)
        b.attrs.pop('data-copy-text', None)

    # 5) 去掉 script
    for sc in soup.find_all('script'):
        sc.decompose()

    # 6) body/article 宽度交给公众号容器
    art = soup.find('article')
    if art:
        art['style'] = merge_style(art.get('style', ''),
                                    'max-width:100%;margin:0;padding:0 4px;background:transparent')

    # 7) 每个元素统一 border-box
    for el in soup.find_all(True):
        cur = el.get('style', '')
        if 'box-sizing' not in cur:
            el['style'] = merge_style(cur, 'box-sizing:border-box')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='', help='图片公网前缀，如 https://xxx')
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()

    html = SRC.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')
    inline_styles(soup)
    rewrite(soup)

    if args.base:
        base = args.base.rstrip('/') + '/'
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and not src.startswith(('http', 'data:')):
                img['src'] = base + src.lstrip('./')

    out = soup.prettify()
    Path(args.out).write_text(out, encoding='utf-8')
    print(f'written: {args.out}  ({len(out)} bytes)')


if __name__ == '__main__':
    sys.exit(main())
