"""
Baixa a tabela oficial de municípios da Receita Federal e
gera o set de códigos para os 134 municípios das DSs ativas.

Roda: python get_rf_municipios.py
"""
import requests
import zipfile
import io
import csv
import unicodedata
import time

NEXTCLOUD_BASE = "https://arquivos.receitafederal.gov.br"
CNPJ_PATH = "Dados/Cadastros/CNPJ"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
PROPFIND_BODY = '<?xml version="1.0" encoding="utf-8" ?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/></d:prop></d:propfind>'

# 134 municípios das DSs ativas (nome normalizado + UF)
MUNICIPIOS_ALVO = [
    ("ABREU E LIMA", "PE"), ("ALMIRANTE TAMANDARE", "PR"), ("ALVORADA", "RS"),
    ("AMERICANA", "SP"), ("APARECIDA DE GOIANIA", "GO"), ("AQUIRAZ", "CE"),
    ("ARAUCARIA", "PR"), ("BARUERI", "SP"), ("BAYEUX", "PB"),
    ("BELO HORIZONTE", "MG"), ("BIGUACU", "SC"), ("BRASILIA", "DF"),
    ("CABEDELO", "PB"), ("CABO FRIO", "RJ"), ("CABO DE SANTO AGOSTINHO", "PE"),
    ("CABREUVA", "SP"), ("CAIEIRAS", "SP"), ("CAJAMAR", "SP"),
    ("CAMARAGIBE", "PE"), ("CAMACARI", "BA"), ("CAMPINA GRANDE", "PB"),
    ("CAMPINAS", "SP"), ("CAMPO BOM", "RS"), ("CAMPO LARGO", "PR"),
    ("CAMPO LIMPO PAULISTA", "SP"), ("CANDEIAS", "BA"), ("CANOAS", "RS"),
    ("CARIACICA", "ES"), ("CAUCAIA", "CE"), ("COLOMBO", "PR"),
    ("CONTAGEM", "MG"), ("CORDEIROPOLIS", "SP"), ("COTIA", "SP"),
    ("CURITIBA", "PR"), ("DIADEMA", "SP"), ("DUQUE DE CAXIAS", "RJ"),
    ("EMBU DAS ARTES", "SP"), ("EMBU-GUACU", "SP"), ("ESTEIO", "RS"),
    ("ESTANCIA VELHA", "RS"), ("EUSEBIO", "CE"), ("FAZENDA RIO GRANDE", "PR"),
    ("FEIRA DE SANTANA", "BA"), ("FERRAZ DE VASCONCELOS", "SP"),
    ("FLORIANOPOLIS", "SC"), ("FORTALEZA", "CE"), ("GOIANIA", "GO"),
    ("GUARAPARI", "ES"), ("GUARULHOS", "SP"), ("HIDROLANDIA", "GO"),
    ("HORIZONTE", "CE"), ("HORTOLANDIA", "SP"), ("IGARASSU", "PE"),
    ("INDAIATUBA", "SP"), ("IRACEMAPOLIS", "SP"), ("ITAITINGA", "CE"),
    ("ITANHAEM", "SP"), ("ITAPECERICA DA SERRA", "SP"),
    ("ITAQUAQUECETUBA", "SP"), ("ITATIBA", "SP"), ("ITU", "SP"),
    ("ITUPEVA", "SP"), ("JABOATAO DOS GUARARAPES", "PE"), ("JACAREI", "SP"),
    ("JOAO PESSOA", "PB"), ("JUNDIAI", "SP"), ("JUQUITIBA", "SP"),
    ("LAURO DE FREITAS", "BA"), ("LIMEIRA", "SP"), ("LOUVEIRA", "SP"),
    ("MAGE", "RJ"), ("MAIRIPORA", "SP"), ("MANAUS", "AM"),
    ("MARACANAU", "CE"), ("MARANGUAPE", "CE"), ("MAUA", "SP"),
    ("MESQUITA", "RJ"), ("MOGI DAS CRUZES", "SP"), ("NILOPOLIS", "RJ"),
    ("NOVA IGUACU", "RJ"), ("NOVA LIMA", "MG"), ("NOVA ODESSA", "SP"),
    ("NOVA SANTA RITA", "RS"), ("NOVO HAMBURGO", "RS"), ("OLINDA", "PE"),
    ("OSASCO", "SP"), ("PACATUBA", "CE"), ("PALHOCA", "SC"),
    ("PAULISTA", "PE"), ("PAULINIA", "SP"), ("PINHAIS", "PR"),
    ("PIRACICABA", "SP"), ("PIRAQUARA", "PR"), ("PORTO ALEGRE", "RS"),
    ("QUEIMADOS", "RJ"), ("RECIFE", "PE"), ("RIO CLARO", "SP"),
    ("RIO DE JANEIRO", "RJ"), ("SABARA", "MG"), ("SALTO", "SP"),
    ("SALVADOR", "BA"), ("SANTA BARBARA D OESTE", "SP"),
    ("SANTA GERTRUDES", "SP"), ("SANTA RITA", "PB"),
    ("SANTANA DE PARNAIBA", "SP"), ("SANTO AMARO DA IMPERATRIZ", "SC"),
    ("SANTO ANDRE", "SP"), ("SAPUCAIA DO SUL", "RS"),
    ("SENADOR CANEDO", "GO"), ("SEROPEDICA", "RJ"), ("SERRA", "ES"),
    ("SERTAOZINHO", "SP"), ("SOROCABA", "SP"), ("SUMARE", "SP"),
    ("SAO BERNARDO DO CAMPO", "SP"), ("SAO CAETANO DO SUL", "SP"),
    ("SAO JOSE DOS CAMPOS", "SP"), ("SAO JOSE DOS PINHAIS", "PR"),
    ("SAO JOSE", "SC"), ("SAO JOAO DE MERITI", "RJ"),
    ("SAO LEOPOLDO", "RS"), ("SAO LOURENCO DA MATA", "PE"),
    ("SAO PAULO", "SP"), ("TABOAO DA SERRA", "SP"), ("TRINDADE", "GO"),
    ("VALINHOS", "SP"), ("VARGEM GRANDE PAULISTA", "SP"), ("VIAMAOO", "RS"),
    ("VIANA", "ES"), ("VILA VELHA", "ES"), ("VINHEDO", "SP"),
    ("VITORIA DE SANTO ANTAO", "PE"), ("VITORIA", "ES"), ("VARZEA PAULISTA", "SP"),
]

# UF → código de estado RF (2 dígitos iniciais do código de município)
UF_PREFIXO = {
    "RO":"01","AC":"02","AM":"03","RR":"04","PA":"05","AP":"06","TO":"07",
    "MA":"08","PI":"09","CE":"10","RN":"11","PB":"12","PE":"13","AL":"14",
    "SE":"15","BA":"16","MG":"17","ES":"18","RJ":"19","SP":"20","PR":"21",
    "SC":"22","RS":"23","MS":"24","MT":"25","GO":"26","DF":"27",
}


def normalize(s: str) -> str:
    return unicodedata.normalize("NFD", s.upper()).encode("ascii", "ignore").decode()


def obter_token_e_periodo():
    r = requests.get(NEXTCLOUD_BASE, headers=HEADERS, timeout=15, allow_redirects=True)
    r.raise_for_status()
    import re
    for text in [r.url, r.text]:
        m = re.search(r"/s/([A-Za-z0-9]{10,25})", text)
        if m:
            token = m.group(1)
            break
    else:
        raise RuntimeError("Token não encontrado.")
    dav_url = f"{NEXTCLOUD_BASE}/public.php/dav/files/{token}/{CNPJ_PATH}/"
    r2 = requests.request("PROPFIND", dav_url, data=PROPFIND_BODY,
                          headers={**HEADERS, "Depth": "1", "Content-Type": "application/xml"}, timeout=15)
    r2.raise_for_status()
    periodos = sorted(re.findall(r"/(\d{4}-\d{2})/", r2.text))
    return token, periodos[-1]


def baixar_municipios(token: str, period: str) -> dict[str, str]:
    """Baixa Municipios.zip e retorna {codigo_rf: nome_municipio}."""
    url = f"{NEXTCLOUD_BASE}/public.php/dav/files/{token}/{CNPJ_PATH}/{period}/Municipios.zip"
    print(f"Baixando tabela de municípios: {url}")
    r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
    r.raise_for_status()

    content = b""
    total = 0
    for chunk in r.iter_content(chunk_size=512 * 1024):
        content += chunk
        total += len(chunk)

    print(f"  {total / 1024:.0f} KB baixados. Processando...")

    municipios = {}
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        with z.open(z.namelist()[0]) as f:
            reader = csv.reader(
                (line.decode("latin-1") for line in f),
                delimiter=";"
            )
            for row in reader:
                if len(row) < 2:
                    continue
                codigo = row[0].strip().zfill(4)
                nome = row[1].strip()
                municipios[codigo] = nome

    print(f"  {len(municipios)} municípios carregados.")
    return municipios


def main():
    token, period = obter_token_e_periodo()
    print(f"Token: {token} | Período: {period}\n")

    municipios_rf = baixar_municipios(token, period)

    # Inverte: nome_normalizado → codigo
    nome_para_codigo: dict[str, str] = {}
    for codigo, nome in municipios_rf.items():
        nome_norm = normalize(nome)
        nome_para_codigo[nome_norm] = codigo

    # Mapeia os 134 municípios
    codigos_alvo = set()
    not_found = []

    for nome, uf in MUNICIPIOS_ALVO:
        nome_norm = normalize(nome)
        if nome_norm in nome_para_codigo:
            codigos_alvo.add(nome_para_codigo[nome_norm])
        else:
            # Tenta variações
            found = False
            for key, codigo in nome_para_codigo.items():
                if nome_norm in key or key in nome_norm:
                    codigos_alvo.add(codigo)
                    found = True
                    break
            if not found:
                not_found.append(f"{nome}-{uf}")

    print(f"\nEncontrados: {len(codigos_alvo)} códigos RF")
    if not_found:
        print(f"Não encontrados ({len(not_found)}): {not_found}")

    print(f"\n{'='*60}")
    print("Cole no etl_cnpj_low_mem.py:")
    print(f"MUNICIPIOS_CODIGOS_RF = {sorted(codigos_alvo)}")
    print(f"{'='*60}")

    # Salva em arquivo para uso no ETL
    with open("municipios_rf_codigos.txt", "w") as f:
        f.write(repr(sorted(codigos_alvo)))
    print("\nSalvo em municipios_rf_codigos.txt")


if __name__ == "__main__":
    main()
