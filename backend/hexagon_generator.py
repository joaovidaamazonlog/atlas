import json
import h3
import pandas as pd
import config as configuration
from pathlib import Path
from datetime import datetime
from shapely.geometry import shape, Point
from shapely.ops import unary_union

# =====================================================
# CONFIGURAÇÕES E CONSTANTES
# =====================================================

class Config:
    """Configurações centralizadas do sistema."""
    BASE_PACKAGES = configuration.BASE_PACKAGES
    DEST_FOLDER = configuration.DEST_FOLDER

# =====================================================
# SERVIÇO SIMPLIFICADO PARA GERAÇÃO DE HEXÁGONOS
# =====================================================

class HexagonGenerator:
    def __init__(self):
        self.demand_df: pd.DataFrame = pd.DataFrame()
        self.hex_to_ceps: dict = {}
        self.hex_radius_map: dict = {}  # Mapa de hex para raio em milhas

    def load_packages_data(self):
        """Carrega apenas os dados de pacotes e gera hexágonos H3 resolução 7."""
        print(f"[{datetime.now()}] Carregando dados de pacotes...")

        # Carregar Demandas (Pacotes)
        df = pd.read_csv(Config.BASE_PACKAGES)
        if 'cep' in df.columns:
            df['cep'] = df['cep'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(8)

        if 'hex' not in df.columns:
            # Usar resolução 7
            df["hex"] = [h3.latlng_to_cell(la, lo, 7) for la, lo in zip(df.latitude, df.longitude)]

        days = pd.to_datetime(df.plan_date).nunique() or 1

        # Agrupar por Estação e Hexágono
        raw_grouped = df.groupby(["station_code", "hex"]).size().reset_index(name="qty")
        raw_grouped["avg_demand"] = (raw_grouped["qty"] / days).round(0).astype(int)

        # Tratamento de duplicidade: Winner Takes All
        hex_totals = raw_grouped.groupby("hex")["avg_demand"].sum().reset_index(name="total_demand")
        hex_winners = raw_grouped.sort_values(by="avg_demand", ascending=False).drop_duplicates(subset=["hex"], keep="first")[["hex", "station_code"]]
        self.demand_df = pd.merge(hex_winners, hex_totals, on="hex")
        self.demand_df.rename(columns={"total_demand": "avg_demand"}, inplace=True)

        print(f"   - Hexágonos únicos após unificação: {len(self.demand_df)}")

        # Criar mapeamento hex -> CEPs
        if 'cep' in df.columns:
            self.hex_to_ceps = df.groupby('hex')['cep'].apply(set).to_dict()

    def generate_hex_geojson(self, output_filename="hexagons_res7.geojson"):
        """Gera GeoJSON com hexágonos H3 resolução 7 e propriedades solicitadas."""
        features = []

        for _, row in self.demand_df.iterrows():
            hex_id = row['hex']
            station_code = row['station_code']
            total_packages = int(row['avg_demand'])
            ceps = list(self.hex_to_ceps.get(hex_id, []))[:10]  # Limitar a 10 CEPs por hex

            # Obter geometria do hexágono H3
            try:
                boundary = h3.cell_to_boundary(hex_id)
                coords = [[c[1], c[0]] for c in boundary]  # [lon, lat]
                coords.append(coords[0])  # Fechar o polígono

                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    },
                    "properties": {
                        "station_code": station_code,
                        "total_packages": total_packages,
                        "ceps": ceps
                    }
                }
                features.append(feature)
            except Exception as e:
                print(f"Erro ao processar hex {hex_id}: {e}")
                continue

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        # Salvar arquivo
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)

        print(f"✅ GeoJSON salvo em {output_path}")
        print(f"   - Total de hexágonos: {len(features)}")

    def get_hex_centroids_from_jurisdiction(self):
        """
        Maximum-coverage circle packing sobre os polígonos de jurisdiction.geojson.

        Estratégia:
        - Raio de cada candidato = distância do ponto à borda (maior círculo que cabe).
        - Grade hexagonal com espaçamento ~500m para cobertura densa.
        - Greedy por área coberta: escolhe o círculo com maior área nova a cada passo.
          Otimização: pré-filtra candidatos cujo centro já está coberto antes do max().
        - Para quando o ganho incremental cai abaixo de MIN_COVERAGE_GAIN_M2.
        - Geometrias inválidas são sanitizadas com buffer(0).

        Retorna DataFrame com: delivery_station, latitude, longitude, radius_miles
        """
        import math
        from shapely.geometry import Point
        from shapely.validation import make_valid

        GRID_STEP_DEG = 500 / 111_000        # ~0.0045° (~500m)
        MIN_RADIUS_MILES = 1                 # descarta candidatos com raio < 1 milha inteira
        MIN_GAIN_M2   = 50_000               # para quando ganho < 0.05 km²
        DEG_TO_M      = 111_000
        MILES_TO_M    = 1609.344

        def miles_floor(dist_m):
            """Maior número inteiro de milhas que cabe na distância dada."""
            return int(dist_m / MILES_TO_M)

        def circle_shape(lat, lon, r_miles):
            r_deg = (r_miles * MILES_TO_M) / DEG_TO_M
            return Point(lon, lat).buffer(r_deg)

        print(f"[{datetime.now()}] Maximum-coverage circle packing em jurisdiction.geojson...")

        try:
            jurisdiction_path = Path(configuration.BASE_JURISDICTION)
            with open(jurisdiction_path, 'r', encoding='utf-8') as f:
                jurisdiction_geojson = json.load(f)
        except FileNotFoundError:
            print(f"❌ Arquivo não encontrado: {jurisdiction_path}")
            return pd.DataFrame()
        except json.JSONDecodeError:
            print(f"❌ Erro ao decodificar JSON: {jurisdiction_path}")
            return pd.DataFrame()

        centroid_data = []

        for feature in jurisdiction_geojson.get('features', []):
            try:
                delivery_station = feature.get('properties', {}).get('delivery_station')
                if not delivery_station:
                    continue

                geometry = shape(feature['geometry'])
                # Sanitizar geometria inválida
                if not geometry.is_valid:
                    geometry = make_valid(geometry)

                minx, miny, maxx, maxy = geometry.bounds

                # --- Grade hexagonal sobre o bounding box ---
                candidates = []  # [lat, lon, r_miles_int, r_m, circle_shape]
                row = 0
                lat = miny
                while lat <= maxy + GRID_STEP_DEG:
                    offset = (GRID_STEP_DEG / 2) if (row % 2 == 1) else 0.0
                    lon = minx + offset
                    while lon <= maxx + GRID_STEP_DEG:
                        pt = Point(lon, lat)
                        if geometry.contains(pt):
                            dist_m = geometry.boundary.distance(pt) * DEG_TO_M
                            r_miles = miles_floor(dist_m)  # inteiro, floor
                            if r_miles >= MIN_RADIUS_MILES:
                                r_m = r_miles * MILES_TO_M
                                candidates.append([lat, lon, r_miles, r_m, circle_shape(lat, lon, r_miles)])
                        lon += GRID_STEP_DEG
                    lat += GRID_STEP_DEG * (3 ** 0.5) / 2
                    row += 1

                if not candidates:
                    # Fallback: polígono estreito — usa o ponto mais central com raio 1mi
                    best_pt, best_dist = None, 0
                    row = 0
                    lat = miny
                    while lat <= maxy + GRID_STEP_DEG:
                        offset = (GRID_STEP_DEG / 2) if (row % 2 == 1) else 0.0
                        lon = minx + offset
                        while lon <= maxx + GRID_STEP_DEG:
                            pt = Point(lon, lat)
                            if geometry.contains(pt):
                                d = geometry.boundary.distance(pt) * DEG_TO_M
                                if d > best_dist:
                                    best_dist, best_pt = d, (lat, lon)
                            lon += GRID_STEP_DEG
                        lat += GRID_STEP_DEG * (3 ** 0.5) / 2
                        row += 1
                    if best_pt:
                        candidates = [[best_pt[0], best_pt[1], 1, MILES_TO_M, circle_shape(best_pt[0], best_pt[1], 1)]]
                        print(f"   ℹ {delivery_station}: polígono estreito, fallback 1mi no ponto mais central")
                    else:
                        print(f"   ⚠ {delivery_station}: sem candidatos válidos")
                        continue

                # --- Greedy maximum-coverage ---
                covered = geometry.__class__()   # geometria vazia
                placed  = []                     # (lat, lon, r_m)

                while candidates:
                    # Filtra candidatos cujo centro já está dentro da área coberta
                    # (eles teriam ganho zero ou mínimo — otimização de velocidade)
                    active = [c for c in candidates if not covered.contains(Point(c[1], c[0]))]
                    if not active:
                        break

                    # Escolhe o que cobre mais área nova
                    best = max(active, key=lambda c: c[4].difference(covered).area)
                    gain_m2 = best[4].difference(covered).area * (DEG_TO_M ** 2)

                    if gain_m2 < MIN_GAIN_M2:
                        break

                    placed.append((best[0], best[1], best[2], best[3]))  # lat, lon, r_miles, r_m
                    covered = covered.union(best[4])

                    # Remove candidatos cujo centro foi coberto pelo novo círculo
                    candidates = [c for c in candidates if not best[4].contains(Point(c[1], c[0]))]

                total_m2   = geometry.area * (DEG_TO_M ** 2)
                covered_m2 = covered.intersection(geometry).area * (DEG_TO_M ** 2)
                pct = 100 * covered_m2 / total_m2 if total_m2 > 0 else 0

                for lat, lon, r_miles, r_m in placed:
                    centroid_data.append({
                        'delivery_station': delivery_station,
                        'latitude': lat,
                        'longitude': lon,
                        'radius_miles': r_miles,
                    })
                    self.hex_radius_map[h3.latlng_to_cell(lat, lon, 8)] = r_miles

                print(f"   ✓ {delivery_station}: {len(placed)} círculos, cobertura ~{pct:.1f}%")

            except Exception as e:
                delivery_station = feature.get('properties', {}).get('delivery_station', 'UNKNOWN')
                print(f"   ⚠ Erro ao processar {delivery_station}: {e}")
                import traceback; traceback.print_exc()
                continue

        centroid_df = pd.DataFrame(centroid_data)
        print(f"\n✅ Total de círculos: {len(centroid_df)}")
        return centroid_df

    def export_csv(self, output_filename="hexagons_res7.csv"):
        """Exporta CSV com station_code, total_packages, latitude, longitude e radius_miles."""
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        import csv
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["station_code", "total_packages", "latitude", "longitude", "radius_miles"])
            for _, row in self.demand_df.iterrows():
                hex_id = row['hex']
                station_code = row['station_code']
                total_packages = int(row['avg_demand'])
                lat, lon = h3.cell_to_latlng(hex_id)
                radius_miles = self.hex_radius_map.get(hex_id, 1.0)
                writer.writerow([station_code, total_packages, lat, lon, radius_miles])

        print(f"✅ CSV salvo em {output_path}")
        print(f"   - Total de hexágonos escritos: {len(self.demand_df)}")

    def export_circles_csv(self, centroid_df: pd.DataFrame, output_filename="marketing_circles.csv"):
        """
        Exporta CSV com os círculos de cobertura de marketing.
        Colunas: delivery_station, latitude, longitude, radius_meters
        """
        if centroid_df.empty:
            print("⚠ Nenhum dado de círculos para exportar.")
            return

        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        import csv
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["delivery_station", "latitude", "longitude", "radius_meters"])
            for _, row in centroid_df.iterrows():
                writer.writerow([
                    row['delivery_station'],
                    row['latitude'],
                    row['longitude'],
                    round(row['radius_miles'] * 1609.344),
                ])

        print(f"✅ CSV de círculos salvo em {output_path}")
        print(f"   - Total de círculos: {len(centroid_df)}")

if __name__ == "__main__":
    try:
        generator = HexagonGenerator()
        generator.load_packages_data()

        # Cobrir polígonos de jurisdição com círculos e exportar CSV
        centroid_df = generator.get_hex_centroids_from_jurisdiction()
        generator.export_circles_csv(centroid_df)

        # Gerar GeoJSON e exportar CSV de demanda
        generator.generate_hex_geojson()
        generator.export_csv()
    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()
