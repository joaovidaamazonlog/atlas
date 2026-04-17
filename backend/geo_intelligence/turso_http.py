"""
turso_http.py
=============
Cliente Turso via HTTP (igual ao _api_backend/api/main.py).
Usa httpx em vez de libsql-client para compatibilidade total.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _turso_http_url(url: str) -> str:
    """Converte libsql:// → https:// para a API HTTP do Turso."""
    return url.replace("libsql://", "https://")


def _arg(v: Any) -> dict:
    """Converte valor Python para o formato de argumento da Turso HTTP API v2.
    
    A API v2 do Turso aceita apenas type=text, type=float ou type=null.
    Inteiros devem ser enviados como text — o SQLite faz a coerção automaticamente.
    """
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "text", "value": str(int(v))}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    # int, str e qualquer outro tipo → text
    return {"type": "text", "value": str(v)}


class TursoHTTP:
    """
    Cliente HTTP síncrono para o Turso (libSQL).
    Usa a Pipeline API v2 do Turso — mesma abordagem do _api_backend.
    """

    def __init__(self, url: str, auth_token: str, timeout: int = 30) -> None:
        self._url = _turso_http_url(url)
        self._token = auth_token
        self._timeout = timeout

    def execute(self, sql: str, args: list = []) -> list[dict]:
        """
        Executa uma query e retorna lista de dicts {coluna: valor}.
        Retorna [] em caso de erro de query (tabela não existe, etc.).
        Lança exceção em caso de erro de rede/autenticação.
        """
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}},
                {"type": "close"},
            ]
        }

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._url}/v2/pipeline",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Turso HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        result = data["results"][0]

        if result.get("type") == "error":
            err_msg = result.get("error", {}).get("message", "unknown error")
            logger.warning("Turso query error: %s | SQL: %s", err_msg, sql[:100])
            raise RuntimeError(f"Turso query error: {err_msg}")

        inner = result.get("response", {}).get("result", {})
        cols = [c["name"] for c in inner.get("cols", [])]
        rows = inner.get("rows", [])

        return [
            {
                cols[i]: (cell.get("value") if cell.get("type") != "null" else None)
                for i, cell in enumerate(row)
            }
            for row in rows
        ]

    def execute_many(self, statements: list[tuple[str, list]]) -> None:
        """
        Executa múltiplas queries em uma única requisição HTTP (batch).
        Mais eficiente que chamar execute() em loop.
        """
        requests = []
        for sql, args in statements:
            requests.append({"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in args]}})
        requests.append({"type": "close"})

        payload = {"requests": requests}

        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                f"{self._url}/v2/pipeline",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Turso HTTP {resp.status_code}: {resp.text[:300]}")
