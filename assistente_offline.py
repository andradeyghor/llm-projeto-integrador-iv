import sys
import json
import requests
from typing import List, Dict, Any
from buscador_local import BuscadorAutoPecas

# Evitar problemas de encoding no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class AssistenteBalcaoOffline:
    def __init__(self, modelo_ollama: str = "qwen2.5:1.5b", url_ollama: str = "http://localhost:11434"):
        self.buscador = BuscadorAutoPecas()
        self.modelo_ollama = modelo_ollama
        self.url_ollama = url_ollama
        self.ollama_disponivel = self._verificar_ollama()

    def _verificar_ollama(self) -> bool:
        """Verifica se o servidor do Ollama está rodando localmente na máquina."""
        try:
            r = requests.get(f"{self.url_ollama}/api/tags", timeout=2)
            if r.status_code == 200:
                modelos_instalados = [m.get("name") for m in r.json().get("models", [])]
                print(f"[INFO] Servidor Ollama detectado! Modelos disponíveis: {modelos_instalados}")
                return True
        except Exception:
            pass
        return False

    def _gerar_resposta_ollama(self, pergunta_cliente: str, produtos: List[Dict[str, Any]]) -> str:
        """Envia o contexto recuperado para o SLM local offline via Ollama."""
        lista_contexto = []
        for i, p in enumerate(produtos, 1):
            lista_contexto.append(
                f"Opção {i}:\n"
                f"- Código: {p['id']}\n"
                f"- Peça: {p['tipo_peca']} ({p['descricao']})\n"
                f"- Aplicação: {p['modelos']} (Anos: {p['ano_inicio'] or 'N/A'} a {p['ano_fim'] or 'N/A'})\n"
                f"- Posição/Lado: {p['posicao']}\n"
                f"- Acabamento: {p['acabamento']}\n"
                f"- Preço: R$ {p['preco']:.2f}"
            )
        contexto_str = "\n\n".join(lista_contexto)

        prompt_sistema = (
            "Você é um balconista experiente e atencioso de uma autopeças clássicas (carros de 1970 a 1999). "
            "Responda à dúvida do cliente de forma educada, prestativa e direta. "
            "Apresente a peça correta com base no catálogo disponível, confirme a compatibilidade do carro/ano, "
            "o lado (LD para passageiro ou LE para motorista) e informe o preço e código da peça. "
            "Não invente dados nem peças fora da lista fornecida."
        )

        prompt_usuario = (
            f"Pergunta do Cliente: \"{pergunta_cliente}\"\n\n"
            f"Peças encontradas no estoque:\n{contexto_str}\n\n"
            "Formule a sua resposta como balconista:"
        )

        try:
            payload = {
                "model": self.modelo_ollama,
                "prompt": f"{prompt_sistema}\n\n{prompt_usuario}",
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 250
                }
            }
            res = requests.post(f"{self.url_ollama}/api/generate", json=payload, timeout=30)
            if res.status_code == 200:
                return res.json().get("response", "").strip()
        except Exception as e:
            return f"[Erro ao consultar SLM local: {e}]"

        return ""

    def _resposta_formatada_direta(self, pergunta_cliente: str, produtos: List[Dict[str, Any]]) -> str:
        """Formato padrão estruturado caso o Ollama ainda não esteja iniciado."""
        linhas = [
            "Olá! Verifiquei nosso estoque para você. Veja as melhores opções disponíveis:\n"
        ]
        for i, p in enumerate(produtos, 1):
            linhas.append(f"📦 Opção {i}: {p['descricao']}")
            linhas.append(f"   • Compatibilidade: {p['modelos']} ({p['ano_inicio'] or 'N/A'} a {p['ano_fim'] or 'N/A'})")
            linhas.append(f"   • Lado/Posição: {p['posicao']}")
            linhas.append(f"   • Preço: R$ {p['preco']:.2f} | Código: {p['id']}\n")
        linhas.append("Quer que eu separe alguma dessas peças para você?")
        return "\n".join(linhas)

    def responder(self, pergunta_cliente: str) -> str:
        produtos = self.buscador.buscar_produtos(pergunta_cliente, top_k=2)
        if not produtos:
            return (
                "Olá! No momento não encontrei essa peça específica no nosso catálogo para esse veículo/ano. "
                "Pode me confirmar o modelo exato e o ano do carro?"
            )

        if self.ollama_disponivel:
            resposta_slm = self._gerar_resposta_ollama(pergunta_cliente, produtos)
            if resposta_slm:
                return resposta_slm

        # Fallback sem SLM ativo
        return self._resposta_formatada_direta(pergunta_cliente, produtos)

def iniciar_chat():
    print("=" * 70)
    print("   🏎️  BALCÃO DE AUTOPEÇAS CLÁSSICAS - ASSISTENTE OFFLINE (RAG) 🏎️")
    print("=" * 70)
    
    assistente = AssistenteBalcaoOffline()
    if not assistente.ollama_disponivel:
        print("\n💡 DICA DE SLM LOCAL:")
        print("   O servidor Ollama não está ativo no momento.")
        print("   O assistente está rodando no modo RAG Local Direto.")
        print("   Para ativar a geração por IA local: instale o Ollama (ollama.com) e rode:")
        print("   > ollama run qwen2.5:1.5b")
        print("-" * 70)

    print("\nDigite sua pergunta sobre peças de carros antigos (ou 'sair' para encerrar):\n")
    while True:
        try:
            user_input = input("Cliente: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["sair", "exit", "quit"]:
                print("Atendimento encerrado. Até logo!")
                break

            resposta = assistente.responder(user_input)
            print(f"\nBalconista:\n{resposta}\n")
            print("-" * 70)
        except (KeyboardInterrupt, EOFError):
            break

if __name__ == "__main__":
    iniciar_chat()
