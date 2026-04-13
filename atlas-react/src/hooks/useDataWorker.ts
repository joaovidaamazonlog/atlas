/**
 * useDataWorker.ts
 * ================
 * Hook de integração com o Web Worker de dados.
 * Instancia o worker, escuta mensagens e despacha para o store Zustand.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { DATA_URLS } from '../lib/config';
import type { WorkerInMessage, WorkerOutMessage } from '../workers/data-worker';

export function useDataWorker() {
  const workerRef = useRef<Worker | null>(null);

  const setAllData = useStore((s) => s.setAllData);
  const setLoading = useStore((s) => s.setLoading);
  const setError = useStore((s) => s.setError);

  useEffect(() => {
    // Instancia o worker com sintaxe Vite (type: 'module')
    const worker = new Worker(
      new URL('../workers/data-worker.ts', import.meta.url),
      { type: 'module' }
    );

    worker.onmessage = (e: MessageEvent<WorkerOutMessage>) => {
      const msg = e.data;

      if (msg.action === 'dataLoaded') {
        setAllData(msg.payload);
        setLoading(false);
      } else if (msg.action === 'filterResult') {
        // Atualiza currentFilteredData diretamente via applyFilters com os dados já filtrados
        // Usamos o store diretamente para evitar re-filtragem
        useStore.setState({ currentFilteredData: msg.filtered });
      } else if (msg.action === 'error') {
        setError(msg.message);
        setLoading(false);
      }
    };

    worker.onerror = (err) => {
      setError(`Erro no Web Worker: ${err.message}`);
      setLoading(false);
    };

    workerRef.current = worker;

    // Cleanup: termina o worker ao desmontar
    return () => {
      worker.terminate();
      workerRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendMessage = useCallback((msg: WorkerInMessage) => {
    workerRef.current?.postMessage(msg);
  }, []);

  const loadData = useCallback(() => {
    setLoading(true, 'Carregando dados...');
    sendMessage({ action: 'loadData', urls: DATA_URLS });
  }, [sendMessage, setLoading]);

  return { sendMessage, loadData };
}
