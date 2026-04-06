const express = require('express');
const cors = require('cors');
const { scrapeGmaps } = require('./scraper');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Endpoint principal da API
app.get('/api/search', async (req, res) => {
    const { type, lat, long } = req.query;

    if (!type || !lat || !long) {
        return res.status(400).json({ 
            error: 'Parâmetros ausentes. Forneça "type", "lat" e "long".' 
        });
    }

    console.log(`Buscando por "${type}" em @${lat},${long}...`);

    try {
        const results = await scrapeGmaps(type, lat, long);
        
        // Formatar o resultado final
        const formattedResults = results.map(item => ({
            nome: item.name || 'N/A',
            endereco: item.address || 'N/A',
            telefone: item.phone || 'N/A',
            site: item.website || 'N/A',
            instagram: 'N/A', // Instagram requer visita à página de detalhes
            google_maps_link: item.link || 'N/A'
        }));

        res.json({
            count: formattedResults.length,
            results: formattedResults
        });
    } catch (error) {
        console.error('Erro na API:', error);
        res.status(500).json({ error: 'Erro interno ao processar a busca.' });
    }
});

app.listen(PORT, () => {
    console.log(`API do Google Maps Scraper rodando em http://localhost:${PORT}`);
});
