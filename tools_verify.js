// 独立验收：不依赖模块自带的断言，从零重新验证一遍
// 检查项：公众号不认的东西是否清干净、该留的是否保留、内容是否零丢失
const { chromium } = require('D:/tools/node/workspace/node_modules/playwright-core');
const path = require('path');
const fs = require('fs');

const EXEC = 'D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe';

(async () => {
  const b = await chromium.launch({ executablePath: EXEC });
  const ctx = await b.newContext({ permissions: ['clipboard-read', 'clipboard-write'], viewport: { width: 677, height: 1600 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto('file:///' + path.resolve('D:/WorkBuddy/Claw/wechat-knowledge-animation/wechat.html').replace(/\\/g,'/'), { waitUntil: 'load' });
  await page.click('#wx-copy');
  await page.waitForTimeout(300);
  const html = await page.evaluate(async () => {
    const res = await navigator.clipboard.read();
    for (const it of res) for (const t of it.types) {
      if (t === 'text/html') return await (await it.getType(t)).text();
    }
    return '';
  });
  await b.close();

  // 头部是否被排除
  const noChrome = !html.includes('我把「知识动画」做成了公开测试包')
                   && !html.includes('小白姐姐 · AI 实操教程 · 2026 年 11 月');

  // 图片路径：不能出现重复目录段（assets/assets/），且对应本地文件必须存在
  const srcs = [...html.matchAll(/<img\b[^>]*\bsrc="([^"]+)"/gi)].map(m => m[1]);
  const dupDir = srcs.filter(s => /\/assets\/assets\//.test(s) || /\/assets\/$/.test(s));
  const ROOT = 'D:/WorkBuddy/Claw/wechat-knowledge-animation';
  const missingLocal = srcs.filter(s => {
    const clean = s.split('?')[0].split('#')[0];
    if (!/\/assets\//.test(clean)) return false;
    const rel = clean.split('/assets/')[1];
    return !fs.existsSync(path.join(ROOT, 'assets', rel));
  });
  // 每张图在本地 assets/ 下都能对上
  const localAllExist = missingLocal.length === 0 && srcs.length === 21;

  const checks = [
    ['① 无 div（会被降级丢样式）', !/<div\b/i.test(html)],
    ['② 无 figure / figcaption', !/<figure\b/i.test(html) && !/<figcaption\b/i.test(html)],
    ['③ 无 display:flex（公众号不支持）', !/display:\s*flex/i.test(html)],
    ['④ 无 background 简写（只认 background-color）', !/style="[^"]*\bbackground:\s/i.test(html)],
    ['⑤ 无 background-image（渐变丢失）', !/background-image/i.test(html)],
    ['⑥ 无 box-shadow', !/box-shadow/i.test(html)],
    ['⑦ 无 position:absolute（会错位）', !/position:\s*absolute/i.test(html)],
    ['⑧ 无 white-space:pre-wrap', !/pre-wrap/i.test(html)],
    ['⑨ 无灰底 rgb(243,245,242)', !/243,\s*245,\s*242/i.test(html)],
    ['⑩ 无 data-* 属性', !/\sdata-\w+=/i.test(html)],
    ['⑪ 无 script 标签', !/<script/i.test(html)],
    ['---', true],
    ['⑫ 头部已排除（标题/署名不进正文）', noChrome],
    ['⑬ 正文首段在', html.includes('大家好，我是小白')],
    ['⑭ 页脚署名保留', html.includes('小白姐姐工作室出品')],
    ['⑮ 绿色高亮底色保留', html.includes('234, 246, 239')],
    ['⑯ 提示框底色保留', html.includes('238, 247, 242')],
    ['⑰ 深色提示词块保留', html.includes('24, 60, 48')],
    ['⑱ 绿色标签底色保留', html.includes('77, 167, 131')],
    ['⑲ 图片 21 张且全 CDN', (html.match(/<img\b/g)||[]).length === 21 && (html.match(/cdn\.jsdelivr\.net/g)||[]).length >= 21],
    ['⑳ 长按提示语保留', html.includes('长按下方文字复制') && html.includes('长按下方网址复制')],
    ['㉑ 提示词换行用 br 保留', (html.match(/<br\s*\/?>/gi)||[]).length > 0],
    ['㉒ 无 console/page 错误', errs.length === 0],
    ['---', true],
    ['㉓ 图片路径无重复目录段（assets/assets/）', dupDir.length === 0],
    ['㉔ 每张图在本地 assets/ 下真实存在', localAllExist],
  ];

  let pass = 0, fail = 0;
  for (const [name, ok] of checks) {
    if (name === '---') { console.log('  ' + '-'.repeat(46)); continue; }
    console.log((ok ? '  PASS  ' : '  FAIL  ') + name);
    ok ? pass++ : fail++;
  }
  console.log(`\n${pass} passed, ${fail} failed`);
  if (errs.length) console.log('errors:', errs.slice(0, 4));

  // 文本完整性
  const orig = fs.readFileSync('D:/WorkBuddy/Claw/wechat-knowledge-animation/index.html', 'utf8');
  const stripTags = s => s.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<[^>]+>/g, '').replace(/\s+/g, '');
  const origText = stripTags(orig);
  const clipText = stripTags(html);
  // 公众号版复制的是正文（不含标题区），所以原文应包含正文
  console.log('正文关键句是否都在:', ['大家好，我是小白','知识动画','Skill','提示词','长按'].every(s => clipText.includes(s.replace(/\s+/g,''))));

  fs.writeFileSync('D:/WorkBuddy/Claw/wechat-knowledge-animation/_verify_clip.html', html, 'utf8');
})();
