# ATLAS/backend/config.py

from datetime import datetime
from pathlib import Path

# --- Caminhos de Arquivos e Pastas ---
BASE_PATH    = Path(r"C:\Users\joaovida\Documents\Projetos\atlas\backend")
PROJECT_ROOT = BASE_PATH.parent
DEST_FOLDER  = PROJECT_ROOT / "output_data"
DB_PATH      = Path(r"C:\Users\joaovida\Documents\Projetos\CNPJ_Brasil")
BASE_PACKAGES = Path(r"C:\Users\joaovida\Documents\Projetos\base_pacotes.csv")

# Arquivos de entrada
EXCEL_FILE_PATH = BASE_PATH / "terra.xlsm"
BASE_PARTNERS   = DEST_FOLDER / "dados_mapa.json"
BASE_JURISDICTION = PROJECT_ROOT / "config" / "jurisdiction.geojson"
BASE_PREVIOUS_SNAPSHOT = DEST_FOLDER / "snapshot_current.json"
CSV_INPUT_PATH  = BASE_PATH / "pontos_teste.csv"
DB_EMPRESAS     = DB_PATH / "cnpj_2025_06.db"

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
    "DBR9": 27,
    "DSP2": 12,
    "DSP4": 11,
    "DSP5": 5,
    "DBH5": 4,
    "DMG2": 13,
    "DBS5": 5,
    "DCE3": 2,
    "DES2": 3,
    "DFR2": 2,
    "DGO2": 4,
    "DPB3": 5,
    "DPE4": 15,
    "DPR2": 6,
    "DRJ3": 22,
    "DRS5": 10,
    "DSA8": 4,
    "DAM1": 5
}

# Arquivo JSON de saída
OUTPUT_JSON_DIR             = DEST_FOLDER
OUTPUT_JSON_FILENAME_PREFIX = "dados_mapa"


# --- Configurações do Excel ---
MACRO_NAME = "RefreshAll_Save"
MACRO_TIMEOUT_SECONDS = 600

# Abas a serem lidas do arquivo Excel
SHEETS_TO_LOAD = [
    "Active",
    "Launches",
    "Delivery Stations",
    "Jurisdictions",
    "WebLeads",
]

# --- Nomes de Colunas (para garantir consistência) ---
# É uma boa prática definir nomes de colunas aqui para evitar erros de digitação no código.
# Adapte os nomes para corresponder exatamente às suas colunas no Excel.
COL_STORE_ID = "StoreID"
COL_LATITUDE = "Latitude"
COL_LONGITUDE = "Longitude"
COL_RADIUS = "Radius"
COL_STATUS = "Status"

ADES_ACCOUNT_MANAGERS = [
  {
    "salesforce_id": "0055G00000B9BgLQAV",
    "alias": "alinmelu",
    "buckets": ["DSP2_T01"]
  },
  {
    "salesforce_id": "0055G00000B9BgVQAV",
    "alias": "oliveiya",
    "buckets": ["DSP2_T03"]
  },
  {
    "salesforce_id": "0055G00000BA5UXQA1",
    "alias": "hhelenam",
    "buckets": ["DSP2_T08"]
  },
  {
    "salesforce_id": "005at00000Bn1KrAAJ",
    "alias": "vferrema",
    "buckets": ["DSP2_T12"]
  },
  {
    "salesforce_id": "005at00000AwtxgAAB",
    "alias": "henrenat",
    "buckets": ["DSP2_T07"]
  },
  {
    "salesforce_id": "005at00000CmvWyAAJ",
    "alias": "jdgouvei",
    "buckets": ["DSP2_T06", "DSP2_T02", "DSP2_T09"]
  },
  {
    "salesforce_id": "005at00000CnOjpAAF",
    "alias": "cavadnat",
    "buckets": ["DSP2_T05", "DSP2_T11"]
  },
  {
    "salesforce_id": "005at00000AwtxhAAB",
    "alias": "spinobar",
    "buckets": ["DSP2_T10", "DSP2_T04"]
  },
  {
    "salesforce_id": "005at000002NE7ZAAW",
    "alias": "natagovr",
    "buckets": ["DSP4_T08", "DSP4_T11"]
  },
  {
    "salesforce_id": "005at00000AwtxdAAB",
    "alias": "almecris",
    "buckets": ["DSP4_T09", "DSP4_T03"]
  },
  {
    "salesforce_id": "005at00000Bn2aGAAR",
    "alias": "nsantvan",
    "buckets": ["DSP4_T04", "DSP4_T10"]
  },
  {
    "salesforce_id": "005at00000Bn7A7AAJ",
    "alias": "sidaline",
    "buckets": ["DSP4_T02", "DSP4_T01"]
  },
  {
    "salesforce_id": "005at00000BnBQcAAN",
    "alias": "fsandian",
    "buckets": ["DSP4_T05", "DSP4_T06", "DSP4_T07"]
  },
  {
    "salesforce_id": "005at00000ADsT6AAL",
    "alias": "andrfec",
    "buckets": ["DSP5_T01", "DSP5_T04", "DSP5_T05"]
  },
  {
    "salesforce_id": "005at000001qfXyAAI",
    "alias": "olfelipy",
    "buckets": ["DSP5_T02", "DSP5_T03"]
  },
  {
    "salesforce_id": "0055G00000BA0QkQAL",
    "alias": "psoubren",
    "buckets": ["DRS5_T01", "DRS5_T05", "DRS5_T09"]
  },
  {
    "salesforce_id": "0055G00000BA5USQA1",
    "alias": "jkowalsq",
    "buckets": ["DRS5_T03", "DRS5_T08"]
  },
  {
    "salesforce_id": "005at00000ADsT7AAL",
    "alias": "julilsil",
    "buckets": ["DRS5_T02", "DRS5_T04", "DRS5_T06", "DRS5_T07", "DRS5_T10"]
  },
  {
    "salesforce_id": "005at000001qfY0AAI",
    "alias": "kelvinbf",
    "buckets": ["DPR2_T01", "DPR2_T03", "DPR2_T05"]
  },
  {
    "salesforce_id": "0055G00000BA0QuQAL",
    "alias": "qlilimat",
    "buckets": ["DPR2_T02", "DPR2_T04", "DPR2_T06"]
  },
  {
    "salesforce_id": "005at000002zVKJAA2",
    "alias": "lopefjen",
    "buckets": ["DBR9_T01"]
  },
  {
    "salesforce_id": "005at000005PufHAAS",
    "alias": "zcarlalo",
    "buckets": ["DBR9_T11", "DBR9_T03"]
  },
  {
    "salesforce_id": "005at000002kSTCAA2",
    "alias": "tlimaca",
    "buckets": ["DBR9_T14", "DBR9_T13"]
  },
  {
    "salesforce_id": "005at00000AwtxfAAB",
    "alias": "wsibruno",
    "buckets": ["DBR9_T06", "DBR9_T26"]
  },
  {
    "salesforce_id": "005at000003bF9eAAE",
    "alias": "suelezsa",
    "buckets": ["DBR9_T15", "DBR9_T07"]
  },
  {
    "salesforce_id": "005at00000AuQv0AAF",
    "alias": "hugomorb",
    "buckets": ["DBR9_T02", "DBR9_T08"]
  },
  {
    "salesforce_id": "005at00000BeXJwAAN",
    "alias": "ltvallim",
    "buckets": ["DBR9_T04", "DBR9_T09"]
  },
  {
    "salesforce_id": "005at00000BeXJvAAN",
    "alias": "angbasto",
    "buckets": ["DBR9_T16", "DBR9_T12"]
  },
  {
    "salesforce_id": "0055G00000B9BgkQAF",
    "alias": "elisidos",
    "buckets": ["DBR9_T21", "DBR9_T19"]
  },
  {
    "salesforce_id": "005at00000AuQuzAAF",
    "alias": "cgbarbos",
    "buckets": ["DBR9_T10", "DBR9_T27"]
  },
  {
    "salesforce_id": "005at00000AwtxeAAB",
    "alias": "vivianpg",
    "buckets": ["DBR9_T18"]
  },
  {
    "salesforce_id": "005at000004rgN0AAI",
    "alias": "lidkarol",
    "buckets": ["DBR9_T20", "DBR9_T17"]
  },
  {
    "salesforce_id": "005at00000CVob9AAD",
    "alias": "anaraujj",
    "buckets": ["DBR9_T22"]
  },
  {
    "salesforce_id": "0055G00000B9Bg6QAF",
    "alias": "wherlecr",
    "buckets": ["DBR9_T25", "DBR9_T23"]
  },
  {
    "salesforce_id": "0055G00000BA5UhQAL",
    "alias": "deoraque",
    "buckets": ["DBR9_T05", "DBR9_T24"]
  },
  {
    "salesforce_id": "005at000003bF9fAAE",
    "alias": "pbefelip",
    "buckets": ["DRJ3_T06"]
  },
  {
    "salesforce_id": "005at000004WxNdAAK",
    "alias": "eazcinti",
    "buckets": ["DRJ3_T01", "DRJ3_T03", "DRJ3_T04", "DRJ3_T07", "DRJ3_T08", "DRJ3_T09", "DRJ3_T13", "DRJ3_T14", "DRJ3_T16", "DRJ3_T17", "DRJ3_T18", "DRJ3_T20", "DRJ3_T22"]
  },
  {
    "salesforce_id": "005at000005PufGAAS",
    "alias": "thalessd",
    "buckets": ["DRJ3_T12", "DRJ3_T19", "DRJ3_T05", "DRJ3_T21"]
  },
  {
    "salesforce_id": "005at000002kSTDAA2",
    "alias": "bruzsilv",
    "buckets": ["DRJ3_T11"]
  },
  {
    "salesforce_id": "005at00000ADsT4AAL",
    "alias": "marthgab",
    "buckets": ["DRJ3_T15"]
  },
  {
    "salesforce_id": "005at0000086YH0AAM",
    "alias": "fenatalh",
    "buckets": ["DRJ3_T02", "DRJ3_T10"]
  },
  {
    "salesforce_id": "0055G00000BA0QGQA1",
    "alias": "erihsouz",
    "buckets": ["DBS5_T01", "DBS5_T02", "DBS5_T03", "DBS5_T06", "DBS5_T09", "DBS5_T12", "DBS5_T13", "DBS5_T14"]
  },
  {
    "salesforce_id": "0055G00000BA0QLQA1",
    "alias": "josimaju",
    "buckets": ["DBS5_T04", "DBS5_T05", "DBS5_T07", "DBS5_T08", "DBS5_T10", "DBS5_T11", "DBS5_T15"]
  },
  {
    "salesforce_id": "005at000004rgMzAAI",
    "alias": "wcaralla",
    "buckets": ["DGO2_T03"]
  },
  {
    "salesforce_id": "005at000003DxQMAA0",
    "alias": "krampeaf",
    "buckets": ["DGO2_T01", "DGO2_T02"]
  },
  {
    "salesforce_id": "0055G00000BA0QBQA1",
    "alias": "mbrenosa",
    "buckets": ["DBH5_T01", "DBH5_T02"]
  },
  {
    "salesforce_id": "005at000002kSTEAA2",
    "alias": "crafaeln",
    "buckets": ["DMG2_T01", "DMG2_T02", "DMG2_T03", "DMG2_T04", "DMG2_T05", "DMG2_T06", "DMG2_T07", "DMG2_T08", "DMG2_T09", "DMG2_T10", "DMG2_T11", "DMG2_T12", "DMG2_T13"]
  },
  {
    "salesforce_id": "005at00000534NZAAY",
    "alias": "cicealme",
    "buckets": ["DPE4_T06", "DPE4_T02", "DPE4_T07"]
  },
  {
    "salesforce_id": "005at000001ntHJAAY",
    "alias": "silvmac",
    "buckets": ["DPE4_T05", "DPE4_T03", "DPE4_T04", "DPE4_T01"]
  },
  {
    "salesforce_id": "005at000002zVKHAA2",
    "alias": "eveomart",
    "buckets": ["DPB3_T01", "DPB3_T02", "DPB3_T03", "DPB3_T04", "DPB3_T05"]
  },
  {
    "salesforce_id": "005at00000ADsT8AAL",
    "alias": "paualane",
    "buckets": ["DCE3_T16", "DCE3_T01", "DCE3_T12", "DCE3_T15", "DCE3_T14"]
  },
  {
    "salesforce_id": "0055G00000BA0QpQAL",
    "alias": "pedtneto",
    "buckets": ["DCE3_T11", "DCE3_T06", "DCE3_T04", "DCE3_T13", "DCE3_T02"]
  },
  {
    "salesforce_id": "005at000002GuY9AAK",
    "alias": "qsidneyl",
    "buckets": ["DCE3_T08", "DCE3_T07", "DCE3_T09", "DCE3_T05", "DCE3_T10", "DCE3_T03"]
  },
  {
    "salesforce_id": "005at000004Oo6DAAS",
    "alias": "cryconce",
    "buckets": ["DSA8_T01", "DSA8_T02"]
  },
  {
    "salesforce_id": "0055G00000BA0QQQA1",
    "alias": "dcfelipe",
    "buckets": ["DSA8_T03", "DSA8_T04"]
  },
  {
    "salesforce_id": "0055G00000BA5UIQA1",
    "alias": "swagnerq",
    "buckets": ["DES2_T01", "DES2_T02", "DES2_T03"]
  }
]

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