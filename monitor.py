import os
import smtplib
import json
import time
from datetime import datetime, timezone, timedelta
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

HISTORICO_ARQUIVO = "historico.json"

# 1. Feeds RSS de Notícias
FEEDS_NOTICIAS = [
    "https://blog.grancursosonline.com.br/feed/",
    "https://www.estrategiaconcursos.com.br/blog/feed/",
    "https://folhadirigida.com.br/feed/",
    "https://proximosconcursos.com/feed/"
]

# 2. Feeds RSS do YouTube
FEEDS_YOUTUBE = [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6PjQvC_3_qN-Uj9h1m0g6w", # Gran
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCs7z5QJbF7rYmO2m2y5s2gA", # Estratégia
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCO6p2bA_uB9Q9t1y1e9z9qg", # Direção
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC7m-d1i6F_tH_w0Y0P3y0Xw"  # Folha Dirigida
]

# 3. Canais do Telegram (abertos)
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

# 4. Páginas de Cupons
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
    # Mantém registros dos últimos 4 dias
    historico_limpo = {k: v for k, v in historico.items() if agora - v < 4 * 86400}
    with open(HISTORICO_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(historico_limpo, f, indent=2, ensure_ascii=False)

def eh_recente(entry, max_horas=48):
    """Verifica se o post foi publicado nas últimas 48 horas."""
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
    return "Data recente"

def coletar_tudo(historico):
    itens = []
    novos_hashes = {}
    agora = time.time()

    # 1. Coleta RSS dos Portais com Filtro de Data
    for url in FEEDS_NOTICIAS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                link = entry.get("link", "")
                if link and link not in historico:
                    if eh_recente(entry, max_horas=48):
                        data_pub = formatar_data(entry)
                        itens.append(
                            f"[Portal RSS - Publicado em {data_pub}]\n"
                            f"Título: {entry.title}\n"
                            f"Link: {link}\n"
                            f"Resumo: {entry.get('summary', '')[:250]}"
                        )
                        novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro RSS {url}: {e}")

    # 2. Coleta YouTube com Filtro de Data
    for url in FEEDS_YOUTUBE:
        try:
            feed = feedparser.parse(url)
            canal = feed.feed.get("title", "YouTube")
            for entry in feed.entries[:8]:
                link = entry.get("link", "")
                if link and link not in historico:
                    if eh_recente(entry, max_horas=48):
                        data_pub = formatar_data(entry)
                        itens.append(
                            f"[Vídeo YouTube - {canal} - Publicado em {data_pub}]\n"
                            f"Título: {entry.title}\n"
                            f"Link: {link}"
                        )
                        novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro YouTube {url}: {e}")

    # 3. Coleta Telegram
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
                            itens.append(f"[Telegram @{canal} - Mensagem Recente]: {texto}")
                            novos_hashes[msg_hash] = agora
        except Exception as e:
            print(f"Erro Telegram @{canal}: {e}")

    # 4. Coleta Páginas de Cupons
    for item in URLS_CUPONS:
        url = item["url"]
        nome = item["nome"]
        try:
            if "feed" in url:
                feed = feedparser.parse(url)
                for entry in feed.entries[:4]:
                    link = entry.get("link", "")
                    if link and link not in historico and eh_recente(entry, 48):
                        itens.append(f"[Cupom/Oferta - {nome}]: {entry.title}\nLink: {link}")
                        novos_hashes[link] = agora
            else:
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    ofertas = soup.find_all(["h3", "h4", "p", "span"], limit=30)
                    textos = [elem.get_text(strip=True) for elem in ofertas if len(elem.get_text(strip=True)) > 15]
                    resumo_pagina = " | ".join(textos[:8])
                    itens.append(f"[Página de Desconto - {nome}]: {resumo_pagina}\nLink: {url}")
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
        "Você é um auditor e jornalista especializado em concursos públicos no Brasil.\n"
        "Sua tarefa é analisar ESTRITAMENTE as notícias e publicações coletadas nas últimas horas fornecidas abaixo.\n\n"
        "🚨 REGRAS CRÍTICAS E INEGOCIÁVEIS (ANTI-ALUCINAÇÃO):\n"
        "1. VERACIDADE E ATUALIDADE TOTAL: Baseie-se APENAS no texto bruto fornecido abaixo. NUNCA use sua memória interna para inventar concursos antigos, datas de 2024/2025 ou fatos encerrados.\n"
        "2. PROIBIDO INVENTAR CUPONS: NUNCA crie códigos de cupons ilustrativos ou inventados (como 'DIRECAO30OFF'). Só cite cupons ou ofertas que estejam explicitamente escritos no texto abaixo. Se não houver código exato, mencione apenas as ofertas ativas reais encontradas.\n"
        "3. Se houver poucas notícias novas na lista, apresente apenas as poucas que existem. NÃO invente itens para completar espaço.\n\n"
        "ESTRUTURA DO RELATÓRIO:\n\n"
        "=========================================\n"
        "🔥 SEÇÃO 1: NOTÍCIAS QUENTES E EDITAIS RECENTES (ÚLTIMAS HORAS)\n"
        "=========================================\n"
        "Filtre os destaques reais contidos no texto (Editais publicados, inscrições, bancas, autorizações).\n"
        "Priorize: Concursos Federais/Nacionais, Área Fiscal, Controle/Gestão, Tribunais e outros órgãos de destaque presentes nos dados.\n"
        "Formato de cada item:\n"
        "📌 **[Nome do Concurso] — [Status Real Atual]**\n"
        "- **Resumo:** Vagas, remuneração ou novidade factual (máx 2 linhas).\n"
        "- **Fonte e Link:** [Link original ou canal de onde a notícia foi extraída]\n\n"
        "=========================================\n"
        "🎟️ SEÇÃO 2: CUPONS E OFERTAS ATIVAS (REAIS)\n"
        "=========================================\n"
        "Liste apenas os descontos, cashbacks ou cupons reais encontrados nas fontes.\n"
        "Se não houver cupons explícitos novos no momento, informe: 'Nenhum cupom inédito detectado nas últimas horas nas fontes monitoradas.'\n\n"
        f"DADOS COLETADOS NAS ÚLTIMAS HORAS:\n{conteudo}"
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
    msg["Subject"] = "🔥 Radar Concursos: Notícias Quentes + Cupons Reais"
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(remetente, senha)
        server.sendmail(remetente, lista_destinatarios, msg.as_string())
    print(f"E-mail enviado com sucesso para: {lista_destinatarios}")

if __name__ == "__main__":
    print("Iniciando varredura com trava de data e anti-alucinação...")
    historico = carregar_historico()
    novidades, novos_hashes = coletar_tudo(historico)

    if novidades:
        print(f"Coletados {len(novidades)} itens novos e recentes. Filtrando com IA...")
        relatorio = analisar_unificado("\n---\n".join(novidades))
        enviar_email(relatorio)
        
        historico.update(novos_hashes)
        salvar_historico(historico)
    else:
        print("Nenhuma novidade recente encontrada nesta rodada. E-mail poupado.")
