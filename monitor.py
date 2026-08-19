import os
import smtplib
import json
import time
from datetime import datetime, timezone
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

HISTORICO_ARQUIVO = "historico.json"

# 1. Feeds RSS de Notícias (Folha Dirigida / Qconcursos no topo da prioridade)
FEEDS_NOTICIAS = [
    {"nome": "Folha Dirigida / Qconcursos", "url": "https://folha.qconcursos.com/feed/", "prioridade": True},
    {"nome": "Folha Dirigida (Blog)", "url": "https://folhadirigida.com.br/feed/", "prioridade": True},
    {"nome": "Gran Cursos Online", "url": "https://blog.grancursosonline.com.br/feed/", "prioridade": False},
    {"nome": "Estratégia Concursos", "url": "https://www.estrategiaconcursos.com.br/blog/feed/", "prioridade": False},
    {"nome": "Próximos Concursos", "url": "https://proximosconcursos.com/feed/", "prioridade": False}
]

# 2. Feeds RSS do YouTube (Folha Dirigida prioritária)
FEEDS_YOUTUBE = [
    {"nome": "Folha Dirigida por Qconcursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC7m-d1i6F_tH_w0Y0P3y0Xw", "prioridade": True},
    {"nome": "Gran Concursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6PjQvC_3_qN-Uj9h1m0g6w", "prioridade": False},
    {"nome": "Estratégia Concursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCs7z5QJbF7rYmO2m2y5s2gA", "prioridade": False},
    {"nome": "Direção Concursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCO6p2bA_uB9Q9t1y1e9z9qg", "prioridade": False}
]

# 3. Canais Oficiais do Telegram
CANAIS_TELEGRAM = [
    {"nome": "folhadirigidanoticias", "prioridade": True},
    {"nome": "GranCursosNoticias", "prioridade": False},
    {"nome": "GranCursosFiscais", "prioridade": False},
    {"nome": "GranCursosGestaoeControle", "prioridade": False},
    {"nome": "GranCursosTribunais", "prioridade": False},
    {"nome": "CaminhoCertoTCESC", "prioridade": False},
    {"nome": "JornadaDoEscrevente", "prioridade": False},
    {"nome": "bancodobrasilec", "prioridade": False}
]

# 4. Páginas de Cupons e Ofertas
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
    historico_limpo = {k: v for k, v in historico.items() if agora - v < 4 * 86400}
    with open(HISTORICO_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(historico_limpo, f, indent=2, ensure_ascii=False)

def eh_recente(entry, max_horas=48):
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        pub_dt = datetime(*parsed_time[:6], tzinfo=timezone.utc)
        agora_dt = datetime.now(timezone.utc)
        if (agora_dt - pub_dt).total_seconds() > max_horas * 3600:
            return False
    return True

def formatar_data(entry):
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed_time:
        return time.strftime("%d/%m/%Y %H:%M", parsed_time)
    return "Recente"

def coletar_tudo(historico):
    itens_prioritarios = []
    itens_complementares = []
    novos_hashes = {}
    agora = time.time()

    # 1. Coleta Portais RSS
    for feed_info in FEEDS_NOTICIAS:
        url = feed_info["url"]
        nome = feed_info["nome"]
        eh_prioridade = feed_info["prioridade"]
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                link = entry.get("link", "")
                if link and link not in historico and eh_recente(entry, 48):
                    data_pub = formatar_data(entry)
                    tag_prefixo = "⭐ [FONTE PRIORITÁRIA - FOLHA DIRIGIDA / QCONCURSOS]" if eh_prioridade else f"[{nome}]"
                    texto_item = (
                        f"{tag_prefixo} Publicado em: {data_pub}\n"
                        f"Título: {entry.title}\n"
                        f"Link: {link}\n"
                        f"Resumo: {entry.get('summary', '')[:300]}"
                    )
                    if eh_prioridade:
                        itens_prioritarios.append(texto_item)
                    else:
                        itens_complementares.append(texto_item)
                    novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro RSS {nome} ({url}): {e}")

    # 2. Coleta YouTube
    for yt_info in FEEDS_YOUTUBE:
        url = yt_info["url"]
        nome = yt_info["nome"]
        eh_prioridade = yt_info["prioridade"]
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                link = entry.get("link", "")
                if link and link not in historico and eh_recente(entry, 48):
                    data_pub = formatar_data(entry)
                    tag_prefixo = "⭐ [VÍDEO PRIORITÁRIO - FOLHA DIRIGIDA]" if eh_prioridade else f"[Vídeo - {nome}]"
                    texto_item = (
                        f"{tag_prefixo} Publicado em: {data_pub}\n"
                        f"Título: {entry.title}\n"
                        f"Link: {link}"
                    )
                    if eh_prioridade:
                        itens_prioritarios.append(texto_item)
                    else:
                        itens_complementares.append(texto_item)
                    novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro YouTube {nome}: {e}")

    # 3. Coleta Telegram
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for tg_info in CANAIS_TELEGRAM:
        canal = tg_info["nome"]
        eh_prioridade = tg_info["prioridade"]
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
                            tag_prefixo = "⭐ [TELEGRAM PRIORITÁRIO - FOLHA DIRIGIDA]" if eh_prioridade else f"[Telegram @{canal}]"
                            texto_item = f"{tag_prefixo}: {texto}"
                            if eh_prioridade:
                                itens_prioritarios.append(texto_item)
                            else:
                                itens_complementares.append(texto_item)
                            novos_hashes[msg_hash] = agora
        except Exception as e:
            print(f"Erro Telegram @{canal}: {e}")

    # 4. Coleta Cupons e Ofertas
    itens_cupons = []
    for item in URLS_CUPONS:
        url = item["url"]
        nome = item["nome"]
        try:
            if "feed" in url:
                feed = feedparser.parse(url)
                for entry in feed.entries[:4]:
                    link = entry.get("link", "")
                    if link and link not in historico and eh_recente(entry, 48):
                        itens_cupons.append(f"[Cupom - {nome}]: {entry.title}\nLink: {link}")
                        novos_hashes[link] = agora
            else:
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    ofertas = soup.find_all(["h3", "h4", "p", "span"], limit=30)
                    textos = [elem.get_text(strip=True) for elem in ofertas if len(elem.get_text(strip=True)) > 15]
                    resumo_pagina = " | ".join(textos[:8])
                    itens_cupons.append(f"[Página de Desconto - {nome}]: {resumo_pagina}\nLink: {url}")
        except Exception as e:
            print(f"Erro Cupons {nome}: {e}")

    todos_itens = itens_prioritarios + itens_complementares + itens_cupons
    return todos_itens, novos_hashes

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
        "Você é um jornalista analista sênior de concursos públicos no Brasil.\n"
        "Analise todo o material coletado nas últimas horas e elabore um boletim objetivo.\n\n"
        "🎯 DIRETRIZ PRINCIPAL DE FONTES:\n"
        "1. DÊ PRIORIDADE MÁXIMA PARA A FOLHA DIRIGIDA / QCONCURSOS (itens marcados com ⭐). Se a Folha noticiou determinado concurso, priorize o resumo e o link dela.\n"
        "2. Em seguida, COMPLEMENTE com as novidades relevantes dos outros portais (Estratégia, Gran, Direção, etc.).\n\n"
        "CRITÉRIOS DE SELEÇÃO:\n"
        "- Priorize fatos reais: editais na praça, inscrições abertas, bancas contratadas, comissões, autorizações e concursos de apelo nacional, fiscal, controle e tribunais.\n"
        "- Descarte apenas guias teóricos sem notícia (ex: 'como estudar para concurso') e notícias encerradas.\n"
        "- Não invente notícias nem crie códigos de cupons ilustrativos.\n\n"
        "ESTRUTURA DO E-MAIL:\n\n"
        "=========================================\n"
        "🔥 SEÇÃO 1: NOTÍCIAS QUENTES E EDITAIS RECENTES\n"
        "=========================================\n"
        "📌 **[Nome do Concurso] — [Status / Destaque]**\n"
        "- **Resumo:** Vagas, salários, cargos ou ato oficial em destaque (2 a 3 linhas objetivas).\n"
        "- **Fonte / Link:** [Link original]\n\n"
        "=========================================\n"
        "🎟️ SEÇÃO 2: CUPONS E OFERTAS ATIVAS\n"
        "=========================================\n"
        "Liste cupons e ofertas reais ativas identificadas nas fontes.\n"
        "Se não houver cupom específico novo, informe: 'Nenhum cupom inédito detectado nas fontes nesta rodada.'\n\n"
        f"DADOS COLETADOS:\n{conteudo}"
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
    msg["Subject"] = "🔥 Radar Concursos: Folha Dirigida & Notícias Quentes"
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(remetente, senha)
        server.sendmail(remetente, lista_destinatarios, msg.as_string())
    print(f"E-mail enviado com sucesso para: {lista_destinatarios}")

if __name__ == "__main__":
    print("Iniciando varredura com prioridade na Folha Dirigida / Qconcursos...")
    historico = carregar_historico()
    novidades, novos_hashes = coletar_tudo(historico)

    if novidades:
        print(f"Coletados {len(novidades)} itens. Processando na IA...")
        relatorio = analisar_unificado("\n---\n".join(novidades))
        enviar_email(relatorio)
        
        historico.update(novos_hashes)
        salvar_historico(historico)
    else:
        print("Nenhuma novidade recente encontrada nesta rodada. E-mail poupado.")
