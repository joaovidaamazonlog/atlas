/**
 * clean_results.js
 * ================
 * Remove entradas duplicadas de gmaps_results.json, mantendo a versão
 * com endereço completo quando houver duplicatas pelo mesmo nome.
 *
 * Uso:
 *   node clean_results.js
 */

const fs   = require('fs');
const path = require('path');

const OUTPUT_PATH = path.join(__dirname, '..', 'output_data', 'gmaps_results.json');

const data = JSON.parse(fs.readFileSync(OUTPUT_PATH, 'utf8'));

let removed = 0;

for (const [tid, entries] of Object.entries(data.results)) {
    const seen = new Map(); // nome → melhor entrada

    for (const entry of entries) {
        const key = entry.nome?.trim().toLowerCase();
        if (!key) continue;

        const hasAddress = entry.endereco && entry.endereco !== 'N/A';

        if (!seen.has(key)) {
            seen.set(key, entry);
        } else {
            const prev = seen.get(key);
            const prevHasAddress = prev.endereco && prev.endereco !== 'N/A';
            // Substituir se a entrada atual tem endereço e a anterior não
            if (!prevHasAddress && hasAddress) {
                seen.set(key, entry);
            }
            removed++;
        }
    }

    data.results[tid] = Array.from(seen.values());
}

data.n_companies = Object.values(data.results).reduce((s, arr) => s + arr.length, 0);

fs.writeFileSync(OUTPUT_PATH, JSON.stringify(data, null, 2), 'utf8');

console.log(`Limpeza concluída: ${removed} duplicatas removidas.`);
console.log(`Total de empresas após limpeza: ${data.n_companies}`);
