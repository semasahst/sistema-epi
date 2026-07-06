import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configuração da página (deve ser a primeira instrução Streamlit)
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DE FONTES DE DADOS (LINKS PÚBLICOS DO GOOGLE SHEETS)
# ==============================================================================
URL_RESPOSTAS = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv&gid=339151256"
URL_FUNCIONARIOS = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv&gid=1116669931"
URL_EPIS = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv&gid=754637684"

# ==============================================================================
# CARREGAMENTO INICIAL DOS DADOS DE APOIO
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_dados_apoio():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except Exception as e:
        st.error(f"Erro ao carregar tabelas auxiliares: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = carregar_dados_apoio()

# ==============================================================================
# FUNÇÃO MASTER: PROCESSAMENTO DINÂMICO DE ALERTAS E PENDÊNCIAS
# ==============================================================================
def processar_dados_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except Exception as e:
        print(f"Erro ao ler CSV de respostas: {e}")
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    # Identificação dinâmica das colunas por posição
    col_timestamp = df_hist.columns[0]
    col_re = df_hist.columns[1]
    col_func = df_hist.columns[2]
    col_epi = df_hist.columns[3]
    col_data = df_hist.columns[4]
    col_qtd = df_hist.columns[5]

    linhas_alertas = []
    hoje = pd.to_datetime(datetime.now().date())
    
    # Dicionários de consulta rápida (EPI -> Validade / CA)
    dicionario_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
    dicionario_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    for _, row in df_hist.iterrows():
        re_val = str(row[col_re]).strip()
        nome_func = str(row[col_func]).strip()
        nome_epi = str(row[col_epi]).strip()
        qtd_val = str(row[col_qtd]).strip()
        raw_timestamp = str(row[col_timestamp]).strip()
        raw_data_entrega = str(row[col_data]).strip()
        
        if not re_val or re_val == 'nan' or re_val == '':
            continue

        # 📋 CAPTURA DE PENDÊNCIA ULTRA-ROBUSTA (Varre texto na célula de data)
        if "PENDENTE" in raw_data_entrega.upper() or "PENDENTE" in raw_timestamp.upper():
            status_assinatura = "Pendente"
            if len(raw_data_entrega) >= 10:
                raw_data_entrega = raw_data_entrega[:10].strip()
        else:
            status_assinatura = "Assinado"
            
        # Conversão padronizada e segura de datas via Pandas
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega, errors='coerce')
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_timestamp.split()[0], dayfirst=True, errors='coerce')
        
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = hoje
            
        # Normaliza eliminando diferenças de horas residuais
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
            
        dias_validade = dicionario_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        
        status = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        # Mapeamento do Departamento (tb_funcionarios)
        depto = "Não Informado"
        if not df_func.empty:
            re_limpo_busca = re_val.split('.')[0].strip()
            f_match = df_func[df_func.iloc[:, 0].astype(str).str.split('.').str[0].str.strip() == re_limpo_busca]
            if not f_match.empty: 
                depto = str(f_match.iloc[0, 2]).strip()
        
        try:
            qtd_salva = int(float(qtd_val))
        except:
            qtd_salva = 1
        
        linhas_alertas.append({
            "RE": re_val.split('.')[0].strip(),
            "Funcionário": nome_func, 
            "Departamento": depto,
            "EPI": nome_epi, 
            "CA": dicionario_ca.get(nome_epi, "N/A"), 
            "Qtd": qtd_salva,
            "Data Entrega": dt_entrega_parsed, 
            "Data Vencimento": dt_vencimento,
            "Dias Restantes": dias_restantes, 
            "Status": status, 
            "Assinatura": status_assinatura
        })
        
    return pd.DataFrame(linhas_alertas)

# Base de processamento unificada
df_base_completa = processar_dados_alertas()

# ==============================================================================
# ESTRUTURA DE NAVEGAÇÃO LATERAL (MENU)
# ==============================================================================
st.sidebar.title("Navegação")
menu = st.sidebar.selectbox("Ir para:", ["📊 Dashboard de Gestão", "⚠️ EPIs Vencidos/A Vencer"])

# ==============================================================================
# MENU 1: DASHBOARD DE GESTÃO
# ==============================================================================
if menu == "📊 Dashboard de Gestão":
    st.header("📊 Painel de Indicadores Estratégicos - HST Semasa")
    
    st.markdown("### 📅 Filtros de Análise Temporal")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        data_ini_dash = st.date_input("Início da Análise:", datetime.now().date() - timedelta(days=90))
    with col_d2:
        data_fim_dash = st.date_input("Fim da Análise:", datetime.now().date())
        
    if df_base_completa.empty:
        st.warning("Sem dados disponíveis para gerar o Dashboard.")
    else:
        # Conversão segura para bater com os inputs de tela
        dt_i = pd.to_datetime(data_ini_dash)
        dt_f = pd.to_datetime(data_fim_dash)
        
        df_dash = df_base_completa[
            (df_base_completa['Data Entrega'] >= dt_i) & 
            (df_base_completa['Data Entrega'] <= dt_f)
        ]
        
        # Indicadores numéricos superiores (Cards)
        total_entregue = df_dash['Qtd'].sum() if not df_dash.empty else 0
        pendentes_qtd = len(df_dash[df_dash['Assinatura'] == "Pendente"])
        vencidos_qtd = len(df_dash[df_dash['Status'] == "🔴 VENCIDO"])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de EPIs Entregues", total_entregue)
        c2.metric("Assinaturas Pendentes", pendentes_qtd)
        c3.metric("Itens Vencidos (NR-6)", vencidos_qtd)
        
        st.markdown("---")
        
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("#### Volumetria de Consumo por Setor")
            if not df_dash.empty:
                df_setor = df_dash.groupby('Departamento')['Qtd'].sum().reset_index()
                st.bar_chart(data=df_setor, x='Departamento', y='Qtd', use_container_width=True)
            else:
                st.info("Nenhum dado no período.")
                
        with col_g2:
            st.markdown("#### Distribuição de Consumo por Modelo de EPI")
            if not df_dash.empty:
                df_ranking = df_dash.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False)
                st.bar_chart(data=df_ranking, x='EPI', y='Qtd', use_container_width=True)
            else:
                st.info("Nenhum dado no período.")

# ==============================================================================
# MENU 2: ALERTAS E PENDÊNCIAS LOGÍSTICAS
# ==============================================================================
elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
    
    if df_base_completa.empty:
        st.warning("Nenhum registro logístico foi localizado na planilha.")
    else:
        aba_validade, aba_assinaturas = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
        
        # --- ABA 1: MONITOR DE VALIDADE ---
        with aba_validade:
            st.markdown("### 🔍 Validade dos EPIs Fornecidos")
            df_exibicao_val = df_base_completa.copy()
            df_exibicao_val['Data Entrega'] = df_exibicao_val['Data Entrega'].dt.strftime('%d/%m/%Y')
            df_exibicao_val['Data Vencimento'] = df_exibicao_val['Data Vencimento'].dt.strftime('%d/%m/%Y')
            st.dataframe(df_exibicao_val.sort_values(by="Dias Restantes"), use_container_width=True)
            
        # --- ABA 2: ASSINATURAS PENDENTES ---
        with aba_assinaturas:
            st.markdown("### 🔍 Filtros Manuais de Cobrança")
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                lista_deptos = sorted(list(df_base_completa['Departamento'].unique()))
                depto_sel = st.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
                
            with col_f2:
                data_ini_p = st.date_input("Data Inicial do Lançamento:", datetime.now().date() - timedelta(days=60), key="ini_p")
            with col_f3:
                data_fim_p = st.date_input("Data Final do Lançamento:", datetime.now().date() + timedelta(days=1), key="fim_p")
                
            # Filtro performático usando Timestamps idênticos do Pandas
            dt_i_p = pd.to_datetime(data_ini_p)
            dt_f_p = pd.to_datetime(data_fim_p)
            
            df_pendentes = df_base_completa[
                (df_base_completa['Assinatura'] == "Pendente") & 
                (df_base_completa['Departamento'].isin(depto_sel)) &
                (df_base_completa['Data Entrega'] >= dt_i_p) & 
                (df_base_completa['Data Entrega'] <= dt_f_p)
            ]
            
            st.markdown(f"📋 **Pendências Filtradas:** {len(df_pendentes)} itens encontrados.")
            
            if df_pendentes.empty:
                st.success("🎉 Excelente! Nenhuma assinatura pendente encontrada com os filtros selecionados.")
            else:
                df_exibicao_p = df_pendentes.copy()
                df_exibicao_p['Data Entrega'] = df_exibicao_p['Data Entrega'].dt.strftime('%d/%m/%Y')
                st.dataframe(
                    df_exibicao_p[["RE", "Funcionário", "Departamento", "EPI", "Qtd", "Data Entrega", "Status"]],
                    use_container_width=True
                )
                
                if st.button("📨 DISPARAR COBRANÇA PARA OS GESTORES FILTRADOS"):
                    st.info("Simulando envio de e-mails de cobrança para as pendências listadas...")
