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
  4. :func:`strip_unsupported`   —— 通用清理（定位 / 列表缩进 / pre-wrap / background 简写 / 无用计算属性）

``strip_unsupported`` 里额外处理的几件事：

* **``background`` 简写 → ``background-color``**：公众号只认长属性，简写会被整个丢掉，
  容器就变成没有底色的透明块（``background: transparent`` → ``background-color: transparent``，
  ``background: none`` → 整条删掉，复合值 ``#fff url(a.png) no-repeat`` 会拆成三条）。
* **absolute 定位按「特征组合」分流**（不依赖 class 名）：
  20~30px 见方 + 有文字 → 步骤编号徽章（保留圆形外观，改 inline-block + margin-right:8px）；
  ≤10px 见方 + 无文字 → 列表绿圆点（inline-block + margin-right）。
  父级 ``padding-left`` 让位、子元素负 ``margin-left`` 同步补偿，文字不会重叠也不会跑位。
* **列表收尾**：圆点 / 徽章是自己画的，列表不再需要原生缩进 →
  列表和列表项的左内边距归 0、列表项 padding 压成一条声明、``position:relative`` 清掉；
  ``list-style`` **保留原值**（保持 ``none``，改成 ``disc`` 会变成双圆点）。

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


def _collapse_sides(vals):
    """四边数值相同时收成一条，避免出现 'padding: 0 0 0 0px' 这种冗余写法。"""
    parsed = [_len_to_px(v) for v in vals]
    if all(p is not None for p in parsed) and len(set(parsed)) == 1:
        return vals[0]
    return ' '.join(vals)


def _set_side(decls, prefix, index, value):
    """index: 0=上 1=右 2=下 3=左。

    简写和 longhand 同步更新，谁生效都不冲突；
    原本没有 longhand 时只改简写，不额外造出重复声明。
    """
    side = _SIDE_NAMES[index]
    longhand = '%s-%s' % (prefix, side)
    vals = [_side_value(decls, prefix, s) for s in _SIDE_NAMES]
    vals[index] = value
    if longhand in decls:
        decls[longhand] = value
    decls[prefix] = _collapse_sides(vals)
    # 简写写在 longhand 后面时，longhand 变成冗余声明 → 删掉，避免同一属性写两遍
    keys = list(decls.keys())
    if longhand in decls and prefix in decls and keys.index(prefix) > keys.index(longhand):
        del decls[longhand]


def _set_padding_single(decls, value='0'):
    """把 padding 归一成**一条**声明（顺手干掉重复的 longhand）。"""
    for key in ('padding-top', 'padding-right', 'padding-bottom', 'padding-left'):
        decls.pop(key, None)
    decls['padding'] = value


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
    'orphans', 'widows', 'text-transform',
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


BADGE_MARGIN_RIGHT = 8.0    # 步骤编号徽章右侧留白（px）


def _classify_absolute(width, height, has_text):
    """按**特征组合**（不依赖 class 名）判断 absolute 元素的用途。

    * ``badge`` —— 20~30px 见方 + 有文字：步骤编号徽章，保留圆形外观
    * ``dot``   —— ≤10px 见方 + 无文字：列表圆点（绿色小圆点）
    * ``other`` —— 其余
    """
    if width is None or height is None:
        return 'other'
    if 20 <= width <= 30 and 20 <= height <= 30 and has_text:
        return 'badge'
    if width <= 10 and height <= 10 and not has_text:
        return 'dot'
    return 'other'


def _has_absolute_descendant(tag):
    for descendant in tag.find_all(True):
        if descendant.get('style') and 'position:absolute' in descendant.get('style').replace(' ', ''):
            return True
    return False


def _flatten_absolute(tag):
    """``position:absolute`` 元素 → 普通流里的行内元素（保留原有外观与横向位置）。

    * 徽章（24px 圆 + 文字）：``display:inline-block`` + ``margin-right:8px``，
      圆形外观（宽高/圆角/底色/字色/行高）全部保留；
    * 列表圆点（7px 圆 + 无文字）：``display:inline-block`` + 右侧留白，
      保留绿色圆点（比浏览器原生 disc 更贴近原稿）；
    * 父级 ``padding-left`` 让位给原本的绝对定位坐标，子元素为抵消 padding
      用的负 ``margin-left`` 同步补偿；父级不再有 absolute 子元素时，
      它的 ``position:relative`` 也会删掉。
    """
    decls = _style_of(tag)
    position = decls.get('position', '').strip().lower()
    if position not in ('absolute', 'fixed'):
        return

    left = _len_to_px(decls.get('left'))
    width = _len_to_px(decls.get('width'))
    height = _len_to_px(decls.get('height'))
    has_text = bool(tag.get_text().strip())
    kind = _classify_absolute(width, height, has_text)

    for prop in _ABS_PROPS:
        decls.pop(prop, None)

    display = decls.get('display', '').strip().lower()
    if display not in ('inline', 'inline-block', 'block'):
        decls['display'] = 'inline-block'

    # 徽章：固定 8px 右侧留白，保证一定排在文字前面且不重叠
    if kind == 'badge':
        _set_side(decls, 'margin', 1, _fmt_px(BADGE_MARGIN_RIGHT))

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

            # 圆点右侧留白（几何还原：文字起始位置与原稿一致）
            if kind == 'dot' and width is not None:
                spacer = padding_left - left - width
                if spacer > 0:
                    _set_side(decls, 'margin', 1, _fmt_px(spacer))

        # 父级已经没有 absolute 子元素了 → position:relative 没必要
        if parent_decls.get('position', '').strip().lower() == 'relative':
            if not _has_absolute_descendant(parent):
                parent_decls.pop('position', None)
                _set_style(parent, parent_decls)

    _set_style(tag, decls)


_BG_REPEAT = ('repeat', 'repeat-x', 'repeat-y', 'no-repeat', 'space', 'round')
_BG_ATTACHMENT = ('scroll', 'fixed', 'local')
_BG_SIZE = ('cover', 'contain')
_BG_POSITION = ('left', 'right', 'top', 'bottom', 'center')


def _normalize_background(decls):
    """``background`` 简写 → 公众号只认的长属性。

    * ``background: #fff``        → ``background-color: #fff``
    * ``background: transparent`` → ``background-color: transparent``
    * ``background: none``        → 整条删掉
    * ``background: #fff url(a.png) no-repeat``
      → ``background-color: #fff`` + ``background-image: url(a.png)``
        + ``background-repeat: no-repeat``（其余部分各自成条）
    """
    raw = decls.get('background')
    if not raw:
        return

    tokens = [t for t in _split_top_level(raw, ' ') if t]
    color = None
    image = None
    repeat = None
    attachment = None
    size = None
    position = []

    for token in tokens:
        low = token.lower()
        if low.startswith('url(') or 'gradient(' in low:
            image = token
        elif low in _BG_REPEAT:
            repeat = low
        elif low in _BG_ATTACHMENT:
            attachment = low
        elif low in _BG_SIZE:
            size = low
        elif low in _BG_POSITION:
            position.append(low)
        elif low == 'none':
            continue
        else:
            candidate = _first_color_token(token)
            if candidate and not _DIRECTION_RE.match(token):
                color = candidate

    del decls['background']
    if color:
        decls['background-color'] = color
    if image:
        decls['background-image'] = image
    if repeat:
        decls['background-repeat'] = repeat
    if attachment:
        decls['background-attachment'] = attachment
    if size:
        decls['background-size'] = size
    if position:
        decls['background-position'] = ' '.join(position)


def _padding_zero_left(decls):
    """把 padding 的**左边**归 0，其余三边保留，并压成一条声明。"""
    vals = [_side_value(decls, 'padding', side) for side in _SIDE_NAMES]
    vals[3] = '0'
    _set_padding_single(decls, _collapse_sides(vals))


def _cleanup_lists(soup):
    """列表布局收尾。

    * ``list-style:none`` 的列表：圆点 / 编号是我们自己画的（绿色圆点、圆形徽章），
      不需要原生缩进 → 列表和列表项的左内边距归 0；
      **``list-style`` 本身保留 ``none``**，改成 ``disc`` 会变成「双圆点」；
    * 列表项的 padding 压成**一条**声明，不再出现重复的 longhand；
    * 列表项上的 ``position:relative``（原本用来锚定 absolute 圆点）
      在没有 absolute 子元素之后删掉；
    * 列表项文字不会紧贴左边：圆点 / 徽章自带 ``margin-right``。
    """
    if soup is None:
        return soup

    for lst in soup.find_all(['ul', 'ol']):
        decls = _style_of(lst)
        list_style = (decls.get('list-style') or decls.get('list-style-type') or '').strip().lower()
        if list_style == 'none':
            _padding_zero_left(decls)
            _set_style(lst, decls)

        for li in lst.find_all('li'):
            li_decls = _style_of(li)
            changed = False
            if any(key in li_decls for key in ('padding', 'padding-top', 'padding-right',
                                               'padding-bottom', 'padding-left')):
                _padding_zero_left(li_decls)
                changed = True
            if (li_decls.get('position', '').strip().lower() == 'relative'
                    and not _has_absolute_descendant(li)):
                li_decls.pop('position', None)
                changed = True
            if changed:
                _set_style(li, li_decls)
    return soup


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

    # 2b) 列表收尾：缩进归 0、padding 压成一条、relative 清掉
    _cleanup_lists(soup)

    # 2c) 已经没有 absolute 子元素了，position:relative 也就没必要（公众号会丢）
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        if decls.get('position', '').strip().lower() != 'relative':
            continue
        if _has_absolute_descendant(tag):
            continue
        decls.pop('position', None)
        for prop in ('top', 'left', 'right', 'bottom'):
            decls.pop(prop, None)
        _set_style(tag, decls)

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
        # text-indent 属于可用属性，保留；只有 0 值是冗余的才删
        indent = decls.get('text-indent')
        if indent is not None and not _len_to_px(indent):
            del decls['text-indent']
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
<ul class="fit" style="list-style:none;padding-left:22px">
  <li style="position:relative;margin:8px 0;padding-left:22px"><span style="position:absolute;left:4px;top:11px;width:7px;height:7px;border-radius:50%;background:#4da783"></span>列表项文字</li>
</ul>
<div class="prompt" style="white-space:pre-wrap">第一行
第二行

第四行</div>
'''


def extra_assertions(soup, min_colored=1):
    """额外断言：列表 / 徽章 / 底色 / 简写残留。"""
    # 1) list-style 保留原值（不改 disc，避免双圆点）
    for lst in soup.find_all(['ul', 'ol']):
        decls = _style_of(lst)
        assert decls.get('list-style', '').strip().lower() != 'disc', 'list-style 被改成了 disc'
        assert decls.get('list-style-type', '').strip().lower() != 'disc', 'list-style-type 被改成了 disc'

    # 2) 列表 / 列表项的左内边距归 0，padding 只留一条声明
    for lst in soup.find_all(['ul', 'ol']):
        decls = _style_of(lst)
        assert not _len_to_px(_side_value(decls, 'padding', 'left')), '列表左内边距没归 0'
        for li in lst.find_all('li'):
            li_decls = _style_of(li)
            for key in ('padding-left', 'padding-top', 'padding-right', 'padding-bottom'):
                assert key not in li_decls, '列表项还有重复的 %s 声明' % key
            assert not _len_to_px(_side_value(li_decls, 'padding', 'left')), '列表项左内边距没归 0'
            assert li_decls.get('position', '').strip().lower() != 'relative', '列表项还留着 position:relative'

    # 3) 24px 左右的圆形徽章：inline-block + margin-right
    badges = 0
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        width = _len_to_px(decls.get('width'))
        height = _len_to_px(decls.get('height'))
        if (width and height and 20 <= width <= 30 and 20 <= height <= 30
                and tag.get_text().strip()):
            badges += 1
            assert decls.get('display', '').strip().lower() == 'inline-block', '徽章没有 inline-block'
            assert (_margin_px(decls, 'right') or 0) > 0, '徽章没有 margin-right'
    assert badges > 0, '一个徽章都没找到'

    # 4) 不存在 absolute / fixed 的小装饰空元素
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        if decls.get('position', '').strip().lower() in ('absolute', 'fixed'):
            width = _len_to_px(decls.get('width'))
            height = _len_to_px(decls.get('height'))
            assert not (width and height and width <= 10 and height <= 10
                        and not tag.get_text().strip()), '还有 absolute 的空装饰小元素'

    # 5) 没有 background 简写 / background-image 残留
    for tag in soup.find_all(True):
        decls = _style_of(tag)
        assert 'background' not in decls, '还有 background 简写'
        assert 'background-image' not in decls, '还有 background-image'

    # 6) 带底色（background-color 非 transparent）的元素数量
    colored = 0
    for tag in soup.find_all(True):
        value = _style_of(tag).get('background-color', '').strip().lower()
        if value and value != 'transparent':
            colored += 1
    assert colored >= min_colored, '带底色的元素太少：%d（要求 ≥%d）' % (colored, min_colored)
    return colored


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
    assert _margin_px(num_style, 'right') == 8.0, 'fixture：编号徽章右侧留白不对'

    li = soup.select_one('.substeps li')
    assert _len_to_px(_side_value(_style_of(li), 'padding', 'left')) == 0.0, 'fixture：li 的 padding-left 没让位'
    tip = soup.select_one('.substeps li p')
    assert _len_to_px(_side_value(_style_of(tip), 'margin', 'left')) == 0.0, 'fixture：负 margin-left 没补偿'

    fit_list = soup.select_one('ul.fit')
    fit_decls = _style_of(fit_list)
    assert fit_decls.get('list-style', '').strip().lower() == 'none', 'fixture：list-style 被改了'
    assert not _len_to_px(_side_value(fit_decls, 'padding', 'left')), 'fixture：列表缩进没归 0'
    fit_li = fit_list.find('li')
    fit_li_decls = _style_of(fit_li)
    assert 'padding-left' not in fit_li_decls, 'fixture：列表项还有重复的 padding-left'
    assert not _len_to_px(_side_value(fit_li_decls, 'padding', 'left')), 'fixture：列表项缩进没归 0'
    assert fit_li_decls.get('position', '').strip().lower() != 'relative', 'fixture：列表项还留着 relative'
    dot = fit_li.find('span')
    dot_decls = _style_of(dot)
    assert dot_decls.get('display', '').strip().lower() == 'inline-block', 'fixture：圆点没变成行内元素'
    assert _margin_px(dot_decls, 'right') == 11.0, 'fixture：圆点右侧留白不对'
    assert dot_decls.get('background-color') == '#4da783', 'fixture：圆点颜色丢了'

    prompt = soup.select_one('.prompt')
    assert len(prompt.find_all('br')) == 3, 'fixture：提示词换行数不对（应为 3 个 br）'
    assert '\n' in prompt.get_text(), 'fixture：换行符被删了'

    extra_assertions(soup, min_colored=1)

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

    # 真实文件的额外断言（列表 / 徽章 / 底色 / 简写残留）
    colored = extra_assertions(soup, min_colored=30)
    print('额外断言通过 ✓  带底色（background-color 非 transparent）元素 %d 个' % colored)
    print('回归样本（flex / 渐变 / 阴影 / 绝对定位 / pre-wrap）全部通过 ✓')

    print()
    print('全部断言通过 ✓  文本长度保持 %d 不变' % before_len)
    return soup


if __name__ == '__main__':
    self_test()
