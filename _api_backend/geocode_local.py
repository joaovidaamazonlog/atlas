"""
geocode_local.py
================
Orquestrador local — dispara 4 workers em paralelo, cada um numa faixa de CEP.
Cada worker roda em processo separado com log próprio.

Uso:
    python geocode_local.py
    python geocode_local.py --workers 4
    python geocode_local.py --no-resume

As faixas de CEP são divididas automaticamente entre os workers.
Os workers do GitHub Actions cobrem outras faixas (ver geocode.yml).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _load_env(env_file: Path) -> None:
    """Carrega variáveis do .env para os processos filhos."""
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# Faixas reservadas para workers LOCAIS
# Os workers do GitHub Actions cobrem 00000000–49999999 (workers 1-5 do yml)
# Aqui cobrimos 50000000–99999999 dividido em 4 faixas
LOCAL_RANGES = [
    ("1", "50000000", "61999999"),
    ("2", "62000000", "73999999"),
    ("3", "74000000", "86999999"),
    ("4", "87000000", "99999999"),
]


def run_worker(worker_id: str, cep_min: str, cep_max: str, extra_args: list[str]) -> subprocess.Popen:
    log_file = Path(f"geocode_worker_{worker_id}.log")
    log_handle = open(log_file, "a", encoding="utf-8")

    cmd = [
        sys.executable, "geocode_worker.py",
        "--worker-id", worker_id,
        "--cep-min",   cep_min,
        "--cep-max",   cep_max,
        *extra_args,
    ]

    print(f"[{datetime.now():%H:%M:%S}] Iniciando worker {worker_id} | CEP {cep_min}–{cep_max} | log → {log_file}")

    return subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=log_handle,
        env=os.environ.copy(),
        cwd=Path(__file__).parent,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers",   type=int, default=4, help="Número de workers (default: 4)")
    parser.add_argument("--no-resume", action="store_true",  help="Reprocessar tudo")
    args = parser.parse_args()

    extra = ["--no-resume"] if args.no_resume else []
    ranges = LOCAL_RANGES[: args.workers]

    # Carrega .env antes de spawnar os workers
    _load_env(Path(__file__).parent / ".env")

    print(f"Iniciando {len(ranges)} workers locais...")
    print("Logs individuais: geocode_worker_<id>.log")
    print("Para acompanhar: tail -f geocode_worker_1.log")
    print("-" * 60)

    procs = []
    for worker_id, cep_min, cep_max in ranges:
        p = run_worker(worker_id, cep_min, cep_max, extra)
        procs.append((worker_id, p))
        time.sleep(2)  # pequeno delay para não sobrecarregar o Turso na inicialização

    print(f"\n{len(procs)} workers rodando. Aguardando conclusão...")
    print("Ctrl+C para interromper (progresso já salvo no Turso).\n")

    try:
        while True:
            alive = [(wid, p) for wid, p in procs if p.poll() is None]
            done  = [(wid, p) for wid, p in procs if p.poll() is not None]

            for wid, p in done:
                status = "OK" if p.returncode == 0 else f"ERRO (código {p.returncode})"
                print(f"[{datetime.now():%H:%M:%S}] Worker {wid} finalizado: {status}")

            procs = alive

            if not alive:
                break

            time.sleep(30)  # checa status a cada 30s

    except KeyboardInterrupt:
        print("\nInterrompido. Encerrando workers...")
        for _, p in procs:
            p.terminate()
        print("Workers encerrados. Progresso salvo no Turso.")
        sys.exit(0)

    print("\nTodos os workers concluídos.")
    print("Verifique o progresso com:")
    print("  SELECT geocode_status, COUNT(*) FROM empresas_geo GROUP BY geocode_status;")


if __name__ == "__main__":
    main()
