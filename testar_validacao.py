import os
import sys
import json
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

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

# Schema para validação estruturada via Pydantic
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

def executar_teste_validacao():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "sua_chave_aqui":
        print("[AVISO] A variavel GEMINI_API_KEY nao esta configurada no seu arquivo .env!")
        print("--> Abra o arquivo .env e adicione: GEMINI_API_KEY=sua_chave_aqui")
        return

    print("[INFO] Conectando a API do Google Gemini...")
    client = genai.Client(api_key=api_key)

    # 5 peças emblemáticas de carros clássicos da base bd.csv:
    # 461058: Retrovisor Kombi Clipper 76/96
    # 600860: Farol Auxiliar Gol/Parati/Saveiro 87/94 LD
    # 410806: Lente Lanterna Traseira Fiat 147 79/82 LD
    # 412033: Lente Lanterna Traseira Chevy 83/94 LE
    # 611274: Filtro de Ar Esportivo Carburador VW Motor AP
    ids_amostra = ["461058", "600860", "410806", "412033", "611274"]

    df = pd.read_csv("bd.csv", dtype={"id": str})
    df_amostra = df[df["id"].isin(ids_amostra)]
    if df_amostra.empty:
        df_amostra = df.head(5)

    print(f"[INFO] Amostra selecionada: {len(df_amostra)} produtos para teste de validacao.")
    print("-" * 70)

    prompt_linhas = []
    for _, row in df_amostra.iterrows():
        prompt_linhas.append(f"- ID: {row['id']} | Nome ERP: {row['nome']} | Qtd Estoque: {row['quantidade']}")

    prompt_texto = "Desnormalize e enriqueça as seguintes autopeças de carros clássicos:\n" + "\n".join(prompt_linhas)

    system_instruction = (
        "Você é um especialista em autopeças de carros antigos nacionais (1970 a 1999). "
        "Sua tarefa é receber os nomes brutos de peças de um ERP (com códigos e abreviações como "
        "LD, LE, RET, LANT, faixas de ano como 87/94 e modelos como GOL/PAR/SAV) e convertê-los "
        "em metadados técnicos precisos, descrições claras e perguntas realistas de clientes de oficina e colecionadores."
    )

    print("[INFO] Enviando 1 unica requisicao para o Gemini 3.6 Flash (~800 tokens)...")
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

        resultado: RespostaLote = RespostaLote.model_validate_json(response.text)

        print("\n[SUCESSO] Resultado obtido e validado com o Schema Pydantic:")
        print("=" * 70)

        resultado_dict = []
        for p in resultado.produtos:
            print(f"\n[ID {p.id_original}]")
            print(f"  Tipo: {p.tipo_peca}")
            print(f"  Montadora: {p.montadora} | Modelos: {', '.join(p.modelos_compativeis)}")
            print(f"  Anos: {p.ano_inicio or 'N/A'} ate {p.ano_fim or 'N/A'} | Posicao: {p.posicao_lado}")
            print(f"  Acabamento: {p.detalhes_acabamento}")
            print(f"  Descricao Amigavel: {p.descricao_amigavel}")
            print("  Perguntas Sinteticas do Balcao:")
            for q in p.perguntas_clientes:
                print(f"    - \"{q}\"")
            resultado_dict.append(p.model_dump())

        # Salvar resultado do teste para inspeção
        os.makedirs("data", exist_ok=True)
        with open("data/teste_validacao.json", "w", encoding="utf-8") as f:
            json.dump(resultado_dict, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("[CONCLUIDO] Resultado completo do teste salvo em: data/teste_validacao.json")

    except Exception as e:
        print(f"\n[ERRO] Ocorreu um erro na chamada da API: {e}")

if __name__ == "__main__":
    executar_teste_validacao()
