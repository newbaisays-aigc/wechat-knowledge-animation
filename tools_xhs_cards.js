// 小红书 3:4 讲解卡片渲染 + 溢出体检
// 用法：node tools_xhs_cards.js
const { chromium } = require('D:/tools/node/workspace/node_modules/playwright-core');
const path = require('path');
const fs = require('fs');

const ROOT = 'D:/WorkBuddy/Claw/wechat-knowledge-animation';
const SRC = path.join(ROOT, 'assets/xhs/cards.html').replace(/\\/g, '/');
const OUT = path.join(ROOT, 'assets/xhs');
const EXEC = 'D:/tools/remotion/browser/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe';

(async () => {
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
  const b = await chromium.launch({ executablePath: EXEC });
  const page = await b.newPage({ viewport: { width: 1140, height: 1500 }, deviceScaleFactor: 1 });
  const errs = [];
  page.on('pageerror', e => errs.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await page.goto('file:///' + SRC, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  const cards = await page.$$('.card');
  console.log('卡片数量：' + cards.length);

  // 体检：溢出 / 图片加载 / 空白
  const report = [];
  for (let i = 0; i < cards.length; i++) {
    const r = await cards[i].evaluate(el => {
      const cr = el.getBoundingClientRect();
      const over = [];
      el.querySelectorAll('*').forEach(c => {
        const b = c.getBoundingClientRect();
        if (b.height === 0 && b.width === 0) return;
        if (b.bottom > cr.bottom + 1 || b.right > cr.right + 1 || b.top < cr.top - 1 || b.left < cr.left - 1) {
          over.push((c.tagName + '.' + (c.className || '')).slice(0, 46) +
            ' b=' + Math.round(b.bottom - cr.bottom) + ' r=' + Math.round(b.right - cr.right));
        }
      });
      const imgs = Array.from(el.querySelectorAll('img')).map(im => ({
        src: im.src.split('/').pop(), ok: im.complete && im.naturalWidth > 0,
        w: im.naturalWidth, h: im.naturalHeight
      }));
      return {
        id: el.id,
        h: Math.round(cr.height), w: Math.round(cr.width),
        scroll: el.scrollHeight,
        over: over.slice(0, 6),
        imgs
      };
    });
    report.push(r);
    await cards[i].screenshot({ path: path.join(OUT, String(i + 1).padStart(2, '0') + '.png') });
  }
  await b.close();

  let bad = 0;
  report.forEach((r, i) => {
    const broken = r.imgs.filter(x => !x.ok);
    const hOver = r.scroll > r.h + 1;
    if (r.over.length || hOver || broken.length) bad++;
    console.log(
      (r.over.length || hOver || broken.length ? '✗ ' : '✓ ') +
      String(i + 1).padStart(2, '0') + ' ' + r.id +
      ' size=' + r.w + 'x' + r.h + ' scrollH=' + r.scroll +
      (hOver ? ' 高度溢出!' : '') +
      (broken.length ? ' 坏图:' + broken.map(x => x.src).join(',') : '') +
      (r.over.length ? '\n    越界: ' + r.over.join(' | ') : '')
    );
  });
  console.log('\n问题卡片数：' + bad + '；页面报错：' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  process.exit(bad || errs.length ? 1 : 0);
})();
