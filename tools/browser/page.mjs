import puppeteer from 'puppeteer-core';
const [path, out, sel] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', defaultViewport: { width: 1440, height: 900 } });
const p = await b.newPage();
await p.goto((process.env.BASE || 'http://localhost:8765') + path, { waitUntil: 'networkidle2' });
if (sel) { const el = await p.$(sel); await el.screenshot({ path: out }); } else await p.screenshot({ path: out });
await b.close();
