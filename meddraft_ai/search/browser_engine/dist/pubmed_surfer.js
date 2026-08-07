export class PubMedSurfer {
    browser;
    constructor(browser) {
        this.browser = browser;
    }
    async search(page, query, limit = 10) {
        console.log(`🔍 PubMedSurfer: Searching PubMed for "${query}"`);
        await page.goto('https://pubmed.ncbi.nlm.nih.gov/', { waitUntil: 'domcontentloaded' });
        await this.browser.delay(2000, 3000);
        const searchInputSelector = '#id_term';
        await page.waitForSelector(searchInputSelector, { timeout: 10000 });
        await this.browser.typeHumanLike(page, searchInputSelector, query);
        await this.browser.delay(1000, 1500);
        await page.keyboard.press('Enter');
        await page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => { });
        await this.browser.delay(2000, 3000);
        // Wait for the results listing (either docsum or article-details page if only 1 result)
        const isSingleResult = await page.$('.article-details').then(r => !!r);
        if (isSingleResult) {
            console.log('ℹ️ PubMed redirected to a single article page.');
            const title = await page.$eval('.heading-title', el => el.textContent?.trim() || 'No Title');
            const pmid = await page.$eval('.current-id', el => el.textContent?.trim() || '');
            const authors = await page.$$eval('.full-name', els => els.map(el => el.textContent?.trim()).join(', '));
            const yearMatch = await page.$eval('.cit', el => el.textContent?.match(/\b(19|20)\d{2}\b/)?.[0] || '');
            const abstract = await page.$eval('#enc-abstract', el => el.textContent?.trim() || '');
            const pmidNum = pmid.replace(/\D/g, '');
            const url = `https://pubmed.ncbi.nlm.nih.gov/${pmidNum}/`;
            // Look for free full text links
            const pdfLink = await page.$eval('.full-text-links a', el => el.href).catch(() => null);
            return [{
                    index: 0,
                    pmid: pmidNum,
                    title,
                    snippet: abstract.slice(0, 300),
                    authors,
                    year: yearMatch,
                    url,
                    pdfLink,
                    hasDirectPDF: !!pdfLink && (pdfLink.includes('.pdf') || pdfLink.includes('pmc')),
                    titleAgentId: null
                }];
        }
        // Multiple results
        await page.waitForSelector('.search-results-list', { timeout: 10000 });
        const results = await page.evaluate(() => {
            const items = document.querySelectorAll('.docsum-content');
            let idCounter = 2000;
            return Array.from(items).map((el, idx) => {
                const titleLink = el.querySelector('.docsum-title');
                const snippetEl = el.querySelector('.full-view-snippet');
                const authorsEl = el.querySelector('.docsum-authors');
                const journalEl = el.querySelector('.docsum-journal-citation');
                let titleAgentId = null;
                if (titleLink) {
                    titleAgentId = idCounter++;
                    titleLink.setAttribute('data-agent-id', titleAgentId.toString());
                }
                const href = titleLink?.href || '';
                const pmidMatch = href.match(/\/(\d+)\/$/);
                const pmid = pmidMatch ? pmidMatch[1] : '';
                // Extract year from citation string
                const citText = journalEl?.textContent || '';
                const yearMatch = citText.match(/\b(19|20)\d{2}\b/);
                const year = yearMatch ? yearMatch[0] : '';
                return {
                    index: idx,
                    pmid,
                    title: titleLink?.textContent?.trim() || 'No Title',
                    snippet: snippetEl?.textContent?.trim() || '',
                    authors: authorsEl?.textContent?.trim() || '',
                    year,
                    url: href,
                    pdfLink: null, // Scraped inside article-details
                    hasDirectPDF: false,
                    titleAgentId
                };
            });
        });
        return results.slice(0, limit);
    }
}
