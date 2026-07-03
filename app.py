import streamlit as st
import pandas as pd
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import io
import plotly.express as px  # Nova biblioteca para os gráficos do Dashboard

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

# Menu de Navegação Atualizado com Dashboard como página inicial
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
# FUNÇÃO AUXILIAR: PROCESSAMENTO GERAL DO HISTÓRICO (Comum para Alertas e Dashboard)
# ==============================================================================
def processar_dados_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except:
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    colunas_disponiveis = list(df_hist.columns)
    if len(colunas_disponiveis) >= 5:
        if 'Carimbo' in colunas_disponiveis[0] or 'Timestamp' in colunas_disponiveis[0]:
            df_hist.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas_disponiveis[6:]
        else:
            df_hist.columns = ['RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas_disponiveis[5:]
        
    df_hist['Data_Entrega'] = pd.to_datetime(df_hist['Data_Entrega'], errors='coerce')
    df_hist = df_hist.dropna(subset=['Data_Entrega'])
    
    # Pega apenas a última entrega de cada EPI para cada trabalhador
    df_ultimas = df_hist.sort_values('Data_Entrega').groupby(['RE', 'EPI']).last().reset_index()
    
    dicionario_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    linhas_alertas = []
    hoje = datetime.now()
    
    for _, row in df_ultimas.iterrows():
        nome_epi = str(row['EPI']).strip()
        dt_entrega = row['Data_Entrega']
        dt_vencimento = dt_entrega + timedelta(days=dicionario_validades.get(nome_epi, 90))
        dias_restantes = (dt_vencimento - hoje).days
        status = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
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
            "Dias Restantes": dias_restantes, "Status": status
        })
        
    return pd.DataFrame(linhas_alertas)

# ==============================================================================
# MENU 1: DASHBOARD DE GESTÃO
# ==============================================================================
if menu == "📊 Dashboard de Gestão":
    st.header("📊 Painel de Indicadores Estratégicos - HST")
    
    with st.spinner("Compilando indicadores..."):
        df_alertas_geral = processar_dados_alertas()
        
    if df_alertas_geral.empty:
        st.info("ℹ️ Nenhum dado de entrega localizado para gerar o painel de indicadores.")
    else:
        # 1. Indicadores Cards (KPIs)
        total_entregas_num = len(df_alertas_geral)
        funcionarios_atendidos = df_alertas_geral['RE'].nunique()
        vencidos_qtd = len(df_alertas_geral[df_alertas_geral['Status'] == "🔴 VENCIDO"])
        criticos_qtd = len(df_alertas_geral[df_alertas_geral['Status'] == "🟡 CRÍTICO (Até 15 dias)"])
        
        # Layout de cartões de métricas superiores
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(label="📦 Total de EPIs Ativos em Uso", value=total_entregas_num)
        c2.metric(label="👥 Colaboradores Cobertos", value=funcionarios_atendidos)
        c3.metric(label="🚨 Contratos de EPI Vencidos", value=vencidos_qtd, delta=f"{vencidos_qtd} Urgentes", delta_color="inverse")
        c4.metric(label="⚠️ Situações Críticas (Até 15 dias)", value=criticos_qtd, delta=f"{criticos_qtd} Alertas", delta_color="off")
        
        st.markdown("---")
        
        # 2. Área de Gráficos Principais
        col_graf1, col_graf2 = st.columns(2)
        
        with col_graf1:
            st.markdown("### 🏆 Ranking de EPIs mais Utilizados")
            # Agrupa por EPI e soma a quantidade real distribuída
            df_epi_rank = df_alertas_geral.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False).head(8)
            fig_bar = px.bar(
                df_epi_rank, x='Qtd', y='EPI', orientation='h',
                labels={'Qtd': 'Quantidade Total', 'EPI': 'Equipamento'},
                color='Qtd', color_continuous_scale='Blugrn'
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}, height=350, margin=dict(l=0, r=0, t=10, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_graf2:
            st.markdown("### 📊 Status de Regularidade Operacional")
            # Gráfico de pizza simples sobre a saúde geral dos EPIs ativos
            df_status_pie = df_alertas_geral['Status'].value_counts().reset_index()
            df_status_pie.columns = ['Status', 'Contagem']
            
            # Mapeamento manual de cores para o padrão Semasa
            mapa_cores = {"🟢 Regular": "#27ae60", "🟡 CRÍTICO (Até 15 dias)": "#f1c40f", "🔴 VENCIDO": "#e74c3c"}
            
            fig_pie = px.pie(
                df_status_pie, values='Contagem', names='Status',
                color='Status', color_discrete_map=mapa_cores,
                hole=0.4
            )
            fig_pie.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)
            
        st.markdown("---")
        
        # 3. Gráfico Ampliado por Departamento
        st.markdown("### 🏢 Panorama de Saúde de EPI por Departamento / Setor")
        
        # Cria tabela dinâmica para separar as barras por Regular/Vencido/Crítico
        df_depto_status = df_alertas_geral.groupby(['Departamento', 'Status']).size().reset_index(name='Quantidade')
        
        fig_depto = px.bar(
            df_depto_status, x='Departamento', y='Quantidade', color='Status',
            color_discrete_map=mapa_cores,
            barmode='group',
            labels={'Quantidade': 'Funcionários/EPIs'}
        )
        fig_depto.update_layout(height=400, margin=dict(l=0, r=0, t=20, b=20))
        st.plotly_chart(fig_depto, use_container_width=True)

# ==============================================================================
# MENU 2: LANÇAR ENTREGA
# ==============================================================================
elif menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega com Assinatura por Crachá")
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
                if uid_cadastrado:
                    st.info(f"💳 **Crachá NFC Homologado:** {uid_cadastrado}")
                else:
                    st.warning("⚠️ Funcionário sem crachá cadastrado. O primeiro bip salvará este cartão como dele.")
            else:
                st.error(f"❌ RE '{re_input}' não encontrado.")
    with col2:
        data_entrega = st.date_input("Data da Entrega", datetime.now())
        
    lista_opcoes_epis = []
    if not df_epis.empty:
        df_epis['Exibicao'] = df_epis.iloc[:, 0].astype(str) + " (CA: " + df_epis.iloc[:, 1].astype(str) + ")"
        lista_opcoes_epis = df_epis['Exibicao'].tolist()
        
    epis_selecionados = st.multiselect("Selecione um ou mais EPIs entregues:", lista_opcoes_epis)
    qtd_entrega = st.number_input("Quantidade Entregue:", min_value=1, value=1, step=1)
    
    st.markdown("---")
    st.markdown("### 🔑 Assinatura Digital Avançada (Biometria NFC)")
    st.caption("Clique no campo abaixo e aproxime o crachá do funcionário no leitor USB para assinar o recebimento.")
    
    nfc_bip = st.text_input("AGUARDANDO LEITURA DO CRACHÁ...", type="password", help="O leitor físico vai preencher e validar este campo.").strip()
    
    if st.button("🚀 GRAVAR ENTREGA E ASSINAR DIGITALMENTE", type="primary"):
        if not re_input or not nome_func:
            st.error("Insira um RE válido antes de validar.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione o EPI.")
        elif not nfc_bip:
            st.error("❌ Assinatura Recusada: É obrigatório bipar o crachá para validar a entrega.")
        elif uid_cadastrado and nfc_bip != uid_cadastrado:
                st.error("🚨 ERRO DE IDENTIDADE: O crachá apresentado não pertence a este colaborador!")
        else:
            with st.spinner("Autenticando assinatura eletrônica..."):
                timestamp_token = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
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
            st.success(f"✅ Itens entregues e validados juridicamente!")
            st.info(f"🔰 **Log Pericial:** {log_seguranca}")
            st.balloons()

# ==============================================================================
# MENU 3: EPIS VENCIDOS / A VENCER
# ==============================================================================
elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Monitor de Controle de Validade de EPIs")
    try:
        df_gestores = pd.read_csv(URL_GESTORES, dtype=str).dropna(how='all')
    except:
        df_gestores = pd.DataFrame()
        
    df_alertas_painel = processar_dados_alertas()
        
    if df_alertas_painel.empty:
        st.info("ℹ️ Nenhuma entrega registrada.")
    else:
        # Formatando as datas de datetime para string legível na exibição da tabela
        df_exibicao = df_alertas_painel.copy()
        df_exibicao['Data Entrega'] = df_exibicao['Data Entrega'].dt.strftime('%d/%m/%Y')
        df_exibicao['Data Vencimento'] = df_exibicao['Data Vencimento'].dt.strftime('%d/%m/%Y')
        
        st.markdown("### 🔍 Filtros de Monitoramento")
        c1, c2 = st.columns(2)
        with c1:
            filtro_status = st.multiselect("Filtrar por Status:", ["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)", "🟢 Regular"], default=["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])
        with c2:
            lista_deptos = sorted(list(df_exibicao['Departamento'].unique())) if not df_exibicao.empty else []
            filtro_depto = st.multiselect("Filtrar por Departamento:", lista_deptos)
            
        if filtro_status: 
            df_exibicao = df_exibicao[df_exibicao['Status'].isin(filtro_status)]
        if filtro_depto: 
            df_exibicao = df_exibicao[df_exibicao['Departamento'].isin(filtro_depto)]
            
        df_exibicao = df_exibicao.sort_values(by="Dias Restantes")
        vencidos_qtd = len(df_exibicao[df_exibicao['Status'] == "🔴 VENCIDO"])
        criticos_qtd = len(df_exibicao[df_exibicao['Status'] == "🟡 CRÍTICO (Até 15 dias)"])
        
        col_card1, col_card2 = st.columns(2)
        col_card1.metric(label="🚨 Funcionários com EPI Vencido (Filtrado)", value=vencidos_qtd, delta=f"{vencidos_qtd} urgentes", delta_color="inverse")
        col_card2.metric(label="⚠️ EPIs Próximos do Vencimento (Filtrado)", value=criticos_qtd, delta=f"{criticos_qtd} atenção")

        st.markdown("---")
        st.markdown("### ✉️ Central de Notificações Automatizadas")
        if st.button("✉️ DISPARAR ALERTAS PARA GESTORES DOS DEPTOS FILTRADOS", type="secondary"):
            df_pendentes = df_exibicao[df_exibicao['Status'].isin(["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])]
            if EMAIL_REMETENTE == "seu_email_aqui@gmail.com":
                st.error("❌ Configure as credenciais de e-mail do Gmail.")
            elif df_pendentes.empty:
                st.success("🎉 Nenhum EPI crítico para notificar.")
            elif df_gestores.empty:
                st.error("❌ Erro ao ler tb_gestores.")
            else:
                with st.spinner("Enviando e-mails..."):
                    for depto_grupo, dados_grupo in df_pendentes.groupby("Departamento"):
                        gestor_row = df_gestores[df_gestores.iloc[:, 0].astype(str).str.strip().str.upper() == str(depto_grupo).strip().upper()]
                        if not gestor_row.empty:
                            email_gestor = gestor_row.iloc[0, 2]
                            nome_gestor = gestor_row.iloc[0, 1]
                            msg = MIMEMultipart()
                            msg['From'] = EMAIL_REMETENTE
                            msg['To'] = email_gestor
                            msg['Subject'] = f"🚨 [HST Semasa] Alerta de EPIs Vencidos - Depto: {depto_grupo}"
                            
                            html_tabela = ""
                            for _, r in dados_grupo.iterrows():
                                cor_status = "#ffcccc" if r['Status'] == "🔴 VENCIDO" else "#fff2cc"
                                html_tabela += f"<tr style='background-color: {cor_status};'><td>{r['RE']}</td><td>{r['Funcionário']}</td><td>{r['EPI']}</td><td>{r['Qtd']}</td><td>{r['Data Vencimento']}</td><td>{r['Dias Restantes']} dias</td></tr>"
                            
                            corpo_html = f"<html><body><h2>Olá, {nome_gestor}!</h2><p>Pendências operacionais do depto <b>{depto_grupo}</b>:</p><table border='1' cellpadding='5' style='border-collapse: collapse;'><tr style='background-color: #f2f2f2;'><th>RE</th><th>Funcionário</th><th>EPI</th><th>Qtd</th><th>Vencimento</th><th>Prazo</th></tr>{html_tabela}</table></body></html>"
                            msg.attach(MIMEText(corpo_html, 'html'))
                            try:
                                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                                server.starttls()
                                server.login(EMAIL_REMETENTE, EMAIL_SENHA)
                                server.sendmail(EMAIL_REMETENTE, email_gestor, msg.as_string())
                                server.quit()
                                st.write(f"📧 Enviado para {nome_gestor} ({depto_grupo})")
                            except Exception as ex:
                                st.write(f"❌ Falha para {depto_grupo}: {ex}")
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

# ==============================================================================
# MENU 4: GERAR FICHA DE EPI
# ==============================================================================
elif menu == "📄 Gerar Ficha de EPI":
    st.header("📄 Módulo de Emissão de Ficha de EPI Digital - NR-6")
    re_busca = st.text_input("Digite o RE do Colaborador para buscar a Ficha:").strip()
    
    if re_busca:
        func_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_busca)]
        if func_match.empty:
            st.error("❌ RE não cadastrado.")
        else:
            nome_colaborador = func_match.iloc[0, 1]
            depto_colaborador = func_match.iloc[0, 2]
            st.info(f"👤 **Trabalhador:** {nome_colaborador} | **Setor:** {depto_colaborador}")
            
            try: df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
            except: df_hist = pd.DataFrame()
                
            if df_hist.empty:
                st.warning("⚠️ Sem histórico de entregas registradas.")
            else:
                colunas = list(df_hist.columns)
                if len(colunas) >= 5:
                    if 'Carimbo' in colunas[0] or 'Timestamp' in colunas[0]:
                        df_hist.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas[6:]
                    else:
                        df_hist.columns = ['RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas[5:]
                
                df_filtrado_func = df_hist[df_hist['RE'].astype(str).str.strip() == str(re_busca)].copy()
                if df_filtrado_func.empty:
                    st.warning("⚠️ Nenhuma entrega localizada.")
                else:
                    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
                    df_filtrado_func['CA'] = df_filtrado_func['EPI'].map(dicionario_ca).fillna("N/A")
                    df_filtrado_func['Quantidade'] = df_filtrado_func['Quantidade'].fillna("1")
                    
                    st.dataframe(df_filtrado_func[['Data_Entrega', 'EPI', 'CA', 'Quantidade']], use_container_width=True, hide_index=True)
                    
                    # Geração do PDF
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
