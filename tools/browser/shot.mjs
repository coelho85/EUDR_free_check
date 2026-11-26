import puppeteer from 'puppeteer-core';
const [file, out] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new',
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'], defaultViewport: { width: 1440, height: 1300 } });
const p = await b.newPage();
await p.goto('http://localhost:8765/forest-check/', { waitUntil: 'networkidle2' });
await (await p.$('#file')).uploadFile(file);
await p.waitForFunction(() => /^Done/.test(document.getElementById('log').textContent) || document.getElementById('log').classList.contains('err'), { timeout: 60000 });
await new Promise((r) => setTimeout(r, 2500));
const el = await p.$('.fc-card');
await el.screenshot({ path: out });
await b.close();
