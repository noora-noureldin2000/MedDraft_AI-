/**
 * Google Images scraper used only as the final, no-API-key fallback.
 * The API providers (SerpApi -> Google CSE -> Brave) stay first in the chain.
 */
export class ImageSurfer {
    browser;
    constructor(browser) {
        this.browser = browser;
    }
    async search(page, query, limit = 10) {
        const searchUrl = `https://www.google.com/search?tbm=isch&hl=en&q=${encodeURIComponent(query)}`;
        console.log(`🖼️ ImageSurfer: searching Google Images for "${query}"`);
        await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
        await this.browser.delay(1500, 2500);
        await this.acceptConsent(page);
        await this.browser.solveReCaptcha(page);
        const blocked = await page.evaluate(() => {
            const text = (document.body?.innerText || '').toLowerCase();
            if (text.includes('unusual traffic') || text.includes('not a robot'))
                return 'captcha';
            if (text.includes('before you continue'))
                return 'consent';
            return '';
        });
        if (blocked) {
            const solved = await this.browser.solveReCaptcha(page);
            if (!solved) {
                throw new Error(`Google Images blocked the request (${blocked}). Run with BROWSER_HEADLESS=false ` +
                    'and solve the challenge manually, or use SerpApi / Google CSE / Brave.');
            }
            await page.waitForLoadState('domcontentloaded').catch(() => { });
            await this.browser.delay(1500, 2500);
        }
        // Trigger lazy loading so the result anchors and image nodes exist.
        for (let i = 0; i < 3; i++) {
            await page.mouse.wheel(0, 1200);
            await this.browser.delay(400, 800);
        }
        await page.waitForSelector('a[href*="imgres"], img', { timeout: 10000 }).catch(() => { });
        const results = await page.evaluate((max) => {
            const out = [];
            const seen = new Set();
            const clean = (value) => (value || '').replace(/\s+/g, ' ').trim().slice(0, 300);
            const absolute = (value) => {
                try {
                    return new URL(value, location.origin).href;
                }
                catch {
                    return '';
                }
            };
            const paramsFor = (value) => {
                try {
                    return new URL(value, location.origin).searchParams;
                }
                catch {
                    return null;
                }
            };
            const positive = (value) => Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
            const add = (imageUrl, thumbnailUrl, contextUrl, title, width, height) => {
                if (out.length >= max)
                    return;
                if (!/^https?:\/\//i.test(imageUrl))
                    return;
                const key = imageUrl.split('#')[0];
                if (seen.has(key))
                    return;
                seen.add(key);
                const pageUrl = /^https?:\/\//i.test(contextUrl) ? contextUrl : '';
                out.push({
                    index: out.length,
                    title: clean(title) || `Image ${out.length + 1}`,
                    imageUrl: key,
                    thumbnailUrl: /^https?:\/\//i.test(thumbnailUrl) ? thumbnailUrl : key,
                    contextUrl: pageUrl,
                    width: positive(width),
                    height: positive(height),
                });
            };
            // Google's result anchors carry the full-size image (imgurl) and the
            // source page (imgrefurl) as query parameters.
            const anchors = Array.from(document.querySelectorAll('a[href*="imgres"], a[href*="imgurl="]'));
            for (const anchor of anchors) {
                if (out.length >= max)
                    break;
                const params = paramsFor(anchor.href);
                if (!params)
                    continue;
                const imageUrl = params.get('imgurl') || '';
                if (!/^https?:\/\//i.test(imageUrl))
                    continue;
                const img = anchor.querySelector('img');
                const thumbnail = img ? img.currentSrc || img.src || '' : '';
                const title = clean(img?.alt) || clean(anchor.getAttribute('aria-label')) || clean(anchor.textContent);
                add(imageUrl, thumbnail, absolute(params.get('imgrefurl') || ''), title, Number(params.get('w')), Number(params.get('h')));
            }
            // Fallback for layouts where only thumbnail nodes are exposed.
            if (out.length < max) {
                const images = Array.from(document.querySelectorAll('img'));
                for (const img of images) {
                    if (out.length >= max)
                        break;
                    const src = img.currentSrc || img.src || '';
                    if (!/^https?:\/\//i.test(src))
                        continue;
                    if ((img.naturalWidth || 0) < 120 || (img.naturalHeight || 0) < 80)
                        continue;
                    if (/gstatic\.com\/images\/(branding|ui)|favicon|sprite|logo/i.test(src))
                        continue;
                    add(src, src, '', img.alt, img.naturalWidth, img.naturalHeight);
                }
            }
            return out;
        }, Math.max(1, Math.min(limit, 50)));
        return results;
    }
    async acceptConsent(page) {
        const selectors = [
            'button#L2AGLb',
            'button:has-text("Accept all")',
            'button:has-text("I agree")',
            'div[role="none"] button:has-text("Accept all")',
        ];
        for (const selector of selectors) {
            const button = page.locator(selector).first();
            if ((await button.count()) === 0)
                continue;
            await button.click({ timeout: 3000 }).catch(() => { });
            await this.browser.delay(800, 1500);
            return;
        }
    }
}
