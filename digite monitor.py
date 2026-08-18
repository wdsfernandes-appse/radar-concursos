import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import requests

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
            for entry in feed.entries[:5]:  # Pega os 5 artigos mais recentes de cada
                textos.append(f"Título: {entry.title}\nLink: {entry.link}\nResumo: {entry.get('summary', '')[:250]}\n")
        except Exception as e:
            print(f"Erro ao ler feed {url}: {e}")
    return "\n---\n".join(textos)

def analisar_com_ia(conteudo, modo):
    api_key = os.environ.get("GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    if modo == "cupons":
        prompt = (
            "Você é um assistente focado em encontrar promoções de concursos (Gran Concursos, Estratégia Concursos, etc).\n"
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

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
    
    if resp.status_code == 200:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
        return f"Erro na IA: {resp.text}"

def enviar_email(assunto, corpo_texto):
    remetente = os.environ.get("EMAIL_ORIGEM")
    senha = os.environ.get("EMAIL_SENHA")
    destinatario = os.environ.get("EMAIL_DESTINO")

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
