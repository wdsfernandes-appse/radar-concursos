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

# 1. Feeds RSS de Notícias (Folha Dirigida prioritária)
FEEDS_NOTICIAS = [
    {"nome": "Folha Dirigida / Qconcursos", "url": "https://folha.qconcursos.com/feed/", "prioridade": True},
    {"nome": "Folha Dirigida (Blog)", "url": "https://folhadirigida.com.br/feed/", "prioridade": True},
    {"nome": "Gran Cursos Online", "url": "https://blog.grancursosonline.com.br/feed/", "prioridade": False},
    {"nome": "Estratégia Concursos", "url": "https://www.estrategiaconcursos.com.br/blog/feed/", "prioridade": False},
    {"nome": "Próximos Concursos", "url": "https://proximosconcursos.com/feed/", "prioridade": False}
]

# 2. Feeds RSS do YouTube
FEEDS_YOUTUBE = [
    {"nome": "Folha Dirigida por Qconcursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC7m-d1i6F_tH_w0Y0P3y0Xw", "prioridade": True},
    {"nome": "Gran Concursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC6PjQvC_3_qN-Uj9h1m0g6w", "prioridade": False},
    {"nome": "Estratégia Concursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCs7z5QJbF7rYmO2m2y5s2gA", "prioridade": False},
    {"nome": "Direção Concursos", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCO6p2bA_uB9Q9t1y1e9z9qg", "prioridade": False}
]

# 3. Canais do Telegram
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

# 4. Páginas Oficiais de Vendas, Banners de Topo e Agregadores de Cupons
URLS_CUPONS = [
    {"nome": "Estratégia Concursos (Página Principal / Loja)", "url": "https://www.estrategiaconcursos.com.br/"},
    {"nome": "Gran Cursos Online (Página Principal / Loja)", "url": "https://www.grancursosonline.com.br/"},
    {"nome": "Direção Concursos (Página Principal / Loja)", "url": "https://www.direcaoconcursos.com.br/"},
    {"nome": "Cuponomia - Estratégia Concursos", "url": "https://www.cuponomia.com.br/desconto/estrategia-concursos"},
    {"nome": "Cuponomia - Gran Cursos", "url": "https://www.cuponomia.com.br/desconto/gran-cursos"},
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

    # 1. RSS
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
            print(f"Erro RSS {nome}: {e}")

    # 2. YouTube
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

    # 3. Telegram
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

    # 4. Raspagem de Cupons e Banners de Topo
    itens_cupons = []
    palavras_cupom = ["cupom", "% off", "off", "desconto", "código", "assinatura", "promoção", "oferta", "lote"]

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
                    
                    # 1. Procura em cabeçalhos, banners e faixas de aviso
                    banners = soup.find_all(["header", "nav", "div", "span", "p", "a", "h2", "h3"], limit=150)
                    textos_capturados = []
                    
                    for el in banners:
                        txt = el.get_text(strip=True)
                        if 10 < len(txt) < 180:
                            txt_lower = txt.lower()
                            if any(k in txt_lower for k in palavras_cupom):
                                if txt not in textos_capturados:
                                    textos_capturados.append(txt)

                    if textos_capturados:
                        resumo_banners = " | ".join(textos_capturados[:8])
                        itens_cupons.append(f"🎟️ [FAIXA / BANNER OFICIAL - {nome}]: {resumo_banners}\nLink: {url}")
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
        "Você é um jornalista analista sênior de concursos e especialista em encontrar códigos de cupons e descontos reais.\n"
        "Analise o material coletado nas últimas horas e gere o boletim com as duas seções abaixo:\n\n"
        "🎯 DIRETRIZES DE NOTÍCIAS:\n"
        "1. PRIORIDADE MÁXIMA PARA FOLHA DIRIGIDA / QCONCURSOS (itens com ⭐).\n"
        "2. COMPLEMENTE com os outros portais (Estratégia, Gran, Direção).\n"
        "3. Priorize atos oficiais: editais publicados, bancas definidas, comissões, autorizações e concursos de alto interesse.\n\n"
        "🎯 DIRETRIZES DE CUPONS E OFERTAS (MÁXIMA ATENÇÃO):\n"
        "1. Procure nos textos marcados como [FAIXA / BANNER OFICIAL] e nas mensagens do Telegram os códigos de cupom de desconto (geralmente palavras em MAIÚSCULAS como 'TRANSPETRO20', 'RECOMECO', 'TURBO30', etc.), porcentagens de desconto e promoções de lote.\n"
        "2. Se encontrar códigos de cupons, DESTAQUE O CÓDIGO EXATO, a porcentagem de desconto e a que cursos/instituição se aplica.\n"
        "3. Se houver apenas promoções de assinatura sem código explícito, resuma a condição da oferta.\n\n"
        "ESTRUTURA DO E-MAIL:\n\n"
        "=========================================\n"
        "🔥 SEÇÃO 1: NOTÍCIAS QUENTES E EDITAIS RECENTES\n"
        "=========================================\n"
        "📌 **[Nome do Concurso] — [Status / Destaque]**\n"
        "- **Resumo:** Vagas, remuneração, cargos ou novidade oficial (2 a 3 linhas).\n"
        "- **Fonte / Link:** [Link original]\n\n"
        "=========================================\n"
        "🎟️ SEÇÃO 2: CUPONS E PROMOÇÕES ATIVAS\n"
        "=========================================\n"
        "Formato para cada cupom ou promoção encontrada:\n"
        "🏷️ **[Instituição: Estratégia / Gran / Direção / Qconcursos]**\n"
        "- **Código do Cupom:** [CÓDIGO ou 'Aplicado direto no site']\n"
        "- **Desconto / Condição:** [Ex: 20% de desconto no Pacote Transpetro, Assinatura em lote promocional, etc.]\n"
        "- **Link:** [URL da oferta]\n\n"
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
    msg["Subject"] = "🔥 Radar Concursos: Notícias Quentes + Cupons em Destaque"
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(remetente, senha)
        server.sendmail(remetente, lista_destinatarios, msg.as_string())
    print(f"E-mail enviado com sucesso para: {lista_destinatarios}")

if __name__ == "__main__":
    print("Iniciando varredura com captura de cupons de cabeçalho...")
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
