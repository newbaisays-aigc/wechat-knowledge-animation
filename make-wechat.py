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
  8. 公众号专属适配：复制标签改成「长按复制」，流程提示改掉「点击/点一下」的说法，
     并在第一个提示词前加一条长按提示（Web 版保持原样，按钮仍然可点）
  9. 在正文顶部插入一条「公众号粘贴版」工具条（含一键复制 / 全选正文按钮）
     —— 工具条在 <article> 之外，复制时不会被带进正文

用法：
    python make-wechat.py                      # 本地相对路径，浏览器打开人工核对
    python make-wechat.py --base https://xxx   # 图片指向公网，可直接粘贴进公众号
"""
import argparse
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

from wecom_div_to_section import div_to_section
from wecom_style_fallback import apply_all as apply_style_fallback

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
    #    注意：article 背景必须留白（#ffffff），不能设 transparent。
    #    设成 transparent 时，浏览器复制会把「透明底下的实际底色」= body 的灰底
    #    #f3f5f2 写进剪贴板，传染给每一个透明的后代元素（实测 51 个 p 里有 30 个
    #    被染上灰底），粘贴到公众号后每段都出现灰色色块。
    art = soup.find('article')
    if art:
        art['style'] = merge_style(art.get('style', ''),
                                    'max-width:100%;margin:0;padding:0 4px;background:#ffffff')
    body = soup.find('body')
    if body:
        body['style'] = merge_style(body.get('style', ''), 'background:#ffffff')

    # 6b) 标记文章头部（品牌名 / 大标题 / 署名行）
    #     公众号的标题、作者是独立输入框，正文里再粘一遍是重复的。
    #     打上 data-wx-chrome 标记，工具条复制时会整块跳过。
    if art:
        for sel in ('.brand', 'h1', '.meta'):
            for el in art.select(sel):
                el['data-wx-chrome'] = '1'

    # 7) 每个元素统一 border-box
    for el in soup.find_all(True):
        cur = el.get('style', '')
        if 'box-sizing' not in cur:
            el['style'] = merge_style(cur, 'box-sizing:border-box')


# ---------------------------------------------------------------- wechat-only adaptation
# 公众号里没有 JS：绿色「复制」标签变成不可点的静态文字，
# 而且原文案（如「点一下就能复制」）在公众号里是假的，必须改掉。
# 这些改法只作用于公众号版，index.html（Web 版）保持原样、按钮照常可点。

WX_HINT_HTML = '''
<div class="wx-hint" style="box-sizing:border-box;margin:16px 0 0;padding:13px 15px;border-radius:8px;
  background:#eef7f2;color:#284b3e;font-size:13.5px;line-height:1.8;">
  <strong style="font-weight:700;">复制小提示：</strong>公众号里没有可点的按钮，长按下面的提示词文字就能选中复制，粘到 WorkBuddy 的对话框直接用。
</div>
'''

FLOW_TIP_WECHAT = '完整流程一共 3 步。文中的绿色标签，长按就能选中复制。'


def adapt_for_wechat(soup):
    """把「点击复制」的说法改成「长按复制」，并补一条长按提示。"""
    # 1) 顶部流程提示：锚点不能跳、按钮不能点，两句话都得改
    tip = soup.select_one('.flow-tip')
    if tip is not None:
        tip.string = FLOW_TIP_WECHAT

    # 2) 提示词块里的绿标（display:block，在文字上方）→「长按下方文字复制」
    for tag in soup.select('.prompt .copy-tag'):
        tag.string = '长按下方文字复制'

    # 3) 网址那处（绿标在「打开 WorkBuddy 官网」后面，网址在下一行）
    for tag in soup.select('.site .copy-tag'):
        tag.string = '长按下方网址复制'

    # 4) 行内那处「复制这句话」（跟在高亮引语后面）
    for tag in soup.select('p > .copy-tag'):
        if not tag.find_parent(class_='prompt') and not tag.find_parent(class_='site'):
            tag.string = '长按复制'

    # 4b) 硬编码的「复制地址 + 这句话」按钮（index.html 里直接写的 button，
    #     不是 JS 生成的，rewrite() 已把它降级成 span，同样点不动）
    for btn in soup.select('.copy-btn'):
        if btn.get_text(strip=True):
            btn.string = '长按上面两行，分两次复制'

    # 5) 第一个提示词块前面插一条长按提示
    first_prompt = soup.select_one('.prompt')
    if first_prompt is not None:
        hint = BeautifulSoup(WX_HINT_HTML, 'lxml').find('div')
        if hint is not None:
            first_prompt.insert_before(hint)


# ---------------------------------------------------------------- toolbar
# 顶部工具条：在 <article> 之外，复制时不会被带进正文。
# 复制按钮走 Range + execCommand('copy')，保留富文本格式和图片地址；
# 同时监听全局 copy 事件，防止用户按 Ctrl+A 时把工具条本身复制进去。
TOOLBAR_HTML = '''
<div id="wx-toolbar" style="position:sticky;top:0;z-index:9999;box-sizing:border-box;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 16px;background:#ffffff;border-bottom:1px solid #e3e9e4;box-shadow:0 2px 10px rgba(29,41,37,.05);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;font-size:13px;line-height:1.5;color:#1d2925;">
  <span style="display:inline-flex;align-items:center;gap:6px;font-weight:700;color:#2f7058;white-space:nowrap;">📋 公众号粘贴版</span>
  <button id="wx-copy" type="button" style="box-sizing:border-box;appearance:none;border:0;border-radius:7px;padding:8px 14px;background:#2f7058;color:#ffffff;font-family:inherit;font-size:13px;font-weight:700;line-height:1.5;cursor:pointer;">复制全文</button>
  <button id="wx-select" type="button" style="box-sizing:border-box;appearance:none;border:1px solid #b9d4c8;border-radius:7px;padding:7px 13px;background:#f3faf6;color:#2f7058;font-family:inherit;font-size:13px;font-weight:700;line-height:1.5;cursor:pointer;">全选正文</button>
  <span style="color:#6b7a74;font-size:12px;">复制后到公众号编辑器里直接粘贴，图片会自动上传</span>
</div>
'''

TOOLBAR_SCRIPT = '''
<script>
(function () {
  var TOOLBAR = document.getElementById('wx-toolbar');
  var ART = document.querySelector('article');
  if (!TOOLBAR || !ART) { return; }

  var locked = false;

  function toast(msg) {
    var t = document.getElementById('wx-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'wx-toast';
      t.setAttribute('style', 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);' +
        'z-index:10000;box-sizing:border-box;padding:10px 18px;border-radius:8px;' +
        'background:rgba(24,60,48,.94);color:#ffffff;font-family:-apple-system,BlinkMacSystemFont,' +
        "'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;font-size:13px;font-weight:600;" +
        'box-shadow:0 6px 24px rgba(0,0,0,.18);opacity:0;transition:opacity .2s;pointer-events:none;');
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.style.opacity = '0'; }, 2200);
  }

  // 只取正文：跳过 data-wx-chrome 标记的头部（品牌名 / 大标题 / 署名行），
  // 公众号的标题和作者是独立输入框，粘进正文会重复。
  function bodyNodes() {
    var out = [];
    for (var i = 0; i < ART.childNodes.length; i++) {
      var n = ART.childNodes[i];
      if (n.nodeType === 1 && n.getAttribute && n.getAttribute('data-wx-chrome')) { continue; }
      if (n.nodeType === 3 && !String(n.nodeValue || '').trim()) { continue; }
      out.push(n);
    }
    return out;
  }

  function selectArticle() {
    var r = document.createRange();
    var nodes = bodyNodes();
    if (nodes.length) {
      r.setStartBefore(nodes[0]);
      r.setEndAfter(nodes[nodes.length - 1]);
    } else {
      r.selectNodeContents(ART);
    }
    var s = window.getSelection();
    s.removeAllRanges();
    s.addRange(r);
    return r;
  }

  // 供 Ctrl+A 兜底用：正文 HTML（已去掉头部）
  function bodyHTML() {
    var nodes = bodyNodes();
    var out = '';
    for (var i = 0; i < nodes.length; i++) { out += nodes[i].outerHTML || ''; }
    return out;
  }

  function bodyText() {
    var nodes = bodyNodes();
    var out = '';
    for (var i = 0; i < nodes.length; i++) {
      out += (nodes[i].innerText !== undefined ? nodes[i].innerText : nodes[i].textContent || '');
      out += String.fromCharCode(10);   // 用 fromCharCode(10) 而不是换行转义：后者在 Python 三引号字符串里会被解析成真实换行，把 JS 字面量截断
    }
    return out;
  }

  // 主按钮：直接把正文富文本写进剪贴板（含图片地址），粘贴到公众号即带样式
  document.getElementById('wx-copy').addEventListener('click', function () {
    selectArticle();
    var ok = false;
    locked = true;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    locked = false;
    if (ok) {
      toast('全文已复制，去公众号编辑器粘贴吧');
    } else {
      window.getSelection().removeAllRanges();
      selectArticle();
      toast('已全选正文，按 Ctrl+C / ⌘+C 复制');
    }
  });

  // 备用按钮：只做高亮选中，用户自己按 Ctrl+C
  document.getElementById('wx-select').addEventListener('click', function () {
    selectArticle();
    toast('已全选正文，按 Ctrl+C / ⌘+C 复制');
  });

  // 兜底：用户按 Ctrl+A 时，选区会包含工具条 —— 拦截 copy 事件，
  // 把剪贴板内容改写为纯正文，工具条不会混进公众号文章里
  document.addEventListener('copy', function (e) {
    if (locked) { return; }
    var s = window.getSelection();
    if (!s || !s.rangeCount) { return; }
    var range = s.getRangeAt(0);
    var inside = TOOLBAR.contains(range.commonAncestorContainer);
    var crosses = false;
    try { crosses = range.intersectsNode(TOOLBAR); } catch (err) { }
    if (!inside && !crosses) { return; }
    var dt = e.clipboardData;
    if (!dt) { return; }
    dt.setData('text/html', bodyHTML());
    dt.setData('text/plain', bodyText());
    e.preventDefault();
  });
})();
</script>
'''


def inject_toolbar(soup):
    """把工具条插到 <article> 之前，脚本追加到 body 末尾。"""
    body = soup.body
    if body is None:
        return
    frag = BeautifulSoup(TOOLBAR_HTML, 'lxml')
    toolbar = frag.find(id='wx-toolbar')
    if toolbar is not None:
        body.insert(0, toolbar)
    script = BeautifulSoup(TOOLBAR_SCRIPT, 'lxml').find('script')
    if script is not None:
        body.append(script)


def apply_wecom_compat(soup):
    """把正文降级成公众号编辑器能稳定渲染的内联样式。

    公众号新版编辑器基于 ProseMirror，白名单里没有 div / figure / figcaption，
    这些标签被降级时**连同身上的内联样式一起丢失** —— 于是所有靠容器承载
    样式的卡片、提示框、网址卡、图注全部塌成连续文本。

    这里做四件事：
      1. div → section，figure → section，figcaption → p（白名单内的块级替代）
      2. flex 布局降级为 block 流 + margin 间距（公众号不支持 flex/grid）
      3. linear-gradient / box-shadow 降级为实色 / 边框
      4. 清掉 absolute 定位等不支持的属性，编号徽章改 inline-block

    必须在 inject_toolbar 之后调用：工具条与提示条是运行时插入的，
    提前转换会漏掉。
    """
    # 工具条要保持横排（按钮并排），不能被 flex 降级拆成竖排。
    # 先把它挪出降级范围，处理完再放回去。
    toolbar = soup.find(id='wx-toolbar')
    parked = None
    if toolbar is not None:
        parked = toolbar.extract()

    div_to_section(soup)
    apply_style_fallback(soup)
    fix_fit_list(soup)

    if parked is not None:
        body = soup.body
        if body is not None:
            body.insert(0, parked)


def fix_fit_list(soup):
    """收拾 ul.fit 列表的冗余缩进。

    列表圆点原本靠 `li:before` 伪元素画（absolute 定位），降级后改成
    inline-block 的真实圆点 span 参与正常流。此时：
      - ul 上为旧 absolute 圆点预留的 padding-left: 22px 成了多余缩进
      - li 上残留 position: relative（已无 absolute 子元素依赖它）
      - li 的 padding 被写了两遍（padding-left 和 padding，后者覆盖前者）
    """
    for ul in soup.select('ul.fit'):
        style = ul.get('style', '')
        # 保留 list-style: none（我们要自己的绿色圆点，不要原生 disc 叠成双点）
        style = re.sub(r'padding-left:\s*22px;?\s*', '', style)
        style = re.sub(r'padding-left:\s*22px', 'padding-left: 0', style)
        ul['style'] = style

    for li in soup.select('ul.fit li'):
        style = li.get('style', '')
        style = re.sub(r'position:\s*relative;?\s*', '', style)
        # 清掉重复的 padding 声明，保留最后一条
        pads = re.findall(r'padding(?:-left)?:\s*[^;]+', style)
        if len(pads) > 1:
            style = re.sub(r'padding(?:-left)?:\s*[^;]+;?\s*', '', style)
            style = merge_style(style, pads[-1].strip())
        li['style'] = style


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='', help='图片公网前缀，如 https://xxx')
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()

    html = SRC.read_text(encoding='utf-8')
    soup = BeautifulSoup(html, 'lxml')
    inline_styles(soup)
    rewrite(soup)
    adapt_for_wechat(soup)
    inject_toolbar(soup)

    # ---- 公众号兼容性降级（必须在 inject_toolbar 之后）----
    # 顺序很重要：工具条和「复制小提示」条都是运行时插入的 div，
    # 放在 inject_toolbar 之前转换会漏掉它们。
    apply_wecom_compat(soup)

    if args.base:
        base = args.base.rstrip('/') + '/'
        # 防呆：--base 是「仓库根 URL」，脚本会自动在后面拼 src 里自带的 assets/。
        # 如果调用方习惯性地把 /assets 也写进 base，路径就会变成 assets/assets/xxx.png
        # ——线上全部 404，而且肉眼看源码很难发现。这里直接把它抹掉。
        if base.rstrip('/').endswith('/assets'):
            base = base[:base.rstrip('/').rfind('/') + 1]
            print('note: --base 末尾的 /assets 已自动去掉（避免路径变成 assets/assets/）')
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and not src.startswith(('http', 'data:')):
                new_src = base + src.lstrip('./')
                # 双保险：拼接后若出现 assets/assets/ 之类重复段，直接去掉重复的那段
                while '/assets/assets/' in new_src:
                    new_src = new_src.replace('/assets/assets/', '/assets/')
                img['src'] = new_src

    # 自检：图片路径里不能有重复目录段，且本地 assets/ 下必须真实存在该文件
    bad = []
    missing = []
    for img in soup.find_all('img'):
        src = img.get('src', '')
        if '/assets/assets/' in src or src.endswith('/assets/'):
            bad.append(src)
            continue
        # 剥掉查询串后，取 assets/ 之后的相对路径去本地核对
        clean = src.split('?')[0].split('#')[0]
        if '/assets/' in clean:
            rel = clean.split('/assets/', 1)[1]
            if not (SRC.parent / 'assets' / rel).exists():
                missing.append(src)
    if bad:
        print('ERROR: 图片路径异常（目录段重复）→ %s' % bad[:3])
        return 1
    if missing:
        print('ERROR: 以下图片在本地 assets/ 下不存在 → %s' % missing[:3])
        return 1
    print('自检通过 ✓ 图片路径无重复段，且 %d 个本地文件全部存在'
          % len(soup.find_all('img')))

    out = soup.prettify()
    Path(args.out).write_text(out, encoding='utf-8')
    print(f'written: {args.out}  ({len(out)} bytes)')


if __name__ == '__main__':
    sys.exit(main())
