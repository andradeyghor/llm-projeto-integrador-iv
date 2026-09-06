import os
import sys
import time
import sqlite3
import argparse
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
    id_original: str = Field(description="ID original do produto no bd.csv")
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
            id_original TEXT PRIMARY KEY,
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

def enriquecer_base(limite_total: Optional[int] = 100, tamanho_lote: int = 15, db_name: str = "produtos_enriquecidos.db"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "sua_chave_aqui":
        raise ValueError("Configure a variável GEMINI_API_KEY no arquivo .env!")

    client = genai.Client(api_key=api_key)
    conn = init_db(db_name)
    cursor = conn.cursor()

    # Identificar IDs já gravados no banco para garantir continuidade sem custo duplicado
    cursor.execute("SELECT id_original FROM produtos")
    processados = set(str(row[0]) for row in cursor.fetchall())
    print(f"[INFO] Itens ja salvos no banco '{db_name}': {len(processados)}")

    df = pd.read_csv("bd.csv", dtype={"id": str})
    df_pendentes = df[~df["id"].astype(str).isin(processados)]

    if limite_total:
        print(f"[INFO] Modo Limitado: processando no maximo {limite_total} itens novos.")
        df_pendentes = df_pendentes.head(limite_total)

    if df_pendentes.empty:
        print("[INFO] Todos os itens selecionados ja foram processados!")
        return

    registros = df_pendentes.to_dict(orient="records")
    total_lotes = (len(registros) + tamanho_lote - 1) // tamanho_lote
    print(f"[INFO] Iniciando processamento: {len(registros)} itens em {total_lotes} lotes de ate {tamanho_lote} itens...")

    system_instruction = (
        "Você é um especialista em autopeças de carros antigos nacionais (1970 a 1999). "
        "Sua tarefa é receber os nomes brutos de peças de um ERP (com códigos e abreviações como "
        "LD, LE, RET, LANT, faixas de ano como 87/94 e modelos como GOL/PAR/SAV) e convertê-los "
        "em metadados técnicos precisos, descrições claras e perguntas realistas de clientes de oficina e colecionadores."
    )

    sucessos = 0
    for i in tqdm(range(0, len(registros), tamanho_lote), desc="Progresso dos Lotes"):
        lote = registros[i:i + tamanho_lote]
        prompt_linhas = [f"- ID: {item['id']} | Nome ERP: {item['nome']} | Preco: R$ {item['preco']}" for item in lote]
        prompt_texto = "Desnormalize e enriqueça as seguintes autopeças de carros clássicos:\n" + "\n".join(prompt_linhas)

        # Retry com backoff para 503 e oscilações temporárias
        max_tentativas = 3
        resultado = None

        for tentativa in range(1, max_tentativas + 1):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt_texto,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=RespostaLote,
                        temperature=0.1,
                    ),
                )
                resultado = RespostaLote.model_validate_json(response.text)
                break
            except Exception as e:
                if tentativa < max_tentativas:
                    tempo_espera = tentativa * 3
                    time.sleep(tempo_espera)
                else:
                    print(f"\n[AVISO] Falha persistente no lote ID {lote[0]['id']}: {e}")

        if not resultado:
            continue

        mapa_lote = {str(item["id"]): item for item in lote}
        for p in resultado.produtos:
            orig = mapa_lote.get(str(p.id_original), {})
            cursor.execute("""
                INSERT OR REPLACE INTO produtos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(p.id_original),
                orig.get("nome", ""),
                float(orig.get("preco", 0.0)),
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
        sucessos += len(resultado.produtos)

    cursor.execute("SELECT COUNT(*) FROM produtos")
    total_db = cursor.fetchone()[0]
    print(f"\n[CONCLUIDO] Lote finalizado! {sucessos} produtos inseridos com sucesso.")
    print(f"[ESTATISTICA] Total de produtos agora no banco '{db_name}': {total_db}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enriquecer catalogo de autopecas com Gemini 3.6 Flash")
    parser.add_argument("--limite", type=int, default=100, help="Quantidade maxima de produtos novos a processar (default: 100)")
    parser.add_argument("--lote", type=int, default=15, help="Tamanho do lote por requisicao a API (default: 15)")
    args = parser.parse_args()

    enriquecer_base(limite_total=args.limite, tamanho_lote=args.lote)
