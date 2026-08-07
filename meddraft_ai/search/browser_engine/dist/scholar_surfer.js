export class ScholarSurfer {
    browser;
    constructor(browser) {
        this.browser = browser;
    }
    async search(page, query, limit = 10) {
        console.log(`🔍 ScholarSurfer: Searching Google Scholar for "${query}"`);
        // Navigate to Google Scholar landing page
        await page.goto('https://scholar.google.com', { waitUntil: 'domcontentloaded' });
        await this.browser.delay(2000, 3000);
        // Solve captcha if present on load
        await this.browser.solveReCaptcha(page);
        // Locate the search input
        const searchInputSelector = 'input[name="q"]';
        await page.waitForSelector(searchInputSelector, { timeout: 10000 });
        // Type query like a human
        await this.browser.typeHumanLike(page, searchInputSelector, query);
        await this.browser.delay(1000, 1500);
        // Press Enter to submit
        await page.keyboard.press('Enter');
        await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => { });
        await this.browser.delay(2000, 3000);
        // Check for captcha again on results load
        await this.browser.solveReCaptcha(page);
        // Wait for the results container
        const resultsContainerSelector = '#gs_res_ccl_mid';
        try {
            await page.waitForSelector(resultsContainerSelector, { timeout: 10000 });
        }
        catch (e) {
            console.log('⚠️ Scholar results container not found, checking if captcha is blocking...');
            const captchaSolved = await this.browser.solveReCaptcha(page);
            if (captchaSolved) {
                await page.waitForSelector(resultsContainerSelector, { timeout: 10000 });
            }
            else {
                throw new Error('Blocked by Google Scholar CAPTCHA or results failed to load.');
            }
        }
        // Now extract search results using page.evaluate
        const results = await page.evaluate(() => {
            const items = document.querySelectorAll('.gs_r.gs_or.gs_scl');
            let idCounter = 1000; // Offset agent IDs for results to avoid overlap
            return Array.from(items).map((el, idx) => {
                const titleEl = el.querySelector('.gs_rt a');
                const pdfEl = el.querySelector('.gs_or_ggside a');
                const snippetEl = el.querySelector('.gs_rs');
                const metaEl = el.querySelector('.gs_a');
                // Assign data-agent-id to title and PDF links
                let titleAgentId = null;
                let pdfAgentId = null;
                if (titleEl) {
                    titleAgentId = idCounter++;
                    titleEl.setAttribute('data-agent-id', titleAgentId.toString());
                }
                if (pdfEl) {
                    pdfAgentId = idCounter++;
                    pdfEl.setAttribute('data-agent-id', pdfAgentId.toString());
                }
                // Parse meta info (e.g. "JD Doe, MD Smith - New England Journal of Medicine, 2021 - nejm.org")
                const metaText = metaEl?.textContent || '';
                let authors = '';
                let year = '';
                const yearMatch = metaText.match(/\b(19|20)\d{2}\b/);
                if (yearMatch)
                    year = yearMatch[0];
                const authorParts = metaText.split('-');
                if (authorParts.length > 0)
                    authors = authorParts[0].trim();
                // Parse citations
                let citations = 0;
                const links = el.querySelectorAll('.gs_fl a');
                links.forEach((link) => {
                    const text = link.textContent || '';
                    if (text.includes('Cited by')) {
                        const citeMatch = text.match(/\d+/);
                        if (citeMatch)
                            citations = parseInt(citeMatch[0], 10);
                    }
                });
                return {
                    index: idx,
                    title: titleEl?.textContent?.trim() || el.querySelector('.gs_rt')?.textContent?.trim() || 'No Title',
                    snippet: snippetEl?.textContent?.trim() || '',
                    authors,
                    year,
                    citations,
                    url: titleEl?.href || null,
                    pdfLink: pdfEl?.href || null,
                    hasDirectPDF: !!pdfEl,
                    titleAgentId,
                    pdfAgentId
                };
            });
        });
        return results.slice(0, limit);
    }
}
