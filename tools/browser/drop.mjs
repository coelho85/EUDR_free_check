// Drop files onto the forest-check page (real Chrome) and print what the page shows.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
const [dir, ...only] = process.argv.slice(2);
const files = fs.readdirSync(dir).filter((f) => !f.startsWith('.') && fs.statSync(path.join(dir, f)).isFile() && (!only.length || only.includes(f))).sort();
const browser = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const out = {};
for (const f of files) {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto((process.env.BASE || 'http://localhost:8765') + (process.env.PAGE || '/forest-check/'), { waitUntil: 'domcontentloaded' });
  const input = await page.waitForSelector('#file');
  const t0 = Date.now();
  await input.uploadFile(path.join(dir, f));
  await page.waitForFunction(() => {
    const l = document.getElementById('log');
    return l.classList.contains('err') || document.body.dataset.step === '3';
  }, { timeout: 180000 }).catch(() => errors.push('TIMEOUT'));
  const r = await page.evaluate(() => ({
    log: document.getElementById('log').textContent.trim(),
    err: document.getElementById('log').classList.contains('err'),
    issues: document.getElementById('issues').hidden ? '' : document.getElementById('issues').innerText.replace(/\s*\n\s*/g, ' | '),
    summary: ['sTotal', 'sForest', 'sClear', 'sNa'].map((id) => document.getElementById(id).textContent).join('/'),
    rows: [...document.querySelectorAll('#tbl tbody tr')].map((tr) => [tr.cells[0].textContent, tr.cells[4].textContent.trim(), tr.title].join(' :: ')),
    cells: [...document.querySelectorAll('#tbl tbody tr')].map((tr) => [...tr.cells].map((c) => c.textContent.trim())),
  }));
  out[f] = { secs: (Date.now() - t0) / 1000, errors, ...r };
  await page.close();
}
await browser.close();
if (process.env.OUTJSON) fs.writeFileSync(process.env.OUTJSON, JSON.stringify(out));
for (const [f, r] of Object.entries(out)) {
  console.log(`\n=== ${f}  (${r.secs.toFixed(1)} s)  ${r.err ? 'ERROR MESSAGE' : 'summary ' + r.summary}`);
  console.log('  message:', r.log);
  if (r.issues) console.log('  data check:', r.issues);
  if (r.errors.length) console.log('  PAGE ERRORS:', r.errors.join(' / '));
  if (process.env.ROWS) r.rows.forEach((x) => console.log('   ', x));
}
