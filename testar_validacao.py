import os
import json
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Schema para validação estruturada via Pydantic
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

def executar_teste_validacao():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "sua_chave_aqui":
        print("⚠️  ATENÇÃO: A variável GEMINI_API_KEY não está configurada no seu arquivo .env!")
        print("➡️  Edite o arquivo .env e cole sua chave do Google AI Studio antes de rodar.")
        return

    print("🔌 Conectando à API do Google Gemini...")
    client = genai.Client(api_key=api_key)

    # Amostra cirúrgica de 5 produtos com diferentes níveis de abreviação e modelos clássicos
    # IDs escolhidos da base:
    # - 16: RET. EXT. PE FERRO KOMBI CLIPPER 76/96 LD/LE (BRACO ZAMAK)
    # - 27: FAROL AUXILIAR GOL/PAR/SAV 87/94 LENTE VIDRO RAIADO LD
    # - 36: LENTE LANTERNA TRASEIRA FIAT 147 79/82 LUZ DA RE LD
    # - 43: LENTE LANTERNA TRASEIRA CHEVY 83/94 TRICOLOR LE
    # - 23: FILTRO DE AR ESPORT. CROM. P/ CARBURADOR VW MOTOR
    ids_amostra = [16, 27, 36, 43, 23]

    df = pd.read_csv("bd.csv")
    df_amostra = df[df["id"].isin(ids_amostra)]
    if df_amostra.empty:
        # Fallback se os IDs variarem
        df_amostra = df.head(5)

    print(f"📦 Amostra selecionada: {len(df_amostra)} produtos para teste de validação.")
    print("-" * 70)

    prompt_linhas = []
    for _, row in df_amostra.iterrows():
        prompt_linhas.append(f"- ID: {row['id']} | Nome ERP: {row['nome']} | Preço: R$ {row['preco']}")

    prompt_texto = "Desnormalize e enriqueça as seguintes autopeças de carros clássicos:\n" + "\n".join(prompt_linhas)

    system_instruction = (
        "Você é um especialista em autopeças de carros antigos nacionais (1970 a 1999). "
        "Sua tarefa é receber os nomes brutos de peças de um ERP (com códigos e abreviações como "
        "LD, LE, RET, LANT, faixas de ano como 87/94 e modelos como GOL/PAR/SAV) e convertê-los "
        "em metadados técnicos precisos, descrições claras e perguntas realistas de clientes de oficina e colecionadores."
    )

    print("🚀 Enviando 1 única requisição para o Gemini 2.5 Flash (consumo de cota mínimo: ~800 tokens)...")
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

        print("\n✅ SUCESSO! Resultado obtido e validado com o Schema Pydantic:")
        print("=" * 70)

        resultado_dict = []
        for p in resultado.produtos:
            print(f"\n[ID {p.id_original}]")
            print(f"  • Tipo: {p.tipo_peca}")
            print(f"  • Montadora: {p.montadora} | Modelos: {', '.join(p.modelos_compativeis)}")
            print(f"  • Anos: {p.ano_inicio or 'N/A'} até {p.ano_fim or 'N/A'} | Posição: {p.posicao_lado}")
            print(f"  • Acabamento: {p.detalhes_acabamento}")
            print(f"  • Descrição Amigável: {p.descricao_amigavel}")
            print("  • Perguntas Sintéticas do Balcão:")
            for q in p.perguntas_clientes:
                print(f"      - \"{q}\"")
            resultado_dict.append(p.model_dump())

        # Salvar resultado do teste para inspeção
        os.makedirs("data", exist_ok=True)
        with open("data/teste_validacao.json", "w", encoding="utf-8") as f:
            json.dump(resultado_dict, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 70)
        print("📁 Resultado completo do teste salvo em: data/teste_validacao.json")

    except Exception as e:
        print(f"\n❌ Ocorreu um erro na chamada da API: {e}")

if __name__ == "__main__":
    executar_teste_validacao()
