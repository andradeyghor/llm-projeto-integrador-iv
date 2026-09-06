import sqlite3
import re
import sys
from typing import List, Dict, Any, Optional

# Evitar problemas de encoding no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class BuscadorAutoPecas:
    def __init__(self, db_path: str = "produtos_enriquecidos.db"):
        self.db_path = db_path
        self._criar_indices()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _criar_indices(self):
        """Garante que existam índices para acelerar a busca offline."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_montadora ON produtos(montadora)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tipo_peca ON produtos(tipo_peca)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_anos ON produtos(ano_inicio, ano_fim)")
        conn.commit()
        conn.close()

    def extrair_filtros_pergunta(self, texto: str) -> Dict[str, Any]:
        """
        Extrai regras preliminares do texto informal do cliente:
        - Anos (ex: 1988, 88, 76, 1994)
        - Lado (LD/direito/passageiro vs LE/esquerdo/motorista)
        """
        texto_lower = texto.lower()
        filtros = {
            "ano": None,
            "lado": None,
            "termos_busca": []
        }

        # 1. Identificar Lado / Posição
        if any(w in texto_lower for w in ["passageiro", "carona", "direito", " ld "]):
            filtros["lado"] = "LD"
        elif any(w in texto_lower for w in ["motorista", "esquerdo", " le "]):
            filtros["lado"] = "LE"

        # 2. Identificar Ano (4 dígitos ou 2 dígitos contextualizados)
        match_ano4 = re.search(r'\b(19\d{2}|20\d{2})\b', texto)
        if match_ano4:
            filtros["ano"] = int(match_ano4.group(1))
        else:
            match_ano2 = re.search(r'\b([789]\d)\b', texto)
            if match_ano2:
                ano_2d = int(match_ano2.group(1))
                filtros["ano"] = 1900 + ano_2d

        # 3. Limpeza de termos para pontuação
        palavras_ignorar = {
            "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
            "em", "no", "na", "nos", "nas", "para", "pra", "pro", "com", "sem",
            "tem", "voce", "voces", "amigo", "boa", "tarde", "noite", "dia",
            "meu", "minha", "preciso", "quero", "gostaria", "serve", "ano"
        }
        tokens = re.findall(r'[a-zA-Z0-9áéíóúâêîôûãõç]+', texto_lower)
        filtros["termos_busca"] = [t for t in tokens if t not in palavras_ignorar and not t.isdigit()]

        return filtros

    def buscar_produtos(self, pergunta: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Busca inteligente com pontuação de relevância (Scoring):
        - Match de modelo: +10 pontos
        - Match de tipo de peça: +8 pontos
        - Compatibilidade de ano: +5 pontos
        - Match de lado/posição: +4 pontos
        - Match em perguntas frequentes / descrição: +2 pontos
        """
        filtros = self.extrair_filtros_pergunta(pergunta)
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id_original, nome_original, preco, tipo_peca, montadora,
                   modelos_compativeis, ano_inicio, ano_fim, posicao_lado,
                   detalhes_acabamento, descricao_amigavel, perguntas_clientes
            FROM produtos
        """)
        todos_produtos = cursor.fetchall()
        conn.close()

        candidatos = []
        termos_busca = filtros["termos_busca"]
        ano_busca = filtros["ano"]
        lado_busca = filtros["lado"]

        for row in todos_produtos:
            (p_id, p_nome_orig, p_preco, p_tipo, p_montadora,
             p_modelos, p_ano_ini, p_ano_fim, p_posicao,
             p_acabamento, p_descricao, p_perguntas) = row

            score = 0
            texto_completo = f"{p_nome_orig} {p_tipo} {p_montadora} {p_modelos} {p_acabamento} {p_descricao} {p_perguntas}".lower()

            # Pontuação por termos de texto
            for termo in termos_busca:
                if p_modelos and termo in p_modelos.lower():
                    score += 10
                elif p_tipo and termo in p_tipo.lower():
                    score += 8
                elif termo in texto_completo:
                    score += 3

            # Bônus por compatibilidade de ano
            if ano_busca and p_ano_ini:
                ano_max = p_ano_fim if p_ano_fim else 2025
                if p_ano_ini <= ano_busca <= ano_max:
                    score += 6
                else:
                    # Penalidade leve se o ano estiver explicitamente fora
                    score -= 4

            # Bônus por lado
            if lado_busca:
                pos_lower = (p_posicao or "").lower()
                if lado_busca.lower() in pos_lower or "ambos" in pos_lower or "universal" in pos_lower:
                    score += 4
                elif ("ld" in pos_lower and lado_busca == "LE") or ("le" in pos_lower and lado_busca == "LD"):
                    score -= 5

            if score > 5:
                candidatos.append({
                    "id": p_id,
                    "nome_erp": p_nome_orig,
                    "preco": p_preco,
                    "tipo_peca": p_tipo,
                    "montadora": p_montadora,
                    "modelos": p_modelos,
                    "ano_inicio": p_ano_ini,
                    "ano_fim": p_ano_fim,
                    "posicao": p_posicao,
                    "acabamento": p_acabamento,
                    "descricao": p_descricao,
                    "score": score
                })

        # Ordenar pelos maiores scores
        candidatos.sort(key=lambda x: x["score"], reverse=True)
        return candidatos[:top_k]

if __name__ == "__main__":
    buscador = BuscadorAutoPecas()
    
    # Testes rápidos de perguntas de balcão
    perguntas_teste = [
        "Tem retrovisor pro Uno Mille 96 do lado do passageiro?",
        "Qual retrovisor serve na minha Kombi Clipper 85?",
        "Tem o retrovisor interno do Escort 88?",
        "Vocês têm farol auxiliar pro Gol quadrado 91 lado direito?"
    ]

    print("=== TESTE DO MECANISMO DE BUSCA OFFLINE ===")
    for q in perguntas_teste:
        print(f"\n❓ Pergunta do Cliente: \"{q}\"")
        resultados = buscador.buscar_produtos(q, top_k=2)
        if not resultados:
            print("  [Nenhum produto correspondente encontrado no banco]")
        for i, res in enumerate(resultados, 1):
            print(f"  ⭐ Sugestão #{i} (Score: {res['score']}):")
            print(f"     Produto: {res['descricao']}")
            print(f"     Compatível: {res['modelos']} ({res['ano_inicio'] or 'N/A'}-{res['ano_fim'] or 'N/A'})")
            print(f"     Posição: {res['posicao']} | Preço: R$ {res['preco']:.2f} | Código: {res['id']}")
