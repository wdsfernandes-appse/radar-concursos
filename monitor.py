import os
import sys
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

FEEDS_NOTICIAS = [
    "https://blog.grancursosonline.com.br/feed/",
    "https://www.estrategiaconcursos.com.br/blog/feed/",
    "https://folhadirigida.com.br/feed/",
    "https://proximosconcursos.com/feed/"
]

FEEDS_YOUTUBE = [
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC6PjQvC_3_qN-Uj9h1m0g6w", # Gran
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCs7z5QJbF7rYmO2m2y5s2gA", # Estrategia
    "https://www.youtube.com/feeds/videos.xml?channel_id=UCO6p2bA_uB9Q9t1y1e9z9qg", # Direcao
    "https://www.youtube.com/feeds/videos.xml?channel_id=UC7m-d1i6F_tH_w0Y0P3y0Xw"  # Folha Dirigida
]

CANAIS_TELEGRAM = [
    "estrategiaconcursos",
    "grancursosonline",
    "folhadirigidanoticias"
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
    # Mantém apenas os links dos últimos 7 dias para o arquivo não crescer indefinidamente
    agora = time.time()
    historico_limpo = {k: v for k, v in historico.items() if agora - v < 7 * 86400}
    with open(HISTORICO_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(historico_limpo, f, indent=2, ensure_ascii=False)

def coletar_novidades(historico):
    itens_novos = []
    novos_hashes = {}
    agora = time.time()

    # 1. Coletar Portais RSS
    for url in FEEDS_NOTICIAS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:12]:
                link = entry.get("link", "")
                if link and link not in historico:
                    itens_novos.append(
                        f"[Portal RSS] Título: {entry.title}\n"
                        f"Link: {link}\n"
                        f"Resumo: {entry.get('summary', '')[:300]}\n"
                    )
                    novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro RSS {url}: {e}")

    # 2. Coletar YouTube
    for url in FEEDS_YOUTUBE:
        try:
            feed = feedparser.parse(url)
            canal_nome = feed.feed.get("title", "YouTube")
            for entry in feed.entries[:6]:
                link = entry.get("link", "")
                if link and link not in historico:
                    itens_novos.append(
                        f"[YouTube - {canal_nome}] Título: {entry.title}\n"
                        f"Link: {link}\n"
                    )
                    novos_hashes[link] = agora
        except Exception as e:
            print(f"Erro YouTube {url}: {e}")

    # 3. Coletar Telegram
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for canal in CANAIS_TELEGRAM:
        try:
            url = f"https://t.me/s/{canal}"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                mensagens = soup.find_all("div", class_="tgme_widget_message_text")
                for msg in mensagens[-8:]:
                    texto_limpo = msg.get_text(separator=" ", strip=True)
                    if texto_limpo:
                        # Cria um identificador único para o texto da mensagem
                        msg_hash = hashlib.md5(texto_limpo.encode("utf-8")).hexdigest()
                        if msg_hash not in historico:
                            itens_novos.append(f"[Telegram @{canal}]: {texto_limpo[:400]}")
                            novos_hashes[msg_hash] = agora
        except Exception as e:
            print(f"Erro Telegram @{canal}: {e}")

    return itens_novos, novos_hashes

def obter_modelo_valido():
    try:
        modelos = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        for m in modelos:
            if "flash" in m.lower():
                return m
        if modelos:
            return modelos[0]
    except Exception as e:
        print(f"Aviso ao listar modelos: {e}")
    return "gemini-1.5-flash-latest"

def analisar_com_ia(conteudo, modo):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    genai.configure(api_key=api_key)
    
    nome_modelo = obter_modelo_valido()
    model = genai.GenerativeModel(nome_modelo)
    
    if modo == "cupons":
        prompt = (
            "Você é um especialista em promoções e cupons para concursos públicos (Gran, Estratégia, Direção, etc).\n"
            "Analise as seguintes publicações INÉDITAS e extraia novos cupons, promoções e ofertas de assinatura ativas.\n"
            "Formate por instituição com código do cupom, desconto e o link direto.\n\n"
            f"Conteúdo:\n{conteudo}"
        )
    else:
        prompt = (
            "Você é um jornalista analista sênior de concursos públicos no Brasil.\n"
            "Analise as matérias e avisos INÉDITOS abaixo e filtre as 8 a 15 NOTÍCIAS MAIS QUENTES.\n\n"
            "CRITÉRIOS DE PRIORIZAÇÃO:\n"
            "1. Concursos Nacionais: CNU, INSS, Caixa, Banco do Brasil, Correios, PF, PRF.\n"
            "2. Área Fiscal: Receita Federal, SEFAZs e ISSs (capitais/grandes municípios).\n"
            "3. Área de Controle/Gestão: TCU, CGU, TCEs, CGEs, carreiras de planejamento.\n"
            "4. Grandes Tribunais: STJ, TSE, TRFs, TJs e TRTs.\n\n"
            "FORMATO DE CADA ITEM:\n"
            "📌 **[Nome do Órgão / Concurso] — [Status: Edital / Banca / Comissão / Autorizado / Previsão]**\n"
            "- **Destaques:** Vagas, remuneração, prazos ou novidades cruciais.\n"
            "- **Fonte / Link:** [URL do artigo, vídeo ou mensagem]\n\n"
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
    print(f"Iniciando coleta anti-repetição - Modo: {modo}")
    
    historico = carregar_historico()
    itens_novos, novos_hashes = coletar_novidades(historico)
    
    if itens_novos:
        print(f"Encontrados {len(itens_novos)} itens inéditos. Analisando com IA...")
        dados_brutos = "\n---\n".join(itens_novos)
        relatorio = analisar_com_ia(dados_brutos, modo)
        
        titulo = "🎟️ Radar de Cupons de Concursos (Novidades)" if modo == "cupons" else "🔥 Radar Concursos: Notícias Inéditas e Editais"
        enviar_email(titulo, relatorio)
        
        # Atualiza e salva o histórico apenas se o envio deu certo
        historico.update(novos_hashes)
        salvar_historico(historico)
    else:
        print("Nenhuma notícia ou link inédito encontrado nas fontes desde a última verificação. E-mail poupado.")
