# SLM de Recomendação de Autopeças para Carros Clássicos (1970–1999)

> **Projeto Integrador IV**  
> Assistente inteligente e offline para recomendação e consulta de autopeças voltado a colecionadores e donos de veículos antigos nacionais (1970 a 1999).

---

## 📌 Visão Geral do Projeto

Lojas de autopeças com foco em veículos clássicos (Gol quadrado, Chevette, Opala, Fusca, Monza, Uno, etc.) utilizam sistemas de gestão (ERP) com nomenclaturas técnicas altamente abreviadas (`LD`, `LE`, `RET.`, `LANT.`, `JTA.CAB.`, faixas de ano `87/94`). 

Este projeto tem como objetivo:
1. **Enriquecer e Desnormalizar o Catálogo (`bd.csv`):** Utilizar modelos de linguagem avançados (Google Gemini 2.5 Flash) para traduzir códigos e abreviações em metadados ricos (montadora, modelo, ano, lado/posição, acabamento) e gerar perguntas sintéticas de clientes de balcão.
2. **Construir um SLM (Small Language Model) 100% Offline:** Permitir que o sistema opere localmente no balcão da loja, sem conexão com a internet (usando modelos como Qwen 2.5 3B ou Llama 3.2 3B via Ollama / llama.cpp).
3. **Mecanismo de Busca Híbrido (RAG Local):** Cruzar a pergunta em linguagem natural do cliente com o catálogo enriquecido para recomendar as peças corretas com preços e compatibilidades exatas.

---

## 🗂️ Estrutura do Repositório

```text
├── bd.csv                      # Base de dados original (8.786 produtos)
├── enriquecer_base.py          # Script de enriquecimento em lote com Gemini API
├── testar_validacao.py         # Script de teste rápido (amostra de 5 itens para economizar cotas)
├── requirements.txt            # Dependências Python do projeto
├── .env.example                # Modelo de configuração de variáveis de ambiente
├── .env                        # Chaves de API locais (ignorado no git)
├── .gitignore                  # Regras de exclusão do git
└── README.md                   # Documentação do projeto
```

---

## 🚀 Como Configurar o Ambiente

### 1. Clonar o repositório e preparar o ambiente
```bash
git clone <url-do-repositorio>
cd llm-projeto-integrador-iv

# Criar e ativar ambiente virtual (recomendado)
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate
```

### 2. Instalar as dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar a Chave da API Gemini
Obtenha sua chave gratuita ou do seu plano em [Google AI Studio](https://aistudio.google.com/).
No arquivo `.env`, preencha:
```env
GEMINI_API_KEY=sua_chave_aqui
```

---

## 🧪 Teste de Validação Rápido (Economia de Cotas)

Para validar a integração com a API sem consumir quase nada da sua cota (apenas ~800 tokens de teste em 5 itens clássicos selecionados):

```bash
python testar_validacao.py
```

O script testará:
- Farol de Gol/Parati/Saveiro 87/94
- Lanterna do Chevette 83/94
- Retrovisor da Kombi Clipper 76/96
- Lente de lanterna do Fiat 147 79/82
- Filtro esportivo para carburador VW motor AP

Ele exibirá no terminal o resultado estruturado em JSON e salvará o resultado de teste em `data/teste_validacao.json`.

---

## 🏭 Enriquecimento em Produção (Lote com Checkpoints)

Após validar a amostra, você pode processar a base inteira ou partes dela:
```bash
# Executa em lotes de 15 itens com gravação incremental no SQLite
python enriquecer_base.py
```
- **Idempotente:** Se interrompido, recomeça exatamente do último produto salvo.
- **Armazenamento:** Salva os resultados no banco local `produtos_enriquecidos.db`.
