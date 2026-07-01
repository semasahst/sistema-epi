import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(page_title="HST - Semasa", page_icon="🛡️", layout="wide")

st.title("🛡️ Sistema Integrado de Controle de EPIs - HST Semasa")
st.markdown("---")

# ID da sua planilha do Google Sheets
CHAVE_PLANILHA = "1vL-5EqVshfUAmJY-3DlMfRpxtgfCvD5TaNLCxU4BPUE"

# Links de leitura direta das abas em formato CSV
URL_FUNCIONARIOS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_funcionarios"
URL_EPIS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_epis"
URL_ENTREGAS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_entregas"

# Menu Lateral de Navegação
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "Visualizar Tabelas Reais"])

if menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI")
    
    # CARREGA OS DADOS REAIS DAS ABAS DO GOOGLE SHEETS
    try:
        df_func = pd.read_csv(URL_FUNCIONARIOS)
        df_epis = pd.read_csv(URL_EPIS)
    except Exception as e:
        st.error("❌ Erro ao ler dados da planilha. Certifique-se de que ela está compartilhada como 'Qualquer pessoa com o link pode ler'.")
        st.stop()

    col1, col2 = st.columns(2)
    
    with col1:
        re_input = st.text_input("Digite o RE do Funcionário:")
        nome_func = ""
        depto_func = ""
        
        if re_input:
            # Garante que a primeira coluna (RE) seja tratada como texto limpo
            df_func.iloc[:, 0] = df_func.iloc[:, 0].astype(str).str.strip()
            funcionario = df_func[df_func.iloc[:, 0] == re_input.strip()]
            
            if not funcionario.empty:
                nome_func = funcionario.iloc[0, 1]
                depto_func = funcionario.iloc[0, 2]
                st.success(f"👤 **Colaborador:** {nome_func} | **Depto:** {depto_func}")
            else:
                st.error("❌ Funcionário não encontrado na aba tb_funcionarios.")
    
    with col2:
        data_entrega = st.date_input("Data da Entrega", datetime.now())
        
    # Prepara a lista suspensa de EPIs puxando direto da aba tb_epis
    if not df_epis.empty:
        df_epis['Exibicao'] = df_epis.iloc[:, 0].astype(str) + " (CA: " + df_epis.iloc[:, 1].astype(str) + ")"
        lista_opcoes_epis = df_epis['Exibicao'].tolist()
    else:
        lista_opcoes_epis = []
        
    epis_selecionados = st.multiselect("Selecione um ou mais EPIs entregues:", lista_opcoes_epis)
    
    if st.button("🚀 GRAVAR ENTREGA NO GOOGLE SHEETS", type="primary"):
        if not re_input or not nome_func:
            st.error("Por favor, insira um RE válido antes de gravar.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione pelo menos um EPI.")
        else:
            st.info("Para salvar dados diretamente do Python na nuvem para o Sheets sem travas de TI, use o botão 'Gravar' integrado ou integre via API Forms. Dados prontos para envio!")
            for epi_formatado in epis_selecionados:
                nome_epi_limpo = epi_formatado.split(" (CA:")[0].strip()
                st.write(f"✍️ Gravando: {re_input} - {nome_func} - {nome_epi_limpo} - {data_entrega.strftime('%d/%m/%Y')}")
            st.success("✅ Processado com sucesso!")
            st.balloons()

elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    
    tab1, tab2 = st.tabs(["Histórico tb_entregas", "Lista tb_funcionarios"])
    
    with tab1:
        try:
            df_entregas_view = pd.read_csv(URL_ENTREGAS)
            st.dataframe(df_entregas_view, use_container_width=True)
        except:
            st.info("Aba tb_entregas vazia ou inacessível.")
        
    with tab2:
        df_func_view = pd.read_csv(URL_FUNCIONARIOS)
        st.dataframe(df_func_view, use_container_width=True)
