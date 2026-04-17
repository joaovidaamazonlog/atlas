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
    "XRJ2": "DRJ3",   # satélite de DRJ3
    "XRJ3": "DRJ3",   # satélite de DRJ3
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
                    {"role": "ADE", "name": "Kelvin Fernandes","alias": "kelvinbf", "email": "kelvinbf@amazon.com", "salesforce_id": "005at000001qfY0AAI", "buckets": ["DPR2_bucket-01", "DPR2_bucket-03", "DPR2_bucket-05"]},
                    {"role": "ADE", "name": "Lilian Mata",     "alias": "qlilimat", "email": "qlilimat@amazon.com", "salesforce_id": "0055G00000BA0QuQAL", "buckets": ["DPR2_bucket-02", "DPR2_bucket-04", "DPR2_bucket-06"]},
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
                ],
            },

            # DBH5 — 4 territórios
            {
                "role": "CTL",
                "name": "Lucas Magela",
                "alias": "lsouzafa",
                "email": "lsouzafa@amazon.com",
                "salesforce_id": "005at00000EJUVP",
                "stations": ["DBH5"],
                "reports": [
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
                    {"role": "ADE", "name": "Wagner Silva",   "alias": "swagnerq", "email": "swagnerq@amazon.com", "salesforce_id": "0055G00000BA5UIQA1", "buckets": ["DES2_bucket-01", "DES2_bucket-02", "DES2_bucket-03"]},
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
