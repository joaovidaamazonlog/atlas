/**
 * scraper.js
 * ==========
 * Scraping do Google Maps via Puppeteer com paralelismo controlado.
 *
 * Estratégia de paralelismo
 * -------------------------
 * - 1 browser compartilhado por chamada a scrapeGmaps
 * - N abas abertas simultaneamente (CONCURRENCY = 3 por padrão)
 * - Delay humano aleatório por aba para evitar detecção
 * - Coordenadas extraídas do link original (mais estável que URL da página)
 */

const puppeteer = require('puppeteer');

/** Número de abas abertas simultaneamente por busca */
const CONCURRENCY = 3;

/** User-agent para evitar bloqueio básico */
const USER_AGENT =
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36';

// ---------------------------------------------------------------------------
// FUNÇÃO PRINCIPAL
// ---------------------------------------------------------------------------

/**
 * Busca estabelecimentos no Google Maps para uma query e localização.
 *
 * @param {string} query  - Tipo de negócio (ex: "lanchonete")
 * @param {string} lat    - Latitude do centroide do território
 * @param {string} long   - Longitude do centroide do território
 * @returns {Promise<Object[]>}
 */
async function scrapeGmaps(query, lat, long) {
    const browser = await puppeteer.launch({
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
    });

    try {
        // ── 1. Coletar links da página de resultados ──────────────────────
        const searchPage = await browser.newPage();
        await searchPage.setUserAgent(USER_AGENT);

        const url = `https://www.google.com/maps/search/${encodeURIComponent(query)}/@${lat},${long},15z?hl=pt-BR`;
        await searchPage.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        await searchPage.waitForSelector('a[href*="/maps/place/"]', { timeout: 15000 }).catch(() => null);
        await autoScroll(searchPage, 'div[role="feed"]');

        const links = await searchPage.$$eval(
            'a[href*="/maps/place/"]',
            anchors => [...new Set(anchors.map(a => a.href))]
        );
        await searchPage.close();

        const uniqueLinks = links.slice(0, 20);
        console.log(`    [scraper] ${uniqueLinks.length} links coletados para "${query}"`);

        // ── 2. Processar links em paralelo com concorrência limitada ──────
        const results = await _processWithConcurrency(browser, uniqueLinks, CONCURRENCY);

        return results.filter(r => r.name);

    } catch (error) {
        console.error('[scraper] Erro:', error.message);
        return [];
    } finally {
        await browser.close();
    }
}

// ---------------------------------------------------------------------------
// PROCESSAMENTO PARALELO
// ---------------------------------------------------------------------------

/**
 * Processa uma lista de links com no máximo `concurrency` abas simultâneas.
 * Usa um pool de Promises para controlar a concorrência sem bibliotecas externas.
 *
 * @param {import('puppeteer').Browser} browser
 * @param {string[]} links
 * @param {number}   concurrency
 * @returns {Promise<Object[]>}
 */
async function _processWithConcurrency(browser, links, concurrency) {
    const results = [];
    const queue   = [...links];
    const active  = new Set();

    return new Promise((resolve) => {
        function next() {
            // Preencher slots disponíveis
            while (active.size < concurrency && queue.length > 0) {
                const link = queue.shift();
                const task = _scrapeDetail(browser, link)
                    .then(result => { if (result) results.push(result); })
                    .catch(err  => console.log(`    [scraper] Erro em ${link.slice(0, 60)}...: ${err.message}`))
                    .finally(() => {
                        active.delete(task);
                        if (queue.length === 0 && active.size === 0) {
                            resolve(results);
                        } else {
                            next();
                        }
                    });
                active.add(task);
            }
        }

        if (links.length === 0) { resolve(results); return; }
        next();
    });
}

// ---------------------------------------------------------------------------
// SCRAPING DE UMA PÁGINA DE DETALHES
// ---------------------------------------------------------------------------

/**
 * Abre uma nova aba, visita a página de detalhes do estabelecimento
 * e extrai nome, endereço, CEP, telefone, site e coordenadas.
 *
 * @param {import('puppeteer').Browser} browser
 * @param {string} link
 * @returns {Promise<Object|null>}
 */
async function _scrapeDetail(browser, link) {
    const page = await browser.newPage();
    await page.setUserAgent(USER_AGENT);

    try {
        await page.goto(link, { waitUntil: 'networkidle2', timeout: 30000 });

        // Delay humano aleatório (800ms – 2s) para evitar detecção
        await delay(800 + Math.random() * 1200);

        // ── Extração de dados via evaluate ────────────────────────────────
        const data = await page.evaluate(() => {
            const getText = (selector) =>
                document.querySelector(selector)?.innerText?.trim() || null;

            const name = getText('h1');

            // Endereço — múltiplos seletores em cascata
            const addressRaw =
                getText('[data-item-id="address"]') ||
                getText('button[data-item-id="address"]') ||
                getText('[aria-label*="Endereço"]') ||
                getText('[aria-label*="Address"]') ||
                (() => {
                    const all = Array.from(document.querySelectorAll('button, div[role="button"]'));
                    const found = all.find(el =>
                        /(?:Rua|Av\.|Avenida|R\.|Alameda|Travessa|Praça)\s+/i.test(el.innerText)
                    );
                    return found?.innerText?.trim() || null;
                })();

            // Telefone — múltiplos seletores
            const phoneRaw =
                getText('[data-item-id="phone"]') ||
                getText('button[data-item-id="phone"]') ||
                getText('[aria-label*="Telefone"]') ||
                getText('[aria-label*="Phone"]');

            // Site
            const website =
                document.querySelector('a[data-item-id="authority"]')?.href ||
                document.querySelector('a[aria-label*="Site"]')?.href ||
                null;

            return { name, addressRaw, phoneRaw, website };
        });

        const bodyText = await page.evaluate(() => document.body.innerText);

        // ── CEP ───────────────────────────────────────────────────────────
        let cep = null;
        const cepMatch = (data.addressRaw || bodyText).match(/\b(\d{5})-?(\d{3})\b/);
        if (cepMatch) cep = cepMatch[1] + cepMatch[2];

        // ── Endereço limpo ────────────────────────────────────────────────
        let address = data.addressRaw
            ? data.addressRaw
                .replace(/^[·•\-–—\s]+/, '')
                .replace(cepMatch ? cepMatch[0] : '', '')
                .replace(/\s{2,}/g, ' ')
                .trim()
            : null;

        if (!address) {
            const m = bodyText.match(/(?:Rua|Av\.|Avenida|R\.|Alameda|Travessa|Praça)\s+[^\n,]+,\s*\d+/i);
            address = m ? m[0].trim() : null;
        }

        if (!cep) {
            const fb = bodyText.match(/\b(\d{5})-?(\d{3})\b/);
            if (fb) cep = fb[1] + fb[2];
        }

        // ── Telefone normalizado ──────────────────────────────────────────
        const normalizePhone = (raw) => {
            if (!raw) return null;
            let d = raw.replace(/\D/g, '');
            if (d.startsWith('55')) d = d.slice(2);
            return (d.length === 10 || d.length === 11) ? d : null;
        };

        let phone = normalizePhone(data.phoneRaw);
        if (!phone) {
            const m = bodyText.match(/(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})-?\d{4}/);
            phone = normalizePhone(m ? m[0] : null);
        }

        // ── Coordenadas ───────────────────────────────────────────────────
        // Prioridade 1: link original (!3d<lat>!4d<lon>)
        // Prioridade 2: URL atual da página (@lat,lon)
        let coordLat = null, coordLon = null;
        const dataCoord = link.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
        if (dataCoord) {
            coordLat = parseFloat(dataCoord[1]);
            coordLon = parseFloat(dataCoord[2]);
        } else {
            const urlCoord = page.url().match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
            if (urlCoord) {
                coordLat = parseFloat(urlCoord[1]);
                coordLon = parseFloat(urlCoord[2]);
            }
        }

        return {
            name:    data.name || null,
            address,
            cep,
            phone,
            website: data.website || null,
            link,
            lat:     coordLat,
            lon:     coordLon,
        };

    } catch (err) {
        throw err;
    } finally {
        await page.close();
    }
}

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

/**
 * Scroll automático robusto — para quando a altura para de crescer.
 * @param {import('puppeteer').Page} page
 * @param {string} selector
 */
async function autoScroll(page, selector) {
    await page.evaluate(async (selector) => {
        const container = document.querySelector(selector);
        if (!container) return;
        await new Promise((resolve) => {
            let lastHeight = 0, sameCount = 0;
            const interval = setInterval(() => {
                container.scrollBy(0, 800);
                const newHeight = container.scrollHeight;
                if (newHeight === lastHeight) { sameCount++; } else { sameCount = 0; lastHeight = newHeight; }
                if (sameCount >= 5) { clearInterval(interval); resolve(); }
            }, 400);
        });
    }, selector);
}

/** @param {number} ms */
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

module.exports = { scrapeGmaps };
