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
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Dicionário de e-mails para os gestores (ajuste os nomes dos Departamentos e e-mails exatamente como constam no seu sistema)
MAPA_EMAILS_GESTORES = {
    "DMO": "adonini@semasa.sp.gov.br",
    "GRH": "ACampos1@semasa.sp.gov.br",
    "DGA": "adonini@semasa.sp.gov.br",
    "DSAA": "ACampos1@semasa.sp.gov.br",
    "DRS": "adonini@semasa.sp.gov.br", 
    "HST_GERAL": ["adonini@semasa.sp.gov.br", "ACampos1@semasa.sp.gov.br"]  # E-mail do HST que recebe o consolidado completo
}
def enviar_notificacao_email(destinatario, assunto, corpo_html):
    """Função genérica de disparo de e-mail com suporte a destinatário único ou lista."""
    remetente = st.secrets.get("EMAIL_REMETENTE", "")
    senha = st.secrets.get("EMAIL_SENHA", "")
    smtp_server = st.secrets.get("EMAIL_SMTP", "smtp.gmail.com")
    porta = int(st.secrets.get("EMAIL_PORTA", 587))
    
    if not remetente or not senha:
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From'] = remetente
        
        # Tratamento inteligente: Se for uma lista de e-mails, junta com vírgula para o cabeçalho
        if isinstance(destinatario, list):
            msg['To'] = ", ".join(destinatario)
            lista_envio = destinatario
        else:
            msg['To'] = destinatario
            lista_envio = [destinatario]
        
        part = MIMEText(corpo_html, 'html')
        msg.attach(part)
        
        server = smtplib.SMTP(smtp_server, porta)
        server.starttls()
        server.login(remetente, senha)
        
        # O servidor SMTP precisa receber a lista exata de quem vai receber o e-mail
        server.sendmail(remetente, lista_envio, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From'] = remetente
        msg['To'] = destinatario
        
        part = MIMEText(corpo_html, 'html')
        msg.attach(part)
        
        server = smtplib.SMTP(smtp_server, porta)
        server.starttls()
        server.login(remetente, senha)
        server.sendmail(remetente, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False

def processar_e_enviar_alertas_mensais(forcar=False):
    """Varre o sistema e envia e-mails customizados aos gestores e ao HST."""
    hoje = datetime.now()
    
    # Validação de Primeiro Dia Útil do Mês (Caso não seja disparo forçado manual)
    if not forcar:
        # Se for sábado (5) ou domingo (6), não roda
        if hoje.weekday() >= 5:
            return "Não executado: Fim de semana."
        # Se for dia 1 e dia de semana, roda. Se for dia 2 ou 3 e segunda-feira, significa que foi o primeiro dia útil.
        if hoje.day == 1:
            pass
        elif hoje.day == 2 and hoje.weekday() == 0: # Segunda-feira pós dia 1 domingo
            pass
        elif hoje.day == 3 and hoje.weekday() == 0: # Segunda-feira pós dia 1 sábado
            pass
        else:
            return "Não executado: Hoje não é o primeiro dia útil do mês."

    # Processa os dados de alertas baseados na última entrega ativa
    df_alertas = construir_base_alertas()
    if df_alertas.empty:
        return "Sem alertas para processar."
        
    df_alertas = df_alertas.sort_values(by="Data Entrega", ascending=True)
    df_alertas = df_alertas.drop_duplicates(subset=["Funcionário", "EPI"], keep="last")
    
    # Filtra apenas o que está Vencido ou Crítico
    df_problemas = df_alertas[df_alertas['Status'].str.contains("🔴|🟡")]
    
    if df_problemas.empty:
        return "Sucesso: Nenhum EPI vencido ou crítico encontrado este mês!"

    # 1. ENVIAR CONSOLIDADO GERAL PARA A EQUIPE DO HST
    email_hst = MAPA_EMAILS_GESTORES.get("HST_GERAL", "")
    if email_hst:
        linhas_html = "".join([f"<tr><td>{r['RE']}</td><td>{r['Funcionário']}</td><td>{r['Departamento']}</td><td>{r['EPI']}</td><td>{r['Status']}</td></tr>" for _, r in df_problemas.iterrows()])
        corpo_hst = f"""
        <h3>📊 Relatório Mensal Consolidado de EPIs - HST SEMASA</h3>
        <p>Prezada equipe do HST, segue abaixo a listagem de todas as inconformidades ativas no sistema neste momento:</p>
        <table border='1' cellpadding='5' style='border-collapse: collapse;'>
            <tr style='background-color: #333; color: white;'><th>RE</th><th>Funcionário</th><th>Departamento</th><th>EPI</th><th>Status</th></tr>
            {linhas_html}
        </table>
        <br><p>Acesse o sistema para mais detalhes.</p>
        """
        enviar_notificacao_email(email_hst, "📊 HST: Consolidado Geral de EPIs Vencidos/Críticos", corpo_hst)

    # 2. ENVIAR ALERTAS INDIVIDUAIS POR ÁREA PARA CADA GESTOR
    departamentos = df_problemas['Departamento'].unique()
    for depto in departamentos:
        email_gestor = MAPA_EMAILS_GESTORES.get(depto, "")
        if email_gestor:
            df_depto = df_problemas[df_problemas['Departamento'] == depto]
            linhas_depto_html = "".join([f"<tr><td>{r['RE']}</td><td>{r['Funcionário']}</td><td>{r['EPI']}</td><td style='color:red;'>{r['Status']}</td></tr>" for _, r in df_depto.iterrows()])
            
            corpo_gestor = f"""
            <h3>⚠️ Alerta de Segurança do Trabalho: EPIs Vencidos em sua Área ({depto})</h3>
            <p>Olá Gestor, identificamos colaboradores sob sua gestão com EPIs vencidos ou em estado crítico de validade. Providencie a substituição imediata:</p>
            <table border='1' cellpadding='5' style='border-collapse: collapse;'>
                <tr style='background-color: #0056b3; color: white;'><th>RE</th><th>Funcionário</th><th>Equipamento (EPI)</th><th>Situação</th></tr>
                {linhas_depto_html}
            </table>
            <br><p><i>Este é um disparo automático mensal emitido em conformidade com a NR-6.</i></p>
            """
            enviar_notificacao_email(email_gestor, f"⚠️ Alerta Mensal: Regularização de EPIs - Setor {depto}", corpo_gestor)
            
    return "E-mails enviados com sucesso para as respectivas áreas e HST!"

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
Declaramos para os devidos fins legais que recebi do SEMASA os Equipamentos de Proteção Individual (EPIs)
relacionados na listagem abaixo, adequados ao risco das minhas funções operacionais. Comprometo-me ao uso
obrigatório, guarda, zelo e higienização dos mesmos. Cláusula de Validação Biométrica Corporativa: Fica
expressamente eleito e acordado entre as partes que a aposição física do crachá funcional NFC com código UID
unívoco e individualizado do trabalhador atua como assinatura eletrônica avançada, plenamente íntegra e com total
validade de prova pericial trabalhista nos termos do Artigo 158 da CLT.
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
    story.append(t)
    story.append(Spacer(1, 35))
    
    story.append(Paragraph("____________________________________________________", style_titulo))
    story.append(Paragraph(f"Assinatura do Colaborador: {nome_func}", ParagraphStyle('Sub', parent=styles['Normal'], alignment=1, fontSize=10)))
    
    story.append(Paragraph("<b>VALIDADO EM AUDITORIA VIA ASSINATURA ELETRÔNICA DE CRACHÁ NFC</b>", style_auditoria))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==============================================================================
# MENU LATERAL DO SISTEMA (ALINHADO E COMPLETO)
# ==============================================================================
menu = st.sidebar.selectbox(
    "Escolha a Visão:", 
    [
        "📝 Lançar Novos EPIs", 
        "✍️ Coletar Assinaturas Pendentes", 
        "📄 Gerar Ficha de EPI (Impressão)", 
        "📊 Dashboard de Gestão", 
        "⚠️ EPIs Vencidos/A Vencer",
        "📧 Disparador de Alertas (HST)"
    ]
)

# ==============================================================================
# EXECUÇÃO DAS VISÕES DO SISTEMA (ESTRUTURA CORRIGIDA)
# ==============================================================================
if menu == "📝 Lançar Novos EPIs":
    st.header("📝 Lançamento e Entrega de EPIs")
    st.markdown("Registre novos fornecimentos de Equipamentos de Proteção Individual em conformidade com a NR-6.")
    
    with st.form("form_lancamento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            re_novo = st.text_input("RE do Colaborador (Apenas números):")
            nome_sugerido = ""
            if re_novo and 'df_func' in locals() and not df_func.empty:
                linhas_f = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_novo).strip()]
                if not linhas_f.empty:
                    nome_sugerido = str(linhas_f.iloc[0, 1]).strip()
            
            nome_novo = st.text_input("Nome Completo do Funcionário:", value=nome_sugerido)
            depto_novo = st.selectbox("Departamento / Setor:", ["Administrativo", "Logística", "Manutenção", "Operações", "Outros"])
        
        with col2:
            epi_novo = st.selectbox("Equipamento (EPI):", ["Avental em Kevlar", "Botina de Segurança", "Capa de Chuva", "Capacete", "Luva Agentes Mecânicos", "Luva Isolante", "Protetor Auricular Plug", "Sapato de Segurança"])
            ca_novo = st.text_input("Número do C.A. (Certificado de Aprovação):")
            qtd_nova = st.number_input("Quantidade Entregue:", min_value=1, value=1, step=1)
            
        data_entrega_nova = st.date_input("Data de Entrega do EPI:", value=datetime.today())
        
        st.markdown("---")
        botao_salvar = st.form_submit_button("💾 Registrar Entrega no Banco de Dados", use_container_width=True)
        
        if botao_salvar:
            if not re_novo or not nome_novo or not ca_novo:
                st.error("❌ Por favor, preencha todos os campos obrigatórios (RE, Nome e CA).")
            else:
                nova_linha = {
                    "Carimbo de data/hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                    "RE": re_novo.strip(),
                    "Funcionário": nome_novo.strip(),
                    "EPI": epi_novo,
                    "Data": data_entrega_nova.strftime("%Y-%m-%d"),
                    "Quantidade": qtd_nova,
                    "CA": ca_novo.strip(),
                    "Assinatura": "Pendente",
                    "Departamento": depto_novo
                }
                try:
                    df_temporario = pd.DataFrame([nova_linha])
                    if os.path.exists("respostas.csv"):
                        df_temporario.to_csv("respostas.csv", mode='a', header=False, index=False, encoding='utf-8')
                    else:
                        df_temporario.to_csv("respostas.csv", index=False, encoding='utf-8')
                    st.success(f"🎉 Registro de {epi_novo} para {nome_novo} salvo com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar arquivo físico: {e}")

elif menu == "✍️ Coletar Assinaturas Pendentes":
    st.header("✍️ Registro de Assinatura Eletrônica via Crachá NFC")
    st.markdown("Aproxime o cartão/crachá físico do colaborador no leitor USB conectado para assinar digitalmente.")
    
    uid_leitor = st.text_input("Aguardando leitura do Sensor NFC (Posicione o Crachá):", key="nfc_uid_input")
    
    if uid_leitor:
        if 'df_func' in locals() and not df_func.empty:
            df_encontrado = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(uid_leitor).strip()]
            
            if not df_encontrado.empty:
                re_func = str(df_encontrado.iloc[0, 0]).strip()
                nome_func = str(df_encontrado.iloc[0, 1]).strip()
                st.info(f"👤 Crachá Identificado: **{nome_func} (RE: {re_func})**")
                
                if not df_base_completa.empty:
                    pendencias = df_base_completa[
                        (df_base_completa["RE"].astype(str).str.strip() == re_func) & 
                        (df_base_completa["Assinatura"] == "Pendente")
                    ]
                    
                    if not pendencias.empty:
                        st.warning(f"Existe(m) {len(pendencias)} EPI(s) aguardando assinatura jurídica.")
                        st.dataframe(pendencias[["EPI", "CA", "Quantidade", "Data Entrega"]], use_container_width=True)
                        
                        if st.button("✍️ Confirmar Assinatura Digital", use_container_width=True, type="primary"):
                            try:
                                df_csv_fisico = pd.read_csv("respostas.csv", encoding='utf-8')
                                mask = (df_csv_fisico["RE"].astype(str).str.strip() == re_func) & (df_csv_fisico["Assinatura"] == "Pendente")
                                df_csv_fisico.loc[mask, "Assinatura"] = f"Assinado digitalmente em {datetime.now().strftime('%d/%m/%Y')}"
                                df_csv_fisico.to_csv("respostas.csv", index=False, encoding='utf-8')
                                st.success("🎉 Documento assinado eletronicamente com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao atualizar base de assinaturas: {e}")
                    else:
                        st.success("🟢 Tudo certo! Este colaborador não possui entregas pendentes.")
            else:
                st.error("❌ Código de crachá ou RE não localizado na tabela.")

elif menu == "📄 Gerar Ficha de EPI (Impressão)":
    st.header("📄 Ficha de Registro de EPIs em PDF (Norma Regulamentadora NR-6)")
    st.markdown("Digite o RE para consolidar todo o histórico do trabalhador e gerar a ficha auditável em PDF.")
    
    re_busca = st.text_input("Digite o RE do Colaborador:", key="re_busca_ficha")
    if re_busca:
        if not df_base_completa.empty:
            df_re = df_base_completa[df_base_completa["RE"].astype(str).str.strip() == str(re_busca).strip()]
            if not df_re.empty:
                nome_func = df_re.iloc[0]["Funcionário"]
                depto_func = df_re.iloc[0]["Departamento"]
                st.success(f"👤 Funcionário localizado: {nome_func} | Setor: {depto_func}")
                
                st.markdown("### Itens que constarão no documento:")
                df_exib = df_re.copy()
                df_exib["Data Entrega"] = df_exib["Data Entrega"].dt.strftime("%d/%m/%Y")
                st.dataframe(df_exib[["EPI", "CA", "Quantidade", "Data Entrega", "Assinatura"]], use_container_width=True)
                st.button("📥 Baixar Ficha de EPI Oficial (PDF)", key="btn_pdf_ficha")
            else:
                st.error("❌ Nenhum registro de entrega foi localizado para este RE no banco de dados.")
        else:
            st.warning("Base de dados vazia.")

# ==============================================================================
# BLOCO CENTRAL DE DADOS E RELATÓRIOS (DASHBOARD, VELEDO, E-MAIL)
# ==============================================================================
else:
    if df_base_completa.empty:
        st.warning("Aguardando a sincronização dos dados...")
    else:
        df_alertas_filtrado = df_base_completa.sort_values(by="Data Entrega", ascending=True)
        df_alertas_filtrado = df_alertas_filtrado.drop_duplicates(subset=["Funcionário", "EPI"], keep="last")

        if 'df_func' in locals() and not df_func.empty and len(df_func.columns) > 3:
            mapa_cargos = {str(row.iloc[1]).strip().upper(): str(row.iloc[3]).strip() for _, row in df_func.iterrows()}
            df_alertas_filtrado['Cargo'] = df_alertas_filtrado['Funcionário'].str.strip().str.upper().map(mapa_cargos).fillna("Não Informado")
        else:
            df_alertas_filtrado['Cargo'] = "Não Informado"

        # Painel de Filtros Laterais
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🔍 Filtros do Painel")
        
        lista_deptos = sorted(df_alertas_filtrado['Departamento'].dropna().unique().tolist())
        deptos_selecionados = st.sidebar.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
        
        lista_cargos = sorted(df_alertas_filtrado['Cargo'].dropna().unique().tolist())
        cargos_selecionados = st.sidebar.multiselect("Filtrar por Cargo:", options=lista_cargos, default=lista_cargos)
        
        lista_status = sorted(df_alertas_filtrado['Status'].dropna().unique().tolist())
        status_selecionados = st.sidebar.multiselect("Filtrar por Status:", options=lista_status, default=lista_status)
        
        df_painel_filtrado = df_alertas_filtrado[
            (df_alertas_filtrado['Departamento'].isin(deptos_selecionados)) & 
            (df_alertas_filtrado['Cargo'].isin(cargos_selecionados)) & 
            (df_alertas_filtrado['Status'].isin(status_selecionados))
        ]

        if menu == "📊 Dashboard de Gestão":
            st.header("📊 Painel de Indicadores Estratégicos")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("EPIs Ativos Monitorados", len(df_painel_filtrado))
            c2.metric("🟢 Itens Regulares", len(df_painel_filtrado[df_painel_filtrado['Status'] == "🟢 Regular"]))
            c3.metric("🟡 Alertas Críticos", len(df_painel_filtrado[df_painel_filtrado['Status'].str.contains("🟡")]))
            c4.metric("🔴 Total Vencidos", len(df_painel_filtrado[df_painel_filtrado['Status'] == "🔴 VENCIDO"]))
            
            st.markdown("---")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("#### 📈 Situação Geral de Validade")
                if not df_painel_filtrado.empty:
                    df_status_grafico = df_painel_filtrado.groupby('Status').size().reset_index(name='Quantidade')
                    st.bar_chart(data=df_status_grafico, x='Status', y='Quantidade', color='Status')
            with col_g2:
                st.markdown("#### 🛡️ Modelos de EPIs Mais Entregues")
                if not df_painel_filtrado.empty:
                    df_epi_grafico = df_painel_filtrado.groupby('EPI').size().reset_index(name='Quantidade').sort_values(by='Quantidade', ascending=False)
                    st.bar_chart(data=df_epi_grafico, x='EPI', y='Quantidade')

            st.markdown("---")
            df_export_clean = df_painel_filtrado[["RE", "Funcionário", "Departamento", "Cargo", "EPI", "CA", "Data Entrega", "Data Vencimento", "Dias Restantes", "Status", "Assinatura"]].copy()
            df_export_clean["Data Entrega"] = df_export_clean["Data Entrega"].dt.strftime("%d/%m/%Y")
            df_export_clean["Data Vencimento"] = df_export_clean["Data Vencimento"].dt.strftime("%d/%m/%Y")
            
            csv_dados = df_export_clean.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Baixar Relatório de Indicadores (CSV)", data=csv_dados, file_name="Relatorio_Indicadores_EPI.csv", mime="text/csv", use_container_width=True)

        elif menu == "⚠️ EPIs Vencidos/A Vencer":
            st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
            aba_val, aba_ass = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
            
            with aba_val:
                if not df_painel_filtrado.empty:
                    df_exib_val = df_painel_filtrado.copy()
                    df_exib_val["Data Entrega"] = df_exib_val["Data Entrega"].dt.strftime("%d/%m/%Y")
                    df_exib_val["Data Vencimento"] = df_exib_val["Data Vencimento"].dt.strftime("%d/%m/%Y")
                    st.dataframe(df_exib_val[["RE", "Funcionário", "Departamento", "Cargo", "EPI", "CA", "Data Entrega", "Data Vencimento", "Dias Restantes", "Status"]].sort_values(by="Dias Restantes"), use_container_width=True)
            
            with aba_ass:
                df_exib_ass = df_painel_filtrado[df_painel_filtrado['Assinatura'] == "Pendente"].copy()
                if not df_exib_ass.empty:
                    df_exib_ass["Data Entrega"] = df_exib_ass["Data Entrega"].dt.strftime("%d/%m/%Y")
                    st.dataframe(df_exib_ass[["RE", "Funcionário", "Departamento", "Cargo", "EPI", "Data Entrega", "Status"]], use_container_width=True)
                else:
                    st.success("🎉 Nenhuma assinatura pendente encontrada!")

        elif menu == "📧 Disparador de Alertas (HST)":
            st.header("📧 Central de Notificações via E-mail")
            st.markdown("Gerencie as rotinas automatizadas de envio de alertas da NR-6.")
            
            if st.button("🚀 Disparar E-mails de Alerta Agora (Forçar Envio)", use_container_width=True):
                with st.spinner("Enviando e-mails corporativos..."):
                    resultado = processar_e_enviar_alertas_mensais(forcar=True)
                    st.success(resultado)

# ==============================================================================
# DISPARO INVISÍVEL VIA WEBHOOK AUTOMÁTICO (CRON-JOB)
# ==============================================================================
if st.query_params.get("executar_alerta") == "1":
    processar_e_enviar_alertas_mensais(forcar=False)
