import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import google.generativeai as genai

# 1. Lista de Feeds RSS para monitorar
FEEDS_NOTICIAS = [
    "https://blog.grancursosonline.com.br/feed/",
    "https://www.estrategiaconcursos.com.br/blog/feed/",
    "https://folhadirigida.com.br/feed/",
    "https://proximosconcursos.com/feed/"
]

def coletar_noticias():
    textos = []
    for url in FEEDS_NOTICIAS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:  # 5 notícias mais recentes de cada
                textos.append(f"Título: {entry.title}\nLink: {entry.link}\nResumo: {entry.get('summary', '')[:250]}\n")
        except Exception as e:
            print(f"Erro ao ler feed {url}: {e}")
    return "\n---\n".join(textos)

def obter_modelo_valido():
    """Identifica automaticamente o melhor modelo de texto liberado na sua chave."""
    try:
        modelos = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        # Prioriza qualquer versão Flash disponível
        for m in modelos:
            if "flash" in m.lower():
                return m
        # Se não achar flash, pega o primeiro modelo compatível disponível
        if modelos:
            return modelos[0]
    except Exception as e:
        print(f"Aviso ao listar modelos: {e}")
    return "gemini-1.5-flash-latest"

def analisar_com_ia(conteudo, modo):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    genai.configure(api_key=api_key)
    
    nome_modelo = obter_modelo_valido()
    print(f"Utilizando o modelo: {nome_modelo}")
    model = genai.GenerativeModel(nome_modelo)
    
    if modo == "cupons":
        prompt = (
            "Você é um assistente focado em encontrar promoções de concursos públicos (Gran Concursos, Estratégia Concursos, etc).\n"
            "Analise as seguintes publicações recentes e identifique cupons ativos, promoções relâmpago ou descontos válidos.\n"
            "Formate em tópicos claros com: Nome do Curso, Código do Cupom / Desconto, e o Link direto.\n"
            "Se não encontrar cupons explícitos, liste as principais ofertas de assinatura vigentes.\n\n"
            f"Conteúdo:\n{conteudo}"
        )
    else:
        prompt = (
            "Você é um analista especialista em concursos públicos.\n"
            "Analise os dados recentes coletados abaixo e filtre apenas o que for NOTÍCIA QUENTE (editais iminentes, autorizações, bancas definidas, notícias urgentes).\n"
            "Descarte notícias irrelevantes ou artigos genéricos.\n"
            "Apresente no máximo 5 tópicos diretos, com resumo em 2 linhas e o Link.\n\n"
            f"Conteúdo:\n{conteudo}"
        )

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro na IA: {str(e)}"

def enviar_email(assunto, corpo_texto):
    remetente = os.environ.get("EMAIL_ORIGEM", "").strip()
    senha = os.environ.get("EMAIL_SENHA", "").strip()
    destinatario = os.environ.get("EMAIL_DESTINO", "").strip()

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(remetente, senha)
        server.sendmail(remetente, destinatario, msg.as_string())
    print("E-mail enviado com sucesso!")

if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "noticias"
    print(f"Iniciando coleta - Modo: {modo}")
    dados_brutos = coletar_noticias()
    
    if dados_brutos:
        relatorio = analisar_com_ia(dados_brutos, modo)
        titulo = "🎟️ Radar de Cupons de Concursos" if modo == "cupons" else "🔥 Radar Concursos: Notícias Quentes"
        enviar_email(titulo, relatorio)
    else:
        print("Nenhum dado coletado dos feeds.")
