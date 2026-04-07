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
        Extrai centroids de hexágonos que cobrem os polígonos de jurisdiction.geojson.
        
        Para cada polígono de jurisdição:
        - Calcula o centroid
        - Usa grid_disk com k=1 para expandir o coverage
        - Define raio de 2 milhas se houver mais de 1 hexágono (grid_disk retorna múltiplos)
        - Define raio de 1 milha se houver apenas o centroid
        
        Retorna DataFrame com: delivery_station, hex, latitude, longitude, radius_miles
        """
        print(f"[{datetime.now()}] Extraindo centroids de hexágonos de jurisdiction.geojson...")
        
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
                
                # Converter geometria GeoJSON para Shapely
                geometry = shape(feature['geometry'])
                
                # Calcular centroid do polígono
                centroid = geometry.centroid
                lat = centroid.y
                lon = centroid.x
                
                # Obter hexágono do centroid (resolução 7)
                center_hex = h3.latlng_to_cell(lat, lon, 7)
                
                # Obter hexágonos vizinhos com grid_disk k=1
                hex_neighbors = h3.grid_disk(center_hex, 1)
                
                # Determinar raio baseado no número de hexágonos
                # Se grid_disk retorna mais de 1 hex (incluindo o centroid), raio é 2 milhas
                # Se retorna apenas o centroid (1 hex), raio é 1 milha
                if len(hex_neighbors) > 1:
                    radius_miles = 2.0
                else:
                    radius_miles = 1.0
                
                # Mapear cada hexágono com seu raio
                for hex_id in hex_neighbors:
                    self.hex_radius_map[hex_id] = radius_miles
                    hex_lat, hex_lon = h3.cell_to_latlng(hex_id)
                    
                    centroid_data.append({
                        'delivery_station': delivery_station,
                        'hex': hex_id,
                        'latitude': hex_lat,
                        'longitude': hex_lon,
                        'radius_miles': radius_miles,
                        'is_center': hex_id == center_hex  # Marcar o hexágono central
                    })
                
                print(f"   ✓ {delivery_station}: {len(hex_neighbors)} hexágonos encontrados (raio: {radius_miles} milhas)")
                
            except Exception as e:
                delivery_station = feature.get('properties', {}).get('delivery_station', 'UNKNOWN')
                print(f"   ⚠ Erro ao processar {delivery_station}: {e}")
                continue
        
        centroid_df = pd.DataFrame(centroid_data)
        print(f"\n✅ Total de hexágonos extraídos: {len(centroid_df)}")
        
        return centroid_df

    def export_csv(self, output_filename="hexagons_res7.csv"):
        """Exporta CSV com station_code, total_packages, latitude, longitude e radius_miles."""
        dest = Path(Config.DEST_FOLDER)
        dest.mkdir(exist_ok=True)
        output_path = dest / output_filename

        # use csv module to avoid pandas heavy import
        import csv
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["station_code", "total_packages", "latitude", "longitude", "radius_miles"])
            for _, row in self.demand_df.iterrows():
                hex_id = row['hex']
                station_code = row['station_code']
                total_packages = int(row['avg_demand'])
                lat, lon = h3.cell_to_latlng(hex_id)
                
                # Obter raio do mapa de hexágonos ou usar padrão de 1 milha
                radius_miles = self.hex_radius_map.get(hex_id, 1.0)
                
                writer.writerow([station_code, total_packages, lat, lon, radius_miles])

        print(f"✅ CSV salvo em {output_path}")
        print(f"   - Total de hexágonos escritos: {len(self.demand_df)}")

if __name__ == "__main__":
    try:
        generator = HexagonGenerator()
        generator.load_packages_data()
        
        # Extrair centroids de hexágonos da jurisdição
        centroid_df = generator.get_hex_centroids_from_jurisdiction()
        
        # Gerar GeoJSON e exportar CSV
        generator.generate_hex_geojson()
        generator.export_csv()
    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()
