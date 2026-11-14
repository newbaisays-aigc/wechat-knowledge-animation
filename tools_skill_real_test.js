// 用真实文章 index.html 跑一遍 skill 的 copy-script.js，
// 验证产出的粘贴版是否满足公众号规则。
// 用法：node tools_skill_real_test.js
const { chromium } = require('D:/tools/node/workspace/node_modules/playwright-core');
const fs = require('fs');

const ROOT = 'D:/WorkBuddy/Claw/wechat-knowledge-animation';
const SKILL_JS = 'D:/00WorkBuddy/.workbuddy/skills/wechat-article-builder/references/copy-script.js';
const EXEC = 'D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe';

(async () => {
  const b = await chromium.launch({ executablePath: EXEC });
  const ctx = await b.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });

  await page.goto('file:///' + ROOT + '/index.html', { waitUntil: 'load' });
  await page.waitForTimeout(800);

  // 给文章容器挂上 skill 需要的 class，并补一个复制按钮
  await page.evaluate(() => {
    const art = document.querySelector('article') || document.querySelector('.article') || document.body.firstElementChild;
    art.classList.add('article-container');
    const btn = document.createElement('button');
    btn.id = 'copy-btn';
    btn.textContent = '复制全文到公众号';
    btn.setAttribute('onclick', 'copyArticle()');
    btn.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:99999';
    document.body.appendChild(btn);
  });

  await page.addScriptTag({ content: fs.readFileSync(SKILL_JS, 'utf8') });
  await page.click('#copy-btn');
  await page.waitForTimeout(800);

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

  const pCount = (html.match(/<p[\s>]/gi) || []).length;
  ok('输出非空', html.length > 5000, html.length + ' 字符');
  ok('无 <section>', !/<section/i.test(html), (html.match(/<section/gi) || []).length + ' 个');
  ok('无 <div>', !/<div/i.test(html), (html.match(/<div/gi) || []).length + ' 个');
  ok('无 <figure>/<figcaption>', !/<figure/i.test(html) && !/<figcaption/i.test(html));
  ok('无嵌套 <p>', !/<p[^>]*>[^<]*<p[\s>]/i.test(html));
  ok('段落数 >= 60', pCount >= 60, pCount + ' 段');
  ok('图片无 loading=lazy', !/loading=/i.test(html));
  ok('无 background 简写', !/style="[^"]*\bbackground:/i.test(html));
  ok('无 border-width 三件套', !/border-width:/i.test(html));
  ok('高亮底色保留', /background-color:\s*rgb/i.test(html));
  ok('绿色左边框保留', /border-left:\s*\d+px solid/i.test(html));
  ok('字体栈非 inherit', !/font-family:\s*inherit/i.test(html));
  ok('列表保留', /<ul[\s>]/i.test(html) && /<li[\s>]/i.test(html));
  const srcTables = (fs.readFileSync(ROOT + '/index.html', 'utf8').match(/<table/gi) || []).length;
  const outTables = (html.match(/<table/gi) || []).length;
  ok('表格数量与源文一致', outTables >= srcTables, '源文 ' + srcTables + ' / 输出 ' + outTables);

  // 图片独占段落：每个 <p> 里最多一张 img，且 img 所在段落不含其它文本
  const pBlocks = html.split(/(?=<p[\s>])/).filter(s => /<p[\s>]/.test(s));
  const imgPs = pBlocks.filter(s => /<img/i.test(s));
  const badImg = imgPs.filter(s => {
    const inner = s.replace(/<img[^>]*>/gi, '').replace(/<[^>]+>/g, '').trim();
    return inner.length > 0;
  });
  ok('图片独占段落', badImg.length === 0, badImg.length + ' 段图带文字');

  let fail = 0;
  checks.forEach(c => {
    if (!c.c) fail++;
    console.log((c.c ? '✓ ' : '✗ ') + c.n + (c.e ? '  [' + c.e + ']' : ''));
  });
  console.log('\n通过 ' + (checks.length - fail) + '/' + checks.length + '；页面报错：' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  if (process.env.DUMP) { fs.writeFileSync(process.env.DUMP, html); console.log('剪贴板 HTML → ' + process.env.DUMP); }
  process.exit(fail || errs.length ? 1 : 0);
})();
