#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
公众号（微信公众平台图文编辑器）HTML 兼容层：块级标签降级。

背景
----
公众号新版编辑器底层是 ProseMirror，它的 HTML 白名单里**没有 div / figure /
figcaption**。这些标签被降级时，**连同它们身上的内联样式一起丢失**——于是
所有靠这些标签承载样式的容器（卡片、提示框、网址卡、图注、分步块）全部塌成
连续文本，块级结构荡然无存。

社区实测的保守基线（md2wechat 官方 HTML 规范 + feishu2wx 社区基线）：

    稳定依赖  p / span / strong / em / ul / ol / li / a / img /
              section / blockquote / h1-h6 / table 系列 / hr / sup / sub
    会降级    figure / figcaption / div / 复杂布局标签
    不支持    script / style / iframe / video

降级映射
--------
    div       →  section      （白名单里的块级元素，背景色/边框/圆角/内边距都保留）
    figure    →  section      （同上；原 style 原样迁移）
    figcaption →  p           （p 是块级元素，公众号里会独立成段，
                                图注不再黏进上一段正文）

约束
----
只改标签名。style / class / id / 其他属性、文本内容、子节点结构一律不动。
已经是白名单稳定标签的元素（p / section / ul / ol / li / h1-h6 / span / a /
img ...）一律保持原样。

用法
----
    from wecom_div_to_section import div_to_section

    soup = BeautifulSoup(html, 'lxml')
    div_to_section(soup)          # 原地修改，同时返回 soup 便于链式调用

命令行自测：
    python wecom_div_to_section.py                   # 用项目里的 wechat.html 自测
    python wecom_div_to_section.py in.html out.html   # 转换单个文件
"""
from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent

# 需要降级的标签 → 公众号白名单里的替代标签
NAME_MAP = {
    'div': 'section',
    'figure': 'section',
    'figcaption': 'p',
}

# 白名单稳定标签：本来就不该被改。
# 列出主要是给自测用——转换前后它们的数量必须逐一保持不变。
# 注意：section / p 不在此列：
#   · section 会被新增（div / figure 降级而来）
#   · p 会被新增（figcaption 降级而来）
# 这两个在 selftest 里用「增量」方式单独断言。
PRESERVE_TAGS = (
    'ul', 'ol', 'li', 'span', 'a', 'img',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'br', 'hr', 'strong', 'em', 'b', 'small', 'sup', 'sub',
    'blockquote', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'code', 'pre',
)


# ------------------------------------------------------------------ 核心转换
def _retag(soup, old_name, new_name):
    """把 soup 里所有 <old_name> 改名为 <new_name>，只改标签名。

    find_all 返回的是一次性列表（快照），所以边遍历边改名是安全的：
    改名不会把元素从树上摘掉，嵌套的同名标签也依然在列表里等着被改。
    """
    for tag in soup.find_all(old_name):
        # Tag.name 赋值 = 改标签名，属性 / 子节点 / 文本全部保留
        tag.name = new_name
    return soup


def div_to_section(soup):
    """公众号白名单降级：div → section、figure → section、figcaption → p。

    div / figure 被降级成 p 时样式会一起丢；section 是安全替代，inline style 原样保留。
    figcaption → p：p 是块级元素，公众号里独立成段，图注不会黏进上一段正文。

    只改标签名：style / class / id / 其他属性、文本内容、子节点结构全部不动。
    嵌套的同名标签也会一并转换。

    参数
    ----
    soup : BeautifulSoup | Tag | str
        待转换的 soup。传 str 时会先解析成 BeautifulSoup 再转换；
        传 None 或空 soup 都不会报错。

    返回
    ----
    BeautifulSoup | Tag | None
        转换后的对象（与入参同一个对象，就地修改）。
    """
    if soup is None:
        return None

    # 兼容直接传字符串的情况：解析后转换，返回新的 soup
    if isinstance(soup, str):
        soup = BeautifulSoup(soup, 'html.parser')
        div_to_section(soup)
        return soup

    # 顺序：先外层（figure → section），再内层（figcaption → p）。
    # 三步互不干扰，每步都是独立的快照遍历。
    _retag(soup, 'div', 'section')
    _retag(soup, 'figure', 'section')
    _retag(soup, 'figcaption', 'p')

    return soup


# 更语义化的别名，和 div_to_section 等价
to_wechat_blocks = div_to_section


def figure_to_section(soup):
    """只做 figure → section（只改标签名，style 原样迁移）。"""
    if soup is None:
        return None
    if isinstance(soup, str):
        soup = BeautifulSoup(soup, 'html.parser')
        figure_to_section(soup)
        return soup
    return _retag(soup, 'figure', 'section')


def figcaption_to_p(soup):
    """只做 figcaption → p（只改标签名，style 原样迁移）。"""
    if soup is None:
        return None
    if isinstance(soup, str):
        soup = BeautifulSoup(soup, 'html.parser')
        figcaption_to_p(soup)
        return soup
    return _retag(soup, 'figcaption', 'p')


def html_to_sections(html):
    """便捷封装：HTML 字符串进，HTML 字符串出。"""
    soup = BeautifulSoup(html, 'html.parser')
    div_to_section(soup)
    return soup.decode()


def convert_file(src, dst):
    """便捷封装：读文件 → 转换 → 写文件。返回转换前后各标签计数。"""
    src, dst = Path(src), Path(dst)
    soup = BeautifulSoup(src.read_text(encoding='utf-8'), 'html.parser')
    before = _counts(soup)
    div_to_section(soup)
    after = _counts(soup)
    # 显式 newline='\n'，避免 Windows 下写出 CRLF 污染
    dst.write_text(soup.prettify(), encoding='utf-8', newline='\n')
    return before, after


def _counts(soup):
    """统计各受关注标签的数量。"""
    tags = ('div', 'figure', 'figcaption', 'section', 'p')
    return {t: len(soup.find_all(t)) for t in tags}


# ------------------------------------------------------------------ 自测入口
def _fingerprint(soup):
    """按文档顺序记录每个元素的 (应有标签名, 属性, 文本)。

    转换前后各取一次指纹，两边必须完全一致，才能同时证明三件事：
      1. 元素数量、顺序都没变（子节点结构没动）
      2. 每个元素的标签名正好是预期的那个（该转的转了，不该转的一个没动）
      3. 属性和文本逐个一致（style / class / id / 内容一个都没动）
    """
    out = []
    for tag in soup.find_all(True):
        attrs = {}
        for k, v in tag.attrs.items():
            attrs[k] = v if isinstance(v, str) else list(v)
        out.append((NAME_MAP.get(tag.name, tag.name), attrs, tag.get_text()))
    return out


def selftest(html_path=None):
    """自测：加载真实产物，统计并断言。返回各标签计数。"""
    html_path = Path(html_path) if html_path else HERE / 'wechat.html'

    if not html_path.exists():
        raise FileNotFoundError(f'找不到测试文件：{html_path}')

    raw = html_path.read_text(encoding='utf-8')
    soup = BeautifulSoup(raw, 'html.parser')

    before = _counts(soup)
    text_len_before = len(soup.get_text())
    total_tags_before = len(soup.find_all(True))
    preserve_before = {t: len(soup.find_all(t)) for t in PRESERVE_TAGS}
    fp_before = _fingerprint(soup)
    # 转换前就已经存在的 section / p：必须原样保留（不能被改、也不能丢）
    pre_sections = list(soup.find_all('section'))
    pre_ps = list(soup.find_all('p'))

    # ---- 执行转换 ----
    div_to_section(soup)

    after = _counts(soup)
    text_len_after = len(soup.get_text())
    total_tags_after = len(soup.find_all(True))
    preserve_after = {t: len(soup.find_all(t)) for t in PRESERVE_TAGS}
    fp_after = _fingerprint(soup)

    # ---- 报告 ----
    print(f'测试文件      : {html_path}')
    print(f'文件大小      : {len(raw)} 字符')
    print('-' * 56)
    print(f'  div          : {before["div"]:>6}  ->  {after["div"]:>6}')
    print(f'  figure       : {before["figure"]:>6}  ->  {after["figure"]:>6}')
    print(f'  figcaption   : {before["figcaption"]:>6}  ->  {after["figcaption"]:>6}')
    print(f'  section      : {before["section"]:>6}  ->  {after["section"]:>6}')
    print(f'  p            : {before["p"]:>6}  ->  {after["p"]:>6}')
    print(f'  标签总数     : {total_tags_before:>6}  ->  {total_tags_after:>6}')
    print(f'  文本长度     : {text_len_before:>6}  ->  {text_len_after:>6}')
    print('-' * 56)

    # ---- 断言 ----
    # 1) 会降级的标签必须清零
    assert after['div'] == 0, f'转换后仍有 {after["div"]} 个 div'
    assert after['figure'] == 0, f'转换后仍有 {after["figure"]} 个 figure'
    assert after['figcaption'] == 0, f'转换后仍有 {after["figcaption"]} 个 figcaption'
    assert '<div' not in soup.decode().lower(), '输出 HTML 里还残留 div'
    assert '<figure' not in soup.decode().lower(), '输出 HTML 里还残留 figure'
    assert '<figcaption' not in soup.decode().lower(), '输出 HTML 里还残留 figcaption'

    # 2) 计数增量对得上
    assert after['section'] == before['section'] + before['div'] + before['figure'], \
        'section 数量增量对不上'
    assert after['p'] == before['p'] + before['figcaption'], \
        'p 数量增量对不上'

    # 3) 内容一点没丢
    assert text_len_before == text_len_after, \
        f'文本长度变了：{text_len_before} -> {text_len_after}'
    assert total_tags_before == total_tags_after, '标签总数变了'

    # 4) 指纹一致 = 只改了标签名，属性 / 结构 / 内容全对
    assert fp_before == fp_after, '元素标签名 / 属性 / 内容与预期不符'

    # 5) 白名单稳定标签一个都没动
    for t in PRESERVE_TAGS:
        assert preserve_before[t] == preserve_after[t], \
            f'稳定标签 <{t}> 数量被改动：{preserve_before[t]} -> {preserve_after[t]}'

    # 6) 转换前就存在的 section / p：必须还是原样、且仍留在树上
    for old in pre_sections:
        assert old.name == 'section', '原有 <section> 被改动了'
        assert old in soup.find_all('section'), '原有 <section> 从树上丢了'
    for old in pre_ps:
        assert old.name == 'p', '原有 <p> 被改动了'
        assert old in soup.find_all('p'), '原有 <p> 从树上丢了'

    print('全部断言通过 ✓')
    print(f'  · div / figure / figcaption 转换后均为 0')
    print(f'  · 文本长度一致（{text_len_before} 字符，未丢内容）')
    print(f'  · {before["div"]} 个 div + {before["figure"]} 个 figure → section，'
          f'{before["figcaption"]} 个 figcaption → p')
    print(f'  · 全文档 {total_tags_before} 个元素逐个比对：标签名 / 属性 / 文本完全符合预期')
    print(f'  · {len(PRESERVE_TAGS)} 种白名单稳定标签数量全部未变')
    return before, after


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv:
        if len(argv) != 2:
            print('用法: python wecom_div_to_section.py [输入.html 输出.html]',
                  file=sys.stderr)
            return 2
        before, after = convert_file(argv[0], argv[1])
        print(f'转换完成: {argv[0]} -> {argv[1]}')
        for tag in ('div', 'figure', 'figcaption', 'section', 'p'):
            print(f'  {tag:<12}{before[tag]:>4} -> {after[tag]:>4}')
        ok = after['div'] == 0 and after['figure'] == 0 and after['figcaption'] == 0
        return 0 if ok else 1

    selftest()
    return 0


if __name__ == '__main__':
    sys.exit(main())
