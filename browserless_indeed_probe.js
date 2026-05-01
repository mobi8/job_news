const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

function progress(message) {
  console.error(message);
}

function clean(value) {
  return (value || '').replace(/\s+/g, ' ').trim();
}

function decodeQueryValue(value) {
  return decodeURIComponent((value || '').replace(/\+/g, ' '));
}

function classifyLocation(location) {
  const value = clean(location).toLowerCase();
  if (value.includes('malta')) return 'Malta';
  if (value.includes('georgia')) return 'Georgia';
  if (value.includes('united arab emirates') || value.includes('uae') || value.includes('dubai') || value.includes('abu dhabi')) {
    return 'UAE';
  }
  return clean(location) || 'Unknown';
}

function compactKeywords(value) {
  const text = decodeQueryValue(value)
    .replace(/\bOR\b/gi, ' / ')
    .replace(/\s+/g, ' ')
    .replace(/^["']|["']$/g, '')
    .trim();
  return (text || 'search').slice(0, 64);
}

function describeSearchUrl(url) {
  try {
    const parsed = new URL(url);
    if (url.includes('indeed.com')) {
      const location = decodeQueryValue(parsed.searchParams.get('l') || parsed.searchParams.get('location') || '');
      return {
        platform: 'Indeed',
        country: classifyLocation(location),
        label: compactKeywords(parsed.searchParams.get('q') || parsed.searchParams.get('query') || ''),
      };
    }
  } catch {
    // Best effort only.
  }
  return {
    platform: 'Search',
    country: 'Unknown',
    label: clean(url).slice(0, 64) || 'search',
  };
}

function buildBrowserlessUrl() {
  const token = process.env.BROWSERLESS_TOKEN || process.env.BROWSERLESS_API_KEY || '';
  if (!token) {
    throw new Error('Missing BROWSERLESS_TOKEN (or BROWSERLESS_API_KEY).');
  }

  const region = process.env.BROWSERLESS_REGION || 'production-sfo.browserless.io';
  const queryParams = new URLSearchParams({ token });
  if (process.env.BROWSERLESS_PROXY_COUNTRY) {
    queryParams.set('proxy', 'residential');
    queryParams.set('proxyCountry', process.env.BROWSERLESS_PROXY_COUNTRY);
  }
  return `wss://${region}/stealth?${queryParams.toString()}`;
}

async function extractIndeedJobs(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const jobs = [];
    const seenUrls = new Set();
    const isTitle = (text) => {
      const value = clean(text);
      if (!value || value.length < 4 || value.length > 180) return false;
      const lowered = value.toLowerCase();
      if ([
        'apply',
        'view job',
        'remote jobs',
        'jobs',
        'full time',
        'part time',
        'see more',
      ].includes(lowered)) return false;
      if (value.startsWith('$') || value.startsWith('Image:')) return false;
      return /[A-Za-z]/.test(value);
    };

    const parseCard = (card, titleAnchor) => {
      const title = clean(titleAnchor?.innerText || titleAnchor?.textContent || '');
      const url = titleAnchor?.href || '';
      if (!title || !url || seenUrls.has(url)) return null;

      const sourceJobIdMatch = url.match(/[?&]jk=([^&]+)/i) || url.match(/\/viewjob\?jk=([^&]+)/i);
      const companyNode =
        card?.querySelector('[data-testid="company-name"]') ||
        card?.querySelector('[data-testid="company-name"] span') ||
        card?.querySelector('span[data-testid="company-name"]') ||
        card?.querySelector('.companyName') ||
        card?.querySelector('span.company');
      const locationNode =
        card?.querySelector('[data-testid="text-location"]') ||
        card?.querySelector('[data-testid="text-location"] div') ||
        card?.querySelector('[data-testid="text-location"] span') ||
        card?.querySelector('.companyLocation') ||
        card?.querySelector('div.companyLocation') ||
        card?.querySelector('span.location');

      const snippetNodes = Array.from(card?.querySelectorAll(
        '[data-testid*="attribute_snippet_testid"], [data-testid="belowJobSnippet"], ' +
        '[class*="snippet"], [class*="description"], li'
      ) || []);
      const company = clean(companyNode ? companyNode.innerText : '');
      const location = clean(locationNode ? locationNode.innerText : '');
      const snippetText = clean(snippetNodes.map((node) => node.innerText || '').join(' '));
      const description = snippetText || clean(
        Array.from(card?.querySelectorAll('span, div') || [])
          .map((el) => el.innerText || '')
          .filter((t) => t.length > 20 && t !== title && t !== company && t !== location)
          .slice(0, 3)
          .join(' ')
      );

      seenUrls.add(url);
      return {
        source: 'indeed_browserless_uae',
        source_job_id: sourceJobIdMatch ? sourceJobIdMatch[1] : url,
        title,
        company: company || 'Indeed',
        location,
        url,
        description,
        remote: /remote/i.test(`${title} ${location} ${description}`),
      };
    };

    const cardSelectors = [
      '[data-testid="slider_container"]',
      'article',
      'li',
      'section',
      'div.job_seen_beacon',
      'div[data-jk]',
    ];

    for (const selector of cardSelectors) {
      const cards = Array.from(document.querySelectorAll(selector));
      for (const card of cards) {
        const titleAnchor =
          card.querySelector('a.jcs-JobTitle') ||
          card.querySelector('h2 a') ||
          card.querySelector('a[data-jk]') ||
          card.querySelector('a.tapItem') ||
          card.querySelector('a.jobTitle-link') ||
          card.querySelector('a[href*="/jobs/view/"]') ||
          card.querySelector('a[href*="/viewjob"]') ||
          card.querySelector('a[href*="/rc/clk"]') ||
          card.querySelector('a[href*="/pagead/clk"]');
        if (!titleAnchor) continue;
        const job = parseCard(card, titleAnchor);
        if (job) jobs.push(job);
      }
      if (jobs.length) break;
    }

    if (!jobs.length) {
      const anchors = Array.from(document.querySelectorAll('a[data-jk], a.tapItem, a.jobTitle-link, a[href*="/jobs/view/"], a[href*="/viewjob"], a[href*="/rc/clk"], a[href*="/pagead/clk"]'))
        .map((a) => ({ href: a.href || '', text: clean(a.innerText || a.textContent || ''), node: a }))
        .filter((item) => item.href && isTitle(item.text));

      for (const item of anchors) {
        if (seenUrls.has(item.href)) continue;
        const card = item.node.closest('article, li, section, div') || item.node.parentElement;
        const lines = clean(card ? card.innerText : '')
          .split(/\n+/)
          .map(clean)
          .filter(Boolean);
        const title = item.text;
        if (!lines.length) continue;
        const titleIndex = lines.findIndex((line) => line.toLowerCase() === title.toLowerCase() || title.toLowerCase().includes(line.toLowerCase()) || line.toLowerCase().includes(title.toLowerCase()));
        if (titleIndex < 0) continue;

        const companyNode =
          card?.querySelector('[data-testid="company-name"]') ||
          card?.querySelector('[data-testid="company-name"] span') ||
          card?.querySelector('span[data-testid="company-name"]') ||
          card?.querySelector('.companyName') ||
          card?.querySelector('span.company');
        const locationNode =
          card?.querySelector('[data-testid="text-location"]') ||
          card?.querySelector('[data-testid="text-location"] div') ||
          card?.querySelector('[data-testid="text-location"] span') ||
          card?.querySelector('.companyLocation') ||
          card?.querySelector('div.companyLocation') ||
          card?.querySelector('span.location');
        const company = clean(companyNode ? companyNode.innerText : '');
        const location = clean(locationNode ? locationNode.innerText : '');
        const description = clean(
          Array.from(card?.querySelectorAll('span, div, p') || [])
            .map((el) => el.innerText || '')
            .filter((t) => t.length > 20 && t !== title && t !== company && t !== location)
            .slice(0, 3)
            .join(' ')
        );

        seenUrls.add(item.href);
        const sourceJobIdMatch = item.href.match(/jk=([^&]+)/i) || item.href.match(/\/viewjob\?jk=([^&]+)/i);
        jobs.push({
          source: 'indeed_browserless_uae',
          source_job_id: sourceJobIdMatch ? sourceJobIdMatch[1] : item.href,
          title,
          company: company || 'Indeed',
          location,
          url: item.href,
          description,
          remote: /remote/i.test(`${title} ${location} ${description}`),
        });
      }
    }

    return {
      pageTitle: document.title,
      href: window.location.href,
      jobs,
    };
  });
}

async function main() {
  const urls = process.argv.slice(2).filter(Boolean);
  if (!urls.length) {
    throw new Error('Usage: node browserless_indeed_probe.js <url> [<url> ...]');
  }

  progress(`Browserless Indeed probe start urls=${urls.length}`);
  const browserlessUrl = buildBrowserlessUrl();
  const browser = await chromium.connectOverCDP(browserlessUrl);

  try {
    let context = null;
    try {
      context = await browser.newContext({ serviceWorkers: 'block' });
    } catch {
      context = browser.contexts()[0] || await browser.newContext({ serviceWorkers: 'block' });
    }

    if (!context) {
      throw new Error('Unable to create browser context');
    }

    await context.route('**/*', (route) => {
      const resourceType = route.request().resourceType();
      if (resourceType === 'image' || resourceType === 'font' || resourceType === 'media') {
        return route.abort('blockedbyclient');
      }
      return route.continue();
    });

    const results = [];
    for (let i = 0; i < urls.length; i += 1) {
      const url = urls[i];
      const contextInfo = describeSearchUrl(url);
      progress(`Indeed | start ${i + 1}/${urls.length} | ${contextInfo.country} | ${contextInfo.label} | ${url}`);
      try {
        const page = await context.newPage();
        await page.setViewportSize({ width: 1440, height: 1024 }).catch(() => {});
        page.setDefaultTimeout(5000);
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForLoadState('networkidle', { timeout: 2500 }).catch(() => {});
        await page.waitForTimeout(300).catch(() => {});
        const result = await extractIndeedJobs(page);
        progress(`Indeed | jobs=${result.jobs.length} | ${url}`);
        results.push(result);
        await page.close().catch(() => {});
      } catch (error) {
        progress(`Indeed | error ${i + 1}/${urls.length} | ${url} | ${error.message || error}`);
        results.push({
          pageTitle: '',
          href: url,
          jobs: [],
          error: String(error && error.message ? error.message : error),
        });
      } finally {
        // No-op: page is closed in the success path, and failed page creation
        // or navigation may already have torn it down.
      }
    }

    process.stdout.write(JSON.stringify(results, null, 2));
  } finally {
    await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
