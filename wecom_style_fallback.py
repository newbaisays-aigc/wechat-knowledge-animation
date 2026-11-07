#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
wecom_style_fallback —— 微信公众号（公众平台图文编辑器）样式降级模块

背景
----
公众号新版编辑器底层是 ProseMirror，只接受有限的内联样式子集。
已确诊会被丢弃 / 错位的写法：

  * ``display:flex``      → 容器被重置成 block，flex 子元素拍平成行内流，卡片挤成一坨
  * ``linear-gradient``   → 渐变背景整个丢掉
  * ``box-shadow``        → 阴影丢掉
  * ``position:absolute`` → 定位错位（编号圆点会跑到奇怪的位置）

本模块提供 4 个**互相独立、可单独调用**的降级函数：

  1. :func:`flatten_flex`        —— flex 布局降级成块级流（gap → margin）
  2. :func:`gradient_to_solid`   —— 渐变背景降级成实色（``.hl`` 高亮保留底线效果）
  3. :func:`strip_shadow`        —— 去掉阴影（``.pick`` 的 inset 下划线改成 border-bottom）
  4. :func:`strip_unsupported`   —— 通用清理（定位 / pre-wrap / 无用计算属性）

设计约束
--------
* **绝不丢文本**：所有操作只改 style 属性和标签结构，一个字符的文字都不动。
  （提示词块里的换行用「插入 ``<br>`` 但保留原换行符」的方式处理，
    这样渲染效果等价于 ``white-space:pre-wrap``，同时 ``get_text()`` 长度完全不变。）
* 四个函数都**就地修改** soup 并返回 soup，可以单独调用，也可以按顺序串联。
* 空 soup / 没有样式的 soup 都能安全处理。

用法
----
    from wecom_style_fallback import apply_all
    soup = BeautifulSoup(html, 'lxml')
    apply_all(soup)

自测::

    python wecom_style_fallback.py
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------ 开关
STRIP_LETTER_SPACING = False     # 保留：原文用它做字距微调（.brand 1.5px 拉开、h1 -.4px 收紧），
                                 # 删掉品牌行会明显变宽。公众号支持 letter-spacing。
NORMALIZE_BACKGROUND = True      # 纯色 background 简写 → background-color（公众号更容易保留）


# ================================================================== 基础工具
def _parse_style(style):
    """``'color: red; font-size: 12px'`` → ``{'color': 'red', 'font-size': '12px'}``"""
    out = {}
    if not style:
        return out
    for piece in style.split(';'):
        if ':' not in piece:
            continue
        k, _, v = piece.partition(':')
        k = k.strip().lower()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


def _dump_style(decls):
    return '; '.join('%s: %s' % (k, v) for k, v in decls.items() if v)


def _style_of(tag):
    return _parse_style(tag.get('style', '') if tag.has_attr('style') else '')


def _set_style(tag, decls):
    text = _dump_style(decls)
    if text:
        tag['style'] = text
    elif tag.has_attr('style'):
        del tag['style']


def _classes(tag):
    raw = tag.get('class')
    if not raw:
        return []
    if isinstance(raw, str):
        return raw.split()
    return list(raw)


_LEN_RE = re.compile(r'^(-?\d*\.?\d+)\s*(px|em|rem|%)?$')


def _len_to_px(value):
    """长度转 px；无法换算（auto / % / 未知单位）返回 None。"""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    m = _LEN_RE.match(v)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in (None, 'px'):
        return num
    if unit in ('em', 'rem'):
        return num * 16.0
    return None


def _fmt_px(value):
    if value is None:
        return None
    if abs(value - round(value)) < 1e-6:
        return '%dpx' % int(round(value))
    return ('%.2f' % value).rstrip('0').rstrip('.') + 'px'


def _sides(decls, prefix):
    """把 margin / padding 简写展开成 [top, right, bottom, left]。"""
    raw = decls.get(prefix, '')
    parts = raw.split()
    if not parts:
        return ['0', '0', '0', '0']
    if len(parts) == 1:
        return [parts[0]] * 4
    if len(parts) == 2:
        return [parts[0], parts[1], parts[0], parts[1]]
    if len(parts) == 3:
        return [parts[0], parts[1], parts[2], parts[1]]
    return parts[:4]


_SIDE_NAMES = ('top', 'right', 'bottom', 'left')


def _side_value(decls, prefix, side):
    """取某一边的**生效值**：简写和 longhand 谁在后面谁生效（和 CSS 层叠顺序一致）。"""
    longhand = '%s-%s' % (prefix, side)
    keys = list(decls.keys())
    short_pos = keys.index(prefix) if prefix in decls else -1
    long_pos = keys.index(longhand) if longhand in decls else -1
    if long_pos > short_pos:
        return decls[longhand]
    if short_pos >= 0:
        return _sides(decls, prefix)[_SIDE_NAMES.index(side)]
    return '0'


def _set_side(decls, prefix, index, value):
    """index: 0=上 1=右 2=下 3=左。简写和 longhand 同步更新，谁生效都不冲突。"""
    side = _SIDE_NAMES[index]
    longhand = '%s-%s' % (prefix, side)
    vals = [_side_value(decls, prefix, s) for s in _SIDE_NAMES]
    vals[index] = value
    collapsed = vals[0] if len(set(vals)) == 1 else ' '.join(vals)
    if longhand in decls:
        decls[longhand] = value
    decls[prefix] = collapsed


def _margin_px(decls, side):
    return _len_to_px(_side_value(decls, 'margin', side))


def _split_top_level(text, sep=','):
    """按顶层分隔符切分，括号内部不切（rgba(...) 里也有逗号）。"""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append(''.join(buf))
    return parts


_COLOR_TOKEN_RE = re.compile(
    r'^(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\)|color\([^)]*\)|[a-zA-Z]+)')
_DIRECTION_RE = re.compile(r'^\s*(to\s+(top|bottom|left|right)|in\s+[a-zA-Z]+|'
                           r'[-+]?\d*\.?\d+(deg|grad|rad|turn))', re.I)


def _first_color_token(part):
    part = part.strip()
    if not part or _DIRECTION_RE.match(part):
        return None
    m = _COLOR_TOKEN_RE.match(part)
    return m.group(1) if m else None


def _gradient_colors(value):
    """从 linear-gradient(...) 里取出所有颜色 stop。"""
    m = re.search(r'gradient\s*\((.*)\)\s*$', value, re.I | re.S)
    if not m:
        return []
    out = []
    for part in _split_top_level(m.group(1), ','):
        color = _first_color_token(part)
        if color:
            out.append(color)
    return out


def _is_transparent(color):
    """判断颜色是否完全透明（alpha == 0）。"""
    if not color:
        return False
    c = color.strip().lower()
    if c.startswith('#'):
        h = c[1:]
        if len(h) == 8 and h[6:8] == '00':
            return True
        if len(h) == 4 and h[3] == '0':
            return True
        return False
    m = re.match(r'rgba?\(([^)]*)\)', c)
    if m:
        parts = [x.strip() for x in m.group(1).split(',')]
        if len(parts) >= 4:
            try:
                return float(parts[3].rstrip('%')) == 0.0
            except ValueError:
                return parts[3] in ('0', '0%')
    m = re.match(r'hsla?\(([^)]*)\)', c)
    if m:
        parts = [x.strip() for x in m.group(1).split(',')]
        if len(parts) >= 4:
            try:
                return float(parts[3].rstrip('%')) == 0.0
            except ValueError:
                return parts[3] in ('0', '0%')
    return False


def _shadow_color(shadow):
    """从 box-shadow 里取颜色（取最后一个颜色 token）。"""
    found = re.findall(r'(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\))', shadow or '')
    return found[-1] if found else None


# ============================================================ 1. flex 降级
FLEX_PROPS = (
    'flex', 'flex-direction', 'flex-wrap', 'flex-flow', 'flex-grow', 'flex-shrink',
    'flex-basis', 'align-items', 'align-self', 'align-content', 'justify-content',
    'justify-items', 'justify-self', 'order', 'gap', 'row-gap', 'column-gap',
)


def _apply_vertical_gap(left, right, gap):
    """纵向间距：优先补在左边元素的 margin-bottom 上（绝不左右各补一次）。"""
    if left[0] == 'tag':
        lst = _style_of(left[1])
        mb = _margin_px(lst, 'bottom')
        if mb is None:                       # margin-bottom: auto 之类，无法处理
            mb = 0.0
        if mb >= gap:
            return                          # 已有间距 → 不再给右边加 margin-top（避免双倍）
        if right[0] == 'tag':
            rst = _style_of(right[1])
            mt = _margin_px(rst, 'top')
            if mt is not None and mt >= gap:
                return
        _set_side(lst, 'margin', 2, _fmt_px(mb + gap))
        _set_style(left[1], lst)
        return
    # 左边是纯文本节点 → 只能加在右边的 margin-top
    if right[0] == 'tag':
        rst = _style_of(right[1])
        mt = _margin_px(rst, 'top')
        if mt is None:
            mt = 0.0
        if mt >= gap:
            return
        _set_side(rst, 'margin', 0, _fmt_px(mt + gap))
        _set_style(right[1], rst)


def _apply_horizontal_gap(left, right, gap):
    """横向间距（行内 flex）：补 margin-right / margin-left。"""
    if left[0] == 'tag':
        lst = _style_of(left[1])
        mr = _len_to_px(_side_value(lst, 'margin', 'right'))
        if mr is None:
            mr = 0.0
        if mr >= gap:
            return
        if right[0] == 'tag':
            rst = _style_of(right[1])
            ml = _len_to_px(_side_value(rst, 'margin', 'left'))
            if ml is not None and ml >= gap:
                return
        _set_side(lst, 'margin', 1, _fmt_px(mr + gap))
        _set_style(left[1], lst)
        return
    if right[0] == 'tag':
        rst = _style_of(right[1])
        ml = _len_to_px(_side_value(rst, 'margin', 'left'))
        if ml is None:
            ml = 0.0
        if ml >= gap:
            return
        _set_side(rst, 'margin', 3, _fmt_px(ml + gap))
        _set_style(right[1], rst)


def _flatten_container(tag):
    """把一个 flex 容器的 gap 变成子元素之间的 margin。"""
    decls = _style_of(tag)
    gap_raw = decls.get('gap') or decls.get('column-gap') or decls.get('row-gap') or ''
    if not gap_raw:
        return
    gap = _len_to_px(gap_raw.split()[0])
    if not gap:
        return

    direction = decls.get('flex-direction', 'row').strip().lower()
    wrap = decls.get('flex-wrap', 'nowrap').strip().lower()
    # 列容器 → 纵向间距；换行容器在块级流里会堆叠 → 也是纵向间距；否则横向间距
    vertical = (direction.startswith('column')
                or (wrap in ('wrap', 'wrap-reverse')
                    and not direction.startswith('row-reverse')))

    items = []
    for node in tag.children:
        if isinstance(node, Tag):
            items.append(('tag', node))
        elif isinstance(node, NavigableString):
            if str(node).strip():
                items.append(('text', node))

    for left, right in zip(items, items[1:]):
        if vertical:
            _apply_vertical_gap(left, right, gap)
        else:
            _apply_horizontal_gap(left, right, gap)


def flatten_flex(soup):
    """把 flex 布局降级成公众号能显示的块级流。

    * ``display:flex`` → ``display:block``；``display:inline-flex`` → ``display:inline-block``
    * 删掉 ``flex-direction / align-items / justify-content / flex-wrap / gap / flex`` 等属性
    * ``gap`` 变成子元素之间的 margin（相邻元素不会算出双倍间距）
    * ``flex: 1 1 46%`` 这类宽度声明直接删除（块级流里不适用）
    """
    if soup is None:
        return soup

    containers = []
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        if decls.get('display', '').strip().lower() in ('flex', 'inline-flex'):
            containers.append(tag)

    # 先把 gap 转成 margin（此时样式还在）
    for tag in containers:
        _flatten_container(tag)

    # 再统一清理 flex 相关属性
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        changed = False
        for prop in FLEX_PROPS:
            if prop in decls:
                del decls[prop]
                changed = True
        if decls.get('min-width', '').strip() == '0':
            del decls['min-width']
            changed = True
        display = decls.get('display', '').strip().lower()
        if display == 'flex':
            decls['display'] = 'block'
            changed = True
        elif display == 'inline-flex':
            decls['display'] = 'inline-block'
            changed = True
        if changed:
            _set_style(tag, decls)
    return soup


# ======================================================== 2. 渐变 → 实色
def gradient_to_solid(soup):
    """``background-image: linear-gradient(...)`` → 实色 ``background-color``。

    例外：``.hl`` 荧光笔高亮用渐变画出「浅绿底 + 底部一条更深的绿线」，
    降级时保留这个效果 —— 底色用 ``#eaf6ef``，底线用 ``border-bottom`` 实色模拟。
    """
    if soup is None:
        return soup

    for tag in soup.find_all(True):
        decls = _style_of(tag)
        bg_image = decls.get('background-image', '')
        if 'gradient' not in bg_image.lower():
            continue

        colors = _gradient_colors(bg_image)
        if 'hl' in _classes(tag):
            # 荧光笔：浅绿底 + 底部深绿线
            decls['background-color'] = decls.get('background-color') or '#eaf6ef'
            line_color = colors[-1] if colors else '#dcefe4'
            if _is_transparent(line_color):
                line_color = '#dcefe4'
            decls['border-bottom'] = '2px solid %s' % line_color
            padding_bottom = _side_value(decls, 'padding', 'bottom')
            if not _len_to_px(padding_bottom):
                decls['padding-bottom'] = '2px'
        else:
            solid = None
            for color in colors:
                if not _is_transparent(color):
                    solid = color
                    break
            if solid:
                decls['background-color'] = solid

        decls.pop('background-image', None)
        _set_style(tag, decls)
    return soup


# ============================================================ 3. 去阴影
def strip_shadow(soup):
    """删除所有 ``box-shadow``。

    ``.pick`` 用 ``box-shadow: inset 0 -2px 0 #8fcdb0`` 画下划线，
    降级成 ``border-bottom: 2px solid #8fcdb0``，视觉效果保留。
    """
    if soup is None:
        return soup

    for tag in soup.find_all(True):
        decls = _style_of(tag)
        shadow = decls.get('box-shadow')
        if shadow is None:
            continue
        del decls['box-shadow']
        if 'pick' in _classes(tag):
            color = _shadow_color(shadow) or '#8fcdb0'
            decls['border-bottom'] = '2px solid %s' % color
        _set_style(tag, decls)
    return soup


# ============================================================ 4. 通用清理
_ABS_PROPS = ('position', 'top', 'left', 'right', 'bottom', 'z-index',
              'transform', 'transform-origin', 'translate', 'rotate', 'scale')

_JUNK_PROPS = (
    'text-decoration-thickness', 'text-decoration-style', 'text-decoration-color',
    'orphans', 'widows', 'text-indent', 'text-transform',
    'font-variant', 'font-variant-ligatures', 'font-variant-numeric',
    'font-variant-east-asian', 'font-variant-caps', 'font-variant-alternates',
    'font-variant-position',
    '-webkit-text-stroke-width', '-webkit-text-stroke-color',
    '-webkit-text-size-adjust', 'text-size-adjust',
    'scroll-behavior', 'scroll-margin', 'scroll-margin-top', 'scroll-margin-bottom',
    'scroll-margin-left', 'scroll-margin-right',
    'scroll-padding', 'scroll-padding-top', 'scroll-padding-bottom',
    'scroll-padding-left', 'scroll-padding-right',
)

_DISPLAY_MAP = {
    'flex': 'block',
    'inline-flex': 'inline-block',
    'grid': 'block',
    'inline-grid': 'inline-block',
    'table': 'block',
    'inline-table': 'inline-block',
    'list-item': 'block',
    'flow-root': 'block',
}
_DISPLAY_KEEP = ('block', 'inline-block', 'inline', 'none')


def _is_br(node):
    return isinstance(node, Tag) and node.name == 'br'


def _convert_prewrap_breaks(el):
    """把元素直接文本里的换行换成 ``<br>``。

    换行符 **保留在文本里**（只是额外插入一个 ``<br>``），
    这样 ① 渲染效果等价于 ``white-space:pre-wrap``；② ``get_text()`` 长度完全不变。

    只处理「真正代表换行」的那些换行：
    * 纯缩进用的换行（前后都没内容）不处理；
    * 已经有 ``<br>`` 负责这次换行的不重复插（原文里提示词就是靠 ``<br>`` 排版的）。
    """
    contents = list(el.children)

    # after_has[i] = 第 i 个节点之后是否还有正文内容（按快照顺序，避免被新插入的 <br> 干扰）
    after_has = [False] * (len(contents) + 1)
    flag = False
    for i in range(len(contents) - 1, -1, -1):
        after_has[i] = flag
        node = contents[i]
        if isinstance(node, Tag):
            if node.get_text().strip():
                flag = True
        elif str(node).strip():
            flag = True

    for i, node in enumerate(contents):
        if isinstance(node, Tag):
            continue
        if not isinstance(node, NavigableString):
            continue

        text = str(node)
        next_node = contents[i + 1] if i + 1 < len(contents) else None
        next_is_br = _is_br(next_node)

        if '\n' not in text:
            continue

        lines = text.split('\n')
        if not any(line.strip() for line in lines):
            continue                       # 纯缩进空白，跳过

        # 每个换行符在 text 里的下标
        positions, p = [], 0
        for line in lines[:-1]:
            p += len(line)
            positions.append(p)
            p += 1

        chosen = []
        for b, pos in enumerate(positions):
            before_txt = '\n'.join(lines[:b + 1])
            after_txt = '\n'.join(lines[b + 1:])
            # 只处理「真正代表换行」的换行：
            #   * 换行前必须有内容（开头的缩进换行不算）
            #   * 换行后必须有内容（结尾的缩进换行不算）
            #   * 已经有 <br> 负责这次换行的不重复插
            if not before_txt.strip():
                continue
            if not (after_txt.strip() or after_has[i + 1]):
                continue
            if not after_txt.strip() and next_is_br:
                continue                  # 已有 <br> 负责这次换行，不重复插
            chosen.append(pos)
        if not chosen:
            continue

        chunks, prev = [], 0
        for pos in chosen:
            chunks.append(text[prev:pos + 1])   # 保留换行符本身
            prev = pos + 1
        chunks.append(text[prev:])

        parent = node.parent
        if parent is None:
            continue
        index = parent.contents.index(node)
        node.extract()

        new_nodes = []
        for ci, chunk in enumerate(chunks):
            if ci > 0:
                new_nodes.append(el.new_tag('br'))
            if chunk:
                new_nodes.append(NavigableString(chunk))
        for offset, new_node in enumerate(new_nodes):
            parent.insert(index + offset, new_node)
    return el


def _flatten_absolute(tag):
    """``position:absolute`` 元素 → 普通流里的行内元素，并保留原来的横向位置。"""
    decls = _style_of(tag)
    position = decls.get('position', '').strip().lower()
    if position not in ('absolute', 'fixed'):
        return

    left = _len_to_px(decls.get('left'))
    width = _len_to_px(decls.get('width'))

    for prop in _ABS_PROPS:
        decls.pop(prop, None)

    display = decls.get('display', '').strip().lower()
    if display not in ('inline', 'inline-block', 'block'):
        decls['display'] = 'inline-block'

    parent = tag.parent
    if parent is not None and isinstance(parent, Tag):
        parent_decls = _style_of(parent)
        padding_left = _len_to_px(_side_value(parent_decls, 'padding', 'left'))
        if padding_left is not None and left is not None:
            # 父级 padding-left 让位给「原本绝对定位的坐标」
            new_padding_left = left
            _set_side(parent_decls, 'padding', 3, _fmt_px(new_padding_left))
            delta = padding_left - new_padding_left
            # 子元素里为抵消 padding 用的负 margin-left 同步补偿
            for child in parent.find_all(True, recursive=False):
                child_decls = _style_of(child)
                margin_left = _len_to_px(_side_value(child_decls, 'margin', 'left'))
                if margin_left is not None and margin_left < 0:
                    _set_side(child_decls, 'margin', 3, _fmt_px(margin_left + delta))
                    _set_style(child, child_decls)
            _set_style(parent, parent_decls)

            # 圆点/徽章右侧留白，保证后续文字的起始位置不变
            if width is not None:
                spacer = padding_left - left - width
                if spacer > 0:
                    _set_side(decls, 'margin', 1, _fmt_px(spacer))

    _set_style(tag, decls)


def _normalize_background(decls):
    """纯色 ``background`` 简写 → ``background-color``（公众号更容易保留颜色）。"""
    raw = decls.get('background')
    if not raw:
        return
    if 'url(' in raw.lower() or 'gradient(' in raw.lower():
        return
    parts = _split_top_level(raw, ' ')
    color = None
    for part in parts:
        if not part:
            continue
        token = _first_color_token(part)
        if token and not _DIRECTION_RE.match(part):
            color = token
            break
    del decls['background']
    if color and color.lower() != 'none':
        decls['background-color'] = color


def strip_unsupported(soup):
    """公众号不认 / 没意义的样式清理。

    * ``position:absolute`` 相关定位属性全部删掉，编号圆点改成普通流里的行内元素
    * ``white-space:pre-wrap`` 删掉（先把提示词里的换行换成 ``<br>``，保住换行效果）
    * 删掉 ``text-decoration-thickness/style/color``、``orphans``、``widows``、
      ``text-indent``、``text-transform``、``font-variant-*``、``-webkit-text-stroke-width``
      等无用计算属性
    * ``display`` 归一化成 block / inline-block / inline / none
    * 保留：color、font-size、font-weight、font-style、line-height、text-align、
      margin*、padding*、border*、background-color、border-radius、vertical-align、
      width/max-width、height、opacity、white-space:nowrap
    """
    if soup is None:
        return soup

    # 1) pre-wrap → <br>
    targets = []
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        if decls.get('white-space', '').strip().lower() == 'pre-wrap' or 'prompt' in _classes(tag):
            targets.append(tag)
    for tag in targets:
        _convert_prewrap_breaks(tag)
        decls = _style_of(tag)
        if decls.get('white-space', '').strip().lower() == 'pre-wrap':
            del decls['white-space']
        _set_style(tag, decls)

    # 2) absolute → 普通流
    for tag in soup.find_all(True):
        _flatten_absolute(tag)

    # 3) 无用属性 + display 归一化 + background 简写
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        changed = False
        for prop in _JUNK_PROPS:
            if prop in decls:
                del decls[prop]
                changed = True
        if STRIP_LETTER_SPACING and 'letter-spacing' in decls:
            del decls['letter-spacing']
            changed = True
        display = decls.get('display', '').strip().lower()
        if display and display not in _DISPLAY_KEEP:
            decls['display'] = _DISPLAY_MAP.get(display, 'block')
            changed = True
        if NORMALIZE_BACKGROUND:
            before = decls.get('background')
            _normalize_background(decls)
            if before != decls.get('background'):
                changed = True
        if changed:
            _set_style(tag, decls)
    return soup


# ============================================================ 组合调用
def apply_all(soup):
    """按推荐顺序跑完 4 个降级函数（每个函数也可以单独调用）。"""
    flatten_flex(soup)
    gradient_to_solid(soup)
    strip_shadow(soup)
    strip_unsupported(soup)
    return soup


# ============================================================ 回归样本
# 一段把所有「公众号不认的写法」都摆齐的最小样本，
# 用来验证每个降级分支真的干了活（项目里的 wechat.html 可能已经被降级过）。
FIXTURE_HTML = '''
<div class="wrap" style="display:flex;flex-wrap:wrap;gap:10px">
  <a class="card" style="flex:1 1 46%;min-width:0;display:flex;flex-direction:column;align-items:flex-start">
    <span class="line" style="display:flex;align-items:center;gap:8px"><b style="flex:none">第 1 步</b>基础安装</span>
    <small>下载安装并登录</small>
  </a>
  <a class="card" style="flex:1 1 46%"><span class="line">第二张卡</span></a>
</div>
<h2 class="step-h" style="display:flex;align-items:center;gap:10px"><span class="n" style="flex:none">第 2 步</span>安装 Skill</h2>
<p>高亮<span class="hl" style="background-color:#eaf6ef;background-image:linear-gradient(180deg, rgba(255,255,255,0) 76%, #dcefe4 76%)">重要的一句</span>结束</p>
<p>选项<span class="pick" style="box-shadow:inset 0 -2px 0 #8fcdb0">可以</span></p>
<ol class="substeps"><li style="position:relative;padding-left:36px"><span class="num" style="position:absolute;left:0;top:0;width:24px;height:24px;border-radius:50%">1</span><b style="display:block">标题</b><p style="margin:0 0 0 -36px">提示文字</p></li></ol>
<div class="prompt" style="white-space:pre-wrap">第一行
第二行

第四行</div>
'''


def fixture_test():
    """回归样本：验证 4 个降级分支都真的生效，且文本一字不丢。"""
    soup = BeautifulSoup(FIXTURE_HTML, 'lxml')
    before_len = len(soup.get_text())

    apply_all(soup)

    assert len(soup.get_text()) == before_len, 'fixture：文本长度变了'
    metrics = style_metrics(soup)
    for key in ('flex', 'gradient', 'box-shadow', 'position-absolute', 'white-space-pre-wrap'):
        assert metrics[key] == 0, 'fixture：还有 %s' % key

    hl = soup.select_one('.hl')
    hl_style = _style_of(hl)
    assert hl_style.get('background-color') == '#eaf6ef', 'fixture：.hl 底色不对'
    assert hl_style.get('border-bottom') == '2px solid #dcefe4', 'fixture：.hl 底线不对'
    assert 'background-image' not in hl_style, 'fixture：.hl 还留着渐变'

    pick = soup.select_one('.pick')
    assert _style_of(pick).get('border-bottom') == '2px solid #8fcdb0', 'fixture：.pick 下划线不对'

    line_badge = soup.select_one('.line b')
    assert _margin_px(_style_of(line_badge), 'right') == 8.0, 'fixture：行内容器 gap 没转成 margin'

    step_badge = soup.select_one('.step-h .n')
    assert _margin_px(_style_of(step_badge), 'right') == 10.0, 'fixture：标题徽章 gap 没转成 margin'

    card = soup.select_one('.card')
    assert _style_of(card).get('display') == 'block', 'fixture：卡片没有降级成块级'
    assert 'flex' not in _style_of(card), 'fixture：flex 属性没删干净'
    assert _margin_px(_style_of(card), 'bottom') == 10.0, 'fixture：容器 gap 没转成 margin'

    num = soup.select_one('.num')
    num_style = _style_of(num)
    assert num_style.get('display') == 'inline-block', 'fixture：编号徽章没变成行内元素'
    assert 'position' not in num_style and 'left' not in num_style, 'fixture：定位属性没删干净'
    assert _margin_px(num_style, 'right') == 12.0, 'fixture：编号徽章右侧留白不对'

    li = soup.select_one('.substeps li')
    assert _len_to_px(_side_value(_style_of(li), 'padding', 'left')) == 0.0, 'fixture：li 的 padding-left 没让位'
    tip = soup.select_one('.substeps li p')
    assert _len_to_px(_side_value(_style_of(tip), 'margin', 'left')) == 0.0, 'fixture：负 margin-left 没补偿'

    prompt = soup.select_one('.prompt')
    assert len(prompt.find_all('br')) == 3, 'fixture：提示词换行数不对（应为 3 个 br）'
    assert '\n' in prompt.get_text(), 'fixture：换行符被删了'

    # 幂等：再跑一遍不应该有变化
    length_after = len(soup.get_text())
    apply_all(soup)
    assert len(soup.get_text()) == length_after, 'fixture：重复执行后文本长度变了'
    assert len(soup.select_one('.prompt').find_all('br')) == 3, 'fixture：重复执行又插了 br'
    return True


# ============================================================ 指标统计
def style_metrics(soup):
    """统计还留在 style 属性里的「公众号不认」的写法。

    只扫 style 属性，不扫 ``<script>`` 文本（工具条的 JS 里有一份 toast 样式，
    那段不会进公众号正文）。
    """
    metrics = {
        'flex': 0,
        'gradient': 0,
        'box-shadow': 0,
        'position-absolute': 0,
        'white-space-pre-wrap': 0,
        'elements': 0,
    }
    if soup is None:
        return metrics
    for tag in soup.find_all(True):
        metrics['elements'] += 1
        decls = _style_of(tag)
        if decls.get('display', '').strip().lower() in ('flex', 'inline-flex'):
            metrics['flex'] += 1
        if 'gradient' in decls.get('background-image', '').lower():
            metrics['gradient'] += 1
        if 'box-shadow' in decls:
            metrics['box-shadow'] += 1
        if decls.get('position', '').strip().lower() in ('absolute', 'fixed'):
            metrics['position-absolute'] += 1
        if decls.get('white-space', '').strip().lower() == 'pre-wrap':
            metrics['white-space-pre-wrap'] += 1
    return metrics


# ============================================================ 自测
def _load_soup(path):
    html = Path(path).read_text(encoding='utf-8')
    try:
        return BeautifulSoup(html, 'lxml')
    except Exception:
        return BeautifulSoup(html, 'html.parser')


def _raw_counts(soup):
    """整份 HTML 里的关键字出现次数（含 <script> 文本，仅作参考）。"""
    text = str(soup)
    return {
        'display:flex': len(re.findall(r'display\s*:\s*(?:inline-)?flex', text)),
        'linear-gradient': text.count('linear-gradient'),
        'box-shadow': text.count('box-shadow'),
        'position:absolute': len(re.findall(r'position\s*:\s*absolute', text)),
        'white-space:pre-wrap': len(re.findall(r'white-space\s*:\s*pre-wrap', text)),
    }


def _print_row(title, text_len, metrics):
    print('  %-22s 文本长度=%-7d flex=%-3d gradient=%-3d shadow=%-3d absolute=%-3d pre-wrap=%d'
          % (title, text_len, metrics['flex'], metrics['gradient'],
             metrics['box-shadow'], metrics['position-absolute'],
             metrics['white-space-pre-wrap']))


def self_test(path=None):
    """自测：跑完 4 个函数后文本长度不变、4 类不受支持写法全部清零。"""
    if path is None:
        candidate = HERE / 'wechat.html'
        path = candidate if candidate.exists() else HERE / 'index.html'
    path = Path(path)

    print('输入文件: %s' % path)
    soup = _load_soup(path)
    before_len = len(soup.get_text())
    before_metrics = style_metrics(soup)
    print()
    print('=== 处理前 ===')
    _print_row('原始', before_len, before_metrics)
    raw = _raw_counts(soup)
    print('  （整份 HTML 关键字计数，含 <script> 里的 toast 样式：%s）' % raw)
    print()

    # 每一步负责清零自己的那几项；最后再统一断言全部为 0
    steps = (
        ('flatten_flex', flatten_flex, ('flex',)),
        ('gradient_to_solid', gradient_to_solid, ('gradient',)),
        ('strip_shadow', strip_shadow, ('box-shadow',)),
        ('strip_unsupported', strip_unsupported,
         ('position-absolute', 'white-space-pre-wrap')),
    )

    for name, func, owned in steps:
        func(soup)
        text_len = len(soup.get_text())
        metrics = style_metrics(soup)
        print('=== 执行 %s ===' % name)
        _print_row(name, text_len, metrics)
        assert text_len == before_len, '%s 之后文本长度变了：%d → %d' % (name, before_len, text_len)
        for key in owned:
            assert metrics[key] == 0, '%s 之后还有 %s' % (name, key)
        print()

    final = style_metrics(soup)
    for key in ('flex', 'gradient', 'box-shadow', 'position-absolute', 'white-space-pre-wrap'):
        assert final[key] == 0, '最终结果里还有 %s：%d' % (key, final[key])

    # 空 soup 安全
    empty = BeautifulSoup('', 'lxml')
    for name, func, _ in steps:
        func(empty)
    assert len(empty.get_text()) == 0
    print('空 soup 安全 ✓')

    # 回归样本：验证每个降级分支
    fixture_test()
    print('回归样本（flex / 渐变 / 阴影 / 绝对定位 / pre-wrap）全部通过 ✓')

    print()
    print('全部断言通过 ✓  文本长度保持 %d 不变' % before_len)
    return soup


if __name__ == '__main__':
    self_test()
