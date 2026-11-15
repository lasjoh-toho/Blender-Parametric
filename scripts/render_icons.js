// SPDX-License-Identifier: GPL-3.0-or-later
// Render docs/icons/*.svg to parametric_design/icons/*.png (128 px, transparent)
// and a contact sheet docs/icons/overview.png. Needs Playwright.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const root = path.dirname(__dirname);
const svgDir = path.join(root, 'docs', 'icons');
const pngDir = path.join(root, 'parametric_design', 'icons');
const SIZE = 128;

(async () => {
  fs.mkdirSync(pngDir, { recursive: true });
  const names = fs.readdirSync(svgDir).filter(f => f.endsWith('.svg')).map(f => f.slice(0, -4)).sort();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: SIZE, height: SIZE }, deviceScaleFactor: 1 });
  for (const name of names) {
    const svg = fs.readFileSync(path.join(svgDir, name + '.svg'), 'utf8')
      .replace('width="32" height="32"', `width="${SIZE}" height="${SIZE}"`);
    await page.setContent(`<body style="margin:0;background:transparent">${svg}</body>`);
    await page.screenshot({ path: path.join(pngDir, name + '.png'), omitBackground: true });
  }
  const cells = names.map(n => `<div class="c">${fs.readFileSync(path.join(svgDir, n + '.svg'), 'utf8')
    .replace('width="32" height="32"', 'width="56" height="56"')}<span>${n}</span></div>`).join('');
  await page.setViewportSize({ width: 920, height: 100 });
  await page.setContent(`<body style="margin:0;background:#303030;font:12px sans-serif;color:#ddd">
    <style>.g{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;padding:16px}
    .c{background:#545454;border-radius:6px;padding:10px 4px 6px;display:flex;flex-direction:column;align-items:center;gap:6px}</style>
    <div class="g">${cells}</div></body>`);
  await page.screenshot({ path: path.join(svgDir, 'overview.png'), fullPage: true });
  await browser.close();
  console.log(`${names.length} icons -> ${pngDir}`);
})();
