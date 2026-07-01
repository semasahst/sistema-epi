import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(page_title="HST - Semasa", page_icon="🛡️", layout="wide")

st.title("🛡️ Sistema Integrado de Controle de EPIs - HST Semasa")
st.markdown("---")

# URL pública da sua planilha do Google Sheets
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1vL-5EqVshfUAmJY-3DlMfRpxtgfCvD5TaNLCxU4BPUE/edit"

# Conexão nativa com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Menu Lateral de Navegação
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "Visualizar Tabelas Reais"])

if menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI (Direto no Sheets)")
    
    # 1. CARREGA OS DADOS REAIS DAS ABAS DO GOOGLE SHEETS
    try:
        df_func = conn.read(spreadsheet=URL_PLANILHA, worksheet="tb_funcionarios", ttl="5m")
        df_epis = conn.read(spreadsheet=URL_PLANILHA, worksheet="tb_epis", ttl="5m")
    except Exception as e:
        st.error("❌ Erro ao conectar com o Google Sheets. Verifique se a planilha está compartilhada como 'Qualquer pessoa com o link pode ler'.")
        st.stop()

    col1, col2 = st.columns(2)
    
    with col1:
        re_input = st.text_input("Digite o RE do Funcionário:")
        nome_func = ""
        depto_func = ""
        
        if re_input:
            # Certifica que a coluna RE seja tratada como texto para busca perfeita
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
        # Assume que Coluna A = Nome, Coluna B = CA
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
            with st.spinner("Gravando dados na planilha..."):
                # Carrega o histórico atual de entregas para anexar as novas linhas
                df_entregas_atual = conn.read(spreadsheet=URL_PLANILHA, worksheet="tb_entregas", ttl="0m")
                
                novas_linhas = []
                for epi_formatado in epis_selecionados:
                    nome_epi_limpo = epi_formatado.split(" (CA:")[0].strip()
                    
                    # Cria a linha correspondente ao formato da sua aba tb_entregas
                    nova_linha = {
                        df_entregas_atual.columns[0]: re_input.strip(),
                        df_entregas_atual.columns[1]: nome_func,
                        df_entregas_atual.columns[2]: nome_epi_limpo,
                        df_entregas_atual.columns[3]: data_entrega.strftime('%Y-%m-%d')
                    }
                    novas_linhas.append(nova_linha)
                
                # Junta o histórico antigo com os novos lançamentos
                df_novas_entregas = pd.DataFrame(novas_linhas)
                df_final = pd.concat([df_entregas_atual, df_novas_entregas], ignore_index=True)
                
                # Salva de volta na aba correspondente do Sheets
                conn.update(spreadsheet=URL_PLANILHA, worksheet="tb_entregas", data=df_final)
                
                st.success(f"✅ Perfeito! {len(epis_selecionados)} EPI(s) gravado(s) com sucesso direto na sua planilha do Google Sheets!")
                st.balloons()

elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    
    tab1, tab2 = st.tabs(["Histórico tb_entregas", "Lista tb_funcionarios"])
    
    with tab1:
        df_entregas_view = conn.read(spreadsheet=URL_PLANILHA, worksheet="tb_entregas", ttl="0m")
        st.dataframe(df_entregas_view, use_container_width=True)
        
    with tab2:
        df_func_view = conn.read(spreadsheet=URL_PLANILHA, worksheet="tb_funcionarios", ttl="10m")
        st.dataframe(df_func_view, use_container_width=True)
