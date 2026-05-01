const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

function progress(message) {
  console.error(message);
}

function clean(value) {
  return (value || '').replace(/\s+/g, ' ').trim();
}

function isLikelyTitle(text) {
  const value = clean(text);
  if (!value || value.length < 3 || value.length > 140) return false;
  if (/jobs in|salaries in|reviews at|overview|browse by|popular search|sign in to apply/i.test(value)) return false;
  if (/^\d+[dk]?$/i.test(value)) return false;
  return /[A-Za-z]/.test(value);
}

function isLikelyLocation(text) {
  return /dubai|united arab emirates|uae|abu dhabi|abudhabi|sharjah|remote/i.test(clean(text));
}

function isLikelyNoise(text) {
  return [
    'search',
    'location',
    'jobs',
    'companies',
    'salaries',
    'for you',
    'sign in',
    'create job alert',
    'upload your cv',
    'upload your resume',
    'discover more',
    'apply now',
    'apply on employer site',
    'easy apply',
    'most relevant',
    'job description',
    'core duties',
    'job introduction',
    'employee reviews at',
    'overview',
    'discover more',
    'show more',
    'sign in to apply',
    'apply on employer site',
    'easy apply',
  ].includes(clean(text).toLowerCase());
}

function defaultUrls() {
  return [
    'https://www.glassdoor.com/Job/jobs-SRCH_IM954.htm',
    'https://www.glassdoor.com/Job/jobs-SRCH_IC2204498.htm',
  ];
}

function buildBrowserlessUrl({ solveCaptchas = false } = {}) {
  const token = process.env.BROWSERLESS_TOKEN || process.env.BROWSERLESS_API_KEY || '';
  if (!token) {
    throw new Error('Missing BROWSERLESS_TOKEN (or BROWSERLESS_API_KEY).');
  }

  const region = process.env.BROWSERLESS_REGION || 'production-sfo.browserless.io';
  const queryParams = new URLSearchParams({ token });
  if (solveCaptchas) {
    queryParams.set('solveCaptchas', 'true');
  }
  if (process.env.BROWSERLESS_PROXY_COUNTRY) {
    queryParams.set('proxy', 'residential');
    queryParams.set('proxyCountry', process.env.BROWSERLESS_PROXY_COUNTRY);
  }
  return `wss://${region}/stealth?${queryParams.toString()}`;
}

function getStorageStatePath() {
  return process.env.GLASSDOOR_STORAGE_STATE_PATH
    || path.join('/Users/lewis/Desktop/agent/outputs', 'browserless_glassdoor_storage_state.json');
}

function shouldRetryWithCaptcha(result) {
  const title = clean(result?.pageTitle || '');
  const body = clean(Array.isArray(result?.debug?.bodyLinesSample) ? result.debug.bodyLinesSample.slice(0, 12).join(' ') : '');
  const blob = `${title} ${body}`.toLowerCase();
  return [
    'just a moment',
    'verify you are human',
    'captcha',
    'checking your browser',
    'access denied',
    'please enable javascript',
  ].some((needle) => blob.includes(needle));
}

async function expandGlassdoorMoreControls(page) {
  const selectors = [
    'button:has-text("Show more")',
    'a:has-text("Show more")',
    '[role="button"]:has-text("Show more")',
    'button:has-text("More")',
    'a:has-text("More")',
    '[role="button"]:has-text("More")',
  ];

  for (const selector of selectors) {
    const locator = page.locator(selector);
    const count = Math.min(await locator.count().catch(() => 0), 3);
    for (let index = 0; index < count; index++) {
      const target = locator.nth(index);
      const visible = await target.isVisible().catch(() => false);
      if (!visible) continue;
      await target.click({ timeout: 1500, force: true }).catch(() => {});
      await page.waitForTimeout(200).catch(() => {});
    }
  }
}

async function extractGlassdoorJobs(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const isLikelyTitle = (text) => {
      const value = clean(text);
      if (!value || value.length < 3 || value.length > 140) return false;
      if (/jobs in|salaries in|reviews at|overview|browse by|popular search|sign in to apply/i.test(value)) return false;
      if (/^\d+[dk]?$/i.test(value)) return false;
      return /[A-Za-z]/.test(value);
    };
    const isLikelyLocation = (text) => /dubai|united arab emirates|uae|abu dhabi|abudhabi|sharjah|remote/i.test(clean(text));
    const isLikelyNoise = (text) => [
      'search',
      'location',
      'jobs',
      'companies',
      'salaries',
      'for you',
      'sign in',
      'create job alert',
      'upload your cv',
      'upload your resume',
      'discover more',
      'apply now',
      'apply on employer site',
      'easy apply',
      'most relevant',
      'job description',
      'core duties',
      'job introduction',
      'employee reviews at',
      'overview',
      'discover more',
      'show more',
      'sign in to apply',
      'apply on employer site',
      'easy apply',
    ].includes(clean(text).toLowerCase());

    const stripContextNoise = (value) =>
      clean(value)
        .replace(/\b(Company Logo|Image:.*?Logo|Most relevant|Create job alert|Easy Apply only|Remote only|Company rating|Date posted|Salary range|For You|Search|Jobs|Companies|Salaries|For Employers|Upload resume|Upload your resume to increase your chances of getting noticed\.|Are you open to new opportunities\?|Skip to main content|Skip to content|Skip to footer)\b/gi, ' ')
        .replace(/\b(\d+[dk]?|\d+h|\d+d\+|30d\+|24h|19d|5d|2d|11d)\b/gi, ' ')
        .replace(/\s+/g, ' ')
        .trim();

    const normalizeCompany = (value) => {
      const stripped = stripContextNoise(value);
      if (!stripped) return '';
      const repeated = stripped.match(/^(.*?)(?:\s+\1)+$/i);
      if (repeated) {
        return clean(repeated[1]);
      }
      return stripped;
    };

    const slugify = (value) =>
      clean(value)
        .toLowerCase()
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');

    const humanizeSlug = (value) =>
      clean(value)
        .replace(/[-_]+/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase());

    const companyFromHref = (href, title) => {
      try {
        const url = new URL(href);
        const path = decodeURIComponent(url.pathname || '');
        const segment = path.split('/job-listing/')[1] || '';
        const slug = segment.replace(/-JV_.*/, '');
        const titleSlug = slugify(title);
        if (slug && titleSlug && slug.startsWith(titleSlug)) {
          const tail = slug.slice(titleSlug.length).replace(/^-+/, '');
          if (tail) {
            return humanizeSlug(tail);
          }
        }
      } catch (_error) {
        return '';
      }
      return '';
    };

    const findLocation = (value) => {
      const match = clean(value).match(/(Dubai|United Arab Emirates|UAE|Abu Dhabi|Ras al-Khaimah|Ras Al-Khaimah|Sharjah|Remote)/i);
      return match ? clean(match[1]) : '';
    };

    const clampDescription = (value, title, anchorTexts) => {
      const cleaned = clean(value);
      if (!cleaned) return '';

      const stopPhrases = [
        'discover more',
        'show more',
        'sign in to apply',
        'apply on employer site',
        'easy apply',
        'job type',
        'date posted',
        'requirement',
        'requirements',
        'skills',
        'qualification',
        'qualifications',
      ];

      const lower = cleaned.toLowerCase();
      let cutIndex = cleaned.length;

      for (const phrase of stopPhrases) {
        const idx = lower.indexOf(phrase);
        if (idx >= 0 && idx < cutIndex) {
          cutIndex = idx;
        }
      }

      for (const anchorText of anchorTexts) {
        if (!anchorText || anchorText === title) continue;
        const idx = lower.indexOf(anchorText.toLowerCase());
        if (idx >= 0 && idx < cutIndex) {
          cutIndex = idx;
        }
      }

      return clean(cleaned.slice(0, cutIndex));
    };

    const jobs = [];
    const seen = new Set();
    const anchors = Array.from(document.querySelectorAll('a'))
      .map((a) => ({ href: a.href || '', text: clean(a.innerText || a.textContent || '') }))
      .filter((item) => item.href && item.text && /glassdoor\./i.test(item.href));

    const bodyText = document.body?.innerText || '';
    const bodyLines = bodyText
      .split(/\n+/)
      .map(clean)
      .filter(Boolean);

    const jobAnchors = anchors.filter((item) => /\/job-listing\//i.test(item.href));
    for (const item of jobAnchors) {
      const title = clean(item.text);
      if (!title || isLikelyLocation(title) || isLikelyNoise(title) || !isLikelyTitle(title)) continue;
      const href = item.href;
      if (!href || seen.has(href)) continue;
      seen.add(href);

      const idx = bodyText.indexOf(title);
      const before = idx >= 0 ? bodyText.slice(Math.max(0, idx - 220), idx) : '';
      const after = idx >= 0 ? bodyText.slice(idx + title.length, idx + title.length + 360) : '';

      const beforeClean = stripContextNoise(before);
      const afterClean = stripContextNoise(after);
      const anchorTexts = jobAnchors.map((anchor) => clean(anchor.text)).filter(Boolean);
      let company = companyFromHref(href, title) || normalizeCompany(beforeClean);
      let location = findLocation(`${beforeClean} ${afterClean}`);

      if (!company) {
        company = 'Glassdoor';
      }
      if (!location) {
        location = /remote/i.test(`${beforeClean} ${afterClean}`) ? 'Remote' : '';
      }

      const description = clampDescription(
        afterClean
          .replace(location, '')
          .replace(/^(?:Dubai|United Arab Emirates|UAE|Abu Dhabi|Ras al-Khaimah|Ras Al-Khaimah|Sharjah|Remote)\b/i, ''),
        title,
        anchorTexts
      );

      jobs.push({
        source: 'glassdoor_uae',
        source_job_id: href,
        title,
        company,
        location,
        url: href,
        description,
        remote: /remote/i.test(`${title} ${company} ${location} ${description}`),
      });
    }

    return {
      pageTitle: document.title,
      href: location.href,
      jobs,
      debug: jobs.length ? undefined : {
        bodyLinesSample: bodyLines.slice(0, 80),
        anchorSamples: anchors.slice(0, 20),
      },
    };
  });
}

async function main() {
  const urls = process.argv.slice(2).filter(Boolean);
  const targetUrls = urls.length ? urls : defaultUrls();
  progress(`Browserless Glassdoor probe start urls=${targetUrls.length}`);
  const storageStatePath = getStorageStatePath();
  const canReuseStorageState = fs.existsSync(storageStatePath);
  const results = [];
  const allowCaptchaRetry = String(process.env.BROWSERLESS_ALLOW_CAPTCHA_RETRY ?? '1').toLowerCase() !== '0';
  const pageTimeoutMs = Number(process.env.GLASSDOOR_PAGE_TIMEOUT_MS || '18000');
  const selectorTimeoutMs = Number(process.env.GLASSDOOR_SELECTOR_TIMEOUT_MS || '8000');

  async function runWithMode({ solveCaptchas }) {
    const browserlessUrl = buildBrowserlessUrl({ solveCaptchas });
    const browser = await chromium.connectOverCDP(browserlessUrl);
    let context = null;

    try {
      try {
        const contextOptions = { serviceWorkers: 'block' };
        if (canReuseStorageState) {
          contextOptions.storageState = storageStatePath;
        }
        context = await browser.newContext(contextOptions);
      } catch (_error) {
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

      const runResults = [];
      for (let i = 0; i < targetUrls.length; i++) {
        const url = targetUrls[i];
        progress(`Glassdoor | start ${i + 1}/${targetUrls.length} | ${url} | captcha=${solveCaptchas ? 'on' : 'off'}`);
        const page = await context.newPage();
        try {
          await page.setViewportSize({ width: 1440, height: 1024 }).catch(() => {});
          page.setDefaultTimeout(selectorTimeoutMs);
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: pageTimeoutMs });
          await page.locator('a[href*="/job-listing/"]').first().waitFor({ timeout: selectorTimeoutMs }).catch(() => {});
          await expandGlassdoorMoreControls(page);
          await page.waitForLoadState('networkidle', { timeout: 3000 }).catch(() => {});
          const result = await extractGlassdoorJobs(page);
          progress(`Glassdoor | jobs=${result.jobs.length} | ${url}`);
          if (!result.jobs.length && result.debug) {
            progress(`Glassdoor | debug body_lines=${result.debug.bodyLinesSample.length} anchors=${result.debug.anchorSamples.length}`);
          }
          runResults.push(result);
        } finally {
          await page.close().catch(() => {});
        }
      }

      if (runResults.some((result) => result.jobs.length > 0)) {
        await context.storageState({ path: storageStatePath }).catch(() => {});
      }

      return runResults;
    } finally {
      await browser.close().catch(() => {});
    }
  }

  const firstPass = await runWithMode({ solveCaptchas: false });
  results.push(...firstPass);

  if (allowCaptchaRetry && results.some(shouldRetryWithCaptcha) && results.every((result) => result.jobs.length === 0)) {
    progress('Glassdoor | captcha-like block detected, retrying with captcha solving');
    const secondPass = await runWithMode({ solveCaptchas: true });
    process.stdout.write(JSON.stringify(secondPass, null, 2));
    return;
  }

  process.stdout.write(JSON.stringify(results, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
