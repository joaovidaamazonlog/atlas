"""
Cria índices no Turso via libsql-client (protocolo nativo, sem timeout HTTP).
"""
import asyncio
import os
from pathlib import Path

import libsql_client

def load_env():
    for line in (Path(__file__).parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

async def main():
    load_env()
    url   = os.environ["TURSO_URL"]
    token = os.environ["TURSO_TOKEN"]

    print(f"Conectando em {url}...")

    # força protocolo HTTP (não WebSocket)
    http_url = url.replace("libsql://", "https://")
    async with libsql_client.create_client(http_url, auth_token=token) as client:
        indexes = [
            ("idx_alvo_uf",  "CREATE INDEX IF NOT EXISTS idx_alvo_uf  ON empresas_alvo (uf)"),
            ("idx_alvo_cep", "CREATE INDEX IF NOT EXISTS idx_alvo_cep ON empresas_alvo (cep)"),
        ]
        for name, sql in indexes:
            print(f"Criando {name}... (pode demorar alguns minutos)")
            await client.execute(sql)
            print(f"  {name} OK.")

    print("\nTodos os índices criados. Pode rodar os workers agora.")

if __name__ == "__main__":
    asyncio.run(main())
