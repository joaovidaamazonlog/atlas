import pandas as pd
import json
import numpy as np
from typing import List, Dict, Any
from utils.formatters import format_date_to_str
from config import DELIVERY_STATIONS

class JsonGenerator:
    """
    Transforma o DataFrame final de lojas no formato JSON exato especificado,
    garantindo a remoção de todos os valores NaN.
    """
    @staticmethod
    def _clean_value(value, default=None):
        """
        Converte valores para serem compatíveis com JSON.
        NaN, NaT, e None se tornam o valor 'default' (que por padrão é null).
        """
        # A verificação pd.isna() lida com np.nan, None, e pd.NaT
        if pd.isna(value):
            return default
        # Converte tipos específicos do numpy para tipos nativos do Python
        if isinstance(value, (np.integer, np.int64)):
            return int(value)
        if isinstance(value, (np.floating, np.float64)):
            # Retorna int se não houver parte fracionária, senão arredonda
            return int(value) if float(value).is_integer() else round(float(value), 2)
        if isinstance(value, np.bool_):
            return bool(value)
        return value

    @staticmethod
    def _create_popup_html(row: pd.Series) -> str:
        """Gera o conteúdo HTML para o popup do marcador no mapa."""
        def table_row(label, value):
            # Usa _clean_value para garantir que 'N/A' seja mostrado para dados ausentes
            return f"<tr><td style='width:40%'><b>{label}:</b></td><td style='width:60%'>{JsonGenerator._clean_value(value, 'N/A')}</td></tr>"

        info_html = "<h5 style='font-weight: bold;'>Store Information</h5><table style='width:100%'>"
        info_html += table_row("Store ID", row.get("StoreID"))
        info_html += table_row("Name", row.get("Name"))
        info_html += table_row("Status", row.get("Status"))
        info_html += table_row("Supply Run", row.get("Supply Run"))
        info_html += table_row("Delivery Station", row.get("Delivery Station"))
        info_html += table_row("Jurisdiction Type", row.get("Jurisdiction Type"))
        info_html += table_row("Launch Date", format_date_to_str(row.get("Launch Date")))
        info_html += table_row("HCP Initiatives", row.get("Hub Delivery Initiatives"))
        info_html += table_row("HCP Host Partner", row.get("HCP Host Partner"))
        info_html += table_row("HCP Rate Card", row.get("HCP Rate Card"))
        info_html += table_row("Radius", f"{JsonGenerator._clean_value(row.get('Radius'), 'N/A')} m")
        info_html += "</table>"
    
        metrics_html = "<h5 style='font-weight: bold; margin-top: 10px;'>Metrics</h5><table style='width:100%'>"
        metrics_html += table_row("ADV", row.get("Actual ADV"))
        metrics_html += table_row("Eligible Packages", row.get("# Eligible Packages"))
        metrics_html += table_row("Partner Capacity", row.get("Partner Capacity"))
        metrics_html += "</table>"
        
        if row.get("Status") != "BG Checks":
            link_salesforce = f'<a href="https://dsp-portal.lightning.force.com/lightning/r/Account/{row.get('Id')}/view" target="_blank">View in Salesforce</a>'
        else:
            link_salesforce = f'<a href="https://dsp-portal.lightning.force.com/lightning/r/Lead/{row.get('Id')}/view" target="_blank">View in Salesforce</a>'
            
        link_whatsapp = ''
        if pd.notna(row.get("Phone")):
            phone_number = row.get("Phone").translate(str.maketrans({"(": "", ")": "", " ": "", "-": "", "+": ""}))
            link_whatsapp = f'Enviar menssagem <a href="https://wa.me/{phone_number}" target="_blank"><i class="fa fa-whatsapp" style="font-size:24px"></i></a>'
            

        return f'<div style="width: auto; max-height: auto; font-size: 12px;">{info_html}<hr class: "my-2">{link_salesforce}<br>{link_whatsapp}<hr class: "my-2">{metrics_html}</div>'

    @staticmethod
    def generate_json(period: dict, final_df: pd.DataFrame, output_path: str):
        """
        Converte o DataFrame para o formato JSON especificado e o salva.
        """
        print(f"Iniciando a geração do arquivo JSON com a estrutura final em: {output_path}")
        
        output_dict = {
            "period": period,
            "deliveryStations": [],
            "allMarkerData": []
        }   
        output_dict["deliveryStations"] = DELIVERY_STATIONS  
        output_dict["period"] = period

        for _, row in final_df.iterrows():
            
            phoneCorrection = str.maketrans({
                "(": "", 
                ")": "", 
                " ": "", 
                "-": "",
                "+": "",
            })
            
            phone = row.get("Phone").translate(phoneCorrection) if pd.notna(row.get("Phone")) else None
            
            # 1. CAMPOS DE NÍVEL SUPERIOR
            top_level_data = {
                "lat": row.get("Latitude"),
                "lon": row.get("Longitude"),
                "popup": JsonGenerator._create_popup_html(row),
                "tooltip": f"ID: {row.get('StoreID')} | Name: {row.get('Name')} | HUB Delivery Initiatives: {row.get('Hub Delivery Initiatives')}",
                "name": row.get("Name"),
                "telefone": phone,
                "store_id": row.get("StoreID"),
                "salesforce_id": row.get("Id"),
                "delivery_station": row.get("Delivery Station"),
                "status": row.get("Status"),
                "capacity": row.get("Volume Cap"),
                "jurisdiction_type": row.get("Jurisdiction Type"),
                "launch_date": format_date_to_str(row.get("Launch Date")),
                "exitedDate": format_date_to_str(row.get("Exit_Date__c")),
                "decision_status": row.get("Decision_Status__c"),
                "supply_run": row.get("Supply Run"),
                "hub_delivey_initiatives": row.get("Hub Delivery Initiatives"),
                "HCP_rate_card": row.get("HCP Rate Card"),
                "HCP_host_partner": row.get("HCP Host Partner"),
                "sorte_code": row.get("Sorte Code"),
                "zip_code": row.get("CEP"),
                "city": row.get("Cidade"),
                "radius": row.get("Radius"),
                "eligible_packages": row.get("# Eligible Packages"),
                "partner_capacity": row.get("Partner Capacity"),
                "ADV": row.get("Actual ADV"),
                "optimization": row.get("optimization_data"),
            }
            
            top_level_data = {k: JsonGenerator._clean_value(v) for k, v in top_level_data.items()}

            # 2. CAMPO "overlap_data"
            overlap_list = row.get("overlap_data")
            if isinstance(overlap_list, list):
                # Limpa cada dicionário dentro da lista de overlaps
                cleaned_overlap_list = [{k: JsonGenerator._clean_value(v) for k, v in item.items()} for item in overlap_list]
                top_level_data["overlap_data"] = cleaned_overlap_list
            else:
                top_level_data["overlap_data"] = None

            # 3. CAMPO "main_store_data"
            main_store_data_raw = {
                "store_id": row.get("StoreID"), 
                "radius": row.get("Radius"),
                "total_packages_allocated": row.get("TotalPackagesAllocated"),
                "eligible_packages": row.get("# Eligible Packages"),
                "partner_capacity": row.get("Partner Capacity"), 
                "ADV": row.get("Actual ADV"),
                "other_partners": row.get("Eligible and Allocated to OTHER partners"),
                "eligible_could_be_allocated": row.get("Eligible and could be allocated to CURRENT partner"),
                "allocated_van": row.get("Allocated to VAN"),
                "working_days": row.get("Qty working days"),
                "capped_days": row.get("% of capped days"),
                "qty_capping_days": row.get("Qty Capping days"),
                "rostering": row.get("Rostering %"),
                "overlapping_count": row.get("overlapping_count"),
                "overlap_percent": row.get("overlap_percent"),
                "dispatched_packages": row.get("Dispatched Packages"),
                "delivered_packages": row.get("Delivered Packages"),
                "dea": row.get("DEA %"),
                "ead" : row.get("EAD %"),
                "dcr": row.get("DCR %"),
                "fdds": row.get("FDDS %"),
                "ftds": row.get("FTDS %"),
            }
            # Limpa todos os valores no dicionário main_store_data
            top_level_data["main_store_data"] = {k: JsonGenerator._clean_value(v) for k, v in main_store_data_raw.items()}
            
            output_dict["allMarkerData"].append(top_level_data)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_dict, f, ensure_ascii=False, indent=4)
            
        print(f"Arquivo JSON gerado com sucesso em '{output_path}'.")