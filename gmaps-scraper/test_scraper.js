const { scrapeGmaps } = require('./scraper');

(async () => {
    console.log('Iniciando teste de scraping para "lanchonete" em São Paulo...');
    const results = await scrapeGmaps('lanchonete', '-23.5505', '-46.6333');
    
    console.log('Resultados encontrados:', results.length);
    if (results.length > 0) {
        console.log('Primeiro resultado:', JSON.stringify(results[0], null, 2));
    } else {
        console.log('Nenhum resultado encontrado.');
    }
})();
