import os
import sys
import sqlite3
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from tqdm import tqdm

# Evitar problemas de encoding no terminal Windows (cp1252)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from google import genai
from google.genai import types

load_dotenv()

# Schema Pydantic para Saída Estruturada
class ProdutoEnriquecido(BaseModel):
    id_original: int = Field(description="ID original do produto no bd.csv")
    tipo_peca: str = Field(description="Tipo da peça, ex: Farol Auxiliar, Lanterna Traseira, Retrovisor, Filtro de Ar")
    montadora: str = Field(description="Montadora principal: Volkswagen, Chevrolet, Fiat, Ford, Universal")
    modelos_compativeis: List[str] = Field(description="Lista normalizada de carros compatíveis, ex: ['Gol', 'Parati', 'Saveiro']")
    ano_inicio: Optional[int] = Field(description="Ano inicial com 4 dígitos (ex: 1987). Null se universal")
    ano_fim: Optional[int] = Field(description="Ano final com 4 dígitos (ex: 1994). Null se universal ou sem fim")
    posicao_lado: str = Field(description="LD (Lado Direito), LE (Lado Esquerdo), Dianteiro, Traseiro, Ambos, Universal")
    detalhes_acabamento: str = Field(description="Detalhes: lente de vidro raiado, acabamento preto, carcaça de ferro, etc.")
    descricao_amigavel: str = Field(description="Descrição em linguagem natural para catálogo e busca semântica")
    perguntas_clientes: List[str] = Field(description="2 ou 3 perguntas reais de balcão que um dono ou mecânico faria procurando esta peça")

class RespostaLote(BaseModel):
    produtos: List[ProdutoEnriquecido]

def init_db(db_name="produtos_enriquecidos.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id_original INTEGER PRIMARY KEY,
            nome_original TEXT,
            preco REAL,
            tipo_peca TEXT,
            montadora TEXT,
            modelos_compativeis TEXT,
            ano_inicio INTEGER,
            ano_fim INTEGER,
            posicao_lado TEXT,
            detalhes_acabamento TEXT,
            descricao_amigavel TEXT,
            perguntas_clientes TEXT
        )
    """)
    conn.commit()
    return conn

def enriquecer_base(limite_total: Optional[int] = None, tamanho_lote: int = 15):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "sua_chave_aqui":
        raise ValueError("Configure a variável GEMINI_API_KEY no arquivo .env!")

    client = genai.Client(api_key=api_key)
    conn = init_db()
    cursor = conn.cursor()

    # Identificar IDs já gravados para garantir continuidade sem custo duplicado
    cursor.execute("SELECT id_original FROM produtos")
    processados = set(row[0] for row in cursor.fetchall())
    print(f"[INFO] Itens ja salvos no banco local 'produtos_enriquecidos.db': {len(processados)}")

    df = pd.read_csv("bd.csv")
    df_pendentes = df[~df["id"].isin(processados)]

    if limite_total:
        print(f"[INFO] Modo Limitado: processando no maximo {limite_total} itens novos.")
        df_pendentes = df_pendentes.head(limite_total)

    if df_pendentes.empty:
        print("[INFO] Todos os itens selecionados ja foram processados!")
        return

    registros = df_pendentes.to_dict(orient="records")
    total_lotes = (len(registros) + tamanho_lote - 1) // tamanho_lote
    print(f"[INFO] Iniciando processamento: {len(registros)} itens em {total_lotes} lotes de {tamanho_lote} itens...")

    system_instruction = (
        "Você é um especialista em autopeças de carros antigos nacionais (1970 a 1999). "
        "Sua tarefa é receber os nomes brutos de peças de um ERP (com códigos e abreviações como "
        "LD, LE, RET, LANT, faixas de ano como 87/94 e modelos como GOL/PAR/SAV) e convertê-los "
        "em metadados técnicos precisos, descrições claras e perguntas realistas de clientes de oficina e colecionadores."
    )

    for i in tqdm(range(0, len(registros), tamanho_lote), desc="Processando Lotes"):
        lote = registros[i:i + tamanho_lote]
        prompt_linhas = [f"- ID: {item['id']} | Nome ERP: {item['nome']} | Preco: R$ {item['preco']}" for item in lote]
        prompt_texto = "Desnormalize e enriqueça as seguintes autopeças de carros clássicos:\n" + "\n".join(prompt_linhas)

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_texto,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=RespostaLote,
                    temperature=0.1,
                ),
            )

            resultado: RespostaLote = RespostaLote.model_validate_json(response.text)
            mapa_lote = {item["id"]: item for item in lote}

            for p in resultado.produtos:
                orig = mapa_lote.get(p.id_original, {})
                cursor.execute("""
                    INSERT OR REPLACE INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p.id_original,
                    orig.get("nome", ""),
                    orig.get("preco", 0.0),
                    p.tipo_peca,
                    p.montadora,
                    ", ".join(p.modelos_compativeis),
                    p.ano_inicio,
                    p.ano_fim,
                    p.posicao_lado,
                    p.detalhes_acabamento,
                    p.descricao_amigavel,
                    " | ".join(p.perguntas_clientes)
                ))
            conn.commit()

        except Exception as e:
            print(f"\n[AVISO] Falha no lote inicial ID {lote[0]['id']}: {e}")
            continue

    print("\n[CONCLUIDO] Processamento finalizado com sucesso!")

if __name__ == "__main__":
    # Exemplo seguro: processar 30 itens em 2 lotes de 15
    enriquecer_base(limite_total=30, tamanho_lote=15)
