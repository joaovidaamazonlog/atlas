# /seu_projeto/config.py

from datetime import datetime

# --- Caminhos de Arquivos e Pastas ---
# Altere estes caminhos para corresponder ao seu ambiente
BASE_PATH = r"C:\Users\joaovida\Documents\Projetos\atlas\backend"
DEST_FOLDER = r"C:\Users\joaovida\Documents\Projetos\atlas\data"

# Arquivo Excel de entrada
EXCEL_FILE_PATH = f"{BASE_PATH}\\terra.xlsm"

#Arquivo CSV de entrada para clustering
CSV_INPUT_PATH = f"{BASE_PATH}\\pontos_teste.csv"

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