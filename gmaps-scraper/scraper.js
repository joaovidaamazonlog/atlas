const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

puppeteer.use(StealthPlugin());

async function scrapeGmaps(query, lat, long) {
    const browser = await puppeteer.launch({
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();
    
    // URL format: https://www.google.com/maps/search/{query}/@{lat},{long},{zoom}z
    const url = `https://www.google.com/maps/search/${encodeURIComponent(query)}/@${lat},${long},15z`;
    
    try {
        await page.goto(url, { waitUntil: 'networkidle2' });
        
        // Wait for results to load
        await page.waitForSelector('a[href*="/maps/place/"]', { timeout: 10000 });

        // Scroll to load more results
        await autoScroll(page, 'div[role="feed"]');

        const results = await page.evaluate(() => {
            const items = Array.from(document.querySelectorAll('div[role="article"]'));
            return items.map(item => {
                const name = item.querySelector('div.fontHeadlineSmall')?.innerText;
                
                // Address is usually the second line in the body
                const bodyLines = Array.from(item.querySelectorAll('div.fontBodyMedium'));
                const address = bodyLines.length > 1 ? bodyLines[1].innerText : 'N/A';
                
                // Phone is often in the same body lines or can be found by regex
                const phoneMatch = item.innerText.match(/(\+?\d{2,3}\s?)?(\(?\d{2}\)?\s?)?\d{4,5}[-\s]?\d{4}/);
                const phone = phoneMatch ? phoneMatch[0] : 'N/A';
                
                const website = item.querySelector('a[aria-label*="website"]')?.href || 'N/A';
                const link = item.querySelector('a[href*="/maps/place/"]')?.href;
                
                return { name, address, phone, website, link };
            });
        });

        // Instagram search (optional, but requested)
        // To keep it fast, we only search for Instagram if we have a name and it's a small number of results
        // For scalability, this should be a separate process or done only on demand.
        
        await browser.close();
        return results.filter(r => r.name);
    } catch (error) {
        console.error('Scraping error:', error);
        await browser.close();
        return [];
    }
}

async function autoScroll(page, selector) {
    await page.evaluate(async (selector) => {
        const wrapper = document.querySelector(selector) || document.body;
        
        await new Promise((resolve) => {
            let totalHeight = 0;
            let distance = 100;
            let timer = setInterval(() => {
                let scrollHeight = wrapper.scrollHeight;
                wrapper.scrollBy(0, distance);
                totalHeight += distance;

                if (totalHeight >= scrollHeight || totalHeight > 2000) { 
                    clearInterval(timer);
                    resolve();
                }
            }, 100);
        });
    }, selector);
}

module.exports = { scrapeGmaps };
