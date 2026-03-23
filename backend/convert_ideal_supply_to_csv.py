import json
import csv
import os

def main():
    # Caminho para o arquivo JSON - usa caminho absoluto baseado no diretório do script
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    json_file_path = os.path.join(base_dir, 'ideal_supply.json')
    csv_file_path = os.path.join(base_dir, 'ideal_supply.csv')

    # Carregar o JSON
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Preparar os dados para CSV
    rows = []
    for territory, slots in data['slots'].items():
        for slot in slots:
            row = {
                'station_code': slot['station_code'],
                'slot_id': slot['slot_id'],
                'capacity_s': slot['capacity_s'],
                'lat': slot['lat'],
                'lon': slot['lon']
            }
            rows.append(row)

    # Escrever para CSV
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['station_code', 'slot_id', 'capacity_s', 'lat', 'lon'], delimiter=',')
        writer.writeheader()
        writer.writerows(rows)

    print(f"Arquivo CSV salvo em {csv_file_path}")
    
if __name__ == "__main__":
    main() 