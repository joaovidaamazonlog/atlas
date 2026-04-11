/**
 * api/save-lead.js
 * ================
 * Vercel Function — proxy seguro para disparar o GitHub Actions workflow.
 * O PAT fica como variável de ambiente na Vercel, nunca exposto no frontend.
 *
 * POST /api/save-lead
 * Body: { action: 'add'|'remove', lead_key, lead_nome, lead_territorio }
 */

export default async function handler(req, res) {
    // CORS — permite chamadas do GitHub Pages
    res.setHeader('Access-Control-Allow-Origin', 'https://joaovidaamazonlog.github.io');
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') return res.status(200).end();
    if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

    const { action, lead_key, lead_nome, lead_territorio } = req.body || {};

    if (!action || !lead_key) {
        return res.status(400).json({ error: 'action e lead_key são obrigatórios' });
    }

    const pat = process.env.GITHUB_PAT;
    if (!pat) {
        return res.status(500).json({ error: 'GITHUB_PAT não configurado' });
    }

    const response = await fetch(
        'https://api.github.com/repos/joaovidaamazonlog/atlas/actions/workflows/save-lead.yml/dispatches',
        {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${pat}`,
                'Accept':        'application/vnd.github+json',
                'Content-Type':  'application/json',
            },
            body: JSON.stringify({
                ref: 'main',
                inputs: {
                    action:          action,
                    lead_key:        lead_key,
                    lead_nome:       lead_nome       || '',
                    lead_territorio: lead_territorio || '',
                },
            }),
        }
    );

    if (!response.ok) {
        const text = await response.text();
        console.error('[save-lead] GitHub API error:', response.status, text);
        return res.status(502).json({ error: 'Erro ao chamar GitHub Actions', detail: text });
    }

    return res.status(200).json({ ok: true });
}
