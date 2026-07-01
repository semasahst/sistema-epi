import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

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
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "⚠️ EPIs Vencidos/A Vencer", "Visualizar Tabelas Reais"])

# CARREGA OS DADOS GERAIS DO GOOGLE SHEETS
try:
    df_func = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
    df_epis = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
except Exception as e:
    st.error("❌ Erro ao conectar com o Google Sheets. Verifique o compartilhamento da planilha.")
    st.stop()

if menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI")
    
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
        
    lista_opcoes_epis = []
    if not df_epis.empty:
        try:
            df_epis['Exibicao'] = df_epis.iloc[:, 0].astype(str) + " (CA: " + df_epis.iloc[:, 1].astype(str) + ")"
            lista_opcoes_epis = df_epis['Exibicao'].tolist()
        except:
            st.warning("⚠️ Formato inesperado na aba tb_epis.")
        
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
                    
                    dados_formulario = {
                        "entry.2087142219": re_input,
                        "entry.1719783905": nome_func,
                        "entry.791852446": nome_epi_limpo,
                        "entry.1336399804": data_entrega.strftime('%Y-%m-%d')
                    }
                    
                    resposta = requests.post(URL_FORM_POST, data=dados_formulario)
                    if resposta.status_code != 200:
                        sucesso_envio = False
            
            if sucesso_envio:
                st.success(f"✅ Perfeito! {len(epis_selecionados)} EPI(s) gravado(s) com sucesso direto na sua planilha!")
                st.balloons()
            else:
                st.error("⚠️ Ocorreu um problema ao enviar alguns itens.")

elif menu == "⚠️ EPIs Vencidos/A Vencer":
    st.header("⚠️ Monitor de Controle de Validade de EPIs")
    st.markdown("O sistema analisa a última entrega de cada EPI para cada funcionário e projeta o vencimento com base na tabela oficial de equipamentos.")
    
    try:
        df_historico = pd.read_csv(URL_RESPOSTAS, dtype=str).dropna(how='all')
    except:
        df_historico = pd.DataFrame()
        
    if df_historico.empty:
        st.info("ℹ️ Nenhuma entrega registrada no histórico para análise.")
    else:
        # Renomeia ou mapeia as colunas do formulário dinamicamente
        # Carimbo de data/hora, RE, Funcionário, EPI, Data
        df_historico.columns = ['Timestamp', 'RE', 'Funcionário', 'EPI', 'Data_Entrega']
        
        # Converte a coluna de data para o formato correto de cálculo
        df_historico['Data_Entrega'] = pd.to_datetime(df_historico['Data_Entrega'], errors='coerce')
        
        # Remove registros com datas inválidas
        df_historico = df_historico.dropna(subset=['Data_Entrega'])
        
        # Filtra para pegar apenas a ÚLTIMA entrega de cada EPI para cada Funcionário
        df_ultimas_entregas = df_historico.sort_values('Data_Entrega').groupby(['RE', 'EPI']).last().reset_index()
        
        # Mapeia os dias de validade de cada EPI
        # Coluna 0 = Nome do EPI, Coluna 1 = CA, Coluna 2 = Dias de Validade
        dicionario_validades = {}
        dicionario_ca = {}
        for _, row in df_epis.iterrows():
            nome_limpo = str(row.iloc[0]).strip()
            try:
                dicionario_validades[nome_limpo] = int(row.iloc[2])
            except:
                dicionario_validades[nome_limpo] = 90 # Valor padrão caso esteja em branco
            dicionario_ca[nome_limpo] = str(row.iloc[1]).strip()
            
        # Calcula as datas de vencimento e status
        linhas_alertas = []
        hoje = datetime.now()
        
        for _, row in df_ultimas_entregas.iterrows():
            re_func = row['RE']
            nome_func = row['Funcionário']
            nome_epi = str(row['EPI']).strip()
            dt_entrega = row['Data_Entrega']
            
            dias_validade = dicionario_validades.get(nome_epi, 90)
            ca_epi = dicionario_ca.get(nome_epi, "N/A")
            
            dt_vencimento = dt_entrega + timedelta(days=dias_validade)
            dias_restantes = (dt_vencimento - hoje).days
            
            # Define o status do Alerta
            if dias_restantes < 0:
                status = "🔴 VENCIDO"
            elif dias_restantes <= 15:
                status = "🟡 CRÍTICO (Até 15 dias)"
            else:
                status = "🟢 Regular"
                
            # Busca o departamento do funcionário
            depto = "Não Informado"
            if not df_func.empty:
                f_match = df_func[df_func.iloc[:, 0].astype(str).str.strip() == str(re_func).strip()]
                if not f_match.empty:
                    depto = f_match.iloc[0, 2]
            
            linhas_alertas.append({
                "RE": re_func,
                "Funcionário": nome_func,
                "Departamento": depto,
                "EPI": nome_epi,
                "CA": ca_epi,
                "Data Entrega": dt_entrega.strftime('%d/%m/%Y'),
                "Data Vencimento": dt_vencimento.strftime('%d/%m/%Y'),
                "Dias Restantes": dias_restantes,
                "Status": status
            })
            
        df_alertas_final = pd.DataFrame(linhas_alertas)
        
        # Filtros no Painel
        st.markdown("### 🔍 Filtros de Monitoramento")
        c1, c2 = st.columns(2)
        with c1:
            filtro_status = st.multiselect("Filtrar por Status:", ["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)", "🟢 Regular"], default=["🔴 VENCIDO", "🟡 CRÍTICO (Até 15 dias)"])
        with c2:
            lista_deptos = sorted(list(df_alertas_final['Departamento'].unique())) if not df_alertas_final.empty else []
            filtro_depto = st.multiselect("Filtrar por Departamento:", lista_deptos)
            
        # Aplica os filtros na tabela
        if not df_alertas_final.empty:
            if filtro_status:
                df_alertas_final = df_alertas_final[df_alertas_final['Status'].isin(filtro_status)]
            if filtro_depto:
                df_alertas_final = df_alertas_final[df_alertas_final['Departamento'].isin(filtro_depto)]
                
            # Ordena pelos prazos mais urgentes
            df_alertas_final = df_alertas_final.sort_values(by="Dias Restantes")
            
            # Apresenta os indicadores rápidos (Cards)
            vencidos_qtd = len(df_alertas_final[df_alertas_final['Status'] == "🔴 VENCIDO"])
            criticos_qtd = len(df_alertas_final[df_alertas_final['Status'] == "🟡 CRÍTICO (Até 15 dias)"])
            
            col_card1, col_card2 = st.columns(2)
            col_card1.metric(label="🚨 Funcionários com EPI Vencido", value=vencidos_qtd, delta=f"{vencidos_qtd} urgentes", delta_color="inverse")
            col_card2.metric(label="⚠️ EPIs Próximos do Vencimento", value=criticos_qtd, delta=f"{criticos_qtd} atenção")
            
            st.markdown("### 📋 Listagem Consolidada de Prazos")
            st.dataframe(df_alertas_final, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 Nenhum registro encontrado para os filtros selecionados!")

elif menu == "Visualizar Tabelas Reais":
    st.header("📊 Dados Atuais do Google Sheets")
    
    tab1, tab2 = st.tabs(["Histórico de Respostas", "Lista tb_funcionarios"])
    with tab1:
        try:
            df_entregas_view = pd.read_csv(URL_RESPOSTAS, dtype=str)
            st.dataframe(df_entregas_view, use_container_width=True)
        except:
            st.info("Aba de respostas vazia.")
    with tab2:
        try:
            df_func_view = pd.read_csv(URL_FUNCIONARIOS, dtype=str)
            st.dataframe(df_func_view, use_container_width=True)
        except:
            st.info("Aba tb_funcionarios inacessível.")
