#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
公众号块级扁平化 —— 把「依赖容器」的结构压平成公众号最稳的段落流。

背景
----
微信公众号编辑器（ProseMirror 底座）对块级容器的支持比想象中窄，实测有两条硬伤：

1. **``<section>`` 不形成可靠的段落边界**
   连续的 ``<section>`` 会被并进同一个段落，视觉上就是「卡片挤成一片文字」。
   社区实测也明确提到「section 标签的 margin/padding 被重置」。

2. **``<p>`` 才是公众号真正认的段落单元**
   ``<p>`` 之间的边界稳定保留，margin/padding 也留着。

所以本模块的策略是：**把所有视觉块都变成顶层 ``<p>``，``<p>`` 内部只留行内内容。**

具体做法
--------
* ``<div>`` → ``<p>``
* ``<figure>`` → ``<p>``（装图片） + 兄弟 ``<p>``（图注独立成段）
* ``<p>`` 里出现块级子元素（``p`` / ``section`` / ``h1-h6`` / ``ul`` / ``ol`` / ``blockquote``）→
  把子元素提成兄弟节点，容器自身的底色 / 边框 / 圆角 / 内边距迁移到第一个子块
* 卡片类容器（``.step`` / ``.note`` / ``.site`` / ``.prompt`` / ``.sub-head``）
  内部的 ``<p>`` 不拆散，而是把内容转成行内文本 + ``<br>``，保持整块外观
* 图片独占一个 ``<p>``（``<p><img></p>`` 是公众号最稳的插图写法）

对外接口
--------
``flatten_to_paragraphs(soup)`` —— 就地改写，返回同一个 soup。
"""
from bs4 import BeautifulSoup, NavigableString, Tag

# 公众号会当成独立块处理的标签
BLOCK = {
    'p', 'div', 'section', 'figure', 'figcaption',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'blockquote', 'pre', 'table', 'hr',
}

# 容器里有这些类时，内部的 p 不拆散（拆了就丢卡片外观）
CARD_CLASSES = ('note', 'site', 'prompt', 'step', 'sub-head', 'flow-nav', 'flow-links')

# 属于「盒子外观」的属性：容器被拆散时，这些要迁移到第一个子块
BOX_PROPS = (
    'background-color', 'background', 'border', 'border-top', 'border-right',
    'border-bottom', 'border-left', 'border-width', 'border-style', 'border-color',
    'border-radius', 'padding', 'padding-top', 'padding-right', 'padding-bottom',
    'padding-left',
)

# 间距类属性：容器消失时，要交给第一个子块
MARGIN_PROPS = ('margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left')


def _style_dict(el):
    raw = (el.get('style') or '').strip()
    out = {}
    for piece in raw.split(';'):
        if ':' not in piece:
            continue
        k, v = piece.split(':', 1)
        k = k.strip().lower()
        if k:
            out[k] = v.strip()
    return out


def _write_style(el, decls):
    el['style'] = '; '.join('%s: %s' % (k, v) for k, v in decls.items() if v)


def _has_class(el, names):
    if el is None:
        return False
    cls = el.get('class') or []
    if isinstance(cls, str):
        cls = cls.split()
    return any(c in names for c in cls)


def _is_card(el):
    """看起来像个「盒子」的元素：有底色或边框。"""
    d = _style_dict(el)
    if d.get('background-color') and d['background-color'].lower() not in ('transparent', 'none'):
        return True
    if any(k.startswith('border') and k != 'border-radius' for k in d):
        return True
    return False


def _margin_split(decls):
    """把 margin 拆成 (上, 下)，供块间衔接使用。"""
    raw = decls.get('margin')
    top = decls.get('margin-top')
    bottom = decls.get('margin-bottom')
    if raw:
        parts = raw.split()
        if len(parts) == 1:
            top = top or parts[0]
            bottom = bottom or parts[0]
        elif len(parts) == 2:
            top = top or parts[0]
            bottom = bottom or parts[1]
        elif len(parts) >= 3:
            top = top or parts[0]
            bottom = bottom or parts[2]
    return top, bottom


# --------------------------------------------------------------- figure 拆分
def _split_figures(soup):
    """<figure><img><figcaption>…</figcaption></figure>
    → <p>…img…</p> + <p>图注</p>（两个兄弟段落）"""
    for fig in list(soup.find_all('figure')):
        cap = fig.find('figcaption')
        fig_style = _style_dict(fig)
        m_top, m_bottom = _margin_split(fig_style)

        # 图片段落
        img_p = soup.new_tag('p')
        img_style = dict(fig_style)
        img_style.pop('margin', None)
        img_style.pop('margin-top', None)
        img_style.pop('margin-bottom', None)
        if m_top:
            img_style['margin-top'] = m_top
        img_style['margin-bottom'] = '0'
        _write_style(img_p, img_style)
        if fig.get('class'):
            img_p['class'] = fig.get('class')

        for child in list(fig.children):
            if child is cap:
                continue
            child.extract()
            img_p.append(child)

        fig.replace_with(img_p)

        # 图注段落
        if cap is not None:
            cap_style = _style_dict(cap)
            cap_style.pop('margin', None)
            cap_style.pop('margin-top', None)
            cap_style.pop('margin-bottom', None)
            cap_style['margin-top'] = '8px'
            if m_bottom:
                cap_style['margin-bottom'] = m_bottom
            cap_p = soup.new_tag('p')
            _write_style(cap_p, cap_style)
            if cap.get('class'):
                cap_p['class'] = cap.get('class')
            for child in list(cap.children):
                child.extract()
                cap_p.append(child)
            img_p.insert_after(cap_p)


# --------------------------------------------------------------- 卡片内联
def _inline_card_children(soup):
    """卡片容器内部的 <p> 不拆散：转成行内内容 + <br>，保持整块外观。

    两阶段：先把要处理的 (父, 子) 收集齐，再统一改写 ——
    边遍历边改 DOM 会让 BeautifulSoup 的惰性 ResultSet 产出失效节点。
    """
    pairs = []
    for parent in list(soup.find_all(['div', 'section', 'p'])):
        if not _has_class(parent, CARD_CLASSES):
            continue
        for child in list(parent.find_all('p', recursive=False)):
            if child.find('img'):
                continue  # 图片段落保持独立
            pairs.append((parent, child))

    for parent, child in pairs:
        if child.parent is None:
            continue
        index = parent.index(child)
        for node in list(child.contents):
            node.extract()
            parent.insert(index, node)
            index += 1
        # 分隔符放在内容「后面」（后面还有内容时才加）
        child.decompose()
        if index < len(parent.contents):
            parent.insert(index, soup.new_tag('br'))


# --------------------------------------------------------------- 拆平块级子元素
def _migrate_box_style(parent, target):
    """容器被拆散时，把盒子外观迁移到第一个子块。"""
    p_style = _style_dict(parent)
    t_style = _style_dict(target)
    for key in BOX_PROPS:
        if key in p_style and key not in t_style:
            t_style[key] = p_style[key]
    _write_style(target, t_style)


def _explode_blocks(soup):
    """把 <p> / <li> 里的块级子元素提成兄弟节点。"""
    for parent in list(soup.find_all(['p', 'li'])):
        blocks = [c for c in parent.children
                  if isinstance(c, Tag) and c.name in BLOCK]
        if not blocks:
            continue

        # 容器「自身」有没有直接文本（不含块级子元素里的文字）
        direct_text = ''.join(c.strip() for c in parent.children
                              if isinstance(c, NavigableString))
        has_text = bool(direct_text)
        if not has_text:
            # 容器只有块 → 容器消失，盒子样式交给第一个块
            _migrate_box_style(parent, blocks[0])
            m_top, m_bottom = _margin_split(_style_dict(parent))
            b_style = _style_dict(blocks[0])
            if m_top and 'margin-top' not in b_style:
                b_style['margin-top'] = m_top
            if m_bottom and 'margin-bottom' not in b_style:
                b_style['margin-bottom'] = m_bottom
            _write_style(blocks[0], b_style)

        anchor = parent
        for b in blocks:
            b.extract()
            anchor.insert_after(b)
            anchor = b

        # 容器被清空了 → 直接删掉，避免留一个空气段落
        if not parent.get_text(strip=True) and not parent.find('img'):
            parent.decompose()


# --------------------------------------------------------------- 图片独占段落
def _isolate_images(soup):
    """<p>文字<img>文字</p> → 图片单独占一个 p。"""
    for p in list(soup.find_all('p')):
        imgs = p.find_all('img', recursive=False)
        if len(imgs) != 1:
            continue
        img = imgs[0]
        others = [c for c in p.children if c is not img and not isinstance(c, NavigableString)]
        text_nodes = [c for c in p.children if isinstance(c, NavigableString) and c.strip()]
        if not others and not text_nodes:
            continue  # 本来就只有一个图
        img_p = soup.new_tag('p')
        img_style = _style_dict(p)
        img_style['margin'] = '0'
        _write_style(img_p, img_style)
        img.extract()
        img_p.append(img)
        p.insert_after(img_p)


# --------------------------------------------------------------- 主入口
def flatten_to_paragraphs(soup):
    """把所有视觉块压平成顶层 <p>，段落内部只留行内内容。"""
    _split_figures(soup)

    # div / section → p（此时 section 里可能还塞着 p，交给后面拆平）
    for tag in list(soup.find_all(['div', 'section'])):
        if tag.name == 'section' and tag.get('id') == 'wx-toolbar':
            continue  # 工具条保持原样
        tag.name = 'p'

    _inline_card_children(soup)
    _explode_blocks(soup)
    _isolate_images(soup)
    return soup


# --------------------------------------------------------------- 自测
if __name__ == '__main__':
    FIX = '''<div class="note"><strong>提示</strong>说明文字</div>
<div class="prompt"><span class="tag">复制</span>给我做一个动画</div>
<figure><img src="a.png" alt="示例"><figcaption>图注文字</figcaption></figure>
<div class="step"><b>Windows</b><p>双击安装包。</p></div>
<div class="flow-nav"><p class="flow-tip">一共3步</p><div class="flow-links"><a><b>第1步</b>安装</a></div></div>
<div class="case"><h4>A｜3D 数据</h4><p class="fit">数据新闻</p><figure><img src="b.gif" alt="案例"><figcaption>案例图注</figcaption></figure></div>'''

    soup = BeautifulSoup(FIX, 'lxml')
    before = soup.get_text()
    flatten_to_paragraphs(soup)

    print('--- 转换结果 ---')
    print(soup.prettify())
    print('--- 校验 ---')
    assert 'div' not in [t.name for t in soup.find_all()], '还有 div'
    assert 'section' not in [t.name for t in soup.find_all()], '还有 section'
    assert 'figure' not in [t.name for t in soup.find_all()], '还有 figure'
    assert 'figcaption' not in [t.name for t in soup.find_all()], '还有 figcaption'
    # 没有 p 套 p
    for p in soup.find_all('p'):
        assert not p.find('p'), '还有嵌套的 p'
    # 没有 p 套 img + 其他
    for p in soup.find_all('p'):
        assert not (p.find('img') and len(p.find_all('img')) == 1
                    and p.get_text(strip=True)), '图片没独占段落'
    assert soup.get_text().replace(' ', '') == before.replace(' ', ''), '文本有丢失'
    print('✓ 无 div/section/figure/figcaption')
    print('✓ 无嵌套 p')
    print('✓ 图片独占段落')
    print('✓ 文本零丢失')
