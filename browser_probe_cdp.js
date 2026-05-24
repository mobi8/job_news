#!/usr/bin/env node

const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

function progress(message) {
  console.error(`[browser_probe_cdp] ${message}`);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestJson(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, options, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 200)}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

async function waitForVersion(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await requestJson(`http://127.0.0.1:${port}/json/version`);
    } catch (error) {
      lastError = error;
      await delay(200);
    }
  }
  throw lastError || new Error('Chrome DevTools endpoint did not become ready');
}

function connect(wsUrl) {
  const socket = new WebSocket(wsUrl);
  let nextId = 1;
  const pending = new Map();
  const listeners = new Map();

  socket.addEventListener('message', (event) => {
    const payload = JSON.parse(event.data);
    if (payload.id && pending.has(payload.id)) {
      const { resolve, reject } = pending.get(payload.id);
      pending.delete(payload.id);
      if (payload.error) reject(new Error(payload.error.message || JSON.stringify(payload.error)));
      else resolve(payload.result);
      return;
    }
    if (payload.method && listeners.has(payload.method)) {
      for (const listener of listeners.get(payload.method)) listener(payload.params || {});
    }
  });

  const opened = new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });

  return {
    opened,
    send(method, params = {}) {
      const id = nextId++;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
      });
    },
    on(method, listener) {
      if (!listeners.has(method)) listeners.set(method, []);
      listeners.get(method).push(listener);
    },
    close() {
      socket.close();
    },
  };
}

function chromePath() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  const candidates = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || 'google-chrome';
}

function randomPort() {
  return 43000 + Math.floor(Math.random() * 10000);
}

function evaluateLinkedInSource() {
  return `(() => {
    const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
    const jobAnchors = Array.from(document.querySelectorAll(
      'a.base-card__full-link, a[data-job-id], a.job-card-title'
    ));
    const jobs = [];
    const seenUrls = new Set();
    for (const anchor of jobAnchors) {
      const card = anchor.closest('li') || anchor.closest('.base-card') || anchor.parentElement;
      const title = clean(anchor.innerText);
      const url = anchor.href || '';
      if (!url.includes('/jobs/view/')) continue;
      const sourceJobIdMatch = url.match(/-(\\d+)(?:[/?#]|$)/) || url.match(/currentJobId=(\\d+)/) || url.match(/\\/jobs\\/view\\/(\\d+)/);
      const companyNode =
        card?.querySelector('.base-search-card__subtitle a') ||
        card?.querySelector('.base-search-card__subtitle') ||
        card?.querySelector('h4 a');
      const locationNode =
        card?.querySelector('.job-search-card__location') ||
        card?.querySelector('.base-search-card__metadata') ||
        card?.querySelector('span[class*="location"]');
      const snippetNode =
        card?.querySelector('.job-search-card__snippet') ||
        card?.querySelector('.base-search-card__snippet') ||
        card?.querySelector('[class*="snippet"]') ||
        card?.querySelector('[class*="description"]') ||
        card?.querySelector('p');
      const company = clean(companyNode ? companyNode.innerText : '');
      const location = clean(locationNode ? locationNode.innerText : '');
      const description = clean(snippetNode ? snippetNode.innerText : '');
      if (!title || !url || seenUrls.has(url)) continue;
      seenUrls.add(url);
      jobs.push({
        source: /emea|europe, middle east/i.test(location) ? 'linkedin_emea' : 'linkedin_public',
        source_job_id: sourceJobIdMatch ? sourceJobIdMatch[1] : url,
        title,
        company: company || 'LinkedIn',
        location,
        url,
        description,
        remote: /remote|emea|europe, middle east/i.test(\`\${title} \${location} \${description}\`),
      });
    }
    const links = Array.from(document.querySelectorAll('a'))
      .map((a) => ({ text: clean(a.innerText), href: a.href || '', cls: a.className || '' }))
      .filter((item) => item.text && item.href)
      .slice(0, 120);
    return { pageTitle: document.title, href: location.href, links, jobs };
  })()`;
}

async function probeUrl(url) {
  if (!url.includes('linkedin.com/jobs/search')) {
    return { pageTitle: 'Unsupported', href: url, jobs: [], error: 'CDP probe supports LinkedIn job search URLs only' };
  }

  const port = randomPort();
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'jobhunt-cdp-'));
  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    '--headless=new',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    'about:blank',
  ];
  const browser = spawn(chromePath(), args, { stdio: ['ignore', 'ignore', 'pipe'] });
  browser.stderr.on('data', (chunk) => {
    const text = String(chunk).trim();
    if (text.includes('DevTools listening')) progress(text);
  });

  try {
    await waitForVersion(port, 10000);
    const target = await requestJson(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' });
    const cdp = connect(target.webSocketDebuggerUrl);
    await cdp.opened;
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    progress(`open LinkedIn: ${url}`);
    const loaded = new Promise((resolve) => cdp.on('Page.loadEventFired', resolve));
    await cdp.send('Page.navigate', { url });
    await Promise.race([loaded, delay(15000)]);
    await delay(3000);
    for (let i = 0; i < 3; i += 1) {
      await cdp.send('Runtime.evaluate', { expression: 'window.scrollTo(0, document.documentElement.scrollHeight)', awaitPromise: true });
      await delay(1200);
    }
    const result = await cdp.send('Runtime.evaluate', {
      expression: evaluateLinkedInSource(),
      returnByValue: true,
      awaitPromise: true,
    });
    cdp.close();
    return result.result?.value || { pageTitle: 'Empty', href: url, jobs: [] };
  } finally {
    browser.kill('SIGTERM');
    await delay(200);
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {
      // Best effort cleanup.
    }
  }
}

async function main() {
  const urls = process.argv.slice(2);
  if (!urls.length) {
    throw new Error('Usage: node browser_probe_cdp.js <url> [<url> ...]');
  }
  const results = [];
  for (const url of urls) {
    try {
      results.push(await probeUrl(url));
    } catch (error) {
      results.push({ pageTitle: 'Error', href: url, jobs: [], error: error.message || String(error) });
    }
  }
  process.stdout.write(JSON.stringify(results, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
