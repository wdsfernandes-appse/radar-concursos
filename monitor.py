import os
import smtplib
import json
import time
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

HISTORICO_ARQUIVO = "historico.json"

# 1. Portais e Blogs de Concursos (RSS)
FEEDS_NOTICIAS = [
    "https://blog.grancursosonline.com.br/feed/",
    "https://www.estrategiaconcursos.com.br/blog/feed/",
    "https://folhadirigida.com.br/feed/",
    "https://proximosconcursos.com/feed/"
]

# 2. Canais do YouTube
FEEDS_YOUTUBE = [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6PjQvC_3_qN-Uj9h1m0g6w", # Gran
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCs7z5QJbF7rYmO2m2y5s2gA", # Estratégia
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCO6p2bA_uB9Q9t1y1e9z9qg", # Direção
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC7m-d1i6F_tH_w0Y0P3y0Xw"  # Folha Dirigida
]

# 3. Canais Oficiais do Telegram
CANAIS_TELEGRAM = [
    "GranCursosNoticias",
    "GranCursosFiscais",
    "GranCursosGestaoeControle",
    "GranCursosTribunais",
    "CaminhoCertoTCESC",
    "JornadaDoEscrevente",
    "bancodobrasilec",
    "folhadirigidanoticias"
]

# 4. Páginas e Feeds de Cupons/Descontos
URLS_CUPONS = [
    {"nome": "Cuponomia - Gran Cursos", "url": "https://www.cuponomia.com.br/desconto/gran-cursos"},
    {"nome": "Cuponomia - Estratégia Concursos", "url": "https://www.cuponomia.com.br/desconto/estrategia-concursos"},
    {"nome": "Cuponomia - Direção Concursos", "url": "https://www.cuponomia.com.br/desconto/direcao-concursos"},
    {"nome": "Gran Cursos Descontos", "url": "https://blog.grancursosonline.com.br/tag/desconto/feed/"}
]

def carregar_historico():
    if os.path.exists(HISTORICO_ARQUIVO):
        try:
            with open(HISTORICO_ARQUIVO, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_historico(historico):
    agora = time.time()
    # Mantém registros dos últimos 5 dias
    historico_limpo = {k: v for k, v in historico.items() if agora - v < 5 * 86400}
    with open(HISTORICO_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(historico_limpo, f, indent=2, ensure_ascii=False)

def coletar_tudo(historico):
    itens = []
    novos_hashes = {}
    agora = time.time()

    # Coleta RSS
    for url in FEEDS_NOTICIAS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:12]:
                link = entry.get("link", "")
                if link and link not in historico:
                    itens.append(f"[Portal RSS]: {entry.title}\nLink: {link}\nResumo: {entry.get('summary', '')[:300]}")
                    novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro RSS {url}: {e}")

    # Coleta YouTube
    for url in FEEDS_YOUTUBE:
        try:
            feed = feedparser.parse(url)
            canal = feed.feed.get("title", "YouTube")
            for entry in feed.entries[:6]:
                link = entry.get("link", "")
                if link and link not in historico:
                    itens.append(f"[YouTube - {canal}]: {entry.title}\nLink: {link}")
                    novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro YouTube {url}: {e}")

    # Coleta Telegram
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for canal in CANAIS_TELEGRAM:
        try:
            url = f"https://t.me/s/{canal}"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                mensagens = soup.find_all("div", class_="tgme_widget_message_text")
                for msg in mensagens[-6:]:
                    texto = msg.get_text(separator=" ", strip=True)
                    if texto and len(texto) > 20:
                        msg_hash = hashlib.md5(texto.encode("utf-8")).hexdigest()
                        if msg_hash not in historico:
                            itens.append(f"[Telegram @{canal}]: {texto}")
                            novos_hashes[msg_hash] = agora
        except Exception as e:
            print(f"Erro Telegram @{canal}: {e}")

    # Coleta Páginas de Cupons
    for item in URLS_CUPONS:
        url = item["url"]
        nome = item["nome"]
        try:
            if "feed" in url:
                feed = feedparser.parse(url)
                for entry in feed.entries[:4]:
                    link = entry.get("link", "")
                    if link and link not in historico:
                        itens.append(f"[Cupom/Oferta - {nome}]: {entry.title}\nLink: {link}")
                        novos_hashes[link] = agora
            else:
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    ofertas = soup.find_all(["h3", "h4", "p", "span"], limit=30)
                    textos = [elem.get_text(strip=True) for elem in ofertas if len(elem.get_text(strip=True)) > 15]
                    resumo_pagina = " | ".join(textos[:10])
                    itens.append(f"[Página de Cupons - {nome}]: {resumo_pagina}\nLink: {url}")
        except Exception as e:
            print(f"Erro Cupons {nome}: {e}")

    return itens, novos_hashes

def obter_modelo():
    try:
        for m in genai.list_models():
            if "flash" in m.name.lower() and "generateContent" in m.supported_generation_methods:
                return m.name
    except Exception:
        pass
    return "gemini-1.5-flash-latest"

def analisar_unificado(conteudo):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(obter_modelo())

    prompt = (
        "Você é um jornalista analista de concursos públicos no Brasil e especialista em encontrar promoções reais.\n"
        "Analise os dados coletados abaixo e monte um relatório direto, informativo e atraente dividido em DUAS SEÇÕES:\n\n"
        "=========================================\n"
        "🔥 SEÇÃO 1: NOTÍCIAS QUENTES E EDITAIS RELEVANTES (8 a 15 Destaques)\n"
        "=========================================\n"
        "CRITÉRIOS DE SELEÇÃO:\n"
        "1. PRIORIZE FATOS CONCRETOS E ATRAENTES: Edital Publicado, Inscrições Abertas, Banca Definida, Comissão Formada, Autorização Oficial ou Salários/Vagas Expressivas.\n"
        "2. ABRANGÊNCIA: Traga tanto os Grandes Concursos Nacionais/Federais/Fiscais/Controle/Tribunais quanto Concursos Estaduais, Universidades Federais, Defensorias, Conselhos e Secretarias Estaduais que tenham boas oportunidades.\n"
        "3. O QUE DESCARTAR: Descarte retificações burocráticas menores (ex: mudança de local de prova ou prazos administrativos sem impacto), dicas genéricas de estudo ou avisos vazios de lives sem notícia factual.\n\n"
        "FORMATO DE CADA ITEM:\n"
        "📌 **[Nome do Órgão / Concurso] — [Status: Edital Publicado / Inscrições Abertas / Banca Definida / Autorizado / Previsão]**\n"
        "- **Resumo:** Número de vagas, remuneração inicial, cargos em destaque ou data-limite importante (2 a 3 linhas bem diretas).\n"
        "- **Link / Fonte:** [URL da matéria ou Canal de Origem]\n\n"
        "=========================================\n"
        "🎟️ SEÇÃO 2: CUPONS, DESCONTOS E PROMOÇÕES ATIVAS\n"
        "=========================================\n"
        "Extraia e organize cupons de desconto ativos, lotes promocionais de assinaturas (Gran, Estratégia, Direção, etc.) "
        "encontrados nas páginas de desconto, canais do Telegram ou YouTube.\n"
        "Indique a Instituição, Código do Cupom / Desconto e o Link correspondente.\n"
        "Se não houver cupons explícitos novos, resuma as melhores ofertas vigentes de assinaturas.\n\n"
        f"Dados coletados para triagem:\n{conteudo}"
    )

    try:
        res = model.generate_content(prompt)
        return res.text
    except Exception as e:
        return f"Erro na IA: {str(e)}"

def enviar_email(corpo):
    remetente = os.environ.get("EMAIL_ORIGEM", "").strip()
    senha = os.environ.get("EMAIL_SENHA", "").strip()
    destinatarios_brutos = os.environ.get("EMAIL_DESTINO", "").strip()
    
    lista_destinatarios = [e.strip() for e in destinatarios_brutos.split(",") if e.strip()]

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = ", ".join(lista_destinatarios)
    msg["Subject"] = "🔥 Radar Concursos: Notícias Quentes + Cupons Ativos"
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(remetente, senha)
        server.sendmail(remetente, lista_destinatarios, msg.as_string())
    print(f"E-mail enviado com sucesso para: {lista_destinatarios}")

if __name__ == "__main__":
    print("Iniciando varredura com filtro calibrado...")
    historico = carregar_historico()
    novidades, novos_hashes = coletar_tudo(historico)

    if novidades:
        print(f"Coletados {len(novidades)} itens novos. Gerando relatório...")
        relatorio = analisar_unificado("\n---\n".join(novidades))
        enviar_email(relatorio)
        
        historico.update(novos_hashes)
        salvar_historico(historico)
    else:
        print("Nenhuma novidade encontrada nesta rodada. E-mail poupado.")
