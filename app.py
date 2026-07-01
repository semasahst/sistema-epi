import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# =========================================================================
# 1. CONFIGURAÇÃO DO BANCO DE DADOS (SQLite)
# =========================================================================
def conectar_banco():
    conn = sqlite3.connect('controle_epi.db')
    cursor = conn.cursor()
    
    # Criação das tabelas caso não existam
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS funcionarios (
            re TEXT PRIMARY KEY,
            nome TEXT,
            departamento TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS epis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            ca TEXT,
            validade_dias INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            re TEXT,
            nome_funcionario TEXT,
            id_epi INTEGER,
            nome_epi TEXT,
            data_entrega TEXT
        )
    ''')
    conn.commit()
    return conn

# Carga inicial de dados para teste se o banco estiver vazio
def carga_inicial():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM epis")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO epis (nome, ca, validade_dias) VALUES ('Luva de Vaqueta', '12345', 90)")
        cursor.execute("INSERT INTO epis (nome, ca, validade_dias) VALUES ('Óculos de Proteção', '45231', 180)")
        cursor.execute("INSERT INTO epis (nome, ca, validade_dias) VALUES ('Abafador de Ruídos', '98765', 365)")
        cursor.execute("INSERT INTO funcionarios (re, nome, departamento) VALUES ('1010', 'Carlos Silva', 'Manutenção')")
        cursor.execute("INSERT INTO funcionarios (re, nome, departamento) VALUES ('2020', 'Ana Souza', 'Laboratório')")
        conn.commit()
    conn.close()

# =========================================================================
# 2. INTERFACE VISUAL (Streamlit)
# =========================================================================
st.set_page_config(page_title="HST - Semasa", page_icon="🛡️", layout="wide")
carga_inicial()

st.title("🛡️ Sistema Integrado de Controle de EPIs - HST Semasa")
st.markdown("---")

# Menu Lateral de Navegação
menu = st.sidebar.selectbox("Navegação", ["Lançar Entrega", "Cadastrar Funcionário/EPI", "Histórico de Entregas"])

if menu == "Lançar Entrega":
    st.header("📋 Registrar Nova Entrega de EPI")
    
    conn = conectar_banco()
    
    col1, col2 = st.columns(2)
    
    with col1:
        re_input = st.text_input("Digite o RE do Funcionário:")
        nome_func = ""
        depto_func = ""
        
        if re_input:
            cursor = conn.cursor()
            cursor.execute("SELECT nome, departamento FROM funcionarios WHERE re = ?", (re_input.strip(),))
            resultado = cursor.fetchone()
            if resultado:
                nome_func = resultado[0]
                depto_func = resultado[1]
                st.success(f"👤 **Colaborador:** {nome_func} | **Depto:** {depto_func}")
            else:
                st.error("❌ Funcionário não encontrado no banco de dados.")
    
    with col2:
        data_entrega = st.date_input("Data da Entrega", datetime.now())
        
    # Carrega os EPIs para a Seleção Múltipla
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, ca FROM epis")
    lista_epis = cursor.fetchall()
    
    # Formata o texto para aparecer "Nome (CA: XXXXX)" na tela
    opcoes_epis = {f"{item[1]} (CA: {item[2]})": item[0] for item in lista_epis}
    
    epis_selecionados = st.multiselect("Selecione um ou mais EPIs entregues:", list(opcoes_epis.keys()))
    
    if st.button("🚀 GRAVAR ENTREGA", type="primary"):
        if not re_input or not nome_func:
            st.error("Por favor, insira um RE válido antes de gravar.")
        elif len(epis_selecionados) == 0:
            st.error("Selecione pelo menos um EPI.")
        else:
            cursor = conn.cursor()
            for epi_formatado in epis_selecionados:
                epi_id = opcoes_epis[epi_formatado]
                # Isola o nome limpo retirando o CA para salvar no histórico
                nome_epi_limpo = epi_formatado.split(" (CA:")[0]
                
                cursor.execute('''
                    INSERT INTO entregas (re, nome_funcionario, id_epi, nome_epi, data_entrega)
                    VALUES (?, ?, ?, ?, ?)
                ''', (re_input.strip(), nome_func, epi_id, nome_epi_limpo, data_entrega.strftime('%Y-%m-%d')))
                
            conn.commit()
            st.success(f"✅ Sucesso! {len(epis_selecionados)} EPI(s) registrado(s) para {nome_func}.")
            
    conn.close()

elif menu == "Cadastrar Funcionário/EPI":
    st.header("➕ Cadastros do Sistema")
    
    tab1, tab2 = st.tabs(["Funcionário", "Equipamento (EPI)"])
    
    with tab1:
        st.subheader("Cadastrar Novo Funcionário")
        re_new = st.text_input("RE:")
        nome_new = st.text_input("Nome Completo:")
        depto_new = st.text_input("Departamento:")
        
        if st.button("Salvar Funcionário"):
            if re_new and nome_new and depto_new:
                conn = conectar_banco()
                cursor = conn.cursor()
                try:
                    cursor.execute("INSERT INTO funcionarios (re, nome, departamento) VALUES (?, ?, ?)", (re_new, nome_new, depto_new))
                    conn.commit()
                    st.success("Funcionário cadastrado com sucesso!")
                except sqlite3.IntegrityError:
                    st.error("Este RE já está cadastrado.")
                conn.close()
            else:
                st.warning("Preencha todos os campos.")
                
    with tab2:
        st.subheader("Cadastrar Novo EPI")
        nome_epi = st.text_input("Nome do EPI:")
        ca_epi = st.text_input("Número do CA:")
        validade_epi = st.number_input("Dias de Validade do EPI:", min_value=1, value=90)
        
        if st.button("Salvar EPI"):
            if nome_epi and ca_epi:
                conn = conectar_banco()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO epis (nome, ca, validade_dias) VALUES (?, ?, ?)", (nome_epi, ca_epi, validade_epi))
                conn.commit()
                conn.close()
                st.success("EPI cadastrado com sucesso!")
            else:
                st.warning("Preencha todos os campos.")

elif menu == "Histórico de Entregas":
    st.header("📜 Histórico Geral de Entregas")
    conn = conectar_banco()
    df = pd.read_sql_query("SELECT re AS RE, nome_funcionario AS Funcionário, nome_epi AS [EPI Entregue], data_entrega AS [Data da Entrega] FROM entregas ORDER BY id DESC", conn)
    conn.close()
    
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhuma entrega registrada até o momento.")
