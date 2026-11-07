// 公众号沙盒验收器（可复用）
//
// 用途：模拟公众号编辑器的清洗规则，把剪贴板 HTML 渲染出来，并量化「格式保留度」。
// 用法：node _sandbox.js [wechat.html路径]
//
// 依据（md2wechat 官方 HTML 规范 + feishu2wx 社区保守基线）：
//   稳定依赖标签：p span strong em ul ol li a img section blockquote h1-h6 table hr sup sub u pre code br
//   会降级：figure figcaption div
//   不支持：script style iframe video
//   样式：class/id/data-* 被清除；display:flex/grid 无效；只保留有限内联样式子集
const { chromium } = require('D:/tools/node/workspace/node_modules/playwright-core');
const path = require('path');
const fs = require('fs');

const EXEC = 'D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe';
const TARGET = process.argv[2] || 'D:/WorkBuddy/Claw/wechat-knowledge-animation/wechat.html';

async function readClipboard(page) {
  await page.click('#wx-copy');
  await page.waitForTimeout(300);
  return page.evaluate(async () => {
    const res = await navigator.clipboard.read();
    for (const it of res) for (const t of it.types) {
      if (t === 'text/html') return await (await it.getType(t)).text();
    }
    return '';
  });
}

async function clean(html) {
  const b = await chromium.launch({ executablePath: EXEC });
  const p = await b.newPage();
  const out = await p.evaluate((html) => {
    const doc = new DOMParser().parseFromString('<div id="root">' + html + '</div>', 'text/html');
    const root = doc.getElementById('root');

    ['script','style','iframe','video','object','embed','form','input','button','select','textarea','noscript'].forEach(t => {
      root.querySelectorAll(t).forEach(el => el.remove());
    });

    const DOWNGRADE = { figure: 'section', figcaption: 'p', div: 'section' };
    for (const [from, to] of Object.entries(DOWNGRADE)) {
      root.querySelectorAll(from).forEach(el => {
        const n = doc.createElement(to);
        for (const a of Array.from(el.attributes)) n.setAttribute(a.name, a.value);
        while (el.firstChild) n.appendChild(el.firstChild);
        el.replaceWith(n);
      });
    }

    root.querySelectorAll('*').forEach(el => {
      el.removeAttribute('class');
      el.removeAttribute('id');
      Array.from(el.attributes).forEach(a => { if (a.name.startsWith('data-')) el.removeAttribute(a.name); });
    });

    const ALLOWED = new Set([
      'color','background-color','font-size','font-weight','font-style','line-height',
      'text-align','text-decoration','text-indent','margin','margin-top','margin-right',
      'margin-bottom','margin-left','padding','padding-top','padding-right','padding-bottom',
      'padding-left','border','border-top','border-right','border-bottom','border-left',
      'border-color','border-style','border-width','border-radius','display','width','max-width',
      'height','min-height','vertical-align','opacity','letter-spacing','word-break',
      'word-wrap','white-space','overflow-wrap','float','clear','list-style'
    ]);
    root.querySelectorAll('*').forEach(el => {
      const st = el.getAttribute('style');
      if (!st) return;
      const kept = st.split(';').map(s => s.trim()).filter(Boolean).filter(decl => {
        const prop = decl.split(':')[0].trim().toLowerCase();
        if (!ALLOWED.has(prop)) return false;
        if (prop === 'display') {
          const v = decl.split(':')[1].trim().toLowerCase();
          if (['flex','grid','inline-flex','inline-grid'].includes(v)) return false;
        }
        return true;
      });
      if (kept.length) el.setAttribute('style', kept.join('; '));
      else el.removeAttribute('style');
    });

    const ALLOWED_TAGS = new Set([
      'p','span','strong','em','ul','ol','li','a','img','section','blockquote',
      'h1','h2','h3','h4','h5','h6','table','thead','tbody','tr','th','td',
      'hr','sup','sub','u','pre','code','br','font','center','small','big','cite','q','s','strike','del','ins','mark','time','abbr','address','article','aside','nav'
    ]);
    let guard = 0;
    while (guard++ < 50) {
      let changed = false;
      root.querySelectorAll('*').forEach(el => {
        if (!ALLOWED_TAGS.has(el.tagName.toLowerCase())) {
          const frag = doc.createDocumentFragment();
          while (el.firstChild) frag.appendChild(el.firstChild);
          el.replaceWith(frag);
          changed = true;
        }
      });
      if (!changed) break;
    }
    return root.innerHTML;
  }, html);
  await b.close();
  return out;
}

(async () => {
  const b = await chromium.launch({ executablePath: EXEC });
  const ctx = await b.newContext({ permissions: ['clipboard-read','clipboard-write'], viewport: { width: 677, height: 1600 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  await page.goto('file:///' + path.resolve(TARGET).replace(/\\/g,'/'), { waitUntil: 'load' });
  const html = await readClipboard(page);
  await b.close();

  // 剪贴板层指标
  const clip = {
    div: (html.match(/<div\b/g)||[]).length,
    section: (html.match(/<section\b/g)||[]).length,
    figure: (html.match(/<figure\b/g)||[]).length,
    figcaption: (html.match(/<figcaption\b/g)||[]).length,
    flex: (html.match(/display:\s*flex/g)||[]).length,
    gradient: (html.match(/linear-gradient/g)||[]).length,
    shadow: (html.match(/box-shadow/g)||[]).length,
    absolute: (html.match(/position:\s*absolute/g)||[]).length,
    grayBg: (html.match(/243,\s*245,\s*242/g)||[]).length,
    imgs: (html.match(/<img\b/g)||[]).length,
    cdnImgs: (html.match(/cdn\.jsdelivr\.net/g)||[]).length,
  };

  const cleaned = await clean(html);
  fs.writeFileSync('D:/WorkBuddy/Claw/wechat-knowledge-animation/_sandbox.html',
    `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body{margin:0;background:#fff;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#1d2925}
      .wx{padding:16px 14px}
      img{max-width:100%;height:auto;display:block}
      p{margin:0 0 18px;line-height:1.9}
      li{margin:8px 0}
    </style></head><body><div class="wx">${cleaned}</div></body></html>`, 'utf8');

  const b2 = await chromium.launch({ executablePath: EXEC });
  const p2 = await b2.newPage();
  await p2.setViewportSize({ width: 677, height: 1600 });
  await p2.goto('file:///D:/WorkBuddy/Claw/wechat-knowledge-animation/_sandbox.html', { waitUntil: 'load' });
  await p2.waitForTimeout(1500);
  await p2.screenshot({ path: 'D:/WorkBuddy/Claw/wechat-knowledge-animation/_sandbox_top.png', clip: { x:0, y:0, width:677, height:1600 } });
  await p2.screenshot({ path: 'D:/WorkBuddy/Claw/wechat-knowledge-animation/_sandbox_full.png', fullPage: true });

  const stats = await p2.evaluate(() => {
    const secs = Array.from(document.querySelectorAll('section'));
    const withBg = secs.filter(s => {
      const b = getComputedStyle(s).backgroundColor;
      return b && b !== 'rgba(0, 0, 0, 0)';
    });
    const ps = Array.from(document.querySelectorAll('p'));
    // 塌陷：一个 p 里塞了多个 section 或 img
    const collapsed = ps.filter(p => p.querySelectorAll('section,img').length > 1).length;
    const uls = Array.from(document.querySelectorAll('ul'));
    const listStyle = uls.map(u => getComputedStyle(u).listStyleType);
    // 圆点徽章是否还在（inline-block）
    const badges = Array.from(document.querySelectorAll('span')).filter(s => {
      const cs = getComputedStyle(s);
      return cs.display === 'inline-block' && parseFloat(cs.width) >= 20 && parseFloat(cs.width) <= 30;
    }).length;
    return {
      段落数: ps.length,
      塌陷段落: collapsed,
      section数: secs.length,
      有底色section: withBg.length,
      图片数: document.querySelectorAll('img').length,
      列表: listStyle,
      徽章数: badges,
    };
  });
  await b2.close();

  console.log('=== 剪贴板层 ===');
  Object.entries(clip).forEach(([k,v]) => console.log(`  ${k}: ${v}`));
  console.log('=== 沙盒渲染层（=公众号实际效果）===');
  Object.entries(stats).forEach(([k,v]) => console.log(`  ${k}: ${Array.isArray(v)?v.join(','):v}`));
  console.log('  页面错误:', errs.length ? errs.slice(0,3) : '无');
})();
