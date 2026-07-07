import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# Configuração global da página do Streamlit (Deve ser a primeira instrução)
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# ==============================================================================
# ENDEREÇOS DAS FONTES DE DADOS (GOOGLE SHEETS - LINK DE EXPORTAÇÃO CORRIGIDO)
# ==============================================================================
URL_RESPOSTAS = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv&gid=339151256"
URL_FUNCIONARIOS = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv&gid=1116669931"
URL_EPIS = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DIMfRpxtgFCvD5TaNLCxU4BPUE/export?format=csv&gid=754637684"

# URL do seu Formulário Google (Google Forms) para a aba de lançamentos
URL_FORMULARIO_GOOGLE = "https://docs.google.com/forms/d/e/1FAIpQLSfRZgRoIfEHUuanvhsMpkfXMSo7BslH_9Oj16nBNhIgSEw0Fg/viewform?usp=sharing&ouid=117567935732640452105"

# ==============================================================================
# CARREGAMENTO DOS DADOS OPERACIONAIS COM SISTEMA DE TRATAMENTO DE ERROS
# ==============================================================================
@st.cache_data(ttl=15)
def buscar_dados_planilhas():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = buscar_dados_planilhas()

# ==============================================================================
# ENGENHARIA DE DADOS MASTER: TRATAMENTO ROBUSTO DE ALERTAS E PENDÊNCIAS
# ==============================================================================
def construir_base_alertas():
    try:
        df_hist = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except Exception as e:
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    # Identificação estrutural baseada estritamente nas posições das colunas
    col_timestamp = df_hist.columns[0]
    col_re = df_hist.columns[1]
    col_func = df_hist.columns[2]
    col_epi = df_hist.columns[3]
    col_data = df_hist.columns[4]
    col_qtd = df_hist.columns[5]

    linhas_processadas = []
    hoje = pd.to_datetime(datetime.now().date())
    
    # Dicionários dinâmicos de busca (EPI -> Validade / Código CA)
    mapa_validades = {}
    mapa_ca = {}
    if not df_epis.empty:
        mapa_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
        mapa_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    for _, row in df_hist.iterrows():
        re_val = str(row[col_re]).strip()
        nome_func = str(row[col_func]).strip()
        nome_epi = str(row[col_epi]).strip()
        qtd_val = str(row[col_qtd]).strip()
        raw_timestamp = str(row[col_timestamp]).strip()
        raw_data_entrega = str(row[col_data]).strip()
        
        if not re_val or re_val == 'nan' or re_val == '':
            continue

        # ✍️ RECONHECIMENTO INTEGRADO DE FILTROS DE ASSINATURA PENDENTE
        if "PENDENTE" in raw_data_entrega.upper() or "PENDENTE" in raw_timestamp.upper():
            status_assinatura = "Pendente"
            if len(raw_data_entrega) >= 10:
                raw_data_entrega = raw_data_entrega[:10].strip()
        else:
            status_assinatura = "Assinado"
            
        # Tratamento de datas unificado via biblioteca do Pandas
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega, errors='coerce')
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_timestamp.split()[0], dayfirst=True, errors='coerce')
        
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = hoje
            
        # Limpeza definitiva de horas para blindar contra discrepância de tipos
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
            
        # Cálculo do ciclo de vida útil do equipamento de proteção
        dias_validade = mapa_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        
        status_validade = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        # Mapeamento do setor do colaborador utilizando dados cruzados da tb_funcionarios
        departamento = "Não Informado"
        if not df_func.empty:
            re_limpo_busca = re_val.split('.')[0].strip()
            f_match = df_func[df_func.iloc[:, 0].astype(str).str.split('.').str[0].str.strip() == re_limpo_busca]
            if not f_match.empty: 
                departamento = str(f_match.iloc[0, 2]).strip()
        
        try:
            quantidade = int(float(qtd_val))
        except:
            quantidade = 1
        
        linhas_processadas.append({
            "RE": re_val.split('.')[0].strip(),
            "Funcionário": nome_func, 
            "Departamento": departamento,
            "EPI": nome_epi, 
            "CA": mapa_ca.get(nome_epi, "N/A"), 
            "Qtd": quantidade,
            "Data Entrega": dt_entrega_parsed, 
            "Data Vencimento": dt_vencimento,
            "Dias Restantes": dias_restantes, 
            "Status": status_validade, 
            "Assinatura": status_assinatura
        })
        
    return pd.DataFrame(linhas_processadas) if linhas_processadas else pd.DataFrame()

# Criação do DataFrame central unificado
df_base_completa = construir_base_alertas()

# ==============================================================================
# MENU LATERAL INTERATIVO (ADICIONADA A OPÇÃO DE LANÇAMENTO)
# ==============================================================================
st.sidebar.markdown("## 🧭 Navegação Sistema")
menu = st.sidebar.selectbox(
    "Escolha a Visão:", 
    ["📝 Lançar Novos EPIs", "📊 Dashboard de Gestão", "⚠️ EPIs Vencidos/A Vencer"]
)

# ==============================================================================
# VISÃO NOVA/RECONSTRUÍDA: FORMULÁRIO DE LANÇAMENTO DE EPIS
# ==============================================================================
if menu == "📝 Lançar Novos EPIs":
    st.header("📝 Registro de Entrega de Equipamentos de Proteção")
    st.markdown("Utilize o formulário integrado abaixo para registrar as novas entregas de EPIs. Os dados serão sincronizados automaticamente com os painéis indicadores.")
    
    # Renderiza o Google Forms de forma embutida (Iframe) na tela de forma limpa
    st.components.v1.iframe(URL_FORMULARIO_GOOGLE, height=800, scrolling=True)


elif df_base_completa.empty:
    st.error("❌ Erro de comunicação com os servidores do Google Sheets ou nenhuma resposta registrada.")
    st.info("Verifique a sua conexão com a internet ou as permissões de compartilhamento das planilhas.")
else:

    # ==============================================================================
    # VISÃO 1: DASHBOARD ANALÍTICO
    # ==============================================================================
    if menu == "📊 Dashboard de Gestão":
        st.header("📊 Painel de Indicadores Estratégicos - HST Semasa")
        
        st.markdown("### 📅 Filtros de Período Temporal")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            data_ini_dash = st.date_input("De:", datetime.now().date() - timedelta(days=90))
        with col_d2:
            data_fim_dash = st.date_input("Até:", datetime.now().date())
            
        dt_i = pd.to_datetime(data_ini_dash)
        dt_f = pd.to_datetime(data_fim_dash)
        
        df_dash = df_base_completa[
            (df_base_completa['Data Entrega'] >= dt_i) & 
            (df_base_completa['Data Entrega'] <= dt_f)
        ]
        
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
            st.markdown("#### Volumetria de Consumo por Setor / Unidade")
            if not df_dash.empty:
                df_setor = df_dash.groupby('Departamento')['Qtd'].sum().reset_index()
                st.bar_chart(data=df_setor, x='Departamento', y='Qtd', use_container_width=True)
            else:
                st.info("Nenhuma movimentação identificada neste intervalo.")
                
        with col_g2:
            st.markdown("#### Distribuição de Consumo por Modelo de EPI")
            if not df_dash.empty:
                df_ranking = df_dash.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False)
                st.bar_chart(data=df_ranking, x='EPI', y='Qtd', use_container_width=True)
            else:
                st.info("Nenhuma movimentação identificada neste intervalo.")

    # ==============================================================================
    # VISÃO 2: GERENCIAMENTO DE LOGÍSTICA E PRAZOS
    # ==============================================================================
    elif menu == "⚠️ EPIs Vencidos/A Vencer":
        st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
        
        aba_validade, aba_assinaturas = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
        
        with aba_validade:
            st.markdown("### 🔍 Visão Ampla de Validade")
            df_exibicao_val = df_base_completa.copy()
            df_exibicao_val['Data Entrega'] = df_exibicao_val['Data Entrega'].dt.strftime('%d/%m/%Y')
            df_exibicao_val['Data Vencimento'] = df_exibicao_val['Data Vencimento'].dt.strftime('%d/%m/%Y')
            st.dataframe(df_exibicao_val.sort_values(by="Dias Restantes"), use_container_width=True)
            
        with aba_assinaturas:
            st.markdown("### 🔍 Triagem Avançada de Pendências")
            col_f1, col_f2, col_f3 = st.columns(3)
            
            with col_f1:
                lista_deptos = sorted(list(df_base_completa['Departamento'].unique()))
                depto_sel = st.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
                
            with col_f2:
                data_ini_p = st.date_input("Início Período:", datetime.now().date() - timedelta(days=60), key="ini_p")
            with col_f3:
                data_fim_p = st.date_input("Fim Período:", datetime.now().date() + timedelta(days=1), key="fim_p")
                
            dt_i_p = pd.to_datetime(data_ini_p)
            dt_f_p = pd.to_datetime(data_fim_p)
            
            df_pendentes = df_base_completa[
                (df_base_completa['Assinatura'] == "Pendente") & 
                (df_base_completa['Departamento'].isin(depto_sel)) &
                (df_base_completa['Data Entrega'] >= dt_i_p) & 
                (df_base_completa['Data Entrega'] <= dt_f_p)
            ]
            
            st.markdown(f"📋 **Pendências Ativas:** {len(df_pendentes)} registros identificados.")
            
            if df_pendentes.empty:
                st.success("🎉 Excelente! Nenhuma assinatura pendente no sistema com os filtros atuais.")
            else:
                df_exibicao_p = df_pendentes.copy()
                df_exibicao_p['Data Entrega'] = df_exibicao_p['Data Entrega'].dt.strftime('%d/%m/%Y')
                st.dataframe(
                    df_exibicao_p[["RE", "Funcionário", "Departamento", "EPI", "Qtd", "Data Entrega", "Status"]],
                    use_container_width=True
                )
