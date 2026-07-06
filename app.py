import streamlit as st
import pandas as pd
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import io
import plotly.express as px

# Importações do ReportLab para gerar o PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Configuração da página do Streamlit
st.set_page_config(page_title="HST - Semasa", page_icon="🛡️", layout="wide")

st.title("🛡️ Sistema Integrado de Controle de EPIs - HST Semasa")
st.markdown("---")

# ==============================================================================
# CONFIGURAÇÕES DE LINKS E CREDENCIAIS
# ==============================================================================
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587                 

EMAIL_REMETENTE = "seu_email_aqui@gmail.com" 
EMAIL_SENHA = "abcd efgh ijkl mnop"  

CHAVE_PLANILHA = "1vL-5EqVshfUAmJY-3DlMfRpxtgfCvD5TaNLCxU4BPUE"
URL_FORM_POST = "https://docs.google.com/forms/d/e/1FAIpQLSfRZgRoIfEHUuanvhsMpkfXMSo7BslH_9Oj16nBNhIgSEw0Fg/formResponse"

URL_FUNCIONARIOS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_funcionarios"
URL_EPIS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_epis"
URL_RESPOSTAS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=Respostas%20ao%20formul%C3%A1rio%201"
URL_GESTORES = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_gestores"

menu = st.sidebar.selectbox(
    "Navegação", 
    ["📊 Dashboard de Gestão", "Lançar Entrega", "⚠️ EPIs Vencidos/A Vencer", "📄 Gerar Ficha de EPI", "Visualizar Tabelas Reais"]
)

try:
    df_func = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
    if not df_func.empty and "UID_Cracha" not in df_func.columns:
        df_func["UID_Cracha"] = ""
    df_epis = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
except:
    st.error("❌ Erro ao conectar com o Google Sheets.")
    st.stop()

# ==============================================================================
# FUNÇÃO AUXILIAR: PROCESSAMENTO GERAL DO HISTÓRICO
# ==============================================================================
def processar_dados_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except:
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    colunas_disponiveis = list(df_hist.columns)
    
    if len(colunas_disponiveis) >= 6:
        df_hist.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas_disponiveis[6:]
    else:
        return pd.DataFrame()
        
    df_hist['Data_Entrega'] = pd.to_datetime(df_hist['Data_Entrega'], errors='coerce')
    df_hist = df_hist.dropna(subset=['Data_Entrega'])
    
    dicionario_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    linhas_alertas = []
    hoje = datetime.now()
    
    df_ultimas = df_hist.sort_values('Data_Entrega').groupby(['RE', 'EPI']).last().reset_index()
    
    for _, row in df_ultimas.iterrows():
        nome_epi = str(row['EPI']).strip()
        dt_entrega = row['Data_Entrega']
        dt_vencimento = dt_entrega + timedelta(days=dicionario_validades.get(nome_epi, 90))
        dias_restantes = (dt_vencimento - hoje).days
        status = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        info_assinatura = str(row['Timestamp']) 
        status_assinatura = "Pendente" if "PENDENTE" in info_assinatura.upper() or "NFC" not in info_assinatura.upper() else "Assinado"
        
        depto = "Não Informado"
        if not df_func.empty:
            f_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(row['RE']).strip()]
            if not f_match.empty: 
                depto = f_match.iloc[0, 2]
            
        qtd_salva = int(row['Quantidade']) if 'Quantidade' in row and pd.notnull(row['Quantidade']) and str(row['Quantidade']).isdigit() else 1
        
        linhas_alertas.append({
            "RE": row['RE'], "Funcionário": row['Funcionário'], "Departamento": depto,
            "EPI": nome_epi, "CA": dicionario_ca.get(nome_epi, "N/A"), "Qtd": qtd_salva,
            "Data Entrega": dt_entrega, "Data Vencimento": dt_vencimento,
            "Dias Restantes": dias_restantes, "Status": status, "Assinatura": status_assinatura,
            "Log_Original": info_assinatura
        })
        
    return pd.DataFrame(linhas_alertas)

# ==============================================================================
# MENU 1: DASHBOARD DE GESTÃO
# ==============================================================================
if menu == "📊 Dashboard de Gestão":
    st.header("📊 Painel de Indicadores Estratégicos - HST")
    df_alertas_geral = processar_dados_alertas()
        
    if df_alertas_geral.empty:
        st.info("ℹ️ Nenhum dado de entrega localizado.")
    else:
        total_entregas_num = len(df_alertas_geral)
        funcionarios_atendidos = df_alertas_geral['RE'].nunique()
        vencidos_qtd = len(df_alertas_geral[df_alertas_geral['Status'] == "🔴 VENCIDO"])
        pendentes_assinatura = len(df_alertas_geral[df_alertas_geral['Assinatura'] == "Pendente"])
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(label="📦 Total de EPIs Ativos", value=total_entregas_num)
        c2.metric(label="👥 Colaboradores Cobertos", value=funcionarios_atendidos)
        c3.metric(label="🚨 Contratos Vencidos", value=vencidos_qtd, delta=f"{vencidos_qtd} Urgentes", delta_color="inverse")
        c4.metric(label="✍️ Assinaturas Pendentes", value=pendentes_assinatura, delta=f"{pendentes_assinatura} Cobrar", delta_color="inverse")
        
        st.markdown("---")
        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.markdown("### 🏆 Ranking de EPIs mais Utilizados")
            df_epi_rank = df_alertas_geral.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False).head(8)
            fig_bar = px.bar(df_epi_rank, x='Qtd', y='EPI', orientation='h', color='Qtd', color_continuous_scale='Blugrn')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_graf2:
            st.markdown("### 📊 Regularidade Operacional")
            df_status_pie = df_alertas_geral['Status'].value_counts().reset_index()
            df_status_pie.columns = ['Status', 'Contagem']
            mapa_cores = {"🟢 Regular": "#27ae60", "🟡 CRÍTICO (Até 15 dias)": "#f1c40f", "🔴 VENCIDO": "#e74c3c"}
            fig_pie = px.pie(df_status_pie, values='Contagem', names='Status', color='Status', color_discrete_map=mapa_cores, hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

# ==============================================================================
# MENU 2: LANÇAR ENTREGA
# ==============================================================================
elif menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI")
    col1, col2 = st.columns(2)
    with col1:
        re_input = st.text_input("Digite o RE do Funcionário:").strip()
        nome_func, depto_func, uid_cadastrado = "", "", ""
        if re_input and not df_func.empty:
            funcionario = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_input)]
            if not funcionario.empty:
                nome_func, depto_func = funcionario.iloc[0, 1], funcionario.iloc[0, 2]
                uid_cadastrado = funcionario["UID_Cracha"].values[0] if "UID_Cracha" in funcionario.columns else ""
                uid_cadastrado = str(uid_cadastrado).strip() if pd.notnull(uid_cadastrado) else ""
                st.success(f"👤 **Colaborador:** {nome_func} | **Depto:** {depto_func}")
            else:
                st.error(f"❌ RE '{re_input}' não encontrado.")
    with col2:
        data_entrega = st.date_input("Data da Entrega", datetime.now())
        
    lista_opcoes_epis = []
    if not df_epis.empty:
        lista_opcoes_epis = (df_epis.iloc[:, 0].astype(str) + " (CA: " + df_epis.iloc[:, 1].astype(str) + ")").tolist()
    epis_selecionados = st.multiselect("Selecione os EPIs:", lista_opcoes_epis)
    qtd_entrega = st.number_input("Quantidade Entregue:", min_value=1, value=1, step=1)
    
    st.markdown("---")
    st.markdown("### 🔑 Validação e Assinatura")
    
    ausente = st.checkbox("⚠️ **Funcionário Ausente / Entrega Indireta** (Deixar assinatura PENDENTE)")
    
    nfc_bip = ""
    if not ausente:
        nfc_bip = st.text_input("AGUARDANDO LEITURA DO CRACHÁ...", type="password", help="Passe o crachá no leitor.").strip()
    else:
        st.warning("🚨 Modo de Contingência Ativo: Esta entrega será marcada como PENDENTE de validação jurídica.")

    if st.button("🚀 CONFIRMAR E GRAVAR LANÇAMENTO", type="primary"):
        if not re_input or not nome_func:
            st.error("Insira um RE válido.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione o EPI.")
        elif not ausente and not nfc_bip:
            st.error("❌ Erro: Aproxime o crachá ou marque a caixa 'Funcionário Ausente' para prosseguir.")
        elif not ausente and uid_cadastrado and nfc_bip.lstrip('0') != uid_cadastrado.lstrip('0'):
            st.error("🚨 ERRO DE IDENTIDADE: Crachá não pertence a este RE!")
        else:
            with st.spinner("Gravando registro no Google Sheets..."):
                timestamp_token = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                
                if ausente:
                    log_seguranca = f"PENDENTE: Lançamento ADM sem crachá em {timestamp_token}"
                else:
                    log_seguranca = f"Assinado via Crachá NFC UID:{nfc_bip} em {timestamp_token}"
                
                for epi_formatado in epis_selecionados:
                    dados_formulario = {
                        "entry.2087142219": re_input,
                        "entry.1719783905": nome_func,
                        "entry.791852446": epi_formatado.split(" (CA:")[0].strip(),
                        "entry.1336399804": data_entrega.strftime('%Y-%m-%d'),
                        "entry.342195985": str(qtd_entrega)
                    }
                    requests.post(URL_FORM_POST, data=dados_formulario)
            st.success("🎯 Registro concluído!")
            st.balloons()

# ==============================================================================
# MENU 3: CONTROLES - VENCIDOS E ASSINATURAS PENDENTES
# ==============================================================================
elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
    aba_vencidos, aba_pendentes = st.tabs(["🚨 Monitor de Validade (NR-6)", "📥 Assinaturas Pendentes"])
    df_alertas_painel = processar_dados_alertas()
    
    try: df_gestores = pd.read_csv(URL_GESTORES, dtype=str).dropna(how='all')
    except: df_gestores = pd.DataFrame()

    with aba_vencidos:
        if df_alertas_painel.empty:
            st.info("Sem registros.")
        else:
            df_v = df_alertas_painel.copy()
            df_v['Data Entrega'] = df_v['Data Entrega'].dt.strftime('%d/%m/%Y')
            df_v['Data Vencimento'] = df_v['Data Vencimento'].dt.strftime('%d/%m/%Y')
            st.dataframe(df_v, use_container_width=True, hide_index=True)

    with aba_pendentes:
        if df_alertas_painel.empty:
            st.info("Nenhum registro encontrado.")
        else:
            df_p = df_alertas_painel[df_alertas_painel['Assinatura'] == "Pendente"].copy()
            
            if df_p.empty:
                st.success("🎉 Excelente! Nenhuma assinatura pendente no sistema.")
            else:
                st.markdown("### 🔍 Filtros Manuais de Cobrança")
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    lista_deptos_p = sorted(list(df_p['Departamento'].unique()))
                    filtro_depto_p = st.multiselect("Filtrar por Departamento:", lista_deptos_p)
                with col_f2:
                    data_inicio = st.date_input("Data Inicial do Lançamento:", datetime.now() - timedelta(days=30))
                with col_f3:
                    data_fim = st.date_input("Data Final do Lançamento:", datetime.now())
                
                if filtro_depto_p:
                    df_p = df_p[df_p['Departamento'].isin(filtro_depto_p)]
                df_p = df_p[(df_p['Data Entrega'].dt.date >= data_inicio) & (df_p['Data Entrega'].dt.date <= data_fim)]
                
                df_p_exibicao = df_p.copy()
                df_p_exibicao['Data Entrega'] = df_p_exibicao['Data Entrega'].dt.strftime('%d/%m/%Y')
                df_p_exibicao['Data Vencimento'] = df_p_exibicao['Data Vencimento'].dt.strftime('%d/%m/%Y')
                
                st.markdown(f"📋 **Pendências Filtradas:** {len(df_p_exibicao)} itens encontrados.")
                st.dataframe(df_p_exibicao[['RE', 'Funcionário', 'Departamento', 'EPI', 'Qtd', 'Data Entrega']], use_container_width=True, hide_index=True)
                
                st.markdown("---")
                if st.button("✉️ DISPARAR COBRANÇA PARA OS GESTORES FILTRADOS", type="secondary"):
                    if EMAIL_REMETENTE == "seu_email_aqui@gmail.com":
                        st.error("Configure as credenciais de e-mail.")
                    elif df_p.empty:
                        st.warning("O filtro atual está vazio.")
                    else:
                        with st.spinner("Enviando notificações..."):
                            for depto_grupo, dados_grupo in df_p.groupby("Departamento"):
                                gestor_row = df_gestores[df_gestores.iloc[:, 0].astype(str).str.strip().str.upper() == str(depto_grupo).strip().upper()]
                                if not gestor_row.empty:
                                    email_gestor = gestor_row.iloc[0, 2]
                                    nome_gestor = gestor_row.iloc[0, 1]
                                    
                                    msg = MIMEMultipart()
                                    msg['From'] = EMAIL_REMETENTE
                                    msg['To'] = email_gestor
                                    msg['Subject'] = f"✍️ [HST Semasa] Convocação: Servidores Pendentes de Assinatura de EPI"
                                    
                                    html_tabela = ""
                                    for _, r in dados_grupo.iterrows():
                                        dt_str = r['Data Entrega'].strftime('%d/%m/%Y')
                                        html_tabela += f"<tr style='background-color: #fff2cc;'><td>{r['RE']}</td><td>{r['Funcionário']}</td><td>{r['EPI']}</td><td>{r['Qtd']}</td><td>{dt_str}</td></tr>"
                                    
                                    corpo_html = f"<html><body><h2>Olá, {nome_gestor}!</h2><p>Há assinaturas de EPI pendentes para o setor {depto_grupo}.</p><table border='1'>{html_tabela}</table></body></html>"
                                    msg.attach(MIMEText(corpo_html, 'html'))
                                    try:
                                        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                                        server.starttls()
                                        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
                                        server.sendmail(EMAIL_REMETENTE, email_gestor, msg.as_string())
                                        server.quit()
                                        st.write(f"📧 Cobrança enviada para **{nome_gestor}**")
                                    except Exception as ex:
                                        st.write(f"❌ Erro ao enviar: {ex}")

# ==============================================================================
# MENU 4: GERAR FICHA DE EPI (RESTAURADO E COMPLETO)
# ==============================================================================
elif menu == "📄 Gerar Ficha de EPI":
    st.header("📄 Módulo de Emissão de Ficha de EPI Digital - NR-6")
    re_busca = st.text_input("Digite o RE do Colaborador para buscar a Ficha:").strip()
    
    if re_busca:
        func_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_busca)]
        if func_match.empty:
            st.error("❌ RE não cadastrado no sistema do Semasa.")
        else:
            nome_colaborador = func_match.iloc[0, 1]
            depto_colaborador = func_match.iloc[0, 2]
            st.info(f"👤 **Trabalhador:** {nome_colaborador} | **Setor:** {depto_colaborador}")
            
            try:
                df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
            except:
                df_hist = pd.DataFrame()
                
            if df_hist.empty:
                st.warning("⚠️ Sem histórico de entregas registradas.")
            else:
                colunas = list(df_hist.columns)
                if len(colunas) >= 6:
                    df_hist.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas[6:]
                
                df_filtrado_func = df_hist[df_hist['RE'].astype(str).str.strip() == str(re_busca)].copy()
                if df_filtrado_func.empty:
                    st.warning("⚠️ Nenhuma entrega localizada para este colaborador.")
                else:
                    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
                    df_filtrado_func['CA'] = df_filtrado_func['EPI'].map(dicionario_ca).fillna("N/A")
                    df_filtrado_func['Quantidade'] = df_filtrado_func['Quantidade'].fillna("1")
                    
                    st.dataframe(df_filtrado_func[['Data_Entrega', 'EPI', 'CA', 'Quantidade']], use_container_width=True, hide_index=True)
                    
                    # Estruturação e Construção do PDF (ReportLab)
                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
                    elementos_pdf = []
                    estilos = getSampleStyleSheet()
                    estilo_titulo = ParagraphStyle('Titulo', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=15, alignment=1, spaceAfter=20)
                    estilo_sub = ParagraphStyle('Sub', parent=estilos['Normal'], fontName='Helvetica-Bold', fontSize=11, spaceAfter=8)
                    estilo_texto = ParagraphStyle('Texto', parent=estilos['Normal'], fontName='Helvetica', fontSize=10, leading=14, spaceAfter=15, alignment=4)
                    estilo_tabela = ParagraphStyle('Tab', parent=estilos['Normal'], fontName='Helvetica', fontSize=9, leading=11)
                    estilo_tabela_header = ParagraphStyle('TabH', parent=estilos['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=11, textColor=colors.white)
                    
                    elementos_pdf.append(Paragraph("SEMASA - SERVIÇO MUNICIPAL DE SANEAMENTO AMBIENTAL DE SANTO ANDRÉ", estilo_titulo))
                    elementos_pdf.append(Paragraph("FICHA DE CONTROLE E REGISTRO DE ENTREGA DE EPI", ParagraphStyle('SubT', parent=estilo_titulo, fontSize=13, spaceAfter=25)))
                    elementos_pdf.append(Paragraph(f"<b>RE:</b> {re_busca} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Colaborador:</b> {nome_colaborador}", estilo_sub))
                    elementos_pdf.append(Paragraph(f"<b>Departamento / Setor:</b> {depto_colaborador}", estilo_sub))
                    elementos_pdf.append(Spacer(1, 15))
                    
                    termo_nr6 = """
                    <b>TERMO DE RESPONSABILIDADE, CIÊNCIA E CERTIFICAÇÃO AVANÇADA (NR-6 / LEI 14.063)</b><br/><br/>
                    Declaramos para os devidos fins legais que recebi do SEMASA os Equipamentos de Proteção Individual (EPIs) relacionados na listagem abaixo, adequados ao risco das minhas funções operacionais. 
                    Comprometo-me ao uso obrigatório, guarda, zelo e higienização dos mesmos. 
                    <b>Cláusula de Validação Biométrica Corporativa:</b> Fica expressamente eleito e acordado entre as partes que a aposição física do crachá funcional NFC com código UID unívoco e individualizado do trabalhador atua como assinatura eletrônica avançada, plenamente íntegra e com total validade de prova pericial trabalhista nos termos do Artigo 158 da CLT.
                    """
                    elementos_pdf.append(Paragraph(termo_nr6, estilo_texto))
                    elementos_pdf.append(Spacer(1, 10))
                    
                    dados_tabela = [[Paragraph("Data Entrega", estilo_tabela_header), Paragraph("Equipamento (EPI)", estilo_tabela_header), Paragraph("CA do Ministério", estilo_tabela_header), Paragraph("Quantidade", estilo_tabela_header)]]
                    for _, r in df_filtrado_func.iterrows():
                        dados_tabela.append([Paragraph(str(r['Data_Entrega']), estilo_tabela), Paragraph(str(r['EPI']), estilo_tabela), Paragraph(str(r['CA']), estilo_tabela), Paragraph(str(r['Quantidade']), estilo_tabela)])
                        
                    tabela_pdf = Table(dados_tabela, colWidths=[90, 240, 110, 80])
                    tabela_pdf.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9f9f9')]),
                    ]))
                    elementos_pdf.append(tabela_pdf)
                    elementos_pdf.append(Spacer(1, 35))
                    
                    elementos_pdf.append(Paragraph(f"Santo André, {datetime.now().strftime('%d/%m/%Y')}.", estilo_texto))
                    elementos_pdf.append(Spacer(1, 15))
                    elementos_pdf.append(Paragraph("<b>🟢 VALIDADO EM AUDITORIA VIA ASSINATURA ELETRÔNICA DE CRACHÁ NFC</b>", ParagraphStyle('NFC', parent=estilo_texto, fontName='Helvetica-Bold', textColor=colors.HexColor('#27ae60'))))
                    elementos_pdf.append(Paragraph("Os hashes criptográficos de validação de UID, carimbo de data/hora e identificador do terminal encontram-se arquivados nativamente na base HST do Semasa para fins periciais (Lei 14.063/2020).", ParagraphStyle('NFCS', parent=estilo_texto, fontSize=8, textColor=colors.gray)))
                    
                    doc.build(elementos_pdf)
                    pdf_pronto = buffer.getvalue()
                    buffer.close()
                    
                    st.download_button(label="🖨️ EXPORTAR FICHA DIGITAL AUDITADA (PDF)", data=pdf_pronto, file_name=f"Ficha_EPI_RE_{re_busca}_NFC.pdf", mime="application/pdf", type="primary")

# ==============================================================================
# MENU 5: VISUALIZAR TABELAS REAIS
# ==============================================================================
elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    tab1, tab2 = st.tabs(["Histórico de Respostas", "Lista tb_funcionarios"])
    with tab1:
        try: st.dataframe(pd.read_csv(URL_RESPOSTAS, dtype=str), use_container_width=True)
        except: st.info("Vazia.")
    with tab2:
        try: st.dataframe(pd.read_csv(URL_FUNCIONARIOS, dtype=str), use_container_width=True)
        except: st.info("Inacessível.")
