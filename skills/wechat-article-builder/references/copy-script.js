/*
 * 微信公众号复制脚本（可直接粘贴进文章 HTML 的 <script> 标签）
 *
 * 功能：点击按钮后，将 .article-container 内容连同样式复制到剪贴板，
 * 粘贴到公众号编辑器后样式完整保留（背景色、圆角、边框、表格、强调色）。
 *
 * ============================ 关键踩坑知识 ============================
 * 【第一轮 · 2026-08 实测】
 * 1. 公众号编辑器只认内联 style，不认 CSS class → 必须 getComputedStyle 内联化
 * 2. 公众号编辑器会剥离 div 的 background-color 和 border，但保留 section 的
 *    → 第一步必须把 div 转成 section
 * 3. border 简写属性 getPropertyValue 可能返回空 → 必须采集 longhand 属性
 *
 * 【第二轮 · 2026-11 实测（这轮推翻了第 2 条的一半）】
 * 4. **section 也不形成可靠的段落边界** —— 连续 section 会被公众号并进同一段，
 *    section 里直接放 <img> 时公众号还会把 img 的 alt 文本吐进正文，
 *    和后面的图注连成一段（实测截图确认）。
 *    → **最终形态：把一切视觉块压平成顶层 <p>**，<p> 是公众号唯一可靠的段落边界。
 * 5. **<p> 里不能嵌 <p>**（浏览器会自动拆散嵌套 p）→ 图片独占 <p><img></p>，
 *    图注是紧跟其后的独立 <p>。
 * 6. **font-family: inherit 会让整条 style 失效**（元素连底色一起丢）
 *    → 内联化时遇到 inherit/initial 一律丢弃，改用具体字体栈。
 * 7. **border 的 longhand 必须排在 border 简写之后**，否则 border:0 会覆盖 border-left，
 *    绿色左边框直接消失。
 * 8. **图片不能带 loading="lazy"** → 视口外的图根本不发起请求（实测裂图 5 张）。
 * 9. **灰底传染**：容器 transparent 会把 body 灰底一起复制 → 正文容器固定 #ffffff。
 *
 * 顶层最终只允许：<p> / <h1-h6> / <ul> / <ol> / <blockquote> / <table> / <hr>
 *
 * HTML 要求：
 *   - 文章容器：<div class="article-container">...</div>
 *   - 按钮：<button id="copy-btn" onclick="copyArticle()">📋复制全文到公众号</button>
 */

function copyArticle() {
  var source = document.querySelector('.article-container');
  var btn = document.getElementById('copy-btn');
  if (!source) { return; }

  // 克隆源内容
  var clone = source.cloneNode(true);

  // === 第一步：内联化所有样式 ===
  var sourceEls = [source].concat(Array.prototype.slice.call(source.querySelectorAll('*')));
  var cloneEls = [clone].concat(Array.prototype.slice.call(clone.querySelectorAll('*')));

  var props = [
    'color', 'background-color',
    'font-size', 'font-weight', 'font-family', 'line-height',
    'text-align', 'text-indent', 'letter-spacing',
    'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
    'margin', 'margin-top', 'margin-bottom', 'margin-left', 'margin-right',
    'border-top', 'border-bottom', 'border-left', 'border-right',
    'border-top-width', 'border-top-style', 'border-top-color',
    'border-bottom-width', 'border-bottom-style', 'border-bottom-color',
    'border-left-width', 'border-left-style', 'border-left-color',
    'border-right-width', 'border-right-style', 'border-right-color',
    'border-radius', 'border-collapse', 'border-spacing',
    'display', 'width', 'max-width', 'box-sizing',
    'vertical-align', 'text-decoration', 'white-space'
  ];
  // 注意：不采集 'background' 和 'border' 简写。
  // background 简写会把 background-color 覆盖成透明（底色全丢），
  // 且公众号本身不认 background 简写；
  // border 简写会把 border-left 覆盖成 0（绿色左边框消失）。

  cloneEls.forEach(function(el, i) {
    var computed = window.getComputedStyle(sourceEls[i]);
    props.forEach(function(prop) {
      var val = computed.getPropertyValue(prop);
      // inherit/initial 会让整条 style 失效，丢弃（踩坑 6）
      if (!val || val === 'initial' || val === 'normal' || val === 'inherit') return;
      el.style.setProperty(prop, val);
    });
  });

  // === 第二步：div / figure 转 section，figcaption 转 p（第一轮规则，保留做保底）===
  var allDivs = clone.querySelectorAll('div');
  for (var d = allDivs.length - 1; d >= 0; d--) {
    var div = allDivs[d];
    var sec = document.createElement('section');
    while (div.firstChild) { sec.appendChild(div.firstChild); }
    for (var a = 0; a < div.attributes.length; a++) {
      sec.setAttribute(div.attributes[a].name, div.attributes[a].value);
    }
    div.parentNode.replaceChild(sec, div);
  }
  var figs = clone.querySelectorAll('figure');
  for (var f = figs.length - 1; f >= 0; f--) {
    var fig = figs[f];
    var fsec = document.createElement('section');
    while (fig.firstChild) { fsec.appendChild(fig.firstChild); }
    for (var fa = 0; fa < fig.attributes.length; fa++) {
      fsec.setAttribute(fig.attributes[fa].name, fig.attributes[fa].value);
    }
    fig.parentNode.replaceChild(fsec, fig);
  }
  var caps = clone.querySelectorAll('figcaption');
  for (var c = caps.length - 1; c >= 0; c--) {
    var cap = caps[c];
    var p = document.createElement('p');
    while (cap.firstChild) { p.appendChild(cap.firstChild); }
    for (var pa = 0; pa < cap.attributes.length; pa++) {
      p.setAttribute(cap.attributes[pa].name, cap.attributes[pa].value);
    }
    cap.parentNode.replaceChild(p, cap);
  }

  // === 第三步：压平成顶层 <p>（第二轮核心，踩坑 4/5/7）===
  flattenToTopLevelParagraphs(clone);

  // === 第四步：图片去 lazy + 独占段落（踩坑 8）===
  wxIsolateImages(clone);

  // === 第五步：自己序列化 HTML 写进剪贴板 ===
  // 为什么不用 execCommand('copy') 自动序列化：
  // Chrome 复制富文本时会把 background-color 折叠成 background 简写
  // （实测：<span style="background-color: rgb(...)"> 复制出来变成 style="background: rgb(...)"），
  // 而公众号不认 background 简写 → 底色会整块丢掉。
  // 自己序列化可以精确控制输出的 style 字符串。
  var html = wxSerializeChildren(clone);
  var plain = (clone.textContent || '').replace(/\n{3,}/g, '\n\n').trim();

  wxWriteClipboard(html, plain).then(function(ok) {
    if (ok) {
      btn.innerHTML = '<span class="btn-icon">✅</span>已复制，去公众号粘贴即可';
      btn.classList.add('copied');
    } else {
      btn.innerHTML = '<span class="btn-icon">⚠️</span>复制失败，请手动选中复制';
    }
    setTimeout(function() {
      btn.innerHTML = '<span class="btn-icon">📋</span>复制全文到公众号';
      btn.classList.remove('copied');
    }, 3000);
  });
}

/* ------------------------------------------------------------------ */
/*  序列化 + 写剪贴板                                                 */
/* ------------------------------------------------------------------ */

function wxEscapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
function wxEscapeAttr(s) {
  return wxEscapeHtml(s).replace(/"/g, '&quot;');
}

/* 用 style.cssText（保留 background-color 这类 longhand），而不是 computed 简写 */
function wxSerialize(node) {
  if (node.nodeType === 3) { return wxEscapeHtml(node.nodeValue); }
  if (node.nodeType !== 1) { return ''; }
  var tag = node.tagName.toLowerCase();
  if (tag === 'br') { return '<br/>'; }
  var style = wxBuildStyle(node);
  if (tag === 'img') {
    var src = node.getAttribute('src') || '';
    var alt = node.getAttribute('alt') || '';
    return '<img src="' + wxEscapeAttr(src) + '" alt="' + wxEscapeAttr(alt) + '" style="' + wxEscapeAttr(style) + '"/>';
  }
  var attrs = '';
  for (var i = 0; i < node.attributes.length; i++) {
    var a = node.attributes[i];
    if (a.name === 'style') { continue; }
    attrs += ' ' + a.name + '="' + wxEscapeAttr(a.value) + '"';
  }
  var inner = '';
  for (var c = 0; c < node.childNodes.length; c++) {
    inner += wxSerialize(node.childNodes[c]);
  }
  return '<' + tag + ' style="' + wxEscapeAttr(style) + '"' + attrs + '>' + inner + '</' + tag + '>';
}

/* 取 cssText 里的某个属性值（rgb() 里没有分号，用 [^;]* 安全） */
function wxGetProp(css, name) {
  var m = css.match(new RegExp('(?:^|;)\\s*' + name + ':\\s*([^;]*)'));
  return m ? m[1].trim() : '';
}

/* 按顶层空格拆值，跳过括号内部（rgb(1, 2, 3) 不能被拆开） */
function wxSplitVals(s) {
  var out = [], cur = '', depth = 0;
  for (var i = 0; i < s.length; i++) {
    var ch = s.charAt(i);
    if (ch === '(') { depth++; } else if (ch === ')') { depth--; }
    if (/\s/.test(ch) && depth === 0) {
      if (cur) { out.push(cur); cur = ''; }
    } else { cur += ch; }
  }
  if (cur) { out.push(cur); }
  return out;
}

/* CSS 边框取值规则：1 值=全同，2 值=上下/左右，3 值=上/左右/下，4 值=上右下左 */
function wxPick(vals, idx) {
  var n = vals.length;
  if (n === 1) { return vals[0]; }
  if (n === 2) { return (idx === 0 || idx === 2) ? vals[0] : vals[1]; }
  if (n === 3) { return idx === 0 ? vals[0] : (idx === 1 ? vals[1] : vals[2]); }
  return vals[idx];
}

/* 把 cssText 里的 border-width/style/color 三件套还原成四方向简写。
   Chrome 会把四方向相同的边框折叠回三件套，而公众号只认 border-left 这类简写。 */
function wxBuildStyle(el) {
  var css = el.style ? el.style.cssText : '';
  if (!css) { return ''; }
  var bw = wxGetProp(css, 'border-width');
  var bs = wxGetProp(css, 'border-style');
  var bc = wxGetProp(css, 'border-color');
  if (!bw || !bs || !bc) { return css; }

  var wv = wxSplitVals(bw), sv = wxSplitVals(bs), cv = wxSplitVals(bc);
  if (!sv.length) { return css; }

  var dirs = ['top', 'right', 'bottom', 'left'];
  var pieces = [];
  dirs.forEach(function(dir, i) {
    var st = wxPick(sv, i);
    if (!st || st === 'none' || st === 'hidden') { return; }
    pieces.push('border-' + dir + ': ' + wxPick(wv, i) + ' ' + st + ' ' + wxPick(cv, i));
  });

  // 从 css 里摘掉三件套，再插回四方向简写
  var out = css
    .replace(/(?:^|;)\s*border-width:\s*[^;]*/i, '')
    .replace(/(?:^|;)\s*border-style:\s*[^;]*/i, '')
    .replace(/(?:^|;)\s*border-color:\s*[^;]*/i, '');
  out = out.replace(/;\s*;/g, ';').replace(/^\s*;\s*/, '').trim();
  if (pieces.length) {
    out = pieces.join('; ') + (out ? '; ' + out : '');
  }
  return out;
}

/* 只输出根节点的子节点（根容器本身是 div，公众号不认） */
function wxSerializeChildren(root) {
  var out = '';
  for (var i = 0; i < root.childNodes.length; i++) {
    out += wxSerialize(root.childNodes[i]);
  }
  return out;
}

/* 优先用 ClipboardItem 写 text/html；不可用时回退 execCommand */
function wxWriteClipboard(html, plain) {
  if (navigator.clipboard && window.ClipboardItem && window.isSecureContext) {
    try {
      var htmlBlob = new Blob([html], { type: 'text/html' });
      var textBlob = new Blob([plain], { type: 'text/plain' });
      return navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })])
        .then(function() { return true; })
        .catch(function() { return wxWriteClipboardFallback(html); });
    } catch (e) {
      return wxWriteClipboardFallback(html);
    }
  }
  return wxWriteClipboardFallback(html);
}

/* 兜底：老路子，把 HTML 塞进离屏容器再 execCommand 复制 */
function wxWriteClipboardFallback(html) {
  try {
    var tempDiv = document.createElement('div');
    tempDiv.style.position = 'fixed';
    tempDiv.style.left = '-9999px';
    tempDiv.style.top = '0';
    tempDiv.style.width = '680px';
    tempDiv.style.background = '#ffffff';
    tempDiv.innerHTML = html;
    document.body.appendChild(tempDiv);
    var range = document.createRange();
    range.selectNodeContents(tempDiv);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand('copy');
    selection.removeAllRanges();
    document.body.removeChild(tempDiv);
    return Promise.resolve(true);
  } catch (e) {
    return Promise.resolve(false);
  }
}

/* ------------------------------------------------------------------ */
/*  压平工具                                                          */
/* ------------------------------------------------------------------ */

var CONTAINER_TAGS = {
  DIV:1, SECTION:1, FIGURE:1, HEADER:1, FOOTER:1,
  MAIN:1, ARTICLE:1, ASIDE:1, NAV:1, FORM:1
};
var TOP_WHITELIST = {
  P:1, H1:1, H2:1, H3:1, H4:1, H5:1, H6:1,
  UL:1, OL:1, BLOCKQUOTE:1, TABLE:1, HR:1
};

function wxIsContainer(el) {
  return el.nodeType === 1 && CONTAINER_TAGS[el.tagName] === 1;
}
function wxIsBlock(el) {
  if (el.nodeType !== 1) return false;
  var t = el.tagName;
  return TOP_WHITELIST[t] === 1 || t === 'PRE';
}
function wxIsTopLevel(el) {
  return el.nodeType === 1 && TOP_WHITELIST[el.tagName] === 1;
}

/* 容器样式迁移到第一个块级子节点，否则底色/边框会随容器一起消失 */
function wxMigrateStyle(container, child) {
  if (!child || !container.style) return;
  var move = [
    'background-color',
    'border-top', 'border-bottom', 'border-left', 'border-right',
    'border-top-width', 'border-top-style',
    'border-top-color', 'border-bottom-width', 'border-bottom-style',
    'border-bottom-color', 'border-left-width', 'border-left-style',
    'border-left-color', 'border-right-width', 'border-right-style',
    'border-right-color', 'border-radius', 'padding', 'padding-top',
    'padding-right', 'padding-bottom', 'padding-left', 'margin',
    'margin-top', 'margin-bottom', 'margin-left', 'margin-right',
    'text-align', 'line-height'
  ];
  move.forEach(function(p) {
    var v = container.style.getPropertyValue(p);
    if (v) child.style.setProperty(p, v);
  });
  // 有底色时子段落要有内边距，否则文字贴边
  var bg = container.style.getPropertyValue('background-color');
  if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' && child.tagName === 'P') {
    if (!child.style.getPropertyValue('padding-top')) child.style.setProperty('padding-top', '16px');
    if (!child.style.getPropertyValue('padding-bottom')) child.style.setProperty('padding-bottom', '16px');
  }
}

/* 递归摊平容器 */
function wxFlatten(node) {
  var kids = Array.prototype.slice.call(node.children);
  for (var i = 0; i < kids.length; i++) {
    var k = kids[i];
    if (wxIsContainer(k)) {
      wxFlatten(k);
      var target = null;
      for (var j = 0; j < k.children.length; j++) {
        if (wxIsBlock(k.children[j])) { target = k.children[j]; break; }
      }
      if (target) wxMigrateStyle(k, target);
      var frag = document.createDocumentFragment();
      while (k.firstChild) { frag.appendChild(k.firstChild); }
      if (k.parentNode) k.parentNode.replaceChild(frag, k);
    } else {
      wxFlatten(k);
    }
  }
}

/* 顶层归一：只允许白名单元素，裸文本/裸元素一律包进 <p> */
function wxNormalizeTop(root) {
  var nodes = Array.prototype.slice.call(root.childNodes);
  nodes.forEach(function(n) {
    if (n.nodeType === 3) {
      if (!n.nodeValue || !n.nodeValue.trim()) { root.removeChild(n); return; }
      var tp = document.createElement('p');
      n.parentNode.insertBefore(tp, n);
      tp.appendChild(n);
      return;
    }
    if (n.nodeType !== 1) { return; }
    if (wxIsTopLevel(n)) { return; }
    var np = document.createElement('p');
    n.parentNode.insertBefore(np, n);
    np.appendChild(n);
  });
}

/* 图片独占段落 + 去掉 lazy */
function wxIsolateImages(root) {
  var imgs = Array.prototype.slice.call(root.querySelectorAll('img'));
  imgs.forEach(function(im) {
    im.removeAttribute('loading');
    im.removeAttribute('decoding');
    var parent = im.parentNode;
    if (parent && parent.tagName === 'P') {
      var others = Array.prototype.slice.call(parent.childNodes).filter(function(n) {
        if (n === im) return false;
        if (n.nodeType === 3) return !!n.nodeValue.trim();
        return true;
      });
      if (others.length === 0) return;           // 已经独占
      var np = document.createElement('p');      // 拆出来单独成段
      np.style.cssText = parent.style.cssText;
      parent.parentNode.insertBefore(np, parent);
      parent.removeChild(im);
      np.appendChild(im);
    } else {
      var np2 = document.createElement('p');     // 裸图包一层
      im.parentNode.insertBefore(np2, im);
      np2.appendChild(im);
    }
  });
}

/* 对外暴露：把任意容器压平成公众号可用的顶层段落结构 */
function flattenToTopLevelParagraphs(root) {
  wxFlatten(root);
  wxNormalizeTop(root);
  wxIsolateImages(root);
}
