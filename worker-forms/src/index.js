// forms.geoanalyticslab.com — receives forest-check registrations and emails them to the owner.
// Validates the email (format, real mail domain, not disposable), optionally checks Cloudflare Turnstile,
// keeps a copy in KV (if bound) and sends a plain-text email through Cloudflare Email Routing.
import { EmailMessage } from 'cloudflare:email';

const ALLOWED_ORIGINS = [
  'https://geoanalyticslab.com',
  'https://www.geoanalyticslab.com',
  'http://localhost:8765',
];

// Common throwaway-address domains (not exhaustive; the MX check catches made-up domains).
const DISPOSABLE = new Set(`mailinator.com guerrillamail.com guerrillamail.net guerrillamail.org sharklasers.com grr.la
10minutemail.com 10minutemail.net tempmail.com temp-mail.org temp-mail.io tempmailo.com tempr.email yopmail.com yopmail.net
yopmail.fr trashmail.com trashmail.de trashmail.net getnada.com nada.email dispostable.com maildrop.cc mailnesia.com
mintemail.com mohmal.com throwawaymail.com fakeinbox.com spamgourmet.com mailcatch.com emailondeck.com moakt.com
tempinbox.com burnermail.io inboxkitten.com mail.tm mailpoof.com spam4.me discard.email 33mail.com mytemp.email
tmpmail.org tmpmail.net emailfake.com fakemail.net luxusmail.org owlymail.com mailsac.com harakirimail.com`.split(/\s+/));

const EMAIL_RE = /^[^\s@"<>(),;:]{1,64}@([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,24}$/;

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const cors = {
      'Access-Control-Allow-Origin': ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0],
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
      Vary: 'Origin',
    };
    const reply = (status, body) => new Response(JSON.stringify(body), {
      status, headers: { ...cors, 'Content-Type': 'application/json' } });

    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (url.pathname !== '/lead' || request.method !== 'POST') return reply(404, { ok: false, error: 'not_found' });
    if (!ALLOWED_ORIGINS.includes(origin)) return reply(403, { ok: false, error: 'origin' });

    let d;
    try { d = await request.json(); } catch { return reply(400, { ok: false, error: 'bad_request' }); }
    if (d.website) return reply(200, { ok: true });   // honeypot field filled in: a bot; pretend success

    const name = clean(d.name, 100), org = clean(d.org, 150), email = clean(d.email, 254).toLowerCase();
    if (!name) return reply(400, { ok: false, error: 'name' });
    if (!org) return reply(400, { ok: false, error: 'org' });
    if (d.consent !== true) return reply(400, { ok: false, error: 'consent' });
    if (!EMAIL_RE.test(email)) return reply(400, { ok: false, error: 'email' });
    const domain = email.split('@')[1];
    if (DISPOSABLE.has(domain)) return reply(400, { ok: false, error: 'email_disposable' });
    if (!(await receivesMail(domain))) return reply(400, { ok: false, error: 'email_domain' });

    if (env.TURNSTILE_SECRET) {
      const ok = await verifyTurnstile(env.TURNSTILE_SECRET, d.turnstile, request.headers.get('CF-Connecting-IP'));
      if (!ok) return reply(400, { ok: false, error: 'captcha' });
    }

    const pct = (v) => (Number.isFinite(+v) && +v >= 0 && +v <= 100 ? Math.round(+v * 10) / 10 : null);
    const lead = {
      time: new Date().toISOString(),
      name, org, email,
      marketing: d.marketing === true,
      forestPct: pct(d.summary?.forestPct),
      noForestPct: pct(d.summary?.noForestPct),
      lang: clean(d.lang, 5),
      country: request.cf?.country || '',
    };

    if (env.LEADS) {   // backup copy, so a lead is never lost if the email fails
      await env.LEADS.put(`lead:${lead.time}:${crypto.randomUUID().slice(0, 8)}`, JSON.stringify(lead));
    }
    try {
      await sendMail(env, lead);
    } catch (e) {
      console.error('email failed', e);
      if (!env.LEADS) return reply(500, { ok: false, error: 'server' });
    }
    return reply(200, { ok: true });
  },
};

function clean(v, max) {
  return String(v ?? '').replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, max);
}

async function receivesMail(domain) {
  // DNS over HTTPS. A domain needs MX records (and not the "null MX" that means "no mail here").
  try {
    const r = await fetch(`https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}&type=MX`,
      { headers: { Accept: 'application/dns-json' } });
    const j = await r.json();
    const mx = (j.Answer || []).filter((a) => a.type === 15).map((a) => a.data.trim());
    return mx.length > 0 && !mx.every((m) => /^0\s+\.?$/.test(m));
  } catch {
    return true;   // DNS lookup failed on our side: don't punish the user
  }
}

async function verifyTurnstile(secret, token, ip) {
  if (!token) return false;
  const body = new FormData();
  body.append('secret', secret); body.append('response', token); if (ip) body.append('remoteip', ip);
  const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body });
  return (await r.json()).success === true;
}

async function sendMail(env, lead) {
  const from = env.MAIL_FROM;          // e.g. forest-check@geoanalyticslab.com (domain with Email Routing)
  const to = env.MAIL_TO;              // must be a verified destination address in Email Routing
  const subject = `Forest check registration: ${lead.org}`;
  const text = [
    'New registration on geoanalyticslab.com/forest-check',
    '',
    `Name:           ${lead.name}`,
    `Organization:   ${lead.org}`,
    `Email:          ${lead.email}`,
    `Updates OK:     ${lead.marketing ? 'yes' : 'no'}`,
    '',
    `Plots with forest:     ${lead.forestPct ?? '?'} %`,
    `Plots without forest:  ${lead.noForestPct ?? '?'} %`,
    '',
    `Time (UTC):     ${lead.time}`,
    `Country (IP):   ${lead.country}`,
    `Page language:  ${lead.lang}`,
  ].join('\r\n');
  const raw = [
    `From: GeoAnalytics Lab forest check <${from}>`,
    `To: <${to}>`,
    `Reply-To: ${encodeHeader(lead.name)} <${lead.email}>`,
    `Subject: ${encodeHeader(subject)}`,
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${crypto.randomUUID()}@geoanalyticslab.com>`,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=utf-8',
    'Content-Transfer-Encoding: base64',
    '',
    b64(text).replace(/.{1,76}/g, '$&\r\n'),
  ].join('\r\n');
  await env.MAILER.send(new EmailMessage(from, to, raw));
}

function b64(s) {
  const bytes = new TextEncoder().encode(s);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
function encodeHeader(s) {   // RFC 2047, so names with accents (ç, ã, é) survive
  return /^[\x20-\x7e]*$/.test(s) ? s.replace(/[\r\n"]/g, '') : `=?UTF-8?B?${b64(s)}?=`;
}
