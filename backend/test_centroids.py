"""
Script de Teste para a Nova Função get_hex_centroids_from_jurisdiction()

Este script demonstra como usar a função para extrair centroids de hexágonos
e analisar os raios de cobertura.
"""

from hexagon_generator import HexagonGenerator
import pandas as pd

def test_jurisdiction_centroids():
    """Testa a extração de centroids de hexágonos da jurisdição."""
    
    print("\n" + "="*70)
    print("TESTE: Extração de Centroids de Hexágonos de Jurisdição")
    print("="*70 + "\n")
    
    # Criar gerador
    generator = HexagonGenerator()
    
    # Extrair centroids
    print("📍 Extraindo centroids de jurisdiction.geojson...\n")
    centroid_df = generator.get_hex_centroids_from_jurisdiction()
    
    if centroid_df.empty:
        print("❌ Nenhum dado foi extraído!")
        return
    
    # Mostrar estatísticas gerais
    print("\n" + "-"*70)
    print("ESTATÍSTICAS GERAIS")
    print("-"*70)
    print(f"Total de hexágonos extraídos: {len(centroid_df)}")
    print(f"Total de delivery stations: {centroid_df['delivery_station'].nunique()}")
    
    # Análise de raios
    print("\n" + "-"*70)
    print("ANÁLISE DE RAIOS")
    print("-"*70)
    radius_stats = centroid_df['radius_miles'].value_counts().sort_index()
    print(f"\nDistribuição de raios:")
    for radius, count in radius_stats.items():
        percentage = (count / len(centroid_df)) * 100
        print(f"  • {radius} milha(s): {count} hexágonos ({percentage:.1f}%)")
    
    print(f"\nRaio de cobertura:")
    print(f"  • Mínimo: {centroid_df['radius_miles'].min()} milhas")
    print(f"  • Máximo: {centroid_df['radius_miles'].max()} milhas")
    print(f"  • Média: {centroid_df['radius_miles'].mean():.2f} milhas")
    
    # Análise por delivery_station
    print("\n" + "-"*70)
    print("ANÁLISE POR DELIVERY STATION")
    print("-"*70)
    station_groups = centroid_df.groupby('delivery_station').agg({
        'hex': 'count',
        'radius_miles': ['min', 'max', 'mean']
    }).round(2)
    station_groups.columns = ['Num_Hexagons', 'Min_Radius', 'Max_Radius', 'Avg_Radius']
    print(station_groups)
    
    # Mostrar hexágonos centrais
    print("\n" + "-"*70)
    print("HEXÁGONOS CENTRAIS POR DELIVERY STATION")
    print("-"*70)
    central_hexs = centroid_df[centroid_df['is_center'] == True]
    for _, row in central_hexs.iterrows():
        print(f"  {row['delivery_station']}: {row['hex']} | Raio: {row['radius_miles']} mi")
    
    # Amostra de dados
    print("\n" + "-"*70)
    print("AMOSTRA DE DADOS (Primeiros 10 registros)")
    print("-"*70)
    print(centroid_df.head(10).to_string(index=False))
    
    # Exportar estatísticas
    output_file = "centroid_analysis.csv"
    centroid_df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"\n✅ Análise salva em: {output_file}")
    
    return centroid_df


def test_radius_distribution():
    """Analisa a distribuição de raios com mais detalhes."""
    
    print("\n" + "="*70)
    print("TESTE: Distribuição de Raios")
    print("="*70 + "\n")
    
    generator = HexagonGenerator()
    centroid_df = generator.get_hex_centroids_from_jurisdiction()
    
    if centroid_df.empty:
        print("❌ Nenhum dado foi extraído!")
        return
    
    # Detalhar por raio
    for radius in sorted(centroid_df['radius_miles'].unique()):
        subset = centroid_df[centroid_df['radius_miles'] == radius]
        print(f"\n📊 Hexágonos com raio de {radius} milhas:")
        print(f"   • Quantidade: {len(subset)}")
        print(f"   • Delivery Stations: {', '.join(subset['delivery_station'].unique())}")
        print(f"   • Hexágonos centrais: {subset['is_center'].sum()}")
    
    return centroid_df


if __name__ == "__main__":
    try:
        # Teste 1: Análise completa
        centroid_df = test_jurisdiction_centroids()
        
        # Teste 2: Distribuição de raios
        test_radius_distribution()
        
        print("\n" + "="*70)
        print("✅ TODOS OS TESTES CONCLUÍDOS COM SUCESSO!")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Erro durante o teste: {e}")
        import traceback
        traceback.print_exc()
