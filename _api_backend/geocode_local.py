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

# UFs divididas em 4 grupos para os workers locais
# Ordenadas aproximadamente por volume (SP tem mais empresas)
LOCAL_UF_GROUPS = [
    ("1", ["SP"]),
    ("2", ["MG", "RJ", "ES"]),
    ("3", ["RS", "SC", "PR", "MS"]),
    ("4", ["BA", "GO", "DF", "MT", "PA", "CE", "PE", "MA", "AM", "RN", "PB", "PI", "AL", "SE", "RO", "TO", "AC", "AP", "RR"]),
]


def run_worker(worker_id: str, ufs: list[str], extra_args: list[str]) -> subprocess.Popen:
    log_file   = Path(f"geocode_worker_{worker_id}.log")
    log_handle = open(log_file, "a", encoding="utf-8")

    cmd = [
        sys.executable, "geocode_worker.py",
        "--worker-id", worker_id,
        *extra_args,
    ]
    for uf in ufs:
        cmd += ["--uf", uf]

    print(f"[{datetime.now():%H:%M:%S}] Iniciando worker {worker_id} | UFs: {', '.join(ufs)} | log → {log_file}")

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

    # Carrega .env antes de spawnar os workers
    _load_env(Path(__file__).parent / ".env")

    print(f"Iniciando {len(LOCAL_UF_GROUPS[:args.workers])} workers locais...")
    print("Logs individuais: geocode_worker_<id>.log")
    print("Para acompanhar: tail -f geocode_worker_1.log")
    print("-" * 60)

    procs = []
    for worker_id, ufs in LOCAL_UF_GROUPS[: args.workers]:
        p = run_worker(worker_id, ufs, extra)
        procs.append((worker_id, p))
        time.sleep(2)

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
