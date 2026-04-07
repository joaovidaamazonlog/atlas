import json
import os
import re

path = os.path.join(os.path.dirname(__file__), '..', 'data', 'gmaps_results.json')

PHONE_RE = re.compile(r'^\+?(?:55\s?)?(?:\(?\d{2}\)?\s?)[\d\s\-(). ]{7,}$')
STREET_RE = re.compile(r'(?:Rua|Av\.|Avenida|R\.|Alameda|Travessa|Praca|Estrada|Rod\.|Beco|Largo)\s+.+', re.IGNORECASE)
STARTS_STREET_RE = re.compile(r'^(?:Rua|Av\.|Avenida|R\.|Alameda|Travessa|Praca|Estrada|Rod\.|Beco|Largo)', re.IGNORECASE)


def parse_address_field(raw):
    """
    Analisa o campo endereco bruto do Google Maps.
    Retorna dict com address, phone, website — o campo pode conter qualquer um desses.
    """
    result = {'address': None, 'phone': None, 'website': None}
    if not raw or raw == 'N/A':
        return result

    # Limpar prefixos visuais
    clean = re.sub(r'[\uE000-\uF8FF]', '', raw)
    clean = re.sub(r'[\n\r\t]+', ' ', clean)
    clean = re.sub(r'^[\s\xb7\u2022\-\u2013\u2014]+', '', clean)
    clean = re.sub(r'\s{2,}', ' ', clean).strip()

    # Detectar telefone
    if PHONE_RE.match(clean):
        digits = re.sub(r'\D', '', clean)
        normalized = digits[2:] if digits.startswith('55') else digits
        if len(normalized) in (10, 11):
            result['phone'] = normalized
        return result

    # Detectar site/URL
    if re.match(r'^https?://', clean, re.IGNORECASE) or re.match(r'^www\.', clean, re.IGNORECASE):
        result['website'] = clean
        return result

    # E endereco — normalizar
    addr = clean
    addr = re.sub(r'\b\d{5}-?\d{3}\b', '', addr)
    addr = re.sub(r'\s*-\s*[A-Z]{2}\s*,.*$', '', addr)
    addr = re.sub(r',?\s*,\s*Brasil\s*$', '', addr, flags=re.IGNORECASE)
    addr = re.sub(r',\s*,', ',', addr)
    addr = re.sub(r'\s{2,}', ' ', addr).strip()

    if not STARTS_STREET_RE.match(addr):
        m = STREET_RE.search(addr)
        if m:
            addr = m.group(0).strip()

    addr = re.sub(r'[\s,\-\u2013\u2014]+$', '', addr).strip()
    result['address'] = addr or None
    return result


with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

removed = 0
normalized = 0
phone_rescued = 0
site_rescued = 0

for tid, entries in data['results'].items():
    seen = {}
    for entry in entries:
        raw_addr = entry.get('endereco', '')
        parsed = parse_address_field(raw_addr)

        # Aproveitar telefone encontrado no campo endereco
        if parsed['phone'] and (not entry.get('telefone') or entry['telefone'] == 'N/A'):
            entry['telefone'] = parsed['phone']
            phone_rescued += 1

        # Aproveitar site encontrado no campo endereco
        if parsed['website'] and (not entry.get('site') or entry['site'] == 'N/A'):
            entry['site'] = parsed['website']
            site_rescued += 1

        # Atualizar endereco com versao normalizada
        new_addr = parsed['address'] or 'N/A'
        if new_addr != raw_addr:
            entry['endereco'] = new_addr
            normalized += 1

        # Deduplicar por google_maps_link (primario) ou nome (fallback)
        link = entry.get('google_maps_link', '')
        key = link if link and link != 'N/A' else (entry.get('nome') or '').strip().lower()
        if not key:
            continue

        has_addr = entry.get('endereco') and entry['endereco'] != 'N/A'
        if key not in seen:
            seen[key] = entry
        else:
            prev = seen[key]
            prev_has_addr = prev.get('endereco') and prev['endereco'] != 'N/A'
            if not prev_has_addr and has_addr:
                seen[key] = entry
            removed += 1

    data['results'][tid] = list(seen.values())

data['n_companies'] = sum(len(v) for v in data['results'].values())

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Enderecos normalizados : {normalized}")
print(f"Telefones resgatados   : {phone_rescued}")
print(f"Sites resgatados       : {site_rescued}")
print(f"Duplicatas removidas   : {removed}")
print(f"Total de empresas      : {data['n_companies']}")
