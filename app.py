import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(page_title="HST - Semasa", page_icon="🛡️", layout="wide")

st.title("🛡️ Sistema Integrado de Controle de EPIs - HST Semasa")
st.markdown("---")

# ID da sua planilha do Google Sheets para LEITURA
CHAVE_PLANILHA = "1vL-5EqVshfUAmJY-3DlMfRpxtgfCvD5TaNLCxU4BPUE"

# URL de envio do Google Forms para GRAVAÇÃO
URL_FORM_POST = "https://docs.google.com/forms/d/e/1FAIpQLSfRZgRoIfEHUuanvhsMpkfXMSo7BslH_9Oj16nBNhIgSEw0Fg/formResponse"

# Links de leitura direta das abas em formato CSV
URL_FUNCIONARIOS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_funcionarios"
URL_EPIS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=tb_epis"
URL_RESPOSTAS = f"https://docs.google.com/spreadsheets/d/{CHAVE_PLANILHA}/gviz/tq?tqx=out:csv&sheet=Respostas%20ao%20formul%C3%A1rio%201"

# Menu Lateral de Navegação
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "Visualizar Tabelas Reais"])

if menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI")
    
    # CARREGA OS DADOS REAIS DAS ABAS DO GOOGLE SHEETS
    try:
        df_func = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_epis = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
    except Exception as e:
        st.error("❌ Erro ao ler dados da planilha. Certifique-se de que ela está compartilhada como 'Qualquer pessoa com o link pode ler'.")
        st.stop()

    col1, col2 = st.columns(2)
    
    with col1:
        re_input = st.text_input("Digite o RE do Funcionário:").strip()
        nome_func = ""
        depto_func = ""
        
        if re_input and not df_func.empty:
            re_procurado = str(re_input)
            funcionario = df_func[df_func.iloc[:, 0].astype(str).str.strip() == re_procurado]
            
            if not funcionario.empty:
                nome_func = funcionario.iloc[0, 1]
                depto_func = funcionario.iloc[0, 2]
                st.success(f"👤 **Colaborador:** {nome_func} | **Depto:** {depto_func}")
            else:
                st.error(f"❌ RE '{re_procurado}' não encontrado na aba tb_funcionarios.")
    
    with col2:
        data_entrega = st.date_input("Data da Entrega", datetime.now())
        
    # Prepara a lista suspensa de EPIs puxando direto da aba tb_epis
    lista_opcoes_epis = []
    if not df_epis.empty:
        try:
            df_epis['Exibicao'] = df_epis.iloc[:, 0].astype(str) + " (CA: " + df_epis.iloc[:, 1].astype(str) + ")"
            lista_opcoes_epis = df_epis['Exibicao'].tolist()
        except:
            st.warning("⚠️ Formato inesperado na aba tb_epis. Verifique as colunas.")
        
    epis_selecionados = st.multiselect("Selecione um ou mais EPIs entregues:", lista_opcoes_epis)
    
    if st.button("🚀 GRAVAR ENTREGA NO GOOGLE SHEETS", type="primary"):
        if not re_input or not nome_func:
            st.error("Por favor, insira um RE válido antes de gravar.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione pelo menos um EPI.")
        else:
            sucesso_envio = True
            with st.spinner("Gravando dados na planilha..."):
                for epi_formatado in epis_selecionados:
                    nome_epi_limpo = epi_formatado.split(" (CA:")[0].strip()
                    
                    # Dicionário atualizado com as chaves corretas extraídas do código-fonte
                    dados_formulario = {
                        "entry.2087142219": re_input,
                        "entry.1719783905": nome_func,
                        "entry.791852446": nome_epi_limpo,
                        "entry.1336399804": data_entrega.strftime('%Y-%m-%d')
                    }
                    
                    # Faz o disparo via POST HTTP para a nuvem do Google
                    resposta = requests.post(URL_FORM_POST, data=dados_formulario)
                    if resposta.status_code != 200:
                        sucesso_envio = False
            
            if sucesso_envio:
                st.success(f"✅ Perfeito! {len(epis_selecionados)} EPI(s) gravado(s) com sucesso direto na sua planilha!")
                st.balloons()
            else:
                st.error("⚠️ Ocorreu um problema ao enviar alguns itens. Verifique as configurações de acesso do formulário.")

elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    
    tab1, tab2 = st.tabs(["Histórico de Respostas", "Lista tb_funcionarios"])
    
    with tab1:
        try:
            df_entregas_view = pd.read_csv(URL_RESPOSTAS, dtype=str)
            st.dataframe(df_entregas_view, use_container_width=True)
        except:
            st.info("Aba de respostas vazia ou ainda processando dados iniciais.")
        
    with tab2:
        try:
            df_func_view = pd.read_csv(URL_FUNCIONARIOS, dtype=str)
            st.dataframe(df_func_view, use_container_width=True)
        except:
            st.info("Aba tb_funcionarios inacessível.")
