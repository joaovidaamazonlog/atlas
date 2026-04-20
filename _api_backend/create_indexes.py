"""
Cria índices necessários no Turso via CLI (turso db shell).
Execute este script para ver os comandos a rodar manualmente.
"""

print("""
Execute os comandos abaixo no Turso shell:

    turso db shell atlas-leads-joaovidaamazonlog

Depois cole:

    CREATE INDEX IF NOT EXISTS idx_alvo_uf  ON empresas_alvo (uf);
    CREATE INDEX IF NOT EXISTS idx_alvo_cep ON empresas_alvo (cep);

Aguarde a conclusão (pode demorar alguns minutos com 3M de registros).
""")
