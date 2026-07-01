import streamlit as st
import pandas as pd
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# Configuração da página do Streamlit
st.set_page_config(page_title="HST - Semasa", page_icon="🛡️", layout="wide")

st.title("🛡️ Sistema Integrado de Controle de EPIs - HST Semasa")
st.markdown("---")

# ==============================================================================
# CONFIGURAÇÕES DE E-MAIL (SMTP) - Ajuste com os dados fornecidos pela TI
# ==============================================================================
SMTP_SERVER = "smtp.office365.com"  # Ex: smtp.gmail.com ou o servidor interno do Semasa
SMTP_PORT = 587
EMAIL_REMETENTE = "seu-email@semasa.sp.gov.br" # E-mail que vai disparar os alertas
EMAIL_SENHA = "sua-senha-aqui"                 # Senha ou Token de aplicativo do e-mail

# ID da sua planilha do Google Sheets para LEITURA
CHAVE_PLANILHA = "1vL-5EqVshfUAmJY-3DlMfRpxtgfCvD5TaNLCxU4BPUE"
URL_FORM_POST = "https://docs.google.com/forms/d/e/1FAIpQLSfRZgRoIfEHUuanvhsMpkfXMSo7BslH_9Oj16nBNhIgSEw0Fg/formResponse"

URL_FUNCIONARIOS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_funcionarios"
URL_EPIS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_epis"
URL_RESPOSTAS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=Respostas%20ao%20formul%C3%A1rio%201"
URL_GESTORES = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_gestores"

# Menu Lateral
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "⚠️ EPIs Vencidos/A Vencer", "Visualizar Tabelas Reais"])

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
    
    if st.button("🚀 GRAVAR ENTREGA NO GOOGLE SHEETS", type="primary"):
        if not re_input or not nome_func:
            st.error("Insira um RE válido.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione um EPI.")
        else:
            sucesso_envio = True
            with st.spinner("Gravando..."):
                for epi_formatado in epis_selecionados:
                    dados_formulario = {
                        "entry.2087142219": re_input,
                        "entry.1719783905": nome_func,
                        "entry.791852446": epi_formatado.split(" (CA:")[0].strip(),
                        "entry.1336399804": data_entrega.strftime('%Y-%m-%d')
                    }
                    requests.post(URL_FORM_POST, data=dados_formulario)
            st.success("✅ Gravado com sucesso!")
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
        df_historico.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega']
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
            
            linhas_alertas.append({
                "RE": row['RE'], "Funcionário": row['Funcionário'], "Departamento": depto,
                "EPI": nome_epi, "CA": dicionario_ca.get(nome_epi, "N/A"),
                "Data Entrega": dt_entrega.strftime('%d/%m/%Y'), "Data Vencimento": dt_vencimento.strftime('%d/%m/%Y'),
                "Dias Restantes": dias_restantes, "Status": status
            })
            
        df_alertas_final = pd.DataFrame(linhas_alertas)
        
        # Botão de Disparo de E-mails
        st.markdown("### ✉️ Central de Notificações Automatizadas")
        if st.button("✉️ DISPARAR ALERTAS PARA GESTORES", type="secondary"):
            df_pendentes = df_alertas_final[df_alertas_final['Status'].isin(["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])]
            
            if df_pendentes.empty:
                st.success("🎉 Excelente! Nenhum EPI vencido ou crítico para notificar no momento.")
            elif df_gestores.empty:
                st.error("❌ Não foi possível carregar a aba tb_gestores para mapear os e-mails.")
            else:
                sucesso_geral = True
                # Agrupa as pendências por departamento para enviar um único e-mail consolidado por gestor
                for depto_grupo, dados_grupo in df_pendentes.groupby("Departamento"):
                    gestor_row = df_gestores[df_gestores.iloc[:, 0].astype(str).str.strip().str.upper() == str(depto_grupo).strip().upper()]
                    
                    if not gestor_row.empty:
                        email_gestor = gestor_row.iloc[0, 2] # Assume que coluna C é o e-mail
                        nome_gestor = gestor_row.iloc[0, 1]  # Coluna B é o nome do gestor
                        
                        # Monta o corpo do e-mail em HTML super elegante
                        msg = MIMEMultipart()
                        msg['From'] = EMAIL_REMETENTE
                        msg['To'] = email_gestor
                        msg['Subject'] = f"🚨 [HST Semasa] Alerta de EPIs Vencidos - Depto: {depto_grupo}"
                        
                        html_tabela = ""
                        for _, r in dados_grupo.iterrows():
                            cor_status = "#ffcccc" if r['Status'] == "🔴 VENCIDO" else "#fff2cc"
                            html_tabela += f"<tr style='background-color: {cor_status};'><td>{r['RE']}</td><td>{r['Funcionário']}</td><td>{r['EPI']}</td><td>{r['Data Vencimento']}</td><td>{r['Dias Restantes']} dias</td></tr>"
                        
                        corpo_html = f"""
                        <html>
                        <body>
                            <h2>Olá, {nome_gestor}!</h2>
                            <p>Este é um alerta automático do <b>Sistema HST Semasa</b>. Os colaboradores abaixo, sob sua gestão no departamento <b>{depto_grupo}</b>, estão trabalhando com EPIs vencidos ou próximos do vencimento:</p>
                            <table border='1' cellpadding='5' style='border-collapse: collapse;'>
                                <tr style='background-color: #f2f2f2;'><th>RE</th><th>Funcionário</th><th>EPI</th><th>Vencimento</th><th>Prazo</th></tr>
                                {html_tabela}
                            </table>
                            <p><br>Por favor, solicite a regularização e a retirada dos novos equipamentos junto ao setor de Segurança do Trabalho o quanto antes.</p>
                            <hr><small>E-mail gerado automaticamente pelo Sistema Integrado de EPIs - Semasa.</small>
                        </body>
                        </html>
                        """
                        msg.attach(MIMEText(corpo_html, 'html'))
                        
                        # Conexão SMTP e envio de fato
                        try:
                            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                            server.starttls()
                            server.login(EMAIL_REMETENTE, EMAIL_SENHA)
                            server.sendmail(EMAIL_REMETENTE, email_gestor, msg.as_string())
                            server.quit()
                            st.write(f"📧 E-mail de resumo enviado com sucesso para o Gestor {nome_gestor} ({depto_grupo})!")
                        except Exception as ex:
                            sucesso_geral = False
                            st.write(f"❌ Falha técnica ao enviar e-mail para o depto {depto_grupo}. (Verifique as credenciais SMTP no código).")
                
                if sucesso_geral:
                    st.success("🎯 Todos os e-mails de alerta aplicáveis foram processados!")
        
        st.markdown("---")
        st.markdown("### 🔍 Filtros de Monitoramento")
        filtro_status = st.multiselect("Filtrar por Status:", ["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)", "🟢 Regular"], default=["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])
        
        if not df_alertas_final.empty:
            if filtro_status:
                df_alertas_final = df_alertas_final[df_alertas_final['Status'].isin(filtro_status)]
            st.dataframe(df_alertas_final.sort_values(by="Dias Restantes"), use_container_width=True, hide_index=True)

elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    tab1, tab2 = st.tabs(["Histórico de Respostas", "Lista tb_funcionarios"])
    with tab1:
        try: st.dataframe(pd.read_csv(URL_RESPOSTAS, dtype=str), use_container_width=True)
        except: st.info("Vazia.")
    with tab2:
        try: st.dataframe(pd.read_csv(URL_FUNCIONARIOS, dtype=str), use_container_width=True)
        except: st.info("Inacessível.")
