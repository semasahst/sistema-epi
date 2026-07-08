import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import base64
import io

# Importações para a geração do PDF da Ficha de EPI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuração global da página do Streamlit
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DE ACESSO AO REPOSITÓRIO (GITHUB)
# ==============================================================================
GITHUB_USER = "semasahst"  
GITHUB_REPO = "sistema-epi"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")

URL_RESPOSTAS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/respostas.csv"
URL_FUNCIONARIOS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/funcionarios.csv"
URL_EPIS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/epis.csv"

# ==============================================================================
# CARREGAMENTO DOS DADOS COM TRATAMENTO DE ERROS
# ==============================================================================
@st.cache_data(ttl=2)
def buscar_dados_planilhas():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except:
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = buscar_dados_planilhas()

# ==============================================================================
# FUNÇÃO MASTER DE GRAVAÇÃO UNIFICADA 
# ==============================================================================
def salvar_lote_no_github(novas_linhas_lista):
    if not GITHUB_TOKEN:
        st.error("❌ Erro: GITHUB_TOKEN não configurado nas Secrets.")
        return False
        
    url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    req_get = requests.get(url_api, headers=headers)
    if req_get.status_code == 200:
        dados_repo = req_get.json()
        sha_arquivo = dados_repo['sha']
        conteudo_antigo = base64.b64decode(dados_repo['content']).decode('utf-8')
        df_atual = pd.read_csv(io.StringIO(conteudo_antigo), header=None, dtype=str)
    else:
        try:
            df_atual = pd.read_csv(URL_RESPOSTAS, header=None, dtype=str)
            sha_arquivo = ""
        except:
            return False

    df_novas = pd.DataFrame(novas_linhas_lista)
    df_final = pd.concat([df_atual, df_novas], ignore_index=True)
    
    csv_string = df_final.to_csv(index=False, header=False)
    conteudo_base64 = base64.b64encode(csv_string.encode('utf-8')).decode('utf-8')
    
    payload = {
        "message": f"Atualização em lote: {len(novas_linhas_lista)} registros",
        "content": conteudo_base64,
        "sha": sha_arquivo
    }
    
    req_put = requests.put(url_api, headers=headers, json=payload)
    return req_put.status_code in [200, 201]

# ==============================================================================
# FUNÇÃO PARA GRAVARE EDITIONS/BAIXAS DE ASSINATURA
# ==============================================================================
def atualizar_csv_completo(df_novo):
    url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    req_get = requests.get(url_api, headers=headers)
    if req_get.status_code == 200:
        sha_arquivo = req_get.json()['sha']
        csv_string = df_novo.to_csv(index=False, header=False)
        conteudo_base64 = base64.b64encode(csv_string.encode('utf-8')).decode('utf-8')
        payload = {"message": "Baixa em assinaturas pendentes", "content": conteudo_base64, "sha": sha_arquivo}
        req_put = requests.put(url_api, headers=headers, json=payload)
        return req_put.status_code in [200, 201]
    return False

# ==============================================================================
# CONSTRUÇÃO DA BASE COMPLETA (HISTÓRICO AUDITÁVEL)
# ==============================================================================
def construir_base_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, header=None, dtype=str).dropna(how='all')
    except:
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    linhas_processadas = []
    hoje = pd.to_datetime(datetime.now().date())
    
    mapa_validades = {}
    mapa_ca = {}
    if not df_epis.empty:
        mapa_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
        mapa_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    for idx, row in df_hist.iterrows():
        total_cols = len(row)
        if total_cols < 2:
            continue
            
        nome_epi = str(row.iloc[0]).strip() if total_cols < 6 else str(row.iloc[1]).strip()
        nome_func = str(row.iloc[4]).strip() if total_cols >= 5 else (str(row.iloc[1]).strip() if total_cols >= 2 else "")
        raw_data_entrega = str(row.iloc[5]).strip() if total_cols >= 6 else (str(row.iloc[2]).strip() if total_cols >= 3 else "PENDENTE")
        
        if not nome_func or nome_func.lower() == 'nan' or nome_func == '':
            continue

        if "PENDENTE" in raw_data_entrega.upper():
            status_assinatura = "Pendente"
            raw_data_entrega_limpa = datetime.now().strftime("%d/%m/%Y")
        else:
            status_assinatura = "Assinado"
            raw_data_entrega_limpa = raw_data_entrega
            
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega_limpa, errors='coerce', dayfirst=True)
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_data_entrega_limpa, errors='coerce')
            if pd.isnull(dt_entrega_parsed):
                dt_entrega_parsed = hoje
            
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
        dias_validade = mapa_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        status_validade = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        re_vinculado = "N/A"
        departamento = "Não Informado"
        if not df_func.empty:
            f_match = df_func[df_func.iloc[:, 1].astype(str).str.strip().str.upper() == nome_func.upper()]
            if not f_match.empty:
                re_vinculado = str(f_match.iloc[0, 0]).split('.')[0].strip()
                departamento = str(f_match.iloc[0, 2]).strip()
        
        linhas_processadas.append({
            "INDEX_ORIGINAL": idx,
            "RE": re_vinculado,
            "Funcionário": nome_func, 
            "Departamento": departamento,
            "EPI": nome_epi, 
            "CA": mapa_ca.get(nome_epi, "N/A"), 
            "Qtd": 1,
            "Data Entrega": dt_entrega_parsed, 
            "Data Vencimento": dt_vencimento,
            "Dias Restantes": dias_restantes, 
            "Status": status_validade, 
            "Assinatura": status_assinatura
        })
        
    return pd.DataFrame(linhas_processadas) if linhas_processadas else pd.DataFrame()

# Definição Global da Base do Sistema
df_base_completa = construir_base_alertas()

# ==============================================================================
# FUNÇÃO AUXILIAR: GERADOR DE PDF DA FICHA DE EPI (NORMA NR-6)
# ==============================================================================
def gerar_pdf_ficha(re_func, nome_func, depto_func, df_itens):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    style_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], alignment=1, fontSize=16, spaceAfter=15)
    style_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=10, leading=14)
    style_termo = ParagraphStyle('Termo', parent=styles['Normal'], fontSize=8, leading=11, alignment=4)
    style_auditoria = ParagraphStyle('Auditoria', parent=styles['Normal'], alignment=1, fontSize=9, textColor=colors.HexColor('#222222'), spaceBefore=20)
    
    story.append(Paragraph("<b>SEMASA - SERVIÇO MUNICIPAL DE SANEAMENTO AMBIENTAL</b>", style_titulo))
    story.append(Paragraph("<b>FICHA DE REGISTRO DE ENTREGA DE EPIs (NR-6)</b>", style_titulo))
    story.append(Spacer(1, 10))
    
    dados_colaborador = f"""
    <b>Colaborador:</b> {nome_func} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>RE:</b> {re_func}<br/>
    <b>Departamento / Setor:</b> {depto_func} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Data de Emissão da Ficha:</b> {datetime.now().strftime('%d/%m/%Y')}
    """
    story.append(Paragraph(dados_colaborador, style_texto))
    story.append(Spacer(1, 15))
    
    termo_legal = """
    Declaro que recebi da SEMASA, gratuitamente, os Equipamentos de Proteção Individual (EPIs) constantes nesta ficha, 
    adequados ao risco das minhas atividades. Comprometo-me a utilizá-los corretamente durante as jornadas de trabalho, 
    zelar pela sua guarda e conservação, e comunicar imediatamente ao setor de Segurança do Trabalho qualquer alteração 
    que o torne impróprio para o uso, estando ciente de que o descumprimento desta norma constitui ato faltoso, conforme 
    artigo 158 da CLT e a Norma Regulamentadora NR-6.
    """
    story.append(Paragraph(f"<i>{termo_legal}</i>", style_termo))
    story.append(Spacer(1, 15))
    
    tabela_dados = [["EPI / Descrição", "C.A.", "Qtd", "Data Entrega", "Forma de Assinatura"]]
    for _, row in df_itens.iterrows():
        dt_str = row['Data Entrega'].strftime('%d/%m/%Y') if isinstance(row['Data Entrega'], datetime) else str(row['Data Entrega'])
        tipo_ass = "Digital (NFC)" if row['Assinatura'] == "Assinado" else "⚠️ PENDENTE (Assinar à caneta)"
        tabela_dados.append([row['EPI'], row['CA'], str(row['Qtd']), dt_str, tipo_ass])
        
    t = Table(tabela_dados, colWidths=[220, 60, 40, 80, 140])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
    ]))
