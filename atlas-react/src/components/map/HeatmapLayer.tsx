/**
 * HeatmapLayer.tsx
 * ================
 * Placeholder para a camada de heatmap.
 *
 * TODO: Implementar com leaflet.heat (plugin adicional).
 * O plugin leaflet.heat requer integração via useEffect com L.heatLayer,
 * pois não possui wrapper react-leaflet oficial.
 *
 * Exemplo de integração futura:
 *   import 'leaflet.heat';
 *   const map = useMap();
 *   useEffect(() => {
 *     const layer = L.heatLayer(points, { radius: 25 });
 *     layer.addTo(map);
 *     return () => { map.removeLayer(layer); };
 *   }, [map, points]);
 */

export default function HeatmapLayer() {
  return null;
}
