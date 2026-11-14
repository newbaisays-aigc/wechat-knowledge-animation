// 验证本 skill 的 copy-script.js 是否满足公众号规则。
// 用法：node test_copy.js
// 依赖：D:/tools/node/workspace/node_modules/playwright-core（playwright-core）
//       D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe
const { chromium } = require('D:/tools/node/workspace/node_modules/playwright-core');
const fs = require('fs');
const os = require('os');
const path = require('path');

const SKILL_JS = path.join(__dirname, 'copy-script.js');
const EXEC = 'D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe';

const FIXTURE = `<!DOCTYPE html><html><head><style>
  .article-container{background:#fff;color:#123;max-width:680px;font-family:inherit}
  .tip{background:#eef7f2;border-left:6px solid #3E8F6C;border-radius:10px;padding:18px}
  .note{background:#fff8e6;padding:20px}
  p{margin:0 0 14px;font-size:16px;line-height:1.7}
  .hl{background:#d7f0e4;color:#0D1916;padding:2px 6px;border-radius:4px}
</style></head><body>
<div class="article-container">
  <p>普通段落，用于确认基础样式还在。</p>
  <div class="tip"><p>提示框第一段。</p><p>提示框第二段。</p></div>
  <figure>
    <img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==" loading="lazy" decoding="async">
    <figcaption>图注文字，应当独立成段。</figcaption>
  </figure>
  <section class="note"><p>section 第一段。</p><p>section 第二段。</p></section>
  <ul><li>列表项一</li><li>列表项二</li></ul>
  <p>带高亮 <span class="hl">高亮词</span> 的段落。</p>
</div>
<button id="copy-btn" onclick="copyArticle()">复制全文到公众号</button>
</body></html>`;

(async () => {
  const FIXTURE_FILE = path.join(os.tmpdir(), '_wx_skill_fixture.html');
  fs.writeFileSync(FIXTURE_FILE, FIXTURE, 'utf8');

  const b = await chromium.launch({ executablePath: EXEC });
  const ctx = await b.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  await page.goto('file:///' + FIXTURE_FILE.replace(/\\/g, '/'), { waitUntil: 'load' });
  await page.addScriptTag({ content: fs.readFileSync(SKILL_JS, 'utf8') });
  await page.click('#copy-btn');
  await page.waitForTimeout(500);

  const html = await page.evaluate(async () => {
    const res = await navigator.clipboard.read();
    for (const it of res) for (const t of it.types) {
      if (t === 'text/html') return await (await it.getType(t)).text();
    }
    return '';
  });
  await b.close();

  const checks = [];
  const ok = (n, c, e) => checks.push({ n, c: !!c, e: e || '' });

  ok('无 <section>', !/<section/i.test(html), (html.match(/<section/gi) || []).length + ' 个');
  ok('无 <div>', !/<div/i.test(html), (html.match(/<div/gi) || []).length + ' 个');
  ok('无 <figure>/<figcaption>', !/<figure/i.test(html) && !/<figcaption/i.test(html));
  ok('无嵌套 <p>', !/<p[^>]*>[^<]*<p[\s>]/i.test(html));
  const pCount = (html.match(/<p[\s>]/gi) || []).length;
  ok('段落数 >= 8', pCount >= 8, pCount + ' 段');
  ok('提示框底色保留', /rgb\(238,\s*247,\s*242\)/i.test(html));
  ok('绿色左边框保留', /border-left:\s*6px solid rgb\(62,\s*143,\s*108\)/i.test(html));
  ok('圆角保留', /border-radius/i.test(html));
  ok('高亮底色保留', /rgb\(215,\s*240,\s*228\)/i.test(html));
  ok('图注独立成段', /<p[^>]*>[^<]*图注文字/.test(html));
  ok('图片去掉 loading', !/loading=/i.test(html));
  ok('图片去掉 decoding', !/decoding=/i.test(html));
  ok('列表保留', /<ul[\s>]/i.test(html) && /<li[\s>]/i.test(html));
  ok('无 background 简写残留', !/style="[^"]*\bbackground:/i.test(html));
  ok('无 border 三件套残留', !/border-width:/i.test(html));
  ok('字体栈非 inherit', !/font-family:\s*inherit/i.test(html));

  let fail = 0;
  checks.forEach(c => {
    if (!c.c) fail++;
    console.log((c.c ? '✓ ' : '✗ ') + c.n + (c.e ? '  [' + c.e + ']' : ''));
  });
  console.log('\n通过 ' + (checks.length - fail) + '/' + checks.length + '；页面报错：' + errs.length);
  if (process.env.DUMP) { fs.writeFileSync(process.env.DUMP, html); console.log('剪贴板 HTML → ' + process.env.DUMP); }
  process.exit(fail || errs.length ? 1 : 0);
})();
