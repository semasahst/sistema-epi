import streamlit as st
import pandas as pd
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import io

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
# CONFIGURAÇÕES DE E-MAIL (GMAIL COMUM)
# ==============================================================================
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587                 

EMAIL_REMETENTE = "seu_email_aqui@gmail.com" 
EMAIL_SENHA = "abcd efgh ijkl mnop"  

# ID da sua planilha do Google Sheets para LEITURA
CHAVE_PLANILHA = "1vL-5EqVshfUAmJY-3DlMfRpxtgfCvD5TaNLCxU4BPUE"
URL_FORM_POST = "https://docs.google.com/forms/d/e/1FAIpQLSfRZgRoIfEHUuanvhsMpkfXMSo7BslH_9Oj16nBNhIgSEw0Fg/formResponse"

URL_FUNCIONARIOS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_funcionarios"
URL_EPIS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_epis"
URL_RESPOSTAS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=Respostas%20ao%20formul%C3%A1rio%201"
URL_GESTORES = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_gestores"

# Menu Lateral com a nova opção de Ficha inclusa
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "⚠️ EPIs Vencidos/A Vencer", "📄 Gerar Ficha de EPI", "Visualizar Tabelas Reais"])

try:
    df_func = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
    df_epis = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
except:
    st.error("❌ Erro ao conectar com o Google Sheets.")
    st.stop()

if menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI")
    col1, col2 = st.columns(2)
    with col1:
        re_input = st.text_input("Digite o RE do Funcionário:").strip()
        nome_func, depto_func = "", ""
        if re_input and not df_func.empty:
            funcionario = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_input)]
            if not funcionario.empty:
                nome_func, depto_func = funcionario.iloc[0, 1], funcionario.iloc[0, 2]
                st.success(f"👤 **Colaborador:** {nome_func} | **Depto:** {depto_func}")
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
    
    if st.button("🚀 GRAVAR ENTREGA NO GOOGLE SHEETS", type="primary"):
        if not re_input or not nome_func:
            st.error("Insira um RE válido.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione um EPI.")
        else:
            with st.spinner("Gravando..."):
                for epi_formatado in epis_selecionados:
                    dados_formulario = {
                        "entry.2087142219": re_input,
                        "entry.1719783905": nome_func,
                        "entry.791852446": epi_formatado.split(" (CA:")[0].strip(),
                        "entry.1336399804": data_entrega.strftime('%Y-%m-%d'),
                        "entry.342195985": str(qtd_entrega) 
                    }
                    requests.post(URL_FORM_POST, data=dados_formulario)
            st.success(f"✅ {len(epis_selecionados)} EPI(s) gravado(s) com quantidade {qtd_entrega}!")
            st.balloons()

elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Monitor de Controle de Validade de EPIs")
    
    try:
        df_historico = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
        df_gestores = pd.read_csv(URL_GESTORES, dtype=str).dropna(how='all')
    except:
        df_historico = pd.DataFrame()
        df_gestores = pd.DataFrame()
        
    if df_historico.empty:
        st.info("ℹ️ Nenhuma entrega registrada.")
    else:
        colunas_disponiveis = list(df_historico.columns)
        if len(colunas_disponiveis) >= 5:
            if 'Carimbo' in colunas_disponiveis[0] or 'Timestamp' in colunas_disponiveis[0]:
                df_historico.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas_disponiveis[6:]
            else:
                df_historico.columns = ['RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas_disponiveis[5:]
            
        df_historico['Data_Entrega'] = pd.to_datetime(df_historico['Data_Entrega'], errors='coerce')
        df_historico = df_historico.dropna(subset=['Data_Entrega'])
        df_ultimas_entregas = df_historico.sort_values('Data_Entrega').groupby(['RE', 'EPI']).last().reset_index()
        
        dicionario_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
        dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
        
        linhas_alertas = []
        hoje = datetime.now()
        
        for _, row in df_ultimas_entregas.iterrows():
            nome_epi = str(row['EPI']).strip()
            dt_entrega = row['Data_Entrega']
            dt_vencimento = dt_entrega + timedelta(days=dicionario_validades.get(nome_epi, 90))
            dias_restantes = (dt_vencimento - hoje).days
            
            status = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
            
            depto = "Não Informado"
            if not df_func.empty:
                f_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(row['RE']).strip()]
                if not f_match.empty: depto = f_match.iloc[0, 2]
                
            qtd_salva = row['Quantidade'] if 'Quantidade' in row and pd.notnull(row['Quantidade']) else "1"
            
            linhas_alertas.append({
                "RE": row['RE'], "Funcionário": row['Funcionário'], "Departamento": depto,
                "EPI": nome_epi, "CA": dicionario_ca.get(nome_epi, "N/A"), "Qtd": qtd_salva,
                "Data Entrega": dt_entrega.strftime('%d/%m/%Y'), "Data Vencimento": dt_vencimento.strftime('%d/%m/%Y'),
                "Dias Restantes": dias_restantes, "Status": status
            })
            
        df_base_alertas = pd.DataFrame(linhas_alertas)
        
        st.markdown("### 🔍 Filtros de Monitoramento")
        c1, c2 = st.columns(2)
        with c1:
            filtro_status = st.multiselect("Filtrar por Status:", ["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)", "🟢 Regular"], default=["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])
        with c2:
            lista_deptos = sorted(list(df_base_alertas['Departamento'].unique())) if not df_base_alertas.empty else []
            filtro_depto = st.multiselect("Filtrar por Departamento:", lista_deptos)
            
        df_alertas_final = df_base_alertas.copy()
        if filtro_status:
            df_alertas_final = df_alertas_final[df_alertas_final['Status'].isin(filtro_status)]
        if filtro_depto:
            df_alertas_final = df_alertas_final[df_alertas_final['Departamento'].isin(filtro_depto)]
            
        df_alertas_final = df_alertas_final.sort_values(by="Dias Restantes")
        
        vencidos_qtd = len(df_alertas_final[df_alertas_final['Status'] == "🔴 VENCIDO"])
        criticos_qtd = len(df_alertas_final[df_alertas_final['Status'] == "🟡 CRÍTICO (Até 15 dias)"])
        
        col_card1, col_card2 = st.columns(2)
        col_card1.metric(label="🚨 Funcionários com EPI Vencido (Filtrado)", value=vencidos_qtd, delta=f"{vencidos_qtd} urgentes", delta_color="inverse")
        col_card2.metric(label="⚠️ EPIs Próximos do Vencimento (Filtrado)", value=criticos_qtd, delta=f"{criticos_qtd} atenção")

        st.markdown("---")
        st.markdown("### ✉️ Central de Notificações Automatizadas")
        
        if st.button("✉️ DISPARAR ALERTAS PARA GESTORES DOS DEPTOS FILTRADOS", type="secondary"):
            df_pendentes = df_alertas_final[df_alertas_final['Status'].isin(["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])]
            
            if EMAIL_REMETENTE == "seu_email_aqui@gmail.com":
                st.error("❌ Configure as credenciais de e-mail do Gmail nas linhas 23 e 24 do código.")
            elif df_pendentes.empty:
                st.success("🎉 Excelente! Nenhum EPI vencido ou crítico para notificar baseado nos filtros atuais.")
            elif df_gestores.empty:
                st.error("❌ Não foi possível carregar a aba tb_gestores.")
            else:
                sucesso_geral = True
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
                            
                            corpo_html = f"""
                            <html>
                            <body>
                                <h2>Olá, {nome_gestor}!</h2>
                                <p>Este é um alerta automático do <b>Sistema HST Semasa</b>. Os colaboradores abaixo possuem pendências de EPI no departamento <b>{depto_grupo}</b>:</p>
                                <table border='1' cellpadding='5' style='border-collapse: collapse;'>
                                    <tr style='background-color: #f2f2f2;'><th>RE</th><th>Funcionário</th><th>EPI</th><th>Qtd Retirada</th><th>Vencimento</th><th>Prazo</th></tr>
                                    {html_tabela}
                                </table>
                                <hr><small>E-mail gerado automaticamente pelo Sistema Integrado de EPIs - Semasa.</small>
                            </body>
                            </html>
                            """
                            msg.attach(MIMEText(corpo_html, 'html'))
                            
                            try:
                                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                                server.starttls()
                                server.login(EMAIL_REMETENTE, EMAIL_SENHA)
                                server.sendmail(EMAIL_REMETENTE, email_gestor, msg.as_string())
                                server.quit()
                                st.write(f"📧 E-mail enviado para o Gestor {nome_gestor} ({depto_grupo})!")
                            except Exception as ex:
                                successo_geral = False
                                st.write(f"❌ Falha para o depto {depto_grupo}: {ex}")
                    
                if sucesso_geral:
                    st.success("🎯 Todos os e-mails aplicáveis foram processados!")

        st.markdown("---")
        st.markdown("### 📋 Listagem Consolidada de Prazos")
        if not df_alertas_final.empty:
            st.dataframe(df_alertas_final, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 Nenhum registro encontrado!")

# ==============================================================================
# MÓDULO NOVO: 📄 GERAR FICHA DE EPI DIGITAL (EM PDF)
# ==============================================================================
elif menu == "📄 Gerar Ficha de EPI":
    st.header("📄 Módulo de Emissão de Ficha de EPI - NR-6")
    st.markdown("Busque o histórico de um trabalhador para emitir o termo impresso assinado.")
    
    re_busca = st.text_input("Digite o RE do Colaborador para buscar a Ficha:").strip()
    
    if re_busca:
        # Busca dados fixos do funcionário
        func_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_busca)]
        
        if func_match.empty:
            st.error("❌ RE não cadastrado na base de dados.")
        else:
            nome_colaborador = func_match.iloc[0, 1]
            depto_colaborador = func_match.iloc[0, 2]
            
            st.info(f"👤 **Trabalhador Localizado:** {nome_colaborador} | **Setor:** {depto_colaborador}")
            
            # Carrega e isola o histórico de entregas reais dele
            try:
                df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
            except:
                df_hist = pd.DataFrame()
                
            if df_hist.empty:
                st.warning("⚠️ Nenhuma entrega gravada no sistema para este RE até o momento.")
            else:
                colunas = list(df_hist.columns)
                if len(colunas) >= 5:
                    if 'Carimbo' in colunas[0] or 'Timestamp' in colunas[0]:
                        df_hist.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas[6:]
                    else:
                        df_hist.columns = ['RE', 'Funcionário', 'EPI', 'Data_Entrega', 'Quantidade'] + colunas[5:]
                
                # Filtra apenas as linhas pertencentes a este RE específico
                df_filtrado_func = df_hist[df_hist['RE'].astype(str).str.strip() == str(re_busca)].copy()
                
                if df_filtrado_func.empty:
                    st.warning("⚠️ Nenhuma entrega localizada para este RE no histórico de respostas.")
                else:
                    st.markdown("### Histórico de Itens a serem inclusos na Ficha")
                    
                    # Cria um dicionário auxiliar para injetar o CA correto na tabela visual
                    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
                    df_filtrado_func['CA'] = df_filtrado_func['EPI'].map(dicionario_ca).fillna("N/A")
                    df_filtrado_func['Quantidade'] = df_filtrado_func['Quantidade'].fillna("1")
                    
                    st.dataframe(df_filtrado_func[['Data_Entrega', 'EPI', 'CA', 'Quantidade']], use_container_width=True, hide_index=True)
                    
                    # ==========================================================
                    # BOTÃO DE MONTAGEM E DOWNLOAD DO PDF (REPORTLAB)
                    # ==========================================================
                    buffer = io.BytesIO()
                    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
                    elementos_pdf = []
                    
                    estilos = getSampleStyleSheet()
                    estilo_titulo = ParagraphStyle('Titulo', parent=estilos['Heading1'], fontName='Helvetica-Bold', fontSize=16, alignment=1, spaceAfter=20)
                    estilo_sub = ParagraphStyle('Sub', parent=estilos['Normal'], fontName='Helvetica-Bold', fontSize=11, spaceAfter=8)
                    estilo_texto = ParagraphStyle('Texto', parent=estilos['Normal'], fontName='Helvetica', fontSize=10, leading=14, spaceAfter=15, alignment=4)
                    estilo_tabela = ParagraphStyle('Tab', parent=estilos['Normal'], fontName='Helvetica', fontSize=9, leading=11)
                    estilo_tabela_header = ParagraphStyle('TabH', parent=estilos['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=11, textColor=colors.white)
                    
                    # 1. Cabeçalho
                    elementos_pdf.append(Paragraph("SEMASA - SERVIÇO MUNICIPAL DE SANEAMENTO AMBIENTAL DE SANTO ANDRÉ", estilo_titulo))
                    elementos_pdf.append(Paragraph("FICHA DE CONTROLE E REGISTRO DE ENTREGA DE EPI", ParagraphStyle('SubT', parent=estilo_titulo, fontSize=13, spaceAfter=25)))
                    
                    # 2. Dados Finais do Trabalhador
                    elementos_pdf.append(Paragraph(f"<b>RE:</b> {re_busca} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Colaborador:</b> {nome_colaborador}", estilo_sub))
                    elementos_pdf.append(Paragraph(f"<b>Departamento / Setor:</b> {depto_colaborador}", estilo_sub))
                    elementos_pdf.append(Spacer(1, 15))
                    
                    # 3. Termo Genérico em total conformidade com a NR-6 e CLT
                    termo_nr6 = """
                    <b>TERMO DE RESPONSABILIDADE E COMPROMISSO (NR-6)</b><br/><br/>
                    Declaramos para os devidos fins que recebi do SEMASA, a título gratuito, os Equipamentos de Proteção Individual (EPIs) constantes na listagem abaixo, adequados ao risco das minhas atividades operacionais. 
                    Comprometo-me a utilizá-los obrigatoriamente durante toda a jornada de trabalho, zelar pela sua perfeita guarda, conservação e higienização, e comunicar imediatamente ao setor de Segurança do Trabalho qualquer alteração que o torne impróprio para o uso. 
                    Estou ciente de que o fornecimento é gratuito, porém a perda injustificada ou dano intencional poderá acarretar em desconto em folha, e o não cumprimento do uso obrigatório constitui ato faltoso passível de punições disciplinares cabíveis conforme o Artigo 158 da CLT.
                    """
                    elementos_pdf.append(Paragraph(termo_nr6, estilo_texto))
                    elementos_pdf.append(Spacer(1, 10))
                    
                    # 4. Estruturação da Tabela de Entregas no PDF
                    dados_tabela = [[Paragraph("Data Entrega", estilo_tabela_header), Paragraph("Equipamento (EPI)", estilo_tabela_header), Paragraph("CA do Ministério", estilo_tabela_header), Paragraph("Quantidade", estilo_tabela_header)]]
                    
                    for _, r in df_filtrado_func.iterrows():
                        dados_tabela.append([
                            Paragraph(str(r['Data_Entrega']), estilo_tabela),
                            Paragraph(str(r['EPI']), estilo_tabela),
                            Paragraph(str(r['CA']), estilo_tabela),
                            Paragraph(str(r['Quantidade']), estilo_tabela)
                        ])
                        
                    tabela_pdf = Table(dados_tabela, colWidths=[90, 240, 110, 80])
                    tabela_pdf.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('BOTTOMPADDING', (0,0), (-1,0), 6),
                        ('TOPPADDING', (0,0), (-1,0), 6),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f9f9f9')]),
                        ('BOTTOMPADDING', (0,1), (-1,-1), 5),
                        ('TOPPADDING', (0,1), (-1,-1), 5),
                    ]))
                    elementos_pdf.append(tabela_pdf)
                    elementos_pdf.append(Spacer(1, 40))
                    
                    # 5. Assinatura e Datação
                    data_hoje = datetime.now().strftime('%d/%m/%Y')
                    elementos_pdf.append(Paragraph(f"Santo André, {data_hoje}.", estilo_texto))
                    elementos_pdf.append(Spacer(1, 30))
                    
                    dados_assinatura = [
                        ["__________________________________________________", "__________________________________________________"],
                        ["Assinatura do Colaborador", "Setor de Segurança do Trabalho - HST"]
                    ]
                    tab_assinatura = Table(dados_assinatura, colWidths=[260, 260])
                    tab_assinatura.setStyle(TableStyle([
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,1), (-1,1), 9),
                    ]))
                    elementos_pdf.append(tab_assinatura)
                    
                    doc.build(elementos_pdf)
                    pdf_pronto = buffer.getvalue()
                    buffer.close()
                    
                    st.markdown("---")
                    st.download_button(
                        label="🖨️ IMPRIMIR / BAIXAR FICHA DE EPI EM PDF",
                        data=pdf_pronto,
                        file_name=f"Ficha_EPI_RE_{re_busca}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )

elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    tab1, tab2 = st.tabs(["Histórico de Respostas", "Lista tb_funcionarios"])
    with tab1:
        try: st.dataframe(pd.read_csv(URL_RESPOSTAS, dtype=str), use_container_width=True)
        except: st.info("Vazia.")
    with tab2:
        try: st.dataframe(pd.read_csv(URL_FUNCIONARIOS, dtype=str), use_container_width=True)
        except: st.info("Inacessível.")
