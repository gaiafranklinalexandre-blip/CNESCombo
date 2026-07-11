import csv
import os
import re
import requests

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# Configurações
CSV_PATH = os.path.join(os.path.dirname(__file__), 'equipamentos_combo.csv')
API_URL  = 'https://darkgoldenrod-pelican-495804.hostingersite.com/sync-combo.php'
API_KEY  = 'painel_combo_2026_key'

COMPETENCIA_RE = re.compile(r'^QT_(\d{6})$')


def to_int(val):
    try:
        return int(val) if val not in (None, '') else 0
    except (TypeError, ValueError):
        return 0


def to_str(val):
    return (val or '').strip()


def detect_competencias(headers):
    """Detecta dinamicamente todos os pares QT_YYYYMM/ATIVO_YYYYMM presentes
    no cabeçalho. Novas competências (colunas novas todo mês) são pegas
    automaticamente, sem precisar alterar este script."""
    competencias = []
    for h in headers:
        m = COMPETENCIA_RE.match(h)
        if m and f'ATIVO_{m.group(1)}' in headers:
            competencias.append(m.group(1))  # 'YYYYMM'
    return sorted(competencias)


def load_csv():
    print(f'Lendo {CSV_PATH}...')
    with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        competencias = detect_competencias(headers)
        print(f'Competências encontradas: {competencias}')

        records = []
        for row in reader:
            cnes = to_int(row.get('CO_CNES'))
            if not cnes:
                continue
            base = {
                'cnes':                cnes,
                'nome_fantasia':       to_str(row.get('NO_FANTASIA')),
                'uf':                  to_str(row.get('SG_UF')),
                'municipio':           to_str(row.get('NO_MUNICIPIO')),
                'ds_equipamento':      to_str(row.get('DS_EQUIPAMENTO')),
                'co_tipo_equipamento': to_str(row.get('CO_TIPO_EQUIPAMENTO')),
                'co_equipamento':      to_str(row.get('CO_EQUIPAMENTO')),
            }
            for comp in competencias:
                qt = row.get(f'QT_{comp}')
                ativo = row.get(f'ATIVO_{comp}')
                if qt is None and ativo is None:
                    continue
                records.append({
                    **base,
                    'competencia': f'{comp[:4]}-{comp[4:]}-01',
                    'quantidade':  to_int(qt),
                    'ativo':       to_str(ativo).upper() or 'NAO',
                })

    print(f'{len(records)} registros após normalização por competência.')
    return records


def sync(records):
    print('Enviando para o servidor...')
    batch_size = 3000
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        resp = requests.post(
            f'{API_URL}?action=sync_combo',
            json={'records': batch},
            headers={'X-Api-Key': API_KEY},
            timeout=180
        )
        resp.raise_for_status()
        result = resp.json()
        total += result.get('upserted', 0)
        print(f'Lote {i // batch_size + 1}: {total} registros enviados no total')

    print(f'Sincronização concluída! {total} registros processados.')


if __name__ == '__main__':
    records = load_csv()
    sync(records)
