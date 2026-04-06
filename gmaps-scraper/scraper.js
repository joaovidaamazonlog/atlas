const puppeteer = require('puppeteer');

async function scrapeGmaps(query, lat, long) {
    const browser = await puppeteer.launch({
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu'
        ]
    });
    const page = await browser.newPage();

    // User-agent para evitar bloqueio básico
    await page.setUserAgent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    );

    const url = `https://www.google.com/maps/search/${encodeURIComponent(query)}/@${lat},${long},15z?hl=pt-BR`;

    try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });

        // Aguardar resultados
        await page.waitForSelector('a[href*="/maps/place/"]', { timeout: 15000 })
            .catch(() => null);

        // Scroll para carregar mais resultados
        await autoScroll(page, 'div[role="feed"]');

        const results = await page.evaluate(() => {
            const items = Array.from(document.querySelectorAll('div[role="article"]'));
            return items.map(item => {
                const name = item.querySelector('div.fontHeadlineSmall')?.innerText?.trim();

                const bodyLines = Array.from(item.querySelectorAll('div.fontBodyMedium span'));
                const address = bodyLines.find(el => el.innerText?.match(/\d{5}-?\d{3}|Rua|Av\.|Avenida/i))?.innerText?.trim() || 'N/A';

                const phoneMatch = item.innerText.match(/(\(?\d{2}\)?\s?)?\d{4,5}[-\s]?\d{4}/);
                const phone = phoneMatch ? phoneMatch[0].trim() : 'N/A';

                const website = item.querySelector('a[data-value="Website"]')?.href || 'N/A';
                const link = item.querySelector('a[href*="/maps/place/"]')?.href || 'N/A';

                return { name, address, phone, website, link };
            });
        });

        await browser.close();
        return results.filter(r => r.name);

    } catch (error) {
        console.error('Scraping error:', error.message);
        await browser.close();
        return [];
    }
}

async function autoScroll(page, selector) {
    await page.evaluate(async (selector) => {
        const wrapper = document.querySelector(selector) || document.body;
        await new Promise((resolve) => {
            let totalHeight = 0;
            const distance = 200;
            const timer = setInterval(() => {
                wrapper.scrollBy(0, distance);
                totalHeight += distance;
                if (totalHeight >= wrapper.scrollHeight || totalHeight > 3000) {
                    clearInterval(timer);
                    resolve();
                }
            }, 150);
        });
    }, selector);
}

module.exports = { scrapeGmaps };
