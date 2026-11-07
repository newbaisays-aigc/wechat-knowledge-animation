import { chromium } from 'file:///D:/tools/node/workspace/node_modules/playwright-core/index.mjs';
const EXEC = 'D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe';
const browser = await chromium.launch({ executablePath: EXEC });
const ctx = await browser.newContext({ viewport: { width: 375, height: 900 } });
const page = await ctx.newPage();
const errs = [];
page.on('console', m => { if (m.type()==='error') errs.push(m.text()); });
page.on('pageerror', e => errs.push(String(e)));
await page.goto('file:///D:/WorkBuddy/Claw/wechat-knowledge-animation/wechat.html', { waitUntil: 'load', timeout: 120000 });
// 滚动到底触发所有 lazy-load
const h = await page.evaluate(() => document.body.scrollHeight);
for (let y = 0; y < h; y += 700) {
  await page.evaluate(v => window.scrollTo(0, v), y);
  await page.waitForTimeout(120);
}
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(4000);
const r = await page.evaluate(() => {
  const de = document.documentElement;
  const imgs = [...document.querySelectorAll('img')];
  return {
    overflow: de.scrollWidth - de.clientWidth,
    total: imgs.length,
    loaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
    broken: imgs.filter(i => i.complete && i.naturalWidth === 0).length,
    allCdn: imgs.every(i => i.src.startsWith('https://cdn.jsdelivr.net/')),
    copyBtns: document.querySelectorAll('.copy-btn').length,
    hl: document.querySelectorAll('.hl').length
  };
});
console.log(JSON.stringify(r, null, 1));
console.log('errs:', errs.length ? errs.slice(0,5) : 'none');
await browser.close();
