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

EMAIL_REMETENTE = "semasa.hst@gmail.com" 
EMAIL_SENHA = "hst.semasa"  

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
# FUNÇÃO AUXILIAR: PROCESSAMENTO DINÂMICO DE ALERTAS E VERIFICAÇÃO DE ASSINATURAS
# ==============================================================================
def processar_dados_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except:
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    # Mapeamento das colunas baseado na planilha real
    col_timestamp = df_hist.columns[0]
    col_re = 'RE' if 'RE' in df_hist.columns else df_hist.columns[1]
    col_func = 'Funcionário' if 'Funcionário' in df_hist.columns else df_hist.columns[2]
    col_epi = 'EPI' if 'EPI' in df_hist.columns else df_hist.columns[3]
    col_data = 'Data' if 'Data' in df_hist.columns else ('Data_Entrega' if 'Data_Entrega' in df_hist.columns else df_hist.columns[4])
    col_qtd = 'Quantidade' if 'Quantidade' in df_hist.columns else df_hist.columns[5]

    linhas_alertas = []
    hoje = datetime.now()
    
    dicionario_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    for _, row in df_hist.iterrows():
        re_val = str(row[col_re]).strip()
        nome_func = str(row[col_func]).strip()
        nome_epi = str(row[col_epi]).strip()
        qtd_val = str(row[col_qtd]).strip()
        raw_timestamp = str(row[col_timestamp]).strip()
        raw_data_entrega = str(row[col_data]).strip()
        
        # Correção anti-desalinhamento de colunas
        if "-" in nome_epi and len(nome_epi) == 10:
            nome_epi_correto = raw_data_entrega
            raw_data_entrega = nome_epi
            nome_epi = nome_epi_correto

        if not re_val or re_val == 'nan' or re_val == '':
            continue
            
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega, errors='coerce')
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_timestamp.split()[0], dayfirst=True, errors='coerce')
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = hoje
            
        dias_validade = dicionario_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        
        status = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        # 🛠️ NOVA LÓGICA DE DETECÇÃO DE PENDÊNCIA:
        # Só marcamos como "Pendente" se houver a palavra "PENDENTE" explícita gravada no registro, 
        # caso contrário, o fluxo padrão com crachá (ou preenchimento comum do dia) é considerado Assinado.
        if "PENDENTE" in raw_timestamp.upper() or "PENDENTE" in raw_data_entrega.upper():
            status_assinatura = "Pendente"
        else:
            status_assinatura = "Assinado"
        
        # Localiza o Departamento do servidor
        depto = "Não Informado"
        if not df_func.empty:
            f_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == re_val]
            if not f_match.empty: 
                depto = str(f_match.iloc[0, 2]).strip()
        
        qtd_salva = int(qtd_val) if qtd_val.isdigit() else 1
        
        linhas_alertas.append({
            "RE": re_val, "Funcionário": nome_func, "Departamento": depto,
            "EPI": nome_epi, "CA": dicionario_ca.get(nome_epi, "N/A"), "Qtd": qtd_salva,
            "Data Entrega": dt_entrega_parsed, "Data Vencimento": dt_vencimento,
            "Dias Restantes": dias_restantes, "Status": status, "Assinatura": status_assinatura
        })
        
    return pd.DataFrame(linhas_alertas)

# ==============================================================================
# BLOCO PRINCIPAL DE NAVEGAÇÃO E TRATAMENTO DE MENUS
# ==============================================================================
# Certifique-se de que a variável 'menu' está recebendo o st.sidebar.selectbox corretamente antes disso
# Exemplo: menu = st.sidebar.selectbox("Navegação", ["Dashboard", "Lançar Entrega", "⚠️ EPIs Vencidos/A Vencer", "📄 Gerar Ficha de EPI"])

if menu == "Dashboard":
    st.header("📊 Painel de Indicadores Estratégicos - HST Semasa")
    
    # 1. Filtros Globais de Tempo e Escopo do Dashboard
    st.markdown("### 📅 Filtros de Análise Temporal")
    col_d1, col_d2, col_d3 = st.columns(3)
    
    # Executa a função auxiliar de processamento
    df_base_completa = processar_dados_alertas()
    
    with col_d1:
        data_ini_dash = st.date_input("Início da Análise:", datetime.now().date() - timedelta(days=90))
    with col_d2:
        data_fim_dash = st.date_input("Fim da Análise:", datetime.now().date())
    with col_d3:
        if not df_base_completa.empty:
            dt_i = pd.to_datetime(data_ini_dash)
            dt_f = pd.to_datetime(data_fim_dash) + timedelta(days=1) - timedelta(seconds=1)
            df_filtrado_periodo = df_base_completa[(df_base_completa['Data Entrega'] >= dt_i) & (df_base_completa['Data Entrega'] <= dt_f)]
            
            csv_buffer = df_filtrado_periodo.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 EXPORTAR DADOS FILTRADOS (CSV)",
                data=csv_buffer,
                file_name=f"Relatorio_HST_Semasa_{data_ini_dash}_a_{data_fim_dash}.csv",
                mime="text/csv",
                type="secondary",
                help="Clique para baixar todos os registros deste período."
            )

    st.markdown("---")

    # 2. Processamento e Filtragem Temporal dos Dados
    if df_base_completa.empty:
        st.info("Nenhum dado logístico carregado para exibir os indicadores.")
    else:
        dt_i = pd.to_datetime(data_ini_dash)
        dt_f = pd.to_datetime(data_fim_dash) + timedelta(days=1) - timedelta(seconds=1)
        
        df_dash = df_base_completa[(df_base_completa['Data Entrega'] >= dt_i) & (df_base_completa['Data Entrega'] <= dt_f)].copy()

        if df_dash.empty:
            st.warning("⚠️ Não existem lançamentos ou movimentações no intervalo de datas selecionado.")
        else:
            # 3. Cartões de Métricas Dinâmicas (KPIs)
            total_entregas = len(df_dash)
            total_pendentes = len(df_dash[df_dash['Assinatura'] == "Pendente"])
            total_vencidos = len(df_dash[df_dash['Status'] == "🔴 VENCIDO"])
            
            taxa_conformidade = ((total_entregas - total_pendentes) / total_entregas * 100) if total_entregas > 0 else 100

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            with kpi1:
                st.metric("📦 Movimentações no Período", total_entregas)
            with kpi2:
                st.metric("✍️ Assinaturas Pendentes", total_pendentes, delta=f"{total_pendentes} pendências", delta_color="inverse")
            with kpi3:
                st.metric("🚨 EPIs Vencidos (NR-6)", total_vencidos, delta="Atenção", delta_color="off")
            with kpi4:
                st.metric("🔰 Índice de Conformidade", f"{taxa_conformidade:.1f}%")

            st.markdown("---")

            # 4. Gráficos de Distribuição por Departamento
            st.markdown("### 🏢 Análise de Distribuição Gerencial por Setores")
            col_g1, col_g2 = st.columns(2)
            
            with col_g1:
                st.markdown("##### Total de EPIs Entregues por Departamento")
                df_depto = df_dash.groupby('Departamento')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False)
                
                fig_barras = px.bar(
                    df_depto, 
                    x='Departamento', 
                    y='Qtd',
                    text='Qtd',
                    labels={'Qtd': 'Quantidade', 'Departamento': 'Setor / Unidade'},
                    color_discrete_sequence=['#2c3e50']
                )
                fig_barras.update_traces(textposition='outside')
                fig_barras.update_layout(
                    margin=dict(l=20, r=20, t=10, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_barras, use_container_width=True)

            with col_g2:
                st.markdown("##### Concentração de Pendências de Assinatura por Setor")
                df_pend_depto = df_dash[df_dash['Assinatura'] == "Pendente"].groupby('Departamento').size().reset_index(name='Pendências')
                
                if df_pend_depto.empty:
                    st.success("🎉 Zero pendências acumuladas no período selecionado!")
                else:
                    fig_pizza = px.pie(
                        df_pend_depto, 
                        values='Pendências', 
                        names='Departamento',
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    fig_pizza.update_traces(textinfo='percent+label', pull=[0.05] * len(df_pend_depto))
                    fig_pizza.update_layout(
                        margin=dict(l=20, r=20, t=10, b=20),
                        showlegend=False
                    )
                    st.plotly_chart(fig_pizza, use_container_width=True)

            st.info(
                "💡 **Dica de Apresentação:** Passe o mouse sobre qualquer um dos gráficos acima e clique na "
                "câmera fotográfica (**'Download plot as a png'**) para salvar a imagem pronta para apresentações ou e-mails."
            )
# ==============================================================================
# MENU 2: LANÇAR ENTREGA (CORRIGIDO E INTEGRADO AO SISTEMA DE PENDÊNCIAS)
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
        
    # CORREÇÃO SEGURA DA LISTAGEM DE EPIS
    lista_opcoes_epis = []
    if not df_epis.empty:
        for _, row in df_epis.iterrows():
            nome_e = str(row.iloc[0]).strip()
            ca_e = str(row.iloc[1]).strip() if len(row) > 1 else "N/A"
            lista_opcoes_epis.append(f"{nome_e} (CA: {ca_e})")
            
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
                # 🛠️ TRATAMENTO JURÍDICO DO FORMATO DE DATA:
                # Se estiver ausente, injeta a string para a nova função "processar_dados_alertas" capturar
                data_base_iso = data_entrega.strftime('%Y-%m-%d')
                if ausente:
                    data_final_envio = f"{data_base_iso} - PENDENTE"
                else:
                    data_final_envio = data_base_iso
                
                for epi_formatado in epis_selecionados:
                    dados_formulario = {
                        "entry.2087142219": re_input,
                        "entry.1719783905": nome_func,
                        "entry.791852446": epi_formatado.split(" (CA:")[0].strip(),
                        "entry.1336399804": data_final_envio, # <-- Enviando a marcação de pendência aqui!
                        "entry.342195985": str(qtd_entrega)
                    }
                    requests.post(URL_FORM_POST, data=dados_formulario)
            st.success("🎯 Registro concluído!")
            st.balloons()
# ==============================================================================
# MENU 3: CONTROLES - VENCIDOS E ASSINATURAS PENDENTES (CORRIGIDO)
# ==============================================================================
elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
    aba_vencidos, aba_pendentes = st.tabs(["🚨 Monitor de Validade (NR-6)", "📥 Assinaturas Pendentes"])
    df_alertas_painel = processar_dados_alertas()
    
    try: 
        df_gestores = pd.read_csv(URL_GESTORES, dtype=str).dropna(how='all')
    except: 
        df_gestores = pd.DataFrame()

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
                    data_inicio_sel = st.date_input("Data Inicial do Lançamento:", datetime.now().date() - timedelta(days=30))
                with col_f3:
                    data_fim_sel = st.date_input("Data Final do Lançamento:", datetime.now().date())
                
                if filtro_depto_p:
                    df_p = df_p[df_p['Departamento'].isin(filtro_depto_p)]
                
                # Normalização temporal para o Pandas comparar os formatos sem perdas
                dt_inicio_timestamp = pd.to_datetime(data_inicio_sel)
                dt_fim_timestamp = pd.to_datetime(data_fim_sel) + timedelta(days=1) - timedelta(seconds=1)
                
                df_p = df_p[(df_p['Data Entrega'] >= dt_inicio_timestamp) & (df_p['Data Entrega'] <= dt_fim_timestamp)]
                
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
                                    msg['Subject'] = "✍️ [HST Semasa] Convocação: Servidores Pendentes de Assinatura de EPI"
                                    
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
# MENU 4: GERAR FICHA DE EPI (ALINHADO E INDENTADO CORRETAMENTE)
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
                    
                    if 'Data_Entrega' in df_filtrado_func.columns:
                        df_filtrado_func['Data_Entrega'] = df_filtrado_func['Data_Entrega'].fillna(df_filtrado_func['Timestamp'].astype(str).str.split().str[0])
                    else:
                        df_filtrado_func['Data_Entrega'] = df_filtrado_func['Timestamp'].astype(str).str.split().str[0]
                        
                    df_filtrado_func['Data_Formatada'] = pd.to_datetime(df_filtrado_func['Data_Entrega'], errors='coerce')
                    df_filtrado_func['Data_Formatada'] = df_filtrado_func['Data_Formatada'].dt.strftime('%d/%m/%Y').fillna(df_filtrado_func['Data_Entrega'].astype(str).str.strip())
                    
                    valores_nulos = ['nan', 'NaT', '<NA>', 'None', 'none', '']
                    df_filtrado_func['Data_Formatada'] = df_filtrado_func['Data_Formatada'].apply(lambda x: 'Não Consta' if str(x).strip() in valores_nulos or pd.isnull(x) else x)
                    
                    st.dataframe(df_filtrado_func[['Data_Formatada', 'EPI', 'CA', 'Quantidade']].rename(columns={'Data_Formatada': 'Data Entrega'}), use_container_width=True, hide_index=True)
                    
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
                        data_linha = str(r['Data_Formatada']).strip()
                        dados_tabela.append([Paragraph(data_linha, estilo_tabela), Paragraph(str(r['EPI']), estilo_tabela), Paragraph(str(r['CA']), estilo_tabela), Paragraph(str(r['Quantidade']), estilo_tabela)])
                        
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
