const { chromium } = require('playwright');

function textOrEmpty(node) {
  return (node?.innerText || node?.textContent || '').replace(/\s+/g, ' ').trim();
}

function progress(message) {
  console.error(message);
}

function shorten(text, maxLen = 72) {
  const normalized = (text || '').replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLen) {
    return normalized;
  }
  return `${normalized.slice(0, maxLen - 1).trimEnd()}…`;
}

function decodeQueryValue(value) {
  return decodeURIComponent((value || '').replace(/\+/g, ' '));
}

function classifyLocation(location) {
  const value = (location || '').toLowerCase();
  if (value.includes('united arab emirates') || value.includes('dubai')) return 'UAE';
  if (value.includes('georgia') || value.includes('tbilisi')) return 'Georgia';
  if (value.includes('malta')) return 'Malta';
  if (value.includes('qatar')) return 'Qatar';
  if (value.includes('bahrain')) return 'Bahrain';
  if (value.includes('saudi')) return 'Saudi Arabia';
  return location || 'Unknown';
}

function compactKeywords(value) {
  const text = decodeQueryValue(value)
    .replace(/\bOR\b/gi, ' / ')
    .replace(/\s+/g, ' ')
    .replace(/^["']|["']$/g, '')
    .trim();
  return shorten(text || 'search', 64);
}

function describeSearchUrl(url) {
  try {
    const parsed = new URL(url);
    if (url.includes('linkedin.com/jobs/search')) {
      const location = decodeQueryValue(parsed.searchParams.get('location') || '');
      return {
        platform: 'LinkedIn',
        country: classifyLocation(location),
        label: compactKeywords(parsed.searchParams.get('keywords') || ''),
      };
    }
    if (url.includes('linkedin.com/company/')) {
      const segments = parsed.pathname.split('/').filter(Boolean);
      const companySlug = segments[1] || 'company';
      return {
        platform: 'LinkedIn',
        country: 'Unknown',
        label: shorten(companySlug.replace(/[-_]+/g, ' '), 64),
      };
    }
    if (url.includes('indeed.com')) {
      const location = decodeQueryValue(parsed.searchParams.get('l') || parsed.searchParams.get('location') || '');
      return {
        platform: 'Indeed',
        country: classifyLocation(location),
        label: compactKeywords(parsed.searchParams.get('q') || parsed.searchParams.get('query') || ''),
      };
    }
    if (url.includes('gamblingcareers.com')) {
      return {
        platform: 'GamblingCareers',
        country: 'Remote',
        label: shorten(parsed.pathname.replace(/\/+/g, ' ').replace(/[-_]+/g, ' ').trim() || 'remote jobs', 64),
      };
    }
    if (url.includes('himalayas.app/jobs')) {
      return {
        platform: 'Himalayas',
        country: 'Remote',
        label: shorten(compactKeywords(parsed.pathname.split('/').pop() || 'igaming'), 64),
      };
    }
    if (url.includes('ziprecruiter.com/Jobs')) {
      return {
        platform: 'ZipRecruiter',
        country: 'Remote',
        label: shorten(compactKeywords(parsed.pathname.split('/').pop() || 'remote jobs'), 64),
      };
    }
  } catch {
    // Best-effort only.
  }
  return {
    platform: url.includes('linkedin.com') ? 'LinkedIn' : url.includes('indeed.com') ? 'Indeed' : 'Search',
    country: 'Unknown',
    label: shorten(url, 64),
  };
}

function errorResult(url, message) {
  return {
    pageTitle: 'Error',
    href: url,
    jobs: [],
    error: message,
  };
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

    // Detect Cloudflare security block
    const cloudflareBlock = document.body.textContent.includes('추가 확인이 필요합니다') ||
                           document.body.textContent.includes('Security Check') ||
                           document.body.textContent.includes('Cloudflare') ||
                           document.querySelector('[class*="challenge"]') ||
                           document.querySelector('iframe[src*="challenges"]');

    if (cloudflareBlock) {
      return {
        pageTitle: document.title,
        href: location.href,
        jobs: [],
        blocked: true,
        reason: 'Cloudflare security check detected',
      };
    }

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

      let snippetText = '';
      const snippetNode =
        card?.querySelector('.job-search-card__snippet') ||
        card?.querySelector('.base-search-card__snippet') ||
        card?.querySelector('[class*="snippet"]') ||
        card?.querySelector('[class*="description"]') ||
        card?.querySelector('p');

      if (snippetNode) {
        snippetText = clean(snippetNode.innerText);
      } else if (card) {
        const allText = Array.from(card.querySelectorAll('*'))
          .map((el) => clean(el.innerText || ''))
          .filter((t) => t.length > 30 && t !== title && t !== clean(companyNode ? companyNode.innerText : '') && t !== clean(locationNode ? locationNode.innerText : ''))
          .slice(0, 1)
          .join(' ');
        snippetText = allText;
      }

      const company = clean(companyNode ? companyNode.innerText : '');
      const location = clean(locationNode ? locationNode.innerText : '');
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

async function evaluateGamblingCareersPage(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const isLikelyTitle = (text) => {
      const value = clean(text);
      if (!value || value.length < 3 || value.length > 180) return false;
      if (/jobs found|find jobs|refine search|email me jobs like this|current search|refine by/i.test(value)) return false;
      if (/^\d+[dk]?$/i.test(value)) return false;
      return /[A-Za-z]/.test(value);
    };
    const splitCompanyLocation = (candidate) => {
      const value = clean(candidate);
      const patterns = [
        /^(?<company>.+?)\s+(?<location>Remote(?:\s*\([^)]*\))?)$/i,
        /^(?<company>.+?)\s+(?<location>Fully Remote(?:\s*\([^)]*\))?)$/i,
        /^(?<company>.+?)\s+(?<location>Hybrid(?:\s*\([^)]*\))?)$/i,
        /^(?<company>.+?)\s+(?<location>Onsite(?:\s*\([^)]*\))?)$/i,
      ];
      for (const pattern of patterns) {
        const match = value.match(pattern);
        if (match?.groups) {
          return {
            company: clean(match.groups.company),
            location: clean(match.groups.location),
          };
        }
      }
      const remoteMatch = value.match(/^(.*?)(\s+Remote(?:\s*\([^)]*\))?)$/i);
      if (remoteMatch) {
        return {
          company: clean(remoteMatch[1]),
          location: clean(remoteMatch[2]),
        };
      }
      return { company: value, location: '' };
    };
    const anchors = Array.from(document.querySelectorAll('a'))
      .map((a) => ({
        href: a.href || '',
        text: clean(a.innerText || a.textContent || ''),
        node: a,
      }))
      .filter((item) => item.href && item.text && /gamblingcareers\.com/i.test(item.href) && /\/job\//i.test(item.href));
    const jobs = [];
    const seen = new Set();
    const bodyText = document.body?.innerText || '';
    const bodyLines = bodyText
      .split(/\n+/)
      .map(clean)
      .filter(Boolean);

    for (const item of anchors) {
      const title = clean(item.text);
      if (!isLikelyTitle(title)) continue;
      if (seen.has(item.href)) continue;
      seen.add(item.href);

      const titleIndex = bodyLines.findIndex((line) => line.toLowerCase() === title.toLowerCase());
      const following = titleIndex >= 0 ? bodyLines.slice(titleIndex + 1) : [];

      let company = '';
      let locationText = '';
      let description = '';

      for (let i = 0; i < following.length && i < 6; i += 1) {
        const line = following[i];
        if (/jobs found|find jobs|refine search|email me jobs like this|current search|refine by/i.test(line)) {
          continue;
        }
        if (/^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$/i.test(line)) {
          continue;
        }
        if (/^(?:full time|part time|contract|contractor|temporary|internship)$/i.test(line)) {
          continue;
        }
        const split = splitCompanyLocation(line);
        if (split.location || /remote|hybrid|onsite/i.test(line)) {
          company = split.company;
          locationText = split.location;
          description = following.slice(i + 1, i + 4).join(' ');
          break;
        }
        if (!company) {
          company = split.company;
        }
      }

      if (!company) company = 'GamblingCareers';
      if (!locationText && /remote/i.test(`${title} ${following.join(' ')}`)) {
        locationText = 'Remote';
      }

      description = clean(description);
      if (!description) {
        const idx = bodyText.indexOf(title);
        if (idx >= 0) {
          description = clean(bodyText.slice(idx + title.length, idx + title.length + 450));
        }
      }
      for (const token of [title, company, locationText]) {
        if (token) {
          description = description.replace(token, ' ').replace(/\s+/g, ' ').trim();
        }
      }

      jobs.push({
        source: 'gamblingcareers_remote',
        source_job_id: item.href,
        title,
        company,
        location: locationText,
        url: item.href,
        description,
        remote: /remote/i.test(`${title} ${company} ${locationText} ${description}`),
      });
    }

    return {
      pageTitle: document.title,
      href: location.href,
      jobs,
      bodyLinesSample: bodyLines.slice(0, 80),
    };
  });
}

async function evaluateHimalayasPage(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
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
      ].includes(lowered)) return false;
      if (value.startsWith('$') || value.startsWith('Image:')) return false;
      return /[A-Za-z]/.test(value);
    };
    const anchors = Array.from(document.querySelectorAll('a[href*="/jobs/"], a[href*="/job/"]'))
      .map((a) => ({
        href: a.href || '',
        text: clean(a.innerText || a.textContent || ''),
        node: a,
      }))
      .filter((item) => item.href && isTitle(item.text));
    const jobs = [];
    const seen = new Set();

    for (const item of anchors) {
      if (seen.has(item.href)) continue;
      const card = item.node.closest('article, li, section, div') || item.node.parentElement;
      const lines = clean(card ? card.innerText : '')
        .split(/\n+/)
        .map(clean)
        .filter(Boolean);
      const title = item.text;
      if (!lines.length) continue;
      const titleIndex = lines.findIndex((line) => line.toLowerCase() === title.toLowerCase() || title.toLowerCase().includes(line.toLowerCase()) || line.toLowerCase().includes(title.toLowerCase()));
      if (titleIndex < 0) continue;

      const before = lines.slice(0, titleIndex);
      const after = lines.slice(titleIndex + 1);
      let company = '';
      for (const line of before.slice(-4).reverse()) {
        const lowered = line.toLowerCase();
        if (lowered.includes('quick apply') || lowered.includes('view job') || lowered.startsWith('$') || lowered.startsWith('image:')) {
          continue;
        }
        if (/[A-Za-z]/.test(line)) {
          company = line;
          break;
        }
      }
      let jobLocation = '';
      let description = '';
      for (let i = 0; i < after.length; i += 1) {
        const line = after[i];
        const lowered = line.toLowerCase();
        if (lowered.includes('remote') || lowered.includes('worldwide') || lowered.includes('fully remote') || lowered.includes('hybrid') || lowered.includes('location restrictions') || line.includes('·')) {
          jobLocation = line;
          description = after.slice(i + 1, i + 4).join(' ');
          break;
        }
      }
      if (!jobLocation && after.some((line) => /remote/i.test(line))) {
        jobLocation = 'Remote';
      }
      if (!company) company = 'Himalayas';
      if (!jobLocation) jobLocation = 'Remote';
      description = clean(description);

      const remote = /remote/i.test(`${title} ${company} ${jobLocation} ${description}`);
      const sourceJobId = item.href;
      if (!sourceJobId || seen.has(sourceJobId)) continue;
      seen.add(sourceJobId);

      jobs.push({
        source: 'himalayas_igaming',
        source_job_id: sourceJobId,
        title,
        company,
        location: jobLocation,
        url: item.href,
        description,
        remote,
      });
    }

    return {
      pageTitle: document.title,
      href: window.location.href,
      jobs,
    };
  });
}

async function evaluateZipRecruiterPage(page) {
  return page.evaluate(() => {
    const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
    const isTitle = (text) => {
      const value = clean(text);
      if (!value || value.length < 4 || value.length > 180) return false;
      const lowered = value.toLowerCase();
      if ([
        'quick apply',
        'estimated pay',
        'all jobs',
        'remote igaming jobs (now hiring)',
        'remote igaming information',
        'what is a remote igaming job?',
      ].includes(lowered)) return false;
      if (value.startsWith('$') || value.startsWith('Image:')) return false;
      return /[A-Za-z]/.test(value);
    };
    const normalizeLocation = (value) => {
      const text = clean(value);
      if (!text) return '';
      if (/remote/i.test(text)) return 'Remote';
      if (/on[- ]site/i.test(text)) return text;
      if (/hybrid/i.test(text)) return text;
      return text;
    };
    const anchors = Array.from(document.querySelectorAll('a[href*="/Jobs/"], a[href*="/jobs/"]'))
      .map((a) => ({
        href: a.href || '',
        text: clean(a.innerText || a.textContent || ''),
        node: a,
      }))
      .filter((item) => item.href && isTitle(item.text));
    const jobs = [];
    const seen = new Set();
    const addJob = ({ href, title, company, location, description }) => {
      const url = clean(href);
      const cleanedTitle = clean(title);
      if (!url || !cleanedTitle || seen.has(url)) return;
      seen.add(url);
      jobs.push({
        source: 'ziprecruiter_igaming',
        source_job_id: url,
        title: cleanedTitle,
        company: clean(company) || 'ZipRecruiter',
        location: normalizeLocation(location) || 'Remote',
        url,
        description: clean(description),
        remote: true,
      });
    };

    for (const item of anchors) {
      if (seen.has(item.href)) continue;
      const card = item.node.closest('article, li, section, div') || item.node.parentElement;
      const lines = clean(card ? card.innerText : '')
        .split(/\n+/)
        .map(clean)
        .filter(Boolean);
      const title = item.text;
      if (!lines.length) continue;
      const titleIndex = lines.findIndex((line) => line.toLowerCase() === title.toLowerCase() || title.toLowerCase().includes(line.toLowerCase()) || line.toLowerCase().includes(title.toLowerCase()));
      if (titleIndex < 0) continue;

      const before = lines.slice(0, titleIndex);
      const after = lines.slice(titleIndex + 1);
      let company = '';
      for (const line of before.slice(-4).reverse()) {
        const lowered = line.toLowerCase();
        if (lowered.includes('quick apply') || lowered.includes('estimated pay') || lowered.startsWith('$') || lowered.startsWith('image:') || lowered.includes('now hiring')) {
          continue;
        }
        if (/[A-Za-z]/.test(line)) {
          company = line;
          break;
        }
      }

      let jobLocation = '';
      let description = '';
      for (let i = 0; i < after.length; i += 1) {
        const line = after[i];
        const lowered = line.toLowerCase();
        if (lowered.includes('remote') || lowered.includes('on-site') || lowered.includes('onsite') || lowered.includes('hybrid') || line.includes('·')) {
          jobLocation = normalizeLocation(line);
          description = after.slice(i + 1, i + 4).join(' ');
          break;
        }
      }
      if (!jobLocation) jobLocation = 'Remote';
      if (!company) company = 'ZipRecruiter';
      addJob({ href: item.href, title, company, location: jobLocation, description });
    }

    if (!jobs.length) {
      const bodyLines = clean(document.body ? document.body.innerText : '')
        .split(/\n+/)
        .map(clean)
        .filter(Boolean);
      const hrefByTitle = new Map();
      for (const item of anchors) {
        const key = item.text.toLowerCase();
        if (!hrefByTitle.has(key)) hrefByTitle.set(key, item.href);
      }

      const isLikelyJobLine = (line) => {
        const value = clean(line);
        if (!value || value.length < 10 || value.length > 260) return false;
        const lowered = value.toLowerCase();
        if ([
          'quick apply',
          'estimated pay',
          'all jobs',
          'remote igaming jobs (now hiring)',
          'remote igaming information',
          'what is a remote igaming job?',
        ].includes(lowered)) return false;
        if (value.startsWith('$') || value.startsWith('Image:')) return false;
        if (!/[A-Za-z]/.test(value)) return false;
        return /(remote|igaming|gaming|casino|sweepstakes|reviewer|analyst|manager|specialist|developer|engineer|writer|editor|sales|marketing|content|affiliate|payments?|risk|compliance|product|support)/i.test(value) || value.split(/\s+/).length >= 3;
      };

      for (let i = 0; i < bodyLines.length; i += 1) {
        const title = bodyLines[i];
        if (!isLikelyJobLine(title)) continue;
        const key = title.toLowerCase();
        const href = hrefByTitle.get(key)
          || Array.from(hrefByTitle.entries()).find(([text]) => text.includes(key) || key.includes(text))?.[1]
          || '';
        if (!href) continue;

        const prev = bodyLines.slice(Math.max(0, i - 3), i).reverse().find((line) => {
          const lowered = line.toLowerCase();
          return lowered && !lowered.includes('quick apply') && !lowered.includes('estimated pay') && !lowered.startsWith('$') && !lowered.includes('now hiring');
        }) || '';
        const next = bodyLines.slice(i + 1, i + 4).find((line) => /remote|on-site|onsite|hybrid|·/i.test(line));
        const description = bodyLines.slice(i + 1, i + 7).join(' ');
        addJob({ href, title, company: prev || 'ZipRecruiter', location: next ? normalizeLocation(next) : 'Remote', description });
      }
    }

    return {
      pageTitle: document.title,
      href: window.location.href,
      jobs,
    };
  });
}

async function handleIndeedWithPlaywright(page, url) {
  try {
    const searchContext = describeSearchUrl(url);
    progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | start`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });

    // Wait for Cloudflare challenge to complete
    let attempts = 0;
    while (attempts < 15) {
      const title = await page.title();
      if (title === 'Just a moment...') {
        progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | challenge ${attempts + 1}/15`);
        await new Promise(resolve => setTimeout(resolve, 2000));
        attempts++;
      } else {
        break;
      }
    }

    await new Promise(resolve => setTimeout(resolve, 3000 + Math.random() * 1000));

    const result = await evaluateIndeedPage(page);
    progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | jobs=${result.jobs?.length || 0}`);
    return result;
  } catch (error) {
    const searchContext = describeSearchUrl(url);
    progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | error ${error.message}`);
    console.error(`Playwright error for Indeed: ${error.message}`);
    return {
      pageTitle: 'Error',
      href: url,
      jobs: [],
      error: error.message,
    };
  }
}

async function main() {
  const urls = process.argv.slice(2).filter(Boolean);
  if (!urls.length) {
    throw new Error('Usage: node browser_probe.js <url> [<url> ...]');
  }

  const headlessEnv = String(process.env.BROWSER_HEADLESS || '').toLowerCase();
  const hasTelegramUrl = urls.some(url => url.includes('t.me/s/'));
  // Always use headless mode for speed; Telegram works fine headless
  const headless = (headlessEnv !== '0' && headlessEnv !== 'false');
  progress(`probe start urls=${urls.length} headless=${headless} telegram=${hasTelegramUrl}`);

  const profileDir = require('path').join(
    require('os').tmpdir(),
    `chrome-profile-${Date.now()}-${process.pid}-${Math.random().toString(36).slice(2, 8)}`
  );
  let browserContext;
  let browser;
  const results = [];
  const executablePathCandidates = [chromium.executablePath()].filter(Boolean);

  try {
    let launchError = null;
    for (const executablePath of executablePathCandidates) {
      try {
        browserContext = await chromium.launchPersistentContext(
          profileDir,
          {
            executablePath,
            // Default to background mode so the browser does not steal focus during batch runs.
            headless,
            userAgent:
              'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            viewport: { width: 1280, height: 720 },
            javaScriptEnabled: true,
            ignoreHTTPSErrors: true,
            args: [
              '--disable-blink-features=AutomationControlled',
              '--disable-dev-shm-usage',
              '--no-first-run',
              '--no-default-browser-check',
            ],
          }
        );
        launchError = null;
        break;
      } catch (err) {
        launchError = err;
      }
    }
    if (!browserContext) {
      throw launchError || new Error('Unable to launch browser context');
    }

    browser = browserContext.browser();

    for (let i = 0; i < urls.length; i++) {
      const url = urls[i];
      const searchContext = describeSearchUrl(url);
      let page;
      try {
        progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | start ${i + 1}/${urls.length}`);
        if (i > 0) {
          await new Promise(resolve => setTimeout(resolve, 2000 + Math.random() * 2000));
        }

        try {
          page = await browserContext.newPage();
        } catch (err) {
          progress(`Failed to create page (context closed?): ${err.message}`);
          results.push(errorResult(url, 'Browser context unavailable'));
          continue;
        }
        await page.addInitScript(() => {
          Object.defineProperty(navigator, 'webdriver', { get: () => false });
          Object.defineProperty(navigator, 'plugins', {
            get: () => [
              { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
              { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            ],
          });
          Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
          window.chrome = { runtime: {} };
          Object.defineProperty(navigator, 'permissions', {
            get: () => ({
              query: () => Promise.resolve({ state: Notification.permission }),
            }),
          });
        });

        if (url.includes('indeed.com')) {
          results.push(await handleIndeedWithPlaywright(page, url));
          try {
            await page.close();
          } catch {
            // Page already closed, create a new one for next iteration
          }
          continue;
        }

        if (url.includes('gamblingcareers.com')) {
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | load`);
          await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 120000 });
          await page.waitForLoadState('domcontentloaded').catch(() => {});
          await page.waitForLoadState('networkidle').catch(() => {});
          await page.waitForSelector('a[href*="/job/"]', { timeout: 30000 }).catch(() => {});
          await page.waitForTimeout(2500 + Math.random() * 1000);
          const result = await evaluateGamblingCareersPage(page);
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | jobs=${result.jobs?.length || 0}`);
          results.push(result);
          await page.close().catch(() => {});
          continue;
        }

        if (url.includes('himalayas.app/jobs')) {
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | load`);
          await page.waitForLoadState('domcontentloaded').catch(() => {});
          await page.waitForLoadState('networkidle').catch(() => {});
          await page.waitForSelector('a[href*="/jobs/"], a[href*="/job/"]', { timeout: 30000 }).catch(() => {});
          await page.waitForTimeout(2000 + Math.random() * 1000);
          const result = await evaluateHimalayasPage(page);
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | jobs=${result.jobs?.length || 0}`);
          results.push(result);
          await page.close().catch(() => {});
          continue;
        }

        if (url.includes('ziprecruiter.com/Jobs')) {
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | load`);
          await page.waitForLoadState('domcontentloaded').catch(() => {});
          await page.waitForLoadState('networkidle').catch(() => {});
          await page.waitForSelector('a[href*="/Jobs/"], a[href*="/jobs/"]', { timeout: 30000 }).catch(() => {});
          await page.waitForTimeout(2500 + Math.random() * 1000);
          const result = await evaluateZipRecruiterPage(page);
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | jobs=${result.jobs?.length || 0}`);
          results.push(result);
          await page.close().catch(() => {});
          continue;
        }

        const isTelegram = url.includes('t.me/s/');
        const waitUntilOption = isTelegram ? 'networkidle' : 'domcontentloaded';
        await page.goto(url, { waitUntil: waitUntilOption, timeout: isTelegram ? 180000 : 120000 });

        if (url.includes('linkedin.com/jobs/search') || url.includes('linkedin.com/company/')) {
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | load`);
          await page.waitForLoadState('domcontentloaded').catch(() => {});
          await page.waitForLoadState('networkidle').catch(() => {});
          await page.waitForSelector('a.base-card__full-link, a[data-job-id], a.job-card-title, a[href*="/jobs/view/"]', { timeout: 30000 }).catch(() => {});
          await page.waitForTimeout(3000 + Math.random() * 1000);

          let previousHeight = 0;
          let scrolls = 0;
          // Keep LinkedIn pagination lighter; most runs do not need a deep scroll sweep.
          const maxScrolls = 2;
          while (scrolls < maxScrolls) {
            const newHeight = await page.evaluate(() => document.documentElement.scrollHeight);
            if (newHeight === previousHeight) break;

            progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | scroll ${scrolls + 1}/${maxScrolls}`);
            await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
            await page.waitForTimeout(2000 + Math.random() * 1000);
            previousHeight = newHeight;
            scrolls++;
          }

          await expandLinkedInMoreButtons(page);
          await page.waitForTimeout(3000 + Math.random() * 2000);

          const result = await evaluateLinkedInPage(page);
          progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | jobs=${result.jobs?.length || 0}`);
          results.push(result);
          await page.close().catch(() => {});
          continue;
        }
      } catch (error) {
        progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | error ${error.message}`);
        console.error(`Error processing ${url}: ${error.message}`);
        results.push(errorResult(url, error.message));
        continue;
      }

      if (url.includes('t.me/s/')) {
        progress(`Telegram | ${searchContext.label} | load complete`);
        // Wait for Telegram JavaScript rendering
        try {
          await page.waitForFunction(() => {
            const messages = document.querySelectorAll('.tgme_widget_message');
            return messages.length > 0;
          }, { timeout: 15000 }).catch(() => {});
        } catch {
          // Best effort
        }
        await page.waitForTimeout(2000);
        results.push(await evaluateTelegramPage(page));
        await page.close().catch(() => {});
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
      progress(`${searchContext.platform} ${searchContext.country} | ${searchContext.label} | done`);
      results.push(result);
      await page.close().catch(() => {});
    }
  } catch (error) {
    progress(`browser launch failed: ${error.message}`);
    console.error(`Browser launch failed: ${error.message}`);
    urls.forEach((url) => results.push(errorResult(url, error.message)));
  } finally {
    if (browserContext) {
      try {
        await browserContext.close();
      } catch {
        // Ignore cleanup errors.
      }
    }
    if (browser) {
      try {
        await browser.close();
      } catch {
        // Ignore cleanup errors.
      }
    }

    try {
      const { rmSync } = require('fs');
      rmSync(profileDir, { recursive: true, force: true });
    } catch {
      // Ignore cleanup errors
    }
  }

  console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(0);
});
