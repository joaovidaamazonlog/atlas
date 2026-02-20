# ATLAS/backend/config.py

from datetime import datetime
from pathlib import Path

# --- Caminhos de Arquivos e Pastas ---
BASE_PATH = Path(r"C:\Users\joaovida\Documents\Projetos\atlas\backend")
DEST_FOLDER = Path(r"C:\Users\joaovida\Documents\Projetos\atlas\data")
DB_PATH = Path(r"C:\Users\joaovida\Documents\Projetos\CNPJ_Brasil")
BASE_PACKAGES = Path(r"C:\Users\joaovida\Documents\Projetos\base_pacotes.csv")

# Arquivos de entrada
EXCEL_FILE_PATH = BASE_PATH / "terra.xlsm"
BASE_PARTNERS = DEST_FOLDER / "dados_mapa.json"
BASE_JURISDICTION = DEST_FOLDER / "jurisdiction.geojson"
BASE_PREVIOUS_SNAPSHOT = DEST_FOLDER / "snapshot_current.json"
CSV_INPUT_PATH = BASE_PATH / "pontos_teste.csv"
DB_EMPRESAS = DB_PATH / "cnpj_2025_06.db"

# Variaveis de configuração de otimização
H3_RESOLUTION = 9
HEX_EDGE_M = 174
RADII_M = [
        {"radius_s": 200, "hex_distance": 1, "penalty": 20},
        {"radius_s": 500, "hex_distance": 3, "penalty": 50},
        {"radius_s": 800, "hex_distance": 5, "penalty": 80},
        {"radius_s": 1100, "hex_distance": 7, "penalty": 1000},
        {"radius_s": 1500, "hex_distance": 9, "penalty": 5000}
    ]
CAPACITIES = [40, 41, 42]
MIN_CAPACITY = 40
MAX_CAPACITY = 42
CLUSTER_PER_STATION = {
    "DBR9": 14,
    "DSP2": 7,
    "DSP4": 6,
    "DSP5": 2,
    "DBH5": 2,
    "DMG2": 2,
    "DBS5": 2,
    "DCE3": 3,
    "DES2": 1,
    "DFR2": 2,
    "DGO2": 2,
    "DPB3": 1,
    "DPE4": 2,
    "DPR2": 2,
    "DRJ3": 6,
    "DRS5": 3,
    "DSA8": 2,
    "DAM1": 2
}

# Arquivo JSON de saída
# O nome do arquivo será dinâmico, mas o diretório de saída é fixo.
OUTPUT_JSON_DIR = DEST_FOLDER 
OUTPUT_JSON_FILENAME_PREFIX = "dados_mapa"
OUTPUT_JSON_SCORECARD_FILENAME_PREFIX = "dados_scorecard"


# --- Configurações do Excel ---
MACRO_NAME = "RefreshAll_Save"
MACRO_TIMEOUT_SECONDS = 600

# Abas a serem lidas do arquivo Excel
SHEETS_TO_LOAD = [
    "Active",
    "Launches",
    "Delivery Stations",
    "ADV - Coverage raw data",
    "Lead",
    "PerfectMile"
]

# --- Nomes de Colunas (para garantir consistência) ---
# É uma boa prática definir nomes de colunas aqui para evitar erros de digitação no código.
# Adapte os nomes para corresponder exatamente às suas colunas no Excel.
COL_STORE_ID = "StoreID"
COL_LATITUDE = "Latitude"
COL_LONGITUDE = "Longitude"
COL_RADIUS = "Radius"
COL_STATUS = "Status"

# --- Configurações de Processamento Scorecard ---
SCORECARD_CONFIG = {
    "col_responsavel" : "Owner",
    "col_origem" : "LeadSource",
    "col_data_contato" : "Initial_Contact_Date__c",
    "col_data_cadastro" : "Vetting_Date__c",
    "col_data_conversao" : "ConvertedDate",
    "col_status" : "Status",
    "col_lead": "Name",
    "metas_contato_por_canal": {
        "Website Pardot Form": 3,
        "In-Person Visit": 30,
        "Cold Call": 50,
        "Referral": 2
    },
    "pesos_contatos_por_origem": {
        "Cold Call": 1,
        "Website Pardot Form": 0.5,
        "In-Person Visit": 2,
        "Referral": 1.5  
    },
    "pesos_cadatros_por_origem": {
        "Cold Call": 3.5,
        "Website Pardot Form": 1.5,
        "In-Person Visit": 3.0,
        "Referral": 2.0  
    },
    "metas_semanais_gerais": {
        "contatos": 2550,
        "cadastros": 58,
        "conversoes": 58
    },
}

ADES_SCOUTING = {
    "mbrenosa": "Breno Santos", 
    "crafaeln": "Rafael Calçado ",
    "erihsouz": "Eric Souza",
    "josimaju": "Josimar Junior",
    "qgucosta": "Gustavo Costa",
    "pedtneto": "Pedro Neto",
    "qsidneyl": "Sidney Lima",
    "clertoli": "Clerton Oliveira",
    "swagnerq": "Wagner Silva",
    "krampeaf": "Fabiane Krampe",
    "eveomart": "Everton Martins",
    "silvmac": "Maria Silva",
    "qlilimat": "Lilian Mata",
    "kelvinbf": "Kelvin Fernandes",
    "scarvleo": "Francisco Leonardo",
    "bruzsilv": "Bruno Silva",
    "psoubren": "Brenda Souza",
    "jkowalsq": "João Kowalski",
    "dcfelipe": "Felipe Duarte",
    "alinmelu": "Aline Melo",
    "hhelenam": "Helena Melo",
    "elisidos": "Elisiane Ferreira",
    "deoraque": "Raquel Oliveira",
    "tlimaca": "Caroline Lima",
    "hildaalu": "Hilda Alves",
    "olfelipy": "Felipe Oliveira",
    "cryconce": "Cristiane Conceição",
    "wcaralla": "Allan Carvalho",
    "cicealme": "Cícero Almeida"
}

DELIVERY_STATIONS = [
    {
        "nome": "DAM1",
        "lat": -3.012941545364498, 
        "lon": -60.0318358491099,
    },
    {
        "nome": "DBR9",
        "lat": -23.526430422399706, 
        "lon": -46.763883028953224,
    },
    {
        "nome": "DSP2",
        "lat": -23.440077109738645, 
        "lon": -46.50445848287223,
    },
    {
        "nome": "DSP3",
        "lat": -23.65894284877369, 
        "lon": -46.837811452779064,
    },
    {
        "nome": "DSP4",
        "lat": -23.718941270492735, 
        "lon": -46.600980458970255,
    },
    {
        "nome": "DSP5",
        "lat": -23.11568603986924, 
        "lon": -47.210424265543885,
    },
    {
        "nome": "DBH5",
        "lat": -19.98598380572051,
        "lon": -43.96515833102083
    },
    {
        "nome": "DMG2",
        "lat": -19.855686335244705,
        "lon": -44.06176972663121,
    },
    {
        "nome": "DBS5",
        "lat": -15.7564055281563,
        "lon": -47.93077102073407,
    },
    {
        "nome": "DCE3",
        "lat": -3.865423633135394,
        "lon": -38.53438256225641,
    },
    {
        "nome": "DES2",
        "lat": -20.360739919147406, 
        "lon": -40.4215887980093,
    },
    {
        "nome": "DFR2",
        "lat": -27.613518349835264, 
        "lon": -48.65384506472715,
    },
    {
        "nome": "DGO2",
        "lat": -16.858168177754923, 
        "lon": -49.2495419237692,
    },
    {
        "nome": "DPB3",
        "lat": -7.126556602336433, 
        "lon": -34.925488687193834,
    },
    {
        "nome": "DPE4",
        "lat": -8.16709371727808, 
        "lon": -34.9463299929972,
    },
    {
        "nome": "DPR2",
        "lat": -25.494566508572724, 
        "lon": -49.325237783873014,
    },
    {
        "nome": "DRJ3",
        "lat": -22.94002864471327,
        "lon": -43.37736341019068,
    },
    {
        "nome": "DRS5",
        "lat": -29.96699187237036, 
        "lon": -51.18428699497623,
    },
    {
        "nome": "DSA8",
        "lat": -12.91006208103336, 
        "lon": -38.460637026769184
    },
    
]