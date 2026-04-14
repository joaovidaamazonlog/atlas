import { useState, useRef, useEffect } from 'react';

interface GeolocationResult {
  position: [number, number] | null;
  isTracking: boolean;
  error: string | null;
  startTracking: () => void;
  stopTracking: () => void;
}

const ERROR_MESSAGES: Record<number, string> = {
  1: 'Permissão de localização negada. Habilite nas configurações do dispositivo.',
  2: 'Localização indisponível no momento.',
  3: 'Tempo esgotado ao obter localização.',
};

export function useGeolocation(): GeolocationResult {
  const [position, setPosition] = useState<[number, number] | null>(null);
  const [isTracking, setIsTracking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const watchIdRef = useRef<number | null>(null);

  const startTracking = () => {
    if (!navigator.geolocation) {
      setError('Geolocalização não suportada neste dispositivo.');
      return;
    }

    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setPosition([pos.coords.latitude, pos.coords.longitude]);
        setIsTracking(true);
        setError(null);
      },
      (err) => {
        setError(ERROR_MESSAGES[err.code] ?? 'Erro desconhecido ao obter localização.');
      }
    );
  };

  const stopTracking = () => {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
    setPosition(null);
    setIsTracking(false);
  };

  useEffect(() => {
    return () => {
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
    };
  }, []);

  return { position, isTracking, error, startTracking, stopTracking };
}
