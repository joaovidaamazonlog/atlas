# ATLAS/backend/shared/config.py

from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------

BASE_PATH    = Path(r"C:\Users\joaovida\Documents\Projetos\atlas\backend")
PROJECT_ROOT = BASE_PATH.parent
DEST_FOLDER  = PROJECT_ROOT / "output_data"
DB_PATH      = Path(r"C:\Users\joaovida\Documents\Projetos\CNPJ_Brasil")

# Entradas
BASE_PACKAGES          = Path(r"C:\Users\joaovida\Documents\Projetos\base_pacotes.csv")
EXCEL_FILE_PATH        = BASE_PATH / "terra.xlsm"
BASE_PARTNERS          = DEST_FOLDER / "dados_mapa.json"
BASE_JURISDICTION      = PROJECT_ROOT / "config" / "jurisdiction.geojson"
BASE_PREVIOUS_SNAPSHOT = DEST_FOLDER / "snapshot_current.json"
DB_EMPRESAS            = DB_PATH / "cnpj_2025_06.db"

# Saída
OUTPUT_JSON_DIR             = DEST_FOLDER
OUTPUT_JSON_FILENAME_PREFIX = "dados_mapa"

# ---------------------------------------------------------------------------
# Otimização H3 / CP-SAT
# ---------------------------------------------------------------------------

H3_RESOLUTION = 9
HEX_EDGE_M    = 174

RADII_M = [
    {"radius_s": 200,  "hex_distance": 1, "penalty": 20},
    {"radius_s": 500,  "hex_distance": 3, "penalty": 50},
    {"radius_s": 800,  "hex_distance": 5, "penalty": 80},
    {"radius_s": 1100, "hex_distance": 7, "penalty": 1000},
    {"radius_s": 1500, "hex_distance": 9, "penalty": 5000},
]

CAPACITIES   = [40, 41, 42]
MIN_CAPACITY = 40
MAX_CAPACITY = 42

CLUSTER_PER_STATION = {
    "DBR9": 27, "DSP2": 12, "DSP4": 11, "DSP5": 5,
    "DBH5": 4,  "DMG2": 13, "DBS5": 5,  "DCE3": 13,
    "DES2": 3,  "DFR2": 2,  "DGO2": 4,  "DPB3": 5,
    "DPE4": 15, "DPR2": 6,  "DRJ3": 22, "DRS5": 10,
    "DSA8": 4,  "DAM1": 5,
}

# ---------------------------------------------------------------------------
# Excel / Salesforce
# ---------------------------------------------------------------------------

MACRO_NAME            = "RefreshAll_Save"
MACRO_TIMEOUT_SECONDS = 600

SHEETS_TO_LOAD = [
    "Active",
    "Launches",
    "Delivery Stations",
    "Jurisdictions",
    "WebLeads",
]

# ---------------------------------------------------------------------------
# Delivery Stations
# ---------------------------------------------------------------------------

# Bases canônicas (com polígono de jurisdição próprio)
DELIVERY_STATIONS = [
    {"nome": "DAM1", "lat": -3.012941545364498,   "lon": -60.0318358491099},
    {"nome": "DBR9", "lat": -23.526430422399706,  "lon": -46.763883028953224},
    {"nome": "DBH5", "lat": -19.98598380572051,   "lon": -43.96515833102083},
    {"nome": "DBS5", "lat": -15.7564055281563,    "lon": -47.93077102073407},
    {"nome": "DCE3", "lat": -3.865423633135394,   "lon": -38.53438256225641},
    {"nome": "DES2", "lat": -20.360739919147406,  "lon": -40.4215887980093},
    {"nome": "DFR2", "lat": -27.613518349835264,  "lon": -48.65384506472715},
    {"nome": "DGO2", "lat": -16.858168177754923,  "lon": -49.2495419237692},
    {"nome": "DMG2", "lat": -19.855686335244705,  "lon": -44.06176972663121},
    {"nome": "DPB3", "lat": -7.126556602336433,   "lon": -34.925488687193834},
    {"nome": "DPE4", "lat": -8.16709371727808,    "lon": -34.9463299929972},
    {"nome": "DPR2", "lat": -25.494566508572724,  "lon": -49.325237783873014},
    {"nome": "DRJ3", "lat": -22.94002864471327,   "lon": -43.37736341019068},
    {"nome": "DRS5", "lat": -29.96699187237036,   "lon": -51.18428699497623},
    {"nome": "DSA8", "lat": -12.91006208103336,   "lon": -38.460637026769184},
    {"nome": "DSP2", "lat": -23.440077109738645,  "lon": -46.50445848287223},
    {"nome": "DSP4", "lat": -23.718941270492735,  "lon": -46.600980458970255},
    {"nome": "DSP5", "lat": -23.11568603986924,   "lon": -47.210424265543885},
]

# Áreas satélite: polígonos incorporados à base canônica correspondente.
# O pipeline trata pacotes dessas áreas como se fossem da base canônica.
STATION_ALIASES = {
    "XBA1": "DSA8",   # satélite de DSA8
    "XCS1": "DRS5",   # satélite de DRS5
    "XGA2": "DGO2",   # satélite de DGO2
    "XPB1": "DPB3",   # satélite de DPB3
    "PUM2": "DRJ3",   # satélite de DRJ3
    "XRJ2": "DRJ3",   # satélite de DRJ3
    "XRJ4": "DRJ3",   # satélite de DRJ3
    "XSJ1": "DSP4",   # satélite de DSP4
    "XSP7": "DSP5",   # satélite de DSP5
    "XSP9": "DSP5",   # satélite de DSP5
    "XCP1": "DSP5",   # satélite de DSP5
}

# ---------------------------------------------------------------------------
# Account Managers (ADEs)
# ---------------------------------------------------------------------------

ADES_ACCOUNT_MANAGERS = [
    {"salesforce_id": "0055G00000B9BgLQAV", "alias": "alinmelu", "buckets": ["DSP2_bucket-01"]},
    {"salesforce_id": "0055G00000B9BgVQAV", "alias": "oliveiya", "buckets": ["DSP2_bucket-03"]},
    {"salesforce_id": "0055G00000BA5UXQA1", "alias": "hhelenam", "buckets": ["DSP2_bucket-08"]},
    {"salesforce_id": "005at00000Bn1KrAAJ", "alias": "vferrema", "buckets": ["DSP2_bucket-12"]},
    {"salesforce_id": "005at00000AwtxgAAB", "alias": "henrenat", "buckets": ["DSP2_bucket-07"]},
    {"salesforce_id": "005at00000CmvWyAAJ", "alias": "jdgouvei", "buckets": ["DSP2_bucket-06", "DSP2_bucket-02", "DSP2_bucket-09"]},
    {"salesforce_id": "005at00000CnOjpAAF", "alias": "cavadnat", "buckets": ["DSP2_bucket-05", "DSP2_bucket-11"]},
    {"salesforce_id": "005at00000AwtxhAAB", "alias": "spinobar", "buckets": ["DSP2_bucket-10", "DSP2_bucket-04"]},
    {"salesforce_id": "005at000002NE7ZAAW", "alias": "natagovr", "buckets": ["DSP4_bucket-08", "DSP4_bucket-11"]},
    {"salesforce_id": "005at00000AwtxdAAB", "alias": "almecris", "buckets": ["DSP4_bucket-09", "DSP4_bucket-03"]},
    {"salesforce_id": "005at00000Bn2aGAAR", "alias": "nsantvan", "buckets": ["DSP4_bucket-04", "DSP4_bucket-10"]},
    {"salesforce_id": "005at00000Bn7A7AAJ", "alias": "sidaline", "buckets": ["DSP4_bucket-02", "DSP4_bucket-01"]},
    {"salesforce_id": "005at00000BnBQcAAN", "alias": "fsandian", "buckets": ["DSP4_bucket-05", "DSP4_bucket-06", "DSP4_bucket-07"]},
    {"salesforce_id": "005at00000ADsT6AAL", "alias": "andrfec",  "buckets": ["DSP5_bucket-01", "DSP5_bucket-04", "DSP5_bucket-05"]},
    {"salesforce_id": "005at000001qfXyAAI", "alias": "olfelipy", "buckets": ["DSP5_bucket-02", "DSP5_bucket-03"]},
    {"salesforce_id": "0055G00000BA0QkQAL", "alias": "psoubren", "buckets": ["DRS5_bucket-01", "DRS5_bucket-05", "DRS5_bucket-09"]},
    {"salesforce_id": "0055G00000BA5USQA1", "alias": "jkowalsq", "buckets": ["DRS5_bucket-03", "DRS5_bucket-08"]},
    {"salesforce_id": "005at00000ADsT7AAL", "alias": "julilsil", "buckets": ["DRS5_bucket-02", "DRS5_bucket-04", "DRS5_bucket-06", "DRS5_bucket-07", "DRS5_bucket-10"]},
    {"salesforce_id": "005at000001qfY0AAI", "alias": "kelvinbf", "buckets": ["DPR2_bucket-01", "DPR2_bucket-03", "DPR2_bucket-05"]},
    {"salesforce_id": "0055G00000BA0QuQAL", "alias": "qlilimat", "buckets": ["DPR2_bucket-02", "DPR2_bucket-04", "DPR2_bucket-06"]},
    {"salesforce_id": "005at000002zVKJAA2", "alias": "lopefjen", "buckets": ["DBR9_bucket-01"]},
    {"salesforce_id": "005at000005PufHAAS", "alias": "zcarlalo", "buckets": ["DBR9_bucket-11", "DBR9_bucket-03"]},
    {"salesforce_id": "005at000002kSTCAA2", "alias": "tlimaca",  "buckets": ["DBR9_bucket-14", "DBR9_bucket-13"]},
    {"salesforce_id": "005at00000AwtxfAAB", "alias": "wsibruno", "buckets": ["DBR9_bucket-06", "DBR9_bucket-26"]},
    {"salesforce_id": "005at000003bF9eAAE", "alias": "suelezsa", "buckets": ["DBR9_bucket-15", "DBR9_bucket-07"]},
    {"salesforce_id": "005at00000AuQv0AAF", "alias": "hugomorb", "buckets": ["DBR9_bucket-02", "DBR9_bucket-08"]},
    {"salesforce_id": "005at00000BeXJwAAN", "alias": "ltvallim", "buckets": ["DBR9_bucket-04", "DBR9_bucket-09"]},
    {"salesforce_id": "005at00000BeXJvAAN", "alias": "angbasto", "buckets": ["DBR9_bucket-16", "DBR9_bucket-12"]},
    {"salesforce_id": "0055G00000B9BgkQAF", "alias": "elisidos", "buckets": ["DBR9_bucket-21", "DBR9_bucket-19"]},
    {"salesforce_id": "005at00000AuQuzAAF", "alias": "cgbarbos", "buckets": ["DBR9_bucket-10", "DBR9_bucket-27"]},
    {"salesforce_id": "005at00000AwtxeAAB", "alias": "vivianpg", "buckets": ["DBR9_bucket-18"]},
    {"salesforce_id": "005at000004rgN0AAI", "alias": "lidkarol", "buckets": ["DBR9_bucket-20", "DBR9_bucket-17"]},
    {"salesforce_id": "005at00000CVob9AAD", "alias": "anaraujj", "buckets": ["DBR9_bucket-22"]},
    {"salesforce_id": "0055G00000B9Bg6QAF", "alias": "wherlecr", "buckets": ["DBR9_bucket-25", "DBR9_bucket-23"]},
    {"salesforce_id": "0055G00000BA5UhQAL", "alias": "deoraque", "buckets": ["DBR9_bucket-05", "DBR9_bucket-24"]},
    {"salesforce_id": "005at000003bF9fAAE", "alias": "pbefelip", "buckets": ["DRJ3_bucket-06"]},
    {"salesforce_id": "005at000004WxNdAAK", "alias": "eazcinti", "buckets": ["DRJ3_bucket-01", "DRJ3_bucket-03", "DRJ3_bucket-04", "DRJ3_bucket-07", "DRJ3_bucket-08", "DRJ3_bucket-09", "DRJ3_bucket-13", "DRJ3_bucket-14", "DRJ3_bucket-16", "DRJ3_bucket-17", "DRJ3_bucket-18", "DRJ3_bucket-20", "DRJ3_bucket-22"]},
    {"salesforce_id": "005at000005PufGAAS", "alias": "thalessd", "buckets": ["DRJ3_bucket-12", "DRJ3_bucket-19", "DRJ3_bucket-05", "DRJ3_bucket-21"]},
    {"salesforce_id": "005at000002kSTDAA2", "alias": "bruzsilv", "buckets": ["DRJ3_bucket-11"]},
    {"salesforce_id": "005at00000ADsT4AAL", "alias": "marthgab", "buckets": ["DRJ3_bucket-15"]},
    {"salesforce_id": "005at0000086YH0AAM", "alias": "fenatalh", "buckets": ["DRJ3_bucket-02", "DRJ3_bucket-10"]},
    {"salesforce_id": "0055G00000BA0QGQA1", "alias": "erihsouz", "buckets": ["DBS5_bucket-01", "DBS5_bucket-02", "DBS5_bucket-03", "DBS5_bucket-06", "DBS5_bucket-09", "DBS5_bucket-12", "DBS5_bucket-13", "DBS5_bucket-14"]},
    {"salesforce_id": "0055G00000BA0QLQA1", "alias": "josimaju", "buckets": ["DBS5_bucket-04", "DBS5_bucket-05", "DBS5_bucket-07", "DBS5_bucket-08", "DBS5_bucket-10", "DBS5_bucket-11", "DBS5_bucket-15"]},
    {"salesforce_id": "005at000004rgMzAAI", "alias": "wcaralla", "buckets": ["DGO2_bucket-03"]},
    {"salesforce_id": "005at000003DxQMAA0", "alias": "krampeaf", "buckets": ["DGO2_bucket-01", "DGO2_bucket-02"]},
    {"salesforce_id": "0055G00000BA0QBQA1", "alias": "mbrenosa", "buckets": ["DBH5_bucket-01", "DBH5_bucket-02"]},
    {"salesforce_id": "005at000002kSTEAA2", "alias": "crafaeln", "buckets": ["DMG2_bucket-01", "DMG2_bucket-02", "DMG2_bucket-03", "DMG2_bucket-04", "DMG2_bucket-05", "DMG2_bucket-06", "DMG2_bucket-07", "DMG2_bucket-08", "DMG2_bucket-09", "DMG2_bucket-10", "DMG2_bucket-11", "DMG2_bucket-12", "DMG2_bucket-13"]},
    {"salesforce_id": "005at00000534NZAAY", "alias": "cicealme", "buckets": ["DPE4_bucket-06", "DPE4_bucket-02", "DPE4_bucket-07"]},
    {"salesforce_id": "005at000001ntHJAAY", "alias": "silvmac",  "buckets": ["DPE4_bucket-05", "DPE4_bucket-03", "DPE4_bucket-04", "DPE4_bucket-01"]},
    {"salesforce_id": "005at000002zVKHAA2", "alias": "eveomart", "buckets": ["DPB3_bucket-01", "DPB3_bucket-02", "DPB3_bucket-03", "DPB3_bucket-04", "DPB3_bucket-05"]},
    {"salesforce_id": "005at00000ADsT8AAL", "alias": "paualane", "buckets": ["DCE3_bucket-16", "DCE3_bucket-01", "DCE3_bucket-12", "DCE3_bucket-15", "DCE3_bucket-14"]},
    {"salesforce_id": "0055G00000BA0QpQAL", "alias": "pedtneto", "buckets": ["DCE3_bucket-11", "DCE3_bucket-06", "DCE3_bucket-04", "DCE3_bucket-13", "DCE3_bucket-02"]},
    {"salesforce_id": "005at000002GuY9AAK", "alias": "qsidneyl", "buckets": ["DCE3_bucket-08", "DCE3_bucket-07", "DCE3_bucket-09", "DCE3_bucket-05", "DCE3_bucket-10", "DCE3_bucket-03"]},
    {"salesforce_id": "005at000004Oo6DAAS", "alias": "cryconce", "buckets": ["DSA8_bucket-01", "DSA8_bucket-02"]},
    {"salesforce_id": "0055G00000BA0QQQA1", "alias": "dcfelipe", "buckets": ["DSA8_bucket-03", "DSA8_bucket-04"]},
    {"salesforce_id": "0055G00000BA5UIQA1", "alias": "swagnerq", "buckets": ["DES2_bucket-01", "DES2_bucket-02", "DES2_bucket-03"]},
]

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Scouting (alias → nome completo)
# ---------------------------------------------------------------------------

ADES_SCOUTING = {
    "mbrenosa": "Breno Santos",
    "crafaeln": "Rafael Calçado",
    "erihsouz": "Eric Souza",
    "josimaju": "Josimar Junior",
    "qgucosta": "Gustavo Costa",
    "pedtneto": "Pedro Neto",
    "qsidneyl": "Sidney Lima",
    "clertoli": "Clerton Oliveira",
    "swagnerq": "Wagner Silva",
    "krampeaf": "Fabiane Krampe",
    "eveomart": "Everton Martins",
    "silvmac":  "Maria Silva",
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
    "tlimaca":  "Caroline Lima",
    "hildaalu": "Hilda Alves",
    "olfelipy": "Felipe Oliveira",
    "cryconce": "Cristiane Conceição",
    "wcaralla": "Allan Carvalho",
    "cicealme": "Cícero Almeida",
}

# ---------------------------------------------------------------------------
# Hierarquia operacional: BDM → CTL → ADE
#
# Estrutura:
#   BDM  — responsável por uma região (conjunto de bases)
#   CTL  — responsável por um subconjunto de territorios dentro de uma base
#   ADE  — responsável por um ou mais territórios (buckets) dentro de uma base
#
# Como preencher:
#   - Campos "name", "email" dos BDMs e CTLs: preencher manualmente.
#   - "salesforce_id" dos ADEs: já populado a partir de ADES_ACCOUNT_MANAGERS.
#   - CTLs sem nome definido estão marcados com "" — preencher conforme o time.
#   - A divisão de CTLs por base é um placeholder; ajuste conforme a realidade.
# ---------------------------------------------------------------------------

TEAM = [

    # ── SP ───────────────────────────────────────────────────────────────────
    {
        "role": "BDM",
        "name": "Yago Romeiro",
        "alias": "yromeiro",
        "email": "yromeiro@amazon.com",
        "salesforce_id": "",
        "region": "SP",
        "stations": ["DBR9"],
        "reports": [

            # DBR9 — 27 territórios
            {
                "role": "CTL",
                "name": "Vanessa Azevedo",
                "alias": "vanferaz",
                "email": "vanferaz@amazon.com",
                "salesforce_id": "005at00000FLBhN",
                "stations": ["DBR9"],
                "reports": [
                    {"role": "ADE", "name": "Kethelyn Santos",              "alias": "sakethel",  "email": "sakethel@amazon.com",  "salesforce_id": "005at00000EJUvE",  "buckets": ["DBR9_bucket-15"]},
                    {"role": "ADE", "name": "Jandira Oliveira",             "alias": "olijandi",  "email": "olijandi@amazon.com",  "salesforce_id": "005at00000EJVT7",  "buckets": ["DBR9_bucket-20"]},
                    {"role": "ADE", "name": "Caroline Lima",                "alias": "tlimaca",   "email": "tlimaca@amazon.com",   "salesforce_id": "005at00000EJUf4",  "buckets": ["DBR9_bucket-16", "DBR9_bucket-12"]},
                    {"role": "ADE", "name": "Mariane Jesus",                "alias": "qjesusm",   "email": "qjesusm@amazon.com",   "salesforce_id": "005at00000EJUyT",  "buckets": ["DBR9_bucket-10", "DBR9_bucket-06"]},
                    {"role": "ADE", "name": "Alicia Da Silva Sofia",        "alias": "alimsilv",  "email": "alimsilv@amazon.com",  "salesforce_id": "005at00000EJV01",  "buckets": ["DBR9_bucket-27"]},
                    {"role": "ADE", "name": "Johni Paiva",                  "alias": "johpaiva",  "email": "johpaiva@amazon.com",  "salesforce_id": "005at00000EJUAV",  "buckets": ["DBR9_bucket-23"]},
                    {"role": "ADE", "name": "Iuri Mendes",                  "alias": "iuriqmen",  "email": "iuriqmen@amazon.com",  "salesforce_id": "005at00000EJUvF",  "buckets": ["DBR9_bucket-24"]},
                    {"role": "ADE", "name": "Ester Santos",                 "alias": "sanestec",  "email": "sanestec@amazon.com",  "salesforce_id": "005at00000EJUwp",  "buckets": ["DBR9_bucket-26"]},
                    {"role": "ADE", "name": "Gabrieli Ferino",              "alias": "gaferino",  "email": "gaferino@amazon.com",  "salesforce_id": "005at00000EJV03",  "buckets": ["DBR9_bucket-14"]},
                    {"role": "ADE", "name": "Rozelia Silva",                "alias": "rozesilv",  "email": "rozesilv@amazon.com",  "salesforce_id": "005at00000EJUwq",  "buckets": ["DBR9_bucket-08", "DBR9_bucket-11"]},
                    {"role": "ADE", "name": "Mayara Silva",                 "alias": "xmayasil",  "email": "xmayasil@amazon.com",  "salesforce_id": "005at00000EJUAY",  "buckets": ["DBR9_bucket-18"]},
                    {"role": "ADE", "name": "Suelen Santos",                "alias": "suelezsa",  "email": "suelezsa@amazon.com",  "salesforce_id": "005at00000EJRPd",  "buckets": ["DBR9_bucket-04"]},
                    {"role": "ADE", "name": "Hugo Moraes",                  "alias": "hugomorb",  "email": "hugomorb@amazon.com",  "salesforce_id": "005at00000EJUtb",  "buckets": ["DBR9_bucket-02"]},
                    {"role": "ADE", "name": "Angelo Bastos",                "alias": "angbasto",  "email": "angbasto@amazon.com",  "salesforce_id": "005at00000EJQ0P",  "buckets": ["DBR9_bucket-19"]},
                    {"role": "ADE", "name": "Giovana Barbosa",              "alias": "cgbarbos",  "email": "cgbarbos@amazon.com",  "salesforce_id": "005at00000EJUta",  "buckets": ["DBR9_bucket-13"]},
                    {"role": "ADE", "name": "Vivian Peres",                 "alias": "vivianpg",  "email": "vivianpg@amazon.com",  "salesforce_id": "005at00000EJOHy",  "buckets": ["DBR9_bucket-05"]},
                    {"role": "ADE", "name": "Andresa Araujo",               "alias": "anaraujj",  "email": "anaraujj@amazon.com",  "salesforce_id": "005at00000EJTeM",  "buckets": ["DBR9_bucket-07"]},
                    {"role": "ADE", "name": "Herlei Cristina Da",           "alias": "wherlecr",  "email": "wherlecr@amazon.com",  "salesforce_id": "005at00000EJSAH",  "buckets": ["DBR9_bucket-01"]},
                    {"role": "ADE", "name": "Raquel Oliveira",              "alias": "deoraque",  "email": "deoraque@amazon.com",  "salesforce_id": "005at00000EJMEX",  "buckets": ["DBR9_bucket-25"]},
                    {"role": "ADE", "name": "Alex Oliveira Serafim Lima",   "alias": "mlimalex",  "email": "mlimalex@amazon.com",  "salesforce_id": "005at00000FLBav",  "buckets": ["DBR9_bucket-09"]},
                    {"role": "ADE", "name": "Jessica Caldo Burrattino",     "alias": "iburratt",  "email": "iburratt@amazon.com",  "salesforce_id": "005at00000FLBe9",  "buckets": ["DBR9_bucket-03"]},
                    {"role": "ADE", "name": "Andreson Alves Da Silva",      "alias": "andrsilg",  "email": "andrsilg@amazon.com",  "salesforce_id": "005at00000FL85C",  "buckets": ["DBR9_bucket-17"]},
                    {"role": "ADE", "name": "Clauton Moura Ferreira",       "alias": "ferclaut",  "email": "ferclaut@amazon.com",  "salesforce_id": "005at00000FLBcX",  "buckets": ["DBR9_bucket-21"]},
                    {"role": "ADE", "name": "Lilian De Oliveira",           "alias": "ililiaol",  "email": "ililiaol@amazon.com",  "salesforce_id": "005at00000FLBfl",  "buckets": ["DBR9_bucket-22"]},
                ],
            },
        ],
    },

    # ── SP/SUL ───────────────────────────────────────────────────────────────
    {
        "role": "BDM",
        "name": "",
        "alias": "",
        "email": "",
        "salesforce_id": "",
        "region": "SP/SUL",
        "stations": ["DSP2", "DSP4", "DSP5", "DPR2", "DFR2", "DRS5"],
        "reports": [

            # DSP2 — 12 territórios
            {
                "role": "CTL",
                "name": "Angelica Damasceno",
                "alias": "damasang",
                "email": "damasang@amazon.com",
                "salesforce_id": "005at00000EJTnu",
                "stations": ["DSP2"],
                "reports": [
                    {"role": "ADE", "name": "Aline Melo",       "alias": "alinmelu",  "email": "alinmelu@amazon.com",  "salesforce_id": "005at00000EJSAI",  "buckets": ["DSP2_bucket-04"]},
                    {"role": "ADE", "name": "Yasmin Oliveira",   "alias": "oliveiya",  "email": "oliveiya@amazon.com",  "salesforce_id": "005at00000EJUVN",  "buckets": ["DSP2_bucket-01"]},
                    {"role": "ADE", "name": "Helena Melo",       "alias": "hhelenam",  "email": "hhelenam@amazon.com",  "salesforce_id": "005at00000EJMEW",  "buckets": ["DSP2_bucket-11"]},
                    {"role": "ADE", "name": "Maria Ferreira",    "alias": "vferrema",  "email": "vferrema@amazon.com",  "salesforce_id": "005at00000EJSBx",  "buckets": ["DSP2_bucket-03"]},
                    {"role": "ADE", "name": "Renato Henrique",   "alias": "henrenat",  "email": "henrenat@amazon.com",  "salesforce_id": "005at00000EJSzr",  "buckets": ["DSP2_bucket-02"]},
                    {"role": "ADE", "name": "Josafa Gouveia",    "alias": "jdgouvei",  "email": "jdgouvei@amazon.com",  "salesforce_id": "005at00000EJV3F",  "buckets": ["DSP2_bucket-12", "DSP2_bucket-10"]},
                    {"role": "ADE", "name": "Natalia Cavadas",   "alias": "cavadnat",  "email": "cavadnat@amazon.com",  "salesforce_id": "005at00000EJV3G",  "buckets": ["DSP2_bucket-05"]},
                    {"role": "ADE", "name": "Barbara Spinola",   "alias": "spinobar",  "email": "spinobar@amazon.com",  "salesforce_id": "005at00000EJSzs",  "buckets": ["DSP2_bucket-08"]},
                    {"role": "ADE", "name": "Patricia Pinto",    "alias": "zpintpat",  "email": "zpintpat@amazon.com",  "salesforce_id": "005at00000EJUyR",  "buckets": ["DSP2_bucket-06"]},
                    {"role": "ADE", "name": "Antonio Junior",    "alias": "ajuniorf",  "email": "ajuniorf@amazon.com",  "salesforce_id": "005at00000EJUwn",  "buckets": ["DSP2_bucket-07", "DSP2_bucket-09"]},
                ],
            },

            # DSP4 — 11 territórios
            {
                "role": "CTL",
                "name": "Julia Simoes Motta",
                "alias": "simoesmj",
                "email": "simoesmj@amazon.com",
                "salesforce_id": "005at00000EJNVZ",
                "stations": ["DSP4"],
                "reports": [
                    {"role": "ADE", "name": "Allyson Yuri De Sousa",          "alias": "souallys",  "email": "souallys@amazon.com",  "salesforce_id": "005at00000EJSYV",  "buckets": ["DSP4_bucket-05", "DSP4_bucket-07"]},
                    {"role": "ADE", "name": "Thaina Antunes",                  "alias": "aantutha",  "email": "aantutha@amazon.com",  "salesforce_id": "005at00000EJUwr",  "buckets": ["DSP4_bucket-09", "DSP4_bucket-06", "DSP4_bucket-04"]},
                    {"role": "ADE", "name": "Veronica Isabelly De Almeida",    "alias": "veralmei",  "email": "veralmei@amazon.com",  "salesforce_id": "-",                "buckets": []},
                    {"role": "ADE", "name": "Fernanda Silva Magalhaes",        "alias": "magalhfe",  "email": "magalhfe@amazon.com",  "salesforce_id": "-",                "buckets": []},
                ],
            },

            # DSP5 — 5 territórios
            {
                "role": "CTL",
                "name": "Luciana Feijo",
                "alias": "lufeijo",
                "email": "lufeijo@amazon.com",
                "salesforce_id": "005at00000F8pkj",
                "stations": ["DSP5"],
                "reports": [
                    {"role": "ADE", "name": "Andreia Feliciano",              "alias": "andrfec",   "email": "andrfec@amazon.com",   "salesforce_id": "005at00000EJPQs",  "buckets": ["DSP5_bucket-04"]},
                    {"role": "ADE", "name": "Felipe Oliveira",                "alias": "olfelipy",  "email": "olfelipy@amazon.com",  "salesforce_id": "005at00000EJIMG",  "buckets": ["DSP5_bucket-05"]},
                    {"role": "ADE", "name": "Beatriz Pimenta",                "alias": "beatrzpi",  "email": "beatrzpi@amazon.com",  "salesforce_id": "005at00000F8gha",  "buckets": ["DSP5_bucket-01"]},
                    {"role": "ADE", "name": "Mychael Willian Damaceno",       "alias": "damacmyc",  "email": "damacmyc@amazon.com",  "salesforce_id": "-",                "buckets": ["DSP5_bucket-02"]},
                    {"role": "ADE", "name": "Luan Carvalho Rubiane",          "alias": "rubiluan",  "email": "rubiluan@amazon.com",  "salesforce_id": "-",                "buckets": ["DSP5_bucket-03"]},
                ],
            },

            # DPR2 — 6 territórios
            {
                "role": "CTL",
                "name": "",
                "alias": "",
                "email": "",
                "salesforce_id": "",
                "stations": ["DPR2"],
                "reports": [
                    {"role": "ADE", "name": "Kelvin Fernandes",                          "alias": "kelvinbf",  "email": "kelvinbf@amazon.com",  "salesforce_id": "005at00000EJUaD",  "buckets": ["DPR2_bucket-01"]},
                    {"role": "ADE", "name": "Dyene Rosere Dos Santos Rech",              "alias": "recdyene",  "email": "recdyene@amazon.com",  "salesforce_id": "-",                "buckets": ["DPR2_bucket-04"]},
                    {"role": "ADE", "name": "Daniel Gomide Rattmann",                    "alias": "drattmad",  "email": "drattmad@amazon.com",  "salesforce_id": "-",                "buckets": ["DPR2_bucket-03"]},
                    {"role": "ADE", "name": "Marcia Alegnasile Dias Dos Santos Lima",    "alias": "marcilik",  "email": "marcilik@amazon.com",  "salesforce_id": "-",                "buckets": ["DPR2_bucket-05"]},
                    {"role": "ADE", "name": "Vanessa Cristina Buiar",                    "alias": "vanbuiar",  "email": "vanbuiar@amazon.com",  "salesforce_id": "-",                "buckets": ["DPR2_bucket-02"]},
                    {"role": "ADE", "name": "Andrelise Laska De Oliveira",               "alias": "handroli",  "email": "handroli@amazon.com",  "salesforce_id": "-",                "buckets": ["DPR2_bucket-06"]},
                ],
            },

            # DFR2 — 2 territórios (sem ADE mapeado ainda)
            {
                "role": "CTL",
                "name": "",
                "alias": "",
                "email": "",
                "salesforce_id": "",
                "stations": ["DFR2"],
                "reports": [
                ],
            },

            # DRS5 — 10 territórios
            {
                "role": "CTL",
                "name": "",
                "alias": "",
                "email": "",
                "salesforce_id": "",
                "stations": ["DRS5"],
                "reports": [
                    {"role": "ADE", "name": "Brenda Sousa",              "alias": "psoubren",  "email": "psoubren@amazon.com",  "salesforce_id": "005at00000EJUYb",  "buckets": ["DRS5_bucket-01", "DRS5_bucket-02", "DRS5_bucket-04", "DRS5_bucket-05"]},
                    {"role": "ADE", "name": "Joao Kowalski",             "alias": "jkowalsq",  "email": "jkowalsq@amazon.com",  "salesforce_id": "005at00000EJUYf",  "buckets": ["DRS5_bucket-03", "DRS5_bucket-08", "DRS5_bucket-06", "DRS5_bucket-07"]},
                    {"role": "ADE", "name": "Marilene Gisele Da Silva",  "alias": "marileu",   "email": "marileu@amazon.com",   "salesforce_id": "-",                "buckets": ["DRS5_bucket-09", "DRS5_bucket-10"]},
                ],
            },
        ],
    },

    # ── RJ/CW ───────────────────────────────────────────────────────────────
    {
        "role": "BDM",
        "name": "Mariana Estevao Faria",
        "alias": "estevaof",
        "email": "estevaof@amazon.com",
        "salesforce_id": "005at00000F8u9H",
        "region": "RJ/CW",
        "stations": ["DSA8", "DES2", "DRJ3", "DBH5", "DMG2", "DGO2", "DBS5"],
        "reports": [

            # DRJ3 — 22 territórios
            {
                "role": "CTL",
                "name": "Yan Abrao",
                "alias": "abraoiya",
                "email": "abraoiya@amazon.com",
                "salesforce_id": "005at00000EJLC4",
                "stations": ["DRJ3"],
                "reports": [
                    {"role": "ADE", "name": "Juliana Almeida",              "alias": "almeijum",  "email": "almeijum@amazon.com",  "salesforce_id": "005at00000EJMBU",  "buckets": []},
                    {"role": "ADE", "name": "Juliete Santos",               "alias": "shjuliet",  "email": "shjuliet@amazon.com",  "salesforce_id": "005at00000EJSjm",  "buckets": []},
                    {"role": "ADE", "name": "Thiago Freitas",               "alias": "freithia",  "email": "freithia@amazon.com",  "salesforce_id": "005at00000EJUyQ",  "buckets": []},
                    {"role": "ADE", "name": "Bruno Silva",                  "alias": "bruzsilv",  "email": "bruzsilv@amazon.com",  "salesforce_id": "005at00000EJUf5",  "buckets": []},
                    {"role": "ADE", "name": "Gabriel Martins",              "alias": "marthgab",  "email": "marthgab@amazon.com",  "salesforce_id": "005at00000EJQN0",  "buckets": []},
                    {"role": "ADE", "name": "Natalia Cristina Ferreira",    "alias": "fenatalh",  "email": "fenatalh@amazon.com",  "salesforce_id": "005at00000EJTsf",  "buckets": []},
                ],
            },

            # DBS5 — 15 territórios
            {
                "role": "CTL",
                "name": "Yan Abrao",
                "alias": "abraoiya",
                "email": "abraoiya@amazon.com",
                "salesforce_id": "005at00000EJLC4",
                "stations": ["DBS5"],
                "reports": [
                    {"role": "ADE", "name": "Eric Souza",    "alias": "erihsouz",  "email": "erihsouz@amazon.com",  "salesforce_id": "005at00000EJUX1",  "buckets": []},
                    {"role": "ADE", "name": "Josimar Junior", "alias": "josimaju",  "email": "josimaju@amazon.com",  "salesforce_id": "005at00000EJUX2",  "buckets": []},
                ],
            },

            # DGO2 — 4 territórios
            {
                "role": "CTL",
                "name": "Yan Abrao",
                "alias": "abraoiya",
                "email": "abraoiya@amazon.com",
                "salesforce_id": "005at00000EJLC4",
                "stations": ["DGO2"],
                "reports": [
                    {"role": "ADE", "name": "Allan Carvalho",  "alias": "wcaralla",  "email": "wcaralla@amazon.com",  "salesforce_id": "005at00000EJNVW",  "buckets": []},
                    {"role": "ADE", "name": "Fabiane Krampe",  "alias": "krampeaf",  "email": "krampeaf@amazon.com",  "salesforce_id": "005at00000EJUgi",  "buckets": []},
                ],
            },

            # DES2 — 3 territórios
            {
                "role": "CTL",
                "name": "Yan Abrao",
                "alias": "abraoiya",
                "email": "abraoiya@amazon.com",
                "salesforce_id": "005at00000EJLC4",
                "stations": ["DES2"],
                "reports": [
                    {"role": "ADE", "name": "Wagner Silva",  "alias": "swagnerq",  "email": "swagnerq@amazon.com",  "salesforce_id": "005at00000EJUYe",  "buckets": []},
                ],
            },

            # DSA8 — 4 territórios
            {
                "role": "CTL",
                "name": "Yan Abrao",
                "alias": "abraoiya",
                "email": "abraoiya@amazon.com",
                "salesforce_id": "005at00000EJLC4",
                "stations": ["DSA8"],
                "reports": [
                    {"role": "ADE", "name": "Cristiane Conceicao",  "alias": "cryconce",  "email": "cryconce@amazon.com",  "salesforce_id": "005at00000EJUn9",  "buckets": ["DSA8_bucket-01", "DSA8_bucket-04"]},
                    {"role": "ADE", "name": "Felipe Duarte",         "alias": "dcfelipe",  "email": "dcfelipe@amazon.com",  "salesforce_id": "005at00000EJUX3",  "buckets": ["DSA8_bucket-02", "DSA8_bucket-03"]},
                ],
            },
        ],
    },

     # ── BH ───────────────────────────────────────────────────────────────────
    {
        "role": "BDM",
        "name": "Luiz Felipe Goulart ",
        "alias": "luizfggs",
        "email": "luizfggs@amazon.com",
        "salesforce_id": "",
        "region": "BH",
        "stations": ["DBH5", "DMG2"],
        "reports": [

            # DBH5 — 4 territórios
            {
                "role": "CTL",
                "name": "Lucas Magela",
                "alias": "lsouzafa",
                "email": "lsouzafa@amazon.com",
                "salesforce_id": "005at00000EJUVP",
                "stations": ["DBH5"],
                "reports": [
                    {"role": "ADE", "name": "Rafael Calcado",   "alias": "crafaeln",  "email": "crafaeln@amazon.com",  "salesforce_id": "005at00000EJUf6",  "buckets": ["DBH5_bucket-01"]},
                    {"role": "ADE", "name": "Aline Souza",       "alias": "alcsouza",  "email": "alcsouza@amazon.com",  "salesforce_id": "005at00000EJV04",  "buckets": ["DBH5_bucket-02"]},
                    {"role": "ADE", "name": "Mathaus Marques",   "alias": "mathausm",  "email": "mathausm@amazon.com",  "salesforce_id": "005at00000EJV05",  "buckets": ["DBH5_bucket-04", "DBH5_bucket-03"]},
                ],
            },

            # DMG2 — 13 territórios
            {
                "role": "CTL",
                "name": "Lucas Magela",
                "alias": "lsouzafa",
                "email": "lsouzafa@amazon.com",
                "salesforce_id": "005at00000EJUVP",
                "stations": ["DMG2"],
                "reports": [
                    {"role": "ADE", "name": "Helder Souza",                        "alias": "heldsouz",  "email": "heldsouz@amazon.com",  "salesforce_id": "005at00000EJUaM",  "buckets": ["DMG2_bucket-10", "DMG2_bucket-11"]},
                    {"role": "ADE", "name": "Jessica Noronha",                     "alias": "noronhje",  "email": "noronhje@amazon.com",  "salesforce_id": "005at00000EJVT6",  "buckets": ["DMG2_bucket-12", "DMG2_bucket-13"]},
                    {"role": "ADE", "name": "Abel Almeida De Oliveira",            "alias": "abelnoli",  "email": "abelnoli@amazon.com",  "salesforce_id": "005at00000FLAmw",  "buckets": []},
                    {"role": "ADE", "name": "Cleyton Rodrigues Lopes",             "alias": "cleytlop",  "email": "cleytlop@amazon.com",  "salesforce_id": "005at00000FL5le",  "buckets": []},
                    {"role": "ADE", "name": "Marcos Cabral Dos Santos",            "alias": "sxmarco",   "email": "sxmarco@amazon.com",   "salesforce_id": "005at00000FLBkb",  "buckets": []},
                    {"role": "ADE", "name": "Renata Nepomuceno De Miranda",        "alias": "cmirrena",  "email": "cmirrena@amazon.com",  "salesforce_id": "005at00000FLBiz",  "buckets": []},
                    {"role": "ADE", "name": "Silas Sergio Da Silva Junior",        "alias": "silasjun",  "email": "silasjun@amazon.com",  "salesforce_id": "005at00000FL6jK",  "buckets": []},
                    {"role": "ADE", "name": "Joao Marcos Francisco Da Cruz",       "alias": "yjoacruz",  "email": "yjoacruz@amazon.com",  "salesforce_id": "005at00000FLBPe",  "buckets": []},
                    {"role": "ADE", "name": "Raoni Luan Silva Miranda",            "alias": "raonimir",  "email": "raonimir@amazon.com",  "salesforce_id": "-",                "buckets": []},
                    {"role": "ADE", "name": "Hudson De Paula Maciel",              "alias": "depauhud",  "email": "depauhud@amazon.com",  "salesforce_id": "-",                "buckets": []},
                    {"role": "ADE", "name": "Giovanni Senra Martins Do Carmo",     "alias": "senramgy",  "email": "senramgy@amazon.com",  "salesforce_id": "-",                "buckets": []},
                ],
            },
        ],
    },

    # ── NORDESTE ─────────────────────────────────────────────────────────────
    {
        "role": "BDM",
        "name": "Danielle Duprat",
        "alias": "dupratda",
        "email": "dupratda@amazon.com",
        "salesforce_id": "",
        "region": "NORDESTE",
        "stations": ["DAM1", "DCE3", "DPE4", "DPB3"],
        "reports": [

            # DCE3 — 16 territórios
            {
                "role": "CTL",
                "name": "Karliane Dos Santos",
                "alias": "kariliad",
                "email": "kariliad@amazon.com",
                "salesforce_id": "005at00000EJTnt",
                "stations": ["DCE3"],
                "reports": [
                    {"role": "ADE", "name": "Alana Paulino",                              "alias": "paualane",  "email": "paualane@amazon.com",  "salesforce_id": "005at00000EJPQu",  "buckets": ["DCE3_bucket-03"]},
                    {"role": "ADE", "name": "Sidney Lima",                                "alias": "qsidneyl",  "email": "qsidneyl@amazon.com",  "salesforce_id": "005at00000EJUdT",  "buckets": ["DCE3_bucket-09"]},
                    {"role": "ADE", "name": "Neymara Maria De Castro Da Silva",           "alias": "neymaras",  "email": "neymaras@amazon.com",  "salesforce_id": "005at00000EJUAX",  "buckets": ["DCE3_bucket-13"]},
                    {"role": "ADE", "name": "Daniel Nascimento Monteiro",                 "alias": "amontdan",  "email": "amontdan@amazon.com",  "salesforce_id": "005at00000EJRsX",  "buckets": ["DCE3_bucket-08"]},
                    {"role": "ADE", "name": "Sidney Alves Da Silva",                      "alias": "sisidne",   "email": "sisidne@amazon.com",   "salesforce_id": "005at00000EJUaJ",  "buckets": ["DCE3_bucket-11"]},
                    {"role": "ADE", "name": "Sidia Oliveira De Sousa",                    "alias": "sidisous",  "email": "sidisous@amazon.com",  "salesforce_id": "005at00000EJUaI",  "buckets": ["DCE3_bucket-06"]},
                    {"role": "ADE", "name": "Huanderson Alexandre Almeida Teodosio",      "alias": "teodhuan",  "email": "teodhuan@amazon.com",  "salesforce_id": "005at00000EJVT4",  "buckets": ["DCE3_bucket-10"]},
                    {"role": "ADE", "name": "Paula Charlene Nogueira Chaves",             "alias": "achavesp",  "email": "achavesp@amazon.com",  "salesforce_id": "005at00000EJVT5",  "buckets": ["DCE3_bucket-02"]},
                    {"role": "ADE", "name": "Thiego Bezerra Marques",                     "alias": "thiemard",  "email": "thiemard@amazon.com",  "salesforce_id": "005at00000EJOwJ",  "buckets": ["DCE3_bucket-01", "DCE3_bucket-05"]},
                    {"role": "ADE", "name": "Thiago Maciel Mora",                         "alias": "thiamora",  "email": "thiamora@amazon.com",  "salesforce_id": "005at00000EJO9q",  "buckets": ["DCE3_bucket-12"]},
                    {"role": "ADE", "name": "Francisco Diego Lima De Sousa",              "alias": "sousatfr",  "email": "sousatfr@amazon.com",  "salesforce_id": "005at00000EJSjo",  "buckets": ["DCE3_bucket-04"]},
                    {"role": "ADE", "name": "Yana Mara Martins Alencar De",               "alias": "alencary",  "email": "alencary@amazon.com",  "salesforce_id": "005at00000EJUyP",  "buckets": ["DCE3_bucket-07"]},
                    {"role": "ADE", "name": "Cristiane Conceicao",                        "alias": "cryconce",  "email": "cryconce@amazon.com",  "salesforce_id": "005at00000EJUn9",  "buckets": ["DCE3_bucket-14", "DCE3_bucket-16"]},
                    {"role": "ADE", "name": "Felipe Duarte",                              "alias": "dcfelipe",  "email": "dcfelipe@amazon.com",  "salesforce_id": "005at00000EJUX3",  "buckets": ["DCE3_bucket-15"]},
                ],
            },

            # DPE4 — 15 territórios
            {
                "role": "CTL",
                "name": "Tiago Grego",
                "alias": "tigregok",
                "email": "tigregok@amazon.com",
                "salesforce_id": "005at00000EJUjt",
                "stations": ["DPE4"],
                "reports": [
                    {"role": "ADE", "name": "Maria Helena",                              "alias": "usilvm",    "email": "usilvm@amazon.com",    "salesforce_id": "005at00000EJOwG",  "buckets": ["DPE4_bucket-11"]},
                    {"role": "ADE", "name": "Claudio Alves Ricardo De Freitas",          "alias": "claujfre",  "email": "claujfre@amazon.com",  "salesforce_id": "005at00000EJSjq",  "buckets": ["DPE4_bucket-10"]},
                    {"role": "ADE", "name": "Renato Rosas Pinto",                        "alias": "rosaspic",  "email": "rosaspic@amazon.com",  "salesforce_id": "-",                "buckets": ["DPE4_bucket-13"]},
                    {"role": "ADE", "name": "Luana Siqueira",                            "alias": "siqluand",  "email": "siqluand@amazon.com",  "salesforce_id": "005at00000EJRsW",  "buckets": ["DPE4_bucket-15"]},
                    {"role": "ADE", "name": "Enyedja Santos",                            "alias": "enyedjas",  "email": "enyedjas@amazon.com",  "salesforce_id": "005at00000EJUAW",  "buckets": ["DPE4_bucket-07"]},
                    {"role": "ADE", "name": "Fernandes Reis Da Silva",                   "alias": "qfernasi",  "email": "qfernasi@amazon.com",  "salesforce_id": "005at00000EJUaK",  "buckets": ["DPE4_bucket-01"]},
                    {"role": "ADE", "name": "Jamerson Esdras De Oliveira Cabral",        "alias": "jamersca",  "email": "jamersca@amazon.com",  "salesforce_id": "005at00000EJUaL",  "buckets": ["DPE4_bucket-09"]},
                    {"role": "ADE", "name": "Jose Borges",                               "alias": "joseboro",  "email": "joseboro@amazon.com",  "salesforce_id": "005at00000EJPIr",  "buckets": ["DPE4_bucket-04"]},
                    {"role": "ADE", "name": "Raimundo Junior",                           "alias": "juniraim",  "email": "juniraim@amazon.com",  "salesforce_id": "005at00000EJOwI",  "buckets": ["DPE4_bucket-12"]},
                    {"role": "ADE", "name": "Jose Silva",                                "alias": "nsiljos",   "email": "nsiljos@amazon.com",   "salesforce_id": "005at00000EJO9r",  "buckets": ["DPE4_bucket-02"]},
                    {"role": "ADE", "name": "Fabio Silva",                               "alias": "fahsilva",  "email": "fahsilva@amazon.com",  "salesforce_id": "005at00000EJO9s",  "buckets": ["DPE4_bucket-05"]},
                    {"role": "ADE", "name": "Diego Barros",                              "alias": "jbarrodi",  "email": "jbarrodi@amazon.com",  "salesforce_id": "005at00000EJOwF",  "buckets": ["DPE4_bucket-08"]},
                    {"role": "ADE", "name": "Davi Santos",                               "alias": "santudav",  "email": "santudav@amazon.com",  "salesforce_id": "005at00000EJPIq",  "buckets": ["DPE4_bucket-03"]},
                    {"role": "ADE", "name": "Cicero Almeida",                            "alias": "cicealme",  "email": "cicealme@amazon.com",  "salesforce_id": "005at00000EJNVa",  "buckets": ["DPE4_bucket-06"]},
                    {"role": "ADE", "name": "Maria Silva",                               "alias": "silvmac",   "email": "silvmac@amazon.com",   "salesforce_id": "005at00000EJIMD",  "buckets": ["DPE4_bucket-14"]},
                ],
            },

            # DPB3 — 5 territórios
            {
                "role": "CTL",
                "name": "Rafael Lana",
                "alias": "rafaelkl",
                "email": "rafaelkl@amazon.com",
                "salesforce_id": "005at00000EJMxf",
                "stations": ["DPB3"],
                "reports": [
                    {"role": "ADE", "name": "Everton Martins",                              "alias": "eveomart",  "email": "eveomart@amazon.com",  "salesforce_id": "005at00000EJPUE",  "buckets": ["DPB3_bucket-01", "DPB3_bucket-02"]},
                    {"role": "ADE", "name": "Anna Beatriz Dos Santos Lima",                 "alias": "annlimay",  "email": "annlimay@amazon.com",  "salesforce_id": "005at00000EJUFO",  "buckets": ["DPB3_bucket-03"]},
                    {"role": "ADE", "name": "Alexandre Pedro Batista De Almeida Junior",    "alias": "junalexj",  "email": "junalexj@amazon.com",  "salesforce_id": "005at00000EJW5n",  "buckets": ["DPB3_bucket-04"]},
                    {"role": "ADE", "name": "Caio Benjamim Lima Simplicio",                 "alias": "simpcaio",  "email": "simpcaio@amazon.com",  "salesforce_id": "005at00000FWAhz",  "buckets": []},
                ],
            },

            # DAM1
            {
                "role": "CTL",
                "name": "",
                "alias": "",
                "email": "",
                "salesforce_id": "",
                "stations": ["DAM1"],
                "reports": [],
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Funções utilitárias derivadas do TEAM (fonte da verdade)
# Definidas APÓS o TEAM para que os índices sejam construídos corretamente.
# ---------------------------------------------------------------------------

def _build_team_index():
    """
    Percorre TEAM recursivamente e constrói índices de lookup rápido.

    Retorna:
        bucket_to_ade   : {territory_id: {name, alias, email, salesforce_id}}
        station_to_ctl  : {station_code: {name, alias, email, salesforce_id}}
        station_to_bdm  : {station_code: {name, alias, email, region}}
        alias_to_name   : {alias: name}  — todos os membros do time
    """
    bucket_to_ade:  dict = {}
    station_to_ctl: dict = {}
    station_to_bdm: dict = {}
    alias_to_name:  dict = {}

    for bdm in TEAM:
        bdm_info = {
            "name":   bdm.get("name", ""),
            "alias":  bdm.get("alias", ""),
            "email":  bdm.get("email", ""),
            "region": bdm.get("region", ""),
        }
        if bdm.get("alias"):
            alias_to_name[bdm["alias"]] = bdm.get("name", "")

        for station in bdm.get("stations", []):
            station_to_bdm[station] = bdm_info

        for ctl in bdm.get("reports", []):
            if ctl.get("role") != "CTL":
                continue
            ctl_info = {
                "name":          ctl.get("name", ""),
                "alias":         ctl.get("alias", ""),
                "email":         ctl.get("email", ""),
                "salesforce_id": ctl.get("salesforce_id", ""),
            }
            if ctl.get("alias"):
                alias_to_name[ctl["alias"]] = ctl.get("name", "")

            for station in ctl.get("stations", []):
                station_to_ctl[station] = ctl_info

            for ade in ctl.get("reports", []):
                if ade.get("role") != "ADE":
                    continue
                if ade.get("alias"):
                    alias_to_name[ade["alias"]] = ade.get("name", "")
                ade_info = {
                    "name":          ade.get("name", ""),
                    "alias":         ade.get("alias", ""),
                    "email":         ade.get("email", ""),
                    "salesforce_id": ade.get("salesforce_id", ""),
                }
                for bucket in ade.get("buckets", []):
                    bucket_to_ade[bucket] = ade_info

    return bucket_to_ade, station_to_ctl, station_to_bdm, alias_to_name


# Índices construídos uma única vez no import
_BUCKET_TO_ADE, _STATION_TO_CTL, _STATION_TO_BDM, _ALIAS_TO_NAME = _build_team_index()


def get_ade_for_territory(territory_id: str) -> dict:
    """
    Retorna {name, alias, email, salesforce_id} do ADE responsável pelo território.
    Retorna dict com strings vazias se não encontrado.
    """
    return _BUCKET_TO_ADE.get(territory_id, {
        "name": "", "alias": "", "email": "", "salesforce_id": ""
    })


def get_ctl_for_station(station_code: str) -> dict:
    """
    Retorna {name, alias, email, salesforce_id} do CTL responsável pela base.
    Retorna dict com strings vazias se não encontrado.
    """
    return _STATION_TO_CTL.get(station_code, {
        "name": "", "alias": "", "email": "", "salesforce_id": ""
    })


def get_bdm_for_station(station_code: str) -> dict:
    """
    Retorna {name, alias, email, region} do BDM responsável pela base.
    Retorna dict com strings vazias se não encontrado.
    """
    return _STATION_TO_BDM.get(station_code, {
        "name": "", "alias": "", "email": "", "region": "OUTROS"
    })


def get_owner_id_for_territory(territory_id: str) -> str | None:
    """
    Retorna o salesforce_id do ADE responsável pelo território.
    Retorna None se não encontrado ou se o salesforce_id for '-'.
    """
    ade = _BUCKET_TO_ADE.get(territory_id)
    if not ade:
        return None
    sf_id = ade.get("salesforce_id", "")
    return sf_id if sf_id and sf_id != "-" else None


def get_name_for_alias(alias: str) -> str:
    """Retorna o nome completo de qualquer membro do time pelo alias."""
    return _ALIAS_TO_NAME.get(alias, alias)
