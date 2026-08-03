const { spawn, execFileSync } = require('child_process');
const http = require('http');
const path = require('path');

let chromium;
let probeProfileDir;
let closeChromeOnExit = false;

// Cleanup on process exit
const onExit = () => {
  if (probeProfileDir && closeChromeOnExit) {
    try {
      execFileSync('pkill', ['-f', `--user-data-dir=${probeProfileDir}`], { stdio: 'ignore' });
    } catch {}
  }
};

process.on('SIGINT', onExit);
process.on('SIGTERM', onExit);
process.on('EXIT', onExit);

function clean(value) {
  return (value || '').replace(/\s+/g, ' ').trim();
}

function envMs(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function searchUrl(query) {
  const url = new URL('https://www.linkedin.com/search/results/content/');
  url.searchParams.set('keywords', query);
  url.searchParams.set('origin', 'GLOBAL_SEARCH_HEADER');
  url.searchParams.set('sortBy', 'date_posted');
  return url.toString();
}

function cdpJson(port, route = '/json/version') {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: '127.0.0.1', port, path: route, timeout: 1200 }, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try { resolve(JSON.parse(body)); } catch (error) { reject(error); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('CDP timeout')); });
  });
}

async function waitForCdp(port, timeoutMs = 20000) {
  const started = Date.now();
  let lastError;
  let attempts = 0;
  while (Date.now() - started < timeoutMs) {
    attempts += 1;
    try {
      const data = await cdpJson(port);
      if (data.webSocketDebuggerUrl) {
        console.error(`LinkedIn Chrome CDP: port ${port} ready after ${attempts} attempts (${Date.now() - started}ms)`);
        return data;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  const elapsed = Date.now() - started;
  const lastErrorMsg = lastError?.message || String(lastError) || 'unknown';
  throw new Error(`Chrome CDP port ${port} did not become ready after ${elapsed}ms (${attempts} attempts). Last error: ${lastErrorMsg}`);
}

function killProfileChrome(profileDir) {
  try {
    execFileSync('pkill', ['-f', `--user-data-dir=${profileDir}`], { stdio: 'ignore' });
  } catch {
    // No matching Chrome process.
  }
}

function psLines() {
  try {
    return execFileSync('ps', ['axo', 'pid=,command='], { encoding: 'utf8' }).split('\n');
  } catch {
    return [];
  }
}

function chromeProcessesForPort(port) {
  const portNeedle = `--remote-debugging-port=${port}`;
  return psLines()
    .map((line) => line.trim())
    .filter((line) => line.includes(portNeedle));
}

function cdpUsesProfile(port, profileDir) {
  const profileNeedle = `--user-data-dir=${profileDir}`;
  return chromeProcessesForPort(port).some((line) => line.includes(profileNeedle));
}

function chromeExecutable() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  if (process.platform === 'darwin') {
    return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  }
  return 'google-chrome';
}

function openChromeCdp(profileDir, port, initialUrl = 'https://www.linkedin.com/') {
  const chrome = chromeExecutable();
  spawn(chrome, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--new-window',
    initialUrl,
  ], { stdio: 'ignore', detached: true }).unref();
}

async function ensureChromeCdp(profileDir, port) {
  let existingCdp;
  try {
    console.error(`LinkedIn Chrome CDP: checking port ${port}`);
    existingCdp = await waitForCdp(port, 3000);
  } catch {
    existingCdp = null;
  }

  if (existingCdp) {
    if (cdpUsesProfile(port, profileDir)) {
      console.error(`LinkedIn Chrome CDP: attaching to existing Chrome profile ${profileDir}`);
      return existingCdp;
    }
    const portProcesses = chromeProcessesForPort(port).join('\n') || 'no matching Chrome process found in ps';
    throw new Error(
      `Chrome CDP port ${port} is active but is not using LinkedIn posts profile ${profileDir}. ` +
      `Close the process using port ${port} or change LINKEDIN_CDP_PORT.\n${portProcesses}`
    );
  }

  // If the same profile is already open without remote debugging, Chrome will
  // ignore the new CDP flags. Close that profile process and relaunch it with CDP.
  console.error(`LinkedIn Chrome CDP: launching Chrome on port ${port}`);
  killProfileChrome(profileDir);
  await new Promise((resolve) => setTimeout(resolve, 1200));
  openChromeCdp(profileDir, port);
  console.error(`LinkedIn Chrome CDP: waiting for Chrome CDP port ${port} to become ready (up to 10s)...`);
  const cdp = await waitForCdp(port, 10000);
  if (!cdpUsesProfile(port, profileDir)) {
    throw new Error(`Chrome CDP port ${port} became ready, but it is not using LinkedIn posts profile ${profileDir}`);
  }
  return cdp;
}

async function detectLoginState(page) {
  return page.evaluate(() => {
    const cleanText = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const href = location.href;
    const body = cleanText(document.body ? document.body.innerText : '');
    const joined = `${href} ${document.title} ${body}`;
    const securityText = /checkpoint|security verification|verify your identity|verify it'?s you|unusual activity|security check/i.test(joined);
    const challengeUrl = /\/checkpoint|\/challenge/i.test(href);
    const captchaFrame = Boolean(document.querySelector('iframe[src*="captcha"], iframe[src*="challenge"], [class*="captcha"]'));
    const signals = {
      loginForm: Boolean(document.querySelector('input[name="session_key"], input#username, form[action*="login"], a[href*="/login"]')),
      authwall: /authwall|로그인하여|sign in to view|join linkedin/i.test(joined),
      checkpoint: securityText || challengeUrl,
      captcha: /captcha|verify you are human/i.test(joined) || captchaFrame,
      finalLoginUrl: /\/login|\/authwall/i.test(href),
      finalCheckpointUrl: challengeUrl,
    };
    const checkpointRequired = signals.checkpoint || signals.captcha || signals.finalCheckpointUrl;
    const loginRequired = signals.loginForm || signals.authwall || signals.finalLoginUrl;
    return {
      href,
      title: document.title,
      signals,
      loginRequired,
      checkpointRequired,
      bodySample: body.slice(0, 220),
    };
  });
}

async function autoScroll(page, rounds = 3) {
  for (let i = 0; i < rounds; i += 1) {
    await page.mouse.wheel(0, 900);
    await page.waitForTimeout(1800 + Math.floor(Math.random() * 800));
  }
}

async function expandSeeMore(page) {
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
    for (const button of buttons.slice(0, 80)) {
      const text = (button.innerText || button.textContent || '').trim().toLowerCase();
      if (/see more|더 보기|더보기|show more/.test(text)) {
        try { button.click(); } catch {}
      }
    }
  });
  await page.waitForTimeout(800);
}

async function extractPosts(page, plan) {
  return page.evaluate((plan) => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const hashText = (value) => {
      let hash = 0;
      for (let i = 0; i < value.length; i += 1) {
        hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
      }
      return Math.abs(hash).toString(36);
    };

    const candidateCards = Array.from(document.querySelectorAll(
      '[role="listitem"], .feed-shared-update-v2, [data-urn]'
    ));
    const cards = [];
    const seen = new Set();

    for (const card of candidateCards) {
      const text = clean(card?.innerText || '');
      if (!text || text.length < 80) continue;
      const locationTerms = Array.isArray(plan.location_terms) ? plan.location_terms : [];
      const hasHiringSignal = /(#hiring\b|we.?re hiring|we are hiring|is hiring|actively hiring|hiring for|job alert|open (role|roles|position|positions|vacancy|vacancies)|vacanc(y|ies)|join our team|apply (now|here|today)|job title\s*:|(^|\s)(role|position)\s*:|looking for .{0,50}(manager|engineer|developer|lead|specialist|candidate|talent|product|sales|business development|bd))/i.test(text);
      const hasLocationSignal = locationTerms.length
        ? locationTerms.some((term) => term && text.toLowerCase().includes(String(term).toLowerCase()))
        : /(dubai|uae|georgia|tbilisi|malta)/i.test(text);
      if (!hasHiringSignal || !hasLocationSignal) continue;

      const lines = text.split('\n').map((line) => clean(line)).filter(Boolean);
      const authorProfile = Array.from(card.querySelectorAll('a[href*="/in/"], a[href*="/company/"]'))
        .map((a) => a.href ? a.href.split('?')[0] : '')
        .find(Boolean);
      const componentText = Array.from(card.querySelectorAll('[componentkey], [data-urn], [data-id]'))
        .map((el) => [
          el.getAttribute('componentkey') || '',
          el.getAttribute('data-urn') || '',
          el.getAttribute('data-id') || '',
        ].join(' '))
        .join(' ');
      const shareMatch = componentText.match(/(?:shareId=|urn:li:share:)(\d+)/);
      const ugcMatch = componentText.match(/(?:ugcPostUrn=)?(urn:li:ugcPost:\d+)/);
      const urnPermalink = shareMatch
        ? `https://www.linkedin.com/feed/update/urn:li:share:${shareMatch[1]}`
        : ugcMatch
          ? `https://www.linkedin.com/feed/update/${decodeURIComponent(ugcMatch[1])}`
          : '';
      const domPermalink = Array.from(card.querySelectorAll('a[href*="/feed/update/"], a[href*="/posts/"]'))
        .map((a) => a.href ? a.href.split('?')[0] : '')
        .find((href) => href && !href.includes('/company/') && !href.includes('/in/') && !href.includes('/search/results/'));
      const permalink = urnPermalink || domPermalink;
      const stableHash = hashText(`${plan.query}|${text.slice(0, 1000)}`);
      const id = permalink || `linkedin-post-${stableHash}`;
      if (seen.has(id)) continue;
      seen.add(id);

      const authorAnchor = card?.querySelector('a[href*="/in/"], a[href*="/company/"]');
      const feedIndex = lines.findIndex((line) => /피드 게시물|feed post/i.test(line));
      const authorFromText = lines[feedIndex + 1] || lines[0] || 'LinkedIn';
      const author = clean(authorAnchor?.innerText || authorFromText).split('\n')[0] || 'LinkedIn';
      const outboundLinks = Array.from(card?.querySelectorAll('a[href]') || [])
        .map((a) => a.href || '')
        .filter((url) => url && !url.includes('linkedin.com/search') && url !== permalink)
        .slice(0, 8);

      cards.push({
        source: plan.source || 'linkedin_post',
        source_job_id: id,
        url: permalink || '',
        author_profile: authorProfile || '',
        author,
        text,
        outbound_links: Array.from(new Set(outboundLinks)),
        query: plan.query,
        category: plan.category,
        domain: plan.domain,
        country: plan.country || 'UAE',
        store_country: plan.store_country || plan.country || 'UAE',
        display_location: plan.display_location || plan.country || 'UAE',
        location_terms: locationTerms,
      });
    }
    return cards;
  }, plan);
}

function envNumber(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) ? value : fallback;
}

function randomBetween(min, max) {
  const low = Math.min(min, max);
  const high = Math.max(min, max);
  return low + Math.floor(Math.random() * (high - low + 1));
}

async function sleepSeconds(seconds) {
  await new Promise((resolve) => setTimeout(resolve, Math.max(0, seconds) * 1000));
}

async function main() {
  console.error('LinkedIn posts probe: loading Playwright...');
  const pw = require('playwright');
  ({ chromium } = pw);
  console.error('LinkedIn posts probe: Playwright loaded');

  const profileDir = path.resolve(process.env.LINKEDIN_POSTS_PROFILE_DIR || 'outputs/linkedin-post-profile');
  probeProfileDir = profileDir;
  const port = Number(process.env.LINKEDIN_CDP_PORT || 9223);
  const plans = JSON.parse(process.env.LINKEDIN_POST_SEARCH_PLANS || '[]');
  const maxPlans = Number(process.env.LINKEDIN_POST_MAX_PLANS || plans.length || 8);
  const scrollRounds = Number(process.env.LINKEDIN_POST_SCROLL_ROUNDS || 3);
  const batchSize = envNumber('LINKEDIN_POST_BATCH_SIZE', 5);
  const batchPauseMin = envNumber('LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS', 60);
  const batchPauseMax = envNumber('LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS', 120);
  const queryPauseMin = envNumber('LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS', 5);
  const queryPauseMax = envNumber('LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS', 8);
  const closeChrome = ['1', 'true', 'yes', 'on'].includes(String(process.env.LINKEDIN_CLOSE_CHROME_AFTER || '0').toLowerCase());
  closeChromeOnExit = closeChrome;

  if (!plans.length) {
    throw new Error('LINKEDIN_POST_SEARCH_PLANS is empty');
  }

  let browser;
  let context;
  let page;
  const allPosts = [];
  const errors = [];
  const recoveries = [];
  let completedPlans = 0;
  let reconnects = 0;

  const disconnectBrowser = async () => {
    if (!browser) return;
    if (closeChrome) {
      await browser.close().catch(() => {});
    } else if (typeof browser.disconnect === 'function') {
      browser.disconnect();
    } else {
      await browser.close().catch(() => {});
    }
    browser = undefined;
    context = undefined;
    page = undefined;
  };

  const connectBrowser = async ({ restart = false } = {}) => {
    await disconnectBrowser();
    if (restart) {
      console.error('LinkedIn Chrome CDP: restarting Chrome profile');
      killProfileChrome(profileDir);
      await new Promise((resolve) => setTimeout(resolve, 1400));
    }
    await ensureChromeCdp(profileDir, port);
    console.error(`LinkedIn Chrome CDP: connecting to http://127.0.0.1:${port}`);
    let connectError;
    try {
      browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
    } catch (error) {
      connectError = error;
      const isConnRefused = /ECONNREFUSED|connect ECONNREFUSED|EPERM|EACCES/.test(String(error));
      if (isConnRefused) {
        console.error(`LinkedIn Chrome CDP: immediate connection failed after CDP check: ${error.message}. Chrome may have exited. Retrying...`);
        await new Promise((resolve) => setTimeout(resolve, 2000));
        browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
      } else {
        throw error;
      }
    }
    context = browser.contexts()[0] || await browser.newContext();
    page = context.pages().find((p) => !p.isClosed() && /linkedin\.com/.test(p.url()))
      || context.pages().find((p) => !p.isClosed())
      || await context.newPage();
    reconnects += 1;
    return page;
  };

  const ensurePage = async () => {
    if (!browser || !context || !page || page.isClosed()) {
      await connectBrowser({ restart: true });
    }
    return page;
  };

  const closeExtraPages = async () => {
    if (!context || !page || page.isClosed()) return;
    for (const extra of context.pages()) {
      if (extra !== page && !extra.isClosed()) {
        await extra.close().catch(() => {});
      }
    }
  };

  try {
    await connectBrowser();
    let feedReady = false;
    for (let attempt = 1; attempt <= 2 && !feedReady; attempt += 1) {
      try {
        await page.goto('https://www.linkedin.com/', {
          waitUntil: 'domcontentloaded',
          timeout: envMs('LINKEDIN_POST_LOGIN_CHECK_TIMEOUT_MS', 10000),
        });
        await page.waitForTimeout(2500);
        const loginState = await detectLoginState(page);
        console.error(`LinkedIn login state: ${JSON.stringify(loginState.signals)} url=${loginState.href} title=${loginState.title}`);
        if (loginState.checkpointRequired) {
          console.error('LinkedIn checkpoint/captcha/additional verification required before post scraping.');
          console.log(JSON.stringify({ posts: [], checkpoint_required: true, reason: 'checkpoint_state_failed', login_state: loginState }, null, 2));
          return;
        }
        if (loginState.loginRequired) {
          console.error('LinkedIn login/authwall required before post scraping.');
          console.log(JSON.stringify({ posts: [], login_required: true, reason: 'login_state_failed', login_state: loginState }, null, 2));
          return;
        }
        if (['1', 'true', 'yes', 'on'].includes(String(process.env.LINKEDIN_POST_LOGIN_CHECK_ONLY || '0').toLowerCase())) {
          console.log(JSON.stringify({ posts: [], login_required: false, reason: 'login_state_ok', login_state: loginState }, null, 2));
          return;
        }
        feedReady = true;
      } catch (error) {
        const message = error?.message || String(error);
        const transient = /ERR_ABORTED|Timeout|Target page, context or browser has been closed|Browser has been closed|Target closed/i.test(message);
        if (transient && attempt === 1) {
          console.error(`LinkedIn feed warmup failed; restarting Chrome and retrying: ${message}`);
          recoveries.push({ query: 'feed_warmup', recovery: 'chrome_restart_retry', error: message });
          await connectBrowser({ restart: true });
          continue;
        }
        throw error;
      }
    }

    const selectedPlans = plans.slice(0, maxPlans);
    for (let planIndex = 0; planIndex < selectedPlans.length; planIndex += 1) {
      const plan = selectedPlans[planIndex];
      const url = searchUrl(plan.query);
      console.error(`LinkedIn posts search: ${plan.query}`);
      let done = false;
      for (let attempt = 1; attempt <= 2 && !done; attempt += 1) {
        try {
          await ensurePage();
          await closeExtraPages();
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: envMs('LINKEDIN_POST_GOTO_TIMEOUT_MS', 60000) });
          await page.waitForTimeout(3500 + Math.floor(Math.random() * 1500));
          await expandSeeMore(page);
          await autoScroll(page, scrollRounds);
          await expandSeeMore(page);
          const posts = await extractPosts(page, plan);
          allPosts.push(...posts);
          completedPlans += 1;
          done = true;
          await sleepSeconds(randomBetween(queryPauseMin, queryPauseMax));
        } catch (error) {
          const message = error?.message || String(error);
          const isClosed = /Target page, context or browser has been closed|Browser has been closed|Target closed|browserContext\.newPage/i.test(message);
          if (isClosed && attempt === 1) {
            console.error(`LinkedIn posts transient page close: ${plan.query}; restarting Chrome and retrying`);
            recoveries.push({ query: plan.query, recovery: 'chrome_restart_retry', error: message });
            await connectBrowser({ restart: true });
            continue;
          }
          console.error(`LinkedIn posts search failed: ${plan.query} attempt ${attempt}: ${message}`);
          errors.push({ query: plan.query, error: message });
          done = true;
        }
      }

      const hasMorePlans = planIndex < selectedPlans.length - 1;
      if (hasMorePlans && batchSize > 0 && (planIndex + 1) % batchSize === 0) {
        const pauseSeconds = randomBetween(batchPauseMin, batchPauseMax);
        console.error(`LinkedIn posts batch cooldown: completed ${planIndex + 1}/${selectedPlans.length}, sleeping ${pauseSeconds}s and restarting Chrome`);
        await disconnectBrowser();
        killProfileChrome(profileDir);
        await sleepSeconds(pauseSeconds);
        await connectBrowser({ restart: true });
      }
    }
  } finally {
    await disconnectBrowser();
  }

  const seen = new Set();
  const unique = [];
  for (const post of allPosts) {
    if (seen.has(post.url)) continue;
    seen.add(post.url);
    unique.push(post);
  }
  console.log(JSON.stringify({
    posts: unique,
    completed_plans: completedPlans,
    attempted_plans: Math.min(maxPlans, plans.length),
    errors,
    recoveries,
    reconnects,
    batch_size: batchSize,
  }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
