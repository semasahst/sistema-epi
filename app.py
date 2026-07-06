import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configuração da página (Deve ser sempre a primeira linha de código Streamlit)
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# ==============================================================================
# LINKS DAS PLANILHAS (GOOGLE SHEETS - EXPORTADOS COMO CSV)
# ==============================================================================
# Link base da planilha mãe
LINK_BASE = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv"

URL_RESPOSTAS = f"{LINK_BASE}&gid=339151256"
URL_FUNCIONARIOS = f"{LINK_BASE}&gid=1116669931"
URL_EPIS = f"{LINK_BASE}&gid=754637684"

# ==============================================================================
# CARREGAMENTO DOS DADOS DE APOIO (COM TRATAMENTO DE ERROS BRUTO)
# ==============================================================================
@st.cache_data(ttl=30)
def carregar_tabelas_auxiliares():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except Exception as e:
        # Fallback caso ocorra erro 404 ou instabilidade no Google Sheets
        st.sidebar.error(f"⚠️ Instabilidade ao conectar com tabelas auxiliares. Usando tabelas vazias.")
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = carregar_tabelas_auxiliares()

# ==============================================================================
# FUNÇÃO MASTER: PROCESSAMENTO UNIFICADO DE ALERTAS E PENDÊNCIAS
# ==============================================================================
def processar_dados_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except Exception as e:
        st.error(f"Erro crítico ao ler planilha de respostas: {e}")
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    # Mapeamento dinâmico baseado estritamente na ordem física das colunas (Índices)
    col_timestamp = df_hist.columns[0]
    col_re = df_hist.columns[1]
    col_func = df_hist.columns[2]
    col_epi = df_hist.columns[3]
    col_data = df_hist.columns[4]
    col_qtd = df_hist.columns[5]

    linhas_alertas = []
    hoje = pd.to_datetime(datetime.now().date())
    
    # Monta os dicionários de consulta se a tabela de EPIs foi carregada com sucesso
    dicionario_validades = {}
    dicionario_ca = {}
    if not df_epis.empty:
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

        # 📋 IDENTIFICAÇÃO DE PENDÊNCIAS EM QUALQUER COLUNA DE DATA
        if "PENDENTE" in raw_data_entrega.upper() or "PENDENTE" in raw_timestamp.upper():
            status_assinatura = "Pendente"
            if len(raw_data_entrega) >= 10:
                raw_data_entrega = raw_data_entrega[:10].strip()
        else:
            status_assinatura = "Assinado"
            
        # Conversão limpa para o formato de data do Pandas (Sem horas residuais)
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega, errors='coerce')
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_timestamp.split()[0], dayfirst=True, errors='coerce')
        
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = hoje
            
        # Zera as horas residuais de forma definitiva para evitar erros em comparações
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
            
        # Busca as validades padrão da tabela de apoio ou assume 90 dias
        dias_validade = dicionario_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        
        status = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        # Mapeamento do Departamento do funcionário
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

# Processa a base master global do app
df_base_completa = processar_dados_alertas()

# ==============================================================================
# MENU LATERAL DE NAVEGAÇÃO
# ==============================================================================
st.sidebar.markdown("## 🧭 Controle Operacional")
menu = st.sidebar.selectbox("Selecione o Painel:", ["📊 Dashboard de Gestão", "⚠️ EPIs Vencidos/A Vencer"])

# ==============================================================================
# PAINEL 1: DASHBOARD DE GESTÃO
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
        st.warning("⚠️ Planilha de respostas vazia ou inacessível no momento.")
    else:
        # Conversão exata para fazer o cruzamento com o Dataframe do Pandas
        dt_i = pd.to_datetime(data_ini_dash)
        dt_f = pd.to_datetime(data_fim_dash)
        
        df_dash = df_base_completa[
            (df_base_completa['Data Entrega'] >= dt_i) & 
            (df_base_completa['Data Entrega'] <= dt_f)
        ]
        
        # Cards de Indicadores Operacionais superiores
        total_entregue = df_dash['Qtd'].sum() if not df_dash.empty else 0
        pendentes_qtd = len(df_dash[df_dash['Assinatura'] == "Pendente"]) if not df_dash.empty else 0
        vencidos_qtd = len(df_dash[df_dash['Status'] == "🔴 VENCIDO"]) if not df_dash.empty else 0
        
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
                st.info("Nenhum dado lançado neste período.")
                
        with col_g2:
            st.markdown("#### Distribuição de Consumo por Modelo de EPI")
            if not df_dash.empty:
                # Groupby estruturado explicitamente com a coluna 'EPI' mapeada
                df_ranking = df_dash.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False)
                st.bar_chart(data=df_ranking, x='EPI', y='Qtd', use_container_width=True)
            else:
                st.info("Nenhum dado lançado neste período.")

# ==============================================================================
# PAINEL 2: GESTÃO DE VALIDADES E PENDÊNCIAS LOGÍSTICAS
# ==============================================================================
elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
    
    if df_base_completa.empty:
        st.warning("Nenhum registro encontrado para listar alertas.")
    else:
        aba_validade, aba_assinaturas = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
        
        # --- ABA 1: MONITOR DE VALIDADE ---
        with aba_validade:
            st.markdown("### 🔍 Controle de Validade Geral")
            df_exibicao_val = df_base_completa.copy()
            df_exibicao_val['Data Entrega'] = df_exibicao_val['Data Entrega'].dt.strftime('%d/%m/%Y')
            df_exibicao_val['Data Vencimento'] = df_exibicao_val['Data Vencimento'].dt.strftime('%d/%m/%Y')
            st.dataframe(df_exibicao_val.sort_values(by="Dias Restantes"), use_container_width=True)
            
        # --- ABA 2: ASSINATURAS PENDENTES (Filtro Dinâmico) ---
        with aba_assinaturas:
            st.markdown("### 🔍 Filtros Manuais de Cobrança")
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                lista_deptos = sorted(list(df_base_completa['Departamento'].unique()))
                depto_sel = st.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
                
            with col_f2:
                data_ini_p = st.date_input("Data Inicial:", datetime.now().date() - timedelta(days=60), key="ini_p")
            with col_f3:
                data_fim_p = st.date_input("Data Final:", datetime.now().date() + timedelta(days=1), key="fim_p")
                
            # Tratamento de Timestamps idênticos para evitar o erro de cruzamento do Pandas
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
                df_exibicao_p['Data Entrega'] = df_exibicao_p['Data Exhibição'].dt.strftime('%d/%m/%Y') if 'Data Exhibição' in df_exibicao_p else df_exibicao_p['Data Entrega'].dt.strftime('%d/%m/%Y')
                st.dataframe(
                    df_exibicao_p[["RE", "Funcionário", "Departamento", "EPI", "Qtd", "Data Entrega", "Status"]],
                    use_container_width=True
                )
