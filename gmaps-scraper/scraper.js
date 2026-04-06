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

    await page.setUserAgent(
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    );

    const url = `https://www.google.com/maps/search/${encodeURIComponent(query)}/@${lat},${long},15z?hl=pt-BR`;

    try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });

        await page.waitForSelector('a[href*="/maps/place/"]', { timeout: 15000 });

        await autoScroll(page, 'div[role="feed"]');

        const links = await page.$$eval(
            'a[href*="/maps/place/"]',
            anchors => anchors.map(a => a.href)
        );

        const uniqueLinks = [...new Set(links)].slice(0, 20);

        const results = [];

        for (const link of uniqueLinks) {
            try {
                await page.goto(link, { waitUntil: 'networkidle2', timeout: 30000 });

                await delay(1500 + Math.random() * 1500);

                let data = await page.evaluate(() => {
                    const getText = (selector) =>
                        document.querySelector(selector)?.innerText?.trim() || null;

                    const name = getText('h1');
                    const addressRaw = getText('[data-item-id="address"]');
                    const phoneRaw = getText('[data-item-id="phone"]');
                    const website =
                        document.querySelector('a[data-item-id="authority"]')?.href || null;

                    return { name, addressRaw, phoneRaw, website };
                });

                const bodyText = await page.evaluate(() => document.body.innerText);

                // ===== CEP =====
                let cep = null;
                const cepMatch = (data.addressRaw || bodyText).match(/\b\d{5}-?\d{3}\b/);
                if (cepMatch) {
                    cep = cepMatch[0].replace('-', '');
                }

                // ===== ENDEREÇO LIMPO (sem CEP) =====
                let address = data.addressRaw;
                if (address && cep) {
                    address = address.replace(cepMatch[0], '').replace(/\s{2,}/g, ' ').trim();
                }

                // fallback endereço
                if (!address) {
                    const match = bodyText.match(/(?:Rua|Av\.|Avenida|R\.)\s+[^\n,]+,\s*\d+/i);
                    address = match ? match[0] : null;
                }

                // ===== TELEFONE NORMALIZADO =====
                let phone = null;

                const normalizePhone = (raw) => {
                    if (!raw) return null;

                    let digits = raw.replace(/\D/g, '');

                    // remove código do país
                    if (digits.startsWith('55')) {
                        digits = digits.slice(2);
                    }

                    // precisa ter DDD + número
                    if (digits.length === 10 || digits.length === 11) {
                        return digits;
                    }

                    return null;
                };

                phone = normalizePhone(data.phoneRaw);

                // fallback regex
                if (!phone) {
                    const match = bodyText.match(/(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})-?\d{4}/);
                    phone = normalizePhone(match ? match[0] : null);
                }

                results.push({
                    name: data.name || null,
                    address,
                    cep,
                    phone,
                    website: data.website || null,
                    link
                });

            } catch (err) {
                console.log('Erro em item:', err.message);
            }
        }

        await browser.close();
        return results;

    } catch (error) {
        console.error('Scraping error:', error.message);
        await browser.close();
        return [];
    }
}

// ===== SCROLL ROBUSTO =====
async function autoScroll(page, selector) {
    await page.evaluate(async (selector) => {
        const container = document.querySelector(selector);
        if (!container) return;

        await new Promise((resolve) => {
            let lastHeight = 0;
            let sameCount = 0;

            const interval = setInterval(() => {
                container.scrollBy(0, 800);

                const newHeight = container.scrollHeight;

                if (newHeight === lastHeight) {
                    sameCount++;
                } else {
                    sameCount = 0;
                    lastHeight = newHeight;
                }

                if (sameCount >= 5) {
                    clearInterval(interval);
                    resolve();
                }
            }, 400);
        });
    }, selector);
}

// ===== DELAY HUMANO =====
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

module.exports = { scrapeGmaps };
