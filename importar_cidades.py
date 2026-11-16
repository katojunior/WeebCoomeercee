import requests
import json

def importar():
    print("Buscando dados no IBGE...")
    url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
    
    try:
        resposta = requests.get(url)
        resposta.raise_for_status()
        municipios = resposta.json()
    except Exception as e:
        print(f"Erro ao conectar com o IBGE: {e}")
        return

    cidades_json = []
    erros = 0
    
    print(f"Processando {len(municipios)} municípios...")

    for m in municipios:
        try:
            # Pegando a UF de forma mais segura
            # Algumas cidades podem ter estruturas de microrregiao diferentes
            uf_data = m.get('microrregiao', {}).get('mesorregiao', {}).get('UF', {})
            uf_id = uf_data.get('id')
            uf_sigla = uf_data.get('sigla')

            if not uf_id:
                # Tentativa secundária caso a estrutura seja 'regiao-imediata'
                uf_data = m.get('regiao-imediata', {}).get('regiao-intermediaria', {}).get('UF', {})
                uf_id = uf_data.get('id')
                uf_sigla = uf_data.get('sigla')

            cidade = {
                "descricaoCidade": m['nome'],
                "descricao_completa": f"{m['nome']} - {uf_sigla}",
                "uf": uf_id, 
                "latitude": None,
                "longitude": None,
                "capital": False,
                "ddd": None, 
                "fusoHorario": "America/Sao_Paulo",
                "codigoIbge": str(m['id'])
            }
            cidades_json.append(cidade)
        except Exception:
            erros += 1
            continue

    # Salvando o arquivo
    with open('todas_as_cidades.json', 'w', encoding='utf-8') as f:
        json.dump(cidades_json, f, ensure_ascii=False, indent=2)
    
    print("-" * 30)
    print(f"✅ Sucesso! {len(cidades_json)} cidades processadas.")
    if erros > 0:
        print(f"⚠️ {erros} registros foram ignorados por falta de dados estruturais.")
    print("Arquivo 'todas_as_cidades.json' gerado com sucesso!")

if __name__ == "__main__":
    importar()