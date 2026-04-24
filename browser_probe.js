const { chromium } = require('playwright-core');

function textOrEmpty(node) {
  return (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
}

async function expandLinkedInMoreButtons(page) {
  try {
    await page.evaluate(() => {
      const candidates = Array.from(document.querySelectorAll('button, [role="button"]'));
      for (const el of candidates) {
        const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
        if (!text) continue;
        if (!/(more|show more|see more|expand)/i.test(text)) continue;
        try {
          el.click();
        } catch {
          // Ignore individual failures; we only want to expand what is visible.
        }
      }
    });
  } catch {
    // Best-effort only.
  }
}

async function evaluateIndeedPage(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const jobCards = Array.from(document.querySelectorAll('[data-testid="slider_container"]'));
    const jobs = [];

    for (const card of jobCards) {
      const titleAnchor =
        card.querySelector('a.jcs-JobTitle') ||
        card.querySelector('h2 a') ||
        card.querySelector('a[href*="/rc/clk"], a[href*="/viewjob"], a[href*="/pagead/clk"]');

      if (!titleAnchor) {
        continue;
      }

      const title = clean(titleAnchor.innerText);
      const url = titleAnchor.href || '';
      const sourceJobIdMatch = url.match(/[?&]jk=([^&]+)/);
      const sourceJobId = sourceJobIdMatch ? sourceJobIdMatch[1] : url.replace(/.*\//, '');
      const companyNode =
        card.querySelector('[data-testid="company-name"]') ||
        card.querySelector('[data-testid="company-name"] span') ||
        card.querySelector('span[data-testid="company-name"]');
      const locationNode =
        card.querySelector('[data-testid="text-location"]') ||
        card.querySelector('[data-testid="text-location"] div') ||
        card.querySelector('[data-testid="text-location"] span');
      const company = clean(companyNode ? companyNode.innerText : '');
      const location = clean(locationNode ? locationNode.innerText : '');
      const snippetNodes = Array.from(card.querySelectorAll(
        '[data-testid*="attribute_snippet_testid"], [data-testid="belowJobSnippet"], ' +
        '[class*="snippet"], [class*="description"], li'
      ));
      const snippetText = clean(snippetNodes.map((node) => node.innerText || '').join(' '));
      const description = snippetText || clean(
        Array.from(card.querySelectorAll('span, div'))
          .map((el) => el.innerText || '')
          .filter((t) => t.length > 20 && t !== title && t !== company && t !== location)
          .slice(0, 3)
          .join(' ')
      );

      if (!title || !url) {
        continue;
      }

      jobs.push({
        source: 'indeed_uae',
        source_job_id: sourceJobId,
        title,
        company: company || 'Indeed',
        location,
        url,
        description,
        remote: /remote/i.test(`${title} ${location} ${description}`),
      });
    }

    const links = Array.from(document.querySelectorAll('a'))
      .map((a) => ({
        text: clean(a.innerText),
        href: a.href || '',
        testid: a.getAttribute('data-testid') || '',
        cls: a.className || '',
      }))
      .filter((item) => item.text && item.href)
      .slice(0, 80);

    const testIds = Array.from(document.querySelectorAll('[data-testid]'))
      .map((el) => el.getAttribute('data-testid'))
      .filter(Boolean)
      .slice(0, 120);

    return {
      pageTitle: document.title,
      href: location.href,
      testIds,
      links,
      jobs,
    };
  });
}

async function evaluateLinkedInPage(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const jobAnchors = Array.from(document.querySelectorAll(
      'a.base-card__full-link, ' +
      'a[data-job-id], ' +
      'a.job-card-title'
    ));
    const jobs = [];
    const seenUrls = new Set();

    for (const anchor of jobAnchors) {
      const card = anchor.closest('li') || anchor.closest('.base-card') || anchor.parentElement;
      const title = clean(anchor.innerText);
      const url = anchor.href || '';
      const sourceJobIdMatch = url.match(/\/jobs\/view\/[^-]+-(\d+)/) || url.match(/currentJobId=(\d+)/) || url.match(/\/jobs\/view\/(\d+)/);
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
      const snippetText = clean(snippetNode ? snippetNode.innerText : '');
      const description = snippetText || clean(
        Array.from(card?.querySelectorAll('span, div, p') || [])
          .map((el) => el.innerText || '')
          .filter((t) => t.length > 20 && t !== title && t !== company && t !== location)
          .slice(0, 3)
          .join(' ')
      );

      if (!title || !url || seenUrls.has(url)) {
        continue;
      }
      seenUrls.add(url);

      jobs.push({
        source: 'linkedin_public',
        source_job_id: sourceJobIdMatch ? sourceJobIdMatch[1] : url,
        title,
        company: company || 'LinkedIn',
        location,
        url,
        description,
        remote: /remote/i.test(`${title} ${location} ${description}`),
      });
    }

    const links = Array.from(document.querySelectorAll('a'))
      .map((a) => ({
        text: clean(a.innerText),
        href: a.href || '',
        testid: a.getAttribute('data-testid') || '',
        cls: a.className || '',
      }))
      .filter((item) => item.text && item.href)
      .slice(0, 120);

    return {
      pageTitle: document.title,
      href: location.href,
      links,
      jobs,
    };
  });
}

async function evaluateTelegramPage(page) {
  return page.evaluate(() => ({
    pageTitle: document.title,
    href: location.href,
    html: document.documentElement.outerHTML,
  }));
}

async function main() {
  const urls = process.argv.slice(2).filter(Boolean);
  if (!urls.length) {
    throw new Error('Usage: node browser_probe.js <url> [<url> ...]');
  }

  const browser = await chromium.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: process.env.BROWSER_HEADLESS !== 'false',
  });

  const context = await browser.newContext({
    userAgent:
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 720 },
  });

  const page = await context.newPage();

  const results = [];

  for (const url of urls) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });

      if (url.includes('indeed.com')) {
        await page.waitForLoadState('domcontentloaded').catch(() => {});
        await page.waitForSelector('[data-testid="slider_container"]', { timeout: 20000 }).catch(() => {});
        await page.waitForTimeout(2000);
        results.push(await evaluateIndeedPage(page));
        continue;
      }

      if (url.includes('linkedin.com/jobs/search')) {
        await page.waitForLoadState('domcontentloaded').catch(() => {});
        await page.waitForSelector('a.base-card__full-link', { timeout: 25000 }).catch(() => {});
        await page.waitForTimeout(2000);
        await page.waitForTimeout(3000);

        let previousHeight = 0;
        let scrolls = 0;
        const maxScrolls = 8;
        while (scrolls < maxScrolls) {
          const newHeight = await page.evaluate(() => document.documentElement.scrollHeight);
          if (newHeight === previousHeight) break;

          await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
          await page.waitForTimeout(1500);
          previousHeight = newHeight;
          scrolls++;
        }

        await expandLinkedInMoreButtons(page);
        await page.waitForTimeout(1000);

        results.push(await evaluateLinkedInPage(page));
        continue;
      }
    } catch (error) {
      console.error(`Error processing ${url}: ${error.message}`);
      results.push({
        pageTitle: 'Error',
        href: url,
        jobs: [],
        error: error.message,
      });
      continue;
    }

    if (url.includes('t.me/s/')) {
      results.push(await evaluateTelegramPage(page));
      continue;
    }

    const result = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a'))
        .map((a) => ({
          text: (a.innerText || '').trim(),
          href: a.href || '',
          testid: a.getAttribute('data-testid') || '',
          cls: a.className || '',
        }))
        .filter((item) => item.text && item.href)
        .slice(0, 120);
      return {
        pageTitle: document.title,
        href: location.href,
        links,
      };
    });
    results.push(result);
  }

  console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 2));
  await context.close();
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
