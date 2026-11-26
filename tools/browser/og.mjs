// Social preview image: run the example on the page and capture the tool card at 1200x630.
import puppeteer from 'puppeteer-core';
const out = process.argv[2];
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new',
  args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'], defaultViewport: { width: 1200, height: 1400, deviceScaleFactor: 1 } });
const p = await b.newPage();
await p.goto((process.env.BASE || 'http://localhost:8765') + '/forest-check/?example=1', { waitUntil: 'networkidle2' });
await p.waitForFunction(() => document.body.dataset.step === '3', { timeout: 60000 });
await new Promise((r) => setTimeout(r, 9000));
const card = await p.$('.fc-body');
const box = await card.boundingBox();
await p.screenshot({ path: out, type: 'jpeg', quality: 85, clip: { x: box.x, y: box.y, width: Math.min(1200, box.width), height: 630 } });
await b.close();
