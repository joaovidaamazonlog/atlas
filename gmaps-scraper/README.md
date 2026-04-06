# Google Maps Scraper API

Uma API REST em JavaScript puro (Node.js + Puppeteer) para extrair dados de empresas do Google Maps de forma escalável, sem a necessidade da API oficial paga.

## 🚀 Funcionalidades

- **Busca por Coordenadas**: Pesquisa empresas próximas a uma latitude e longitude específicas.
- **Tipos de Negócio**: Suporta qualquer termo de pesquisa (lanchonete, sapateiro, etc.).
- **Dados Extraídos**: Nome, Endereço, Telefone, Site e Link do Google Maps.
- **Escalável**: Implementado com Puppeteer-Stealth para evitar bloqueios e suporte a scroll automático para carregar múltiplos resultados.

## 🛠️ Instalação

1. Clone o repositório:
   ```bash
   git clone <repo-url>
   cd gmaps-scraper-api
   ```

2. Instale as dependências:
   ```bash
   npm install
   ```

3. Inicie a API:
   ```bash
   node index.js
   ```

## 📖 Como Usar (API)

A API roda por padrão na porta `3000`. Você pode fazer uma requisição `GET` para o endpoint `/api/search`.

### Exemplo de Requisição (Fetch)

```javascript
const response = await fetch('http://localhost:3000/api/search?type=lanchonete&lat=-23.5505&long=-46.6333');
const data = await response.json();
console.log(data.results);
```

### Parâmetros da Query

| Parâmetro | Descrição | Exemplo |
| :--- | :--- | :--- |
| `type` | Tipo de empresa ou termo de busca | `sapateiro` |
| `lat` | Latitude da coordenada central | `-23.5505` |
| `long` | Longitude da coordenada central | `-46.6333` |

### Exemplo de Resposta JSON

```json
{
  "count": 20,
  "results": [
    {
      "nome": "Bar e Lanches Estadão",
      "endereco": "Viaduto Nove de Julho, 193 - Centro Histórico de São Paulo, São Paulo - SP, 01050-060, Brazil",
      "telefone": "+55 11 3257-7121",
      "site": "http://www.estadaolanches.com.br/",
      "google_maps_link": "https://www.google.com/maps/place/..."
    }
  ]
}
```

## 🛡️ Considerações de Escalabilidade

- **Proxy**: Para uso em larga escala, recomenda-se o uso de proxies rotativos no Puppeteer.
- **Cache**: Implementar um cache (ex: Redis) para evitar buscas repetidas nas mesmas coordenadas.
- **Headless**: A API roda em modo `headless: "new"` para máxima performance.

## 📄 Licença

Este projeto é open-source sob a licença MIT.
