import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import base64
import io

# Configuração global da página do Streamlit
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DE ACESSO AO REPOSITÓRIO (GITHUB)
# ==============================================================================
GITHUB_USER = "semasahst"  
GITHUB_REPO = "sistema-epi"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")

URL_RESPOSTAS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/respostas.csv"
URL_FUNCIONARIOS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/funcionarios.csv"
URL_EPIS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/epis.csv"

# ==============================================================================
# CARREGAMENTO DOS DADOS COM TRATAMENTO DE ERROS
# ==============================================================================
@st.cache_data(ttl=2)
def buscar_dados_planilhas():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except:
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = buscar_dados_planilhas()

# ==============================================================================
# FUNÇÃO MASTER DE GRAVAÇÃO UNIFICADA (ALINHADA COM A PLANILHA REAL)
# ==============================================================================
def salvar_lote_no_github(novas_linhas_lista):
    if not GITHUB_TOKEN:
        st.error("❌ Erro: GITHUB_TOKEN não configurado nas Secrets.")
        return False
        
    url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    req_get = requests.get(url_api, headers=headers)
    if req_get.status_code == 200:
        dados_repo = req_get.json()
        sha_arquivo = dados_repo['sha']
        conteudo_antigo = base64.b64decode(dados_repo['content']).decode('utf-8')
        df_atual = pd.read_csv(io.StringIO(conteudo_antigo), header=None, dtype=str)
    else:
        try:
            df_atual = pd.read_csv(URL_RESPOSTAS, header=None, dtype=str)
            sha_arquivo = ""
        except:
            return False

    df_novas = pd.DataFrame(novas_linhas_lista)
    df_final = pd.concat([df_atual, df_novas], ignore_index=True)
    
    csv_string = df_final.to_csv(index=False, header=False)
    conteudo_base64 = base64.b64encode(csv_string.encode('utf-8')).decode('utf-8')
    
    payload = {
        "message": f"Atualização em lote: {len(novas_linhas_lista)} registros",
        "content": conteudo_base64,
        "sha": sha_arquivo
    }
    
    req_put = requests.put(url_api, headers=headers, json=payload)
    return req_put.status_code in [200, 201]

# ==============================================================================
# FUNÇÃO PARA GRAVAR EDITIONS/BAIXAS DE ASSINATURA
# ==============================================================================
def atualizar_csv_completo(df_novo):
    url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    req_get = requests.get(url_api, headers=headers)
    if req_get.status_code == 200:
        sha_arquivo = req_get.json()['sha']
        csv_string = df_novo.to_csv(index=False, header=False)
        conteudo_base64 = base64.b64encode(csv_string.encode('utf-8')).decode('utf-8')
        payload = {"message": "Baixa em assinaturas pendentes", "content": conteudo_base64, "sha": sha_arquivo}
        req_put = requests.put(url_api, headers=headers, json=payload)
        return req_put.status_code in [200, 201]
    return False

# ==============================================================================
# CONSTRUÇÃO DA BASE DE ALERTAS COM MAPEAMENTO CIRÚRGICO DAS COLUNAS REALISTAS
# ==============================================================================
def construir_base_alertas():
    try:
        # Lê sem cabeçalho para garantir precisão pelos índices das colunas reais
        df_hist = pd.read_csv(URL_RESPOSTAS, header=None, dtype=str).dropna(how='all')
    except:
        return pd.DataFrame()
        
    if df_hist.empty:
        return pd.DataFrame()
        
    linhas_processadas = []
    hoje = pd.to_datetime(datetime.now().date())
    
    mapa_validades = {}
    mapa_ca = {}
    if not df_epis.empty:
        mapa_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
        mapa_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    # Mapeamento com base estrita no layout visual do GitHub enviado pelo usuário
    for idx, row in df_hist.iterrows():
        if len(row) < 6:
            continue
            
        nome_epi = str(row.iloc[1]).strip()       # Coluna B
        nome_func = str(row.iloc[4]).strip()      # Coluna E
        raw_data_entrega = str(row.iloc[5]).strip() # Coluna F (Onde está gravado "PENDENTE" ou a data)
        
        if not nome_func or nome_func == 'nan' or nome_func == '':
            continue

        # Identificação precisa do status pendente
        if "PENDENTE" in raw_data_entrega.upper():
            status_assinatura = "Pendente"
            raw_data_entrega_limpa = datetime.now().strftime("%d/%m/%Y")
        else:
            status_assinatura = "Assinado"
            raw_data_entrega_limpa = raw_data_entrega
            
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega_limpa, errors='coerce', dayfirst=True)
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_data_entrega_limpa, errors='coerce')
            if pd.isnull(dt_entrega_parsed):
                dt_entrega_parsed = hoje
            
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
        dias_validade = mapa_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        status_validade = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 dias)" if dias_restantes <= 15 else "🟢 Regular")
        
        # Faz a busca reversa do RE pelo Nome do Funcionário cadastrado na base funcionarios.csv
        re_vinculado = "N/A"
        departamento = "Não Informado"
        if not df_func.empty:
            f_match = df_func[df_func.iloc[:, 1].astype(str).str.strip().str.upper() == nome_func.upper()]
            if not f_match.empty:
                re_vinculado = str(f_match.iloc[0, 0]).split('.')[0].strip()
                departamento = str(f_match.iloc[0, 2]).strip()
        
        linhas_processadas.append({
            "INDEX_ORIGINAL": idx,
            "RE": re_vinculado,
            "Funcionário": nome_func, 
            "Departamento": departamento,
            "EPI": nome_epi, 
            "CA": mapa_ca.get(nome_epi, "N/A"), 
            "Qtd": 1,
            "Data Entrega": dt_entrega_parsed, 
            "Data Vencimento": dt_vencimento,
            "Dias Restantes": dias_restantes, 
            "Status": status_validade, 
            "Assinatura": status_assinatura
        })
        
    return pd.DataFrame(linhas_processadas) if linhas_processadas else pd.DataFrame()

df_base_completa = construir_base_alertas()

# ==============================================================================
# MENU LATERAL INTERATIVO
# ==============================================================================
st.sidebar.markdown("## 🧭 Navegação Sistema")
menu = st.sidebar.selectbox(
    "Escolha a Visão:", 
    ["📝 Lançar Novos EPIs", "✍️ Coletar Assinaturas Pendentes", "📊 Dashboard de Gestão", "⚠️ EPIs Vencidos/A Vencer"]
)

# ==============================================================================
# VISÃO 1: LANÇAMENTO COM REVERÇÃO E ENCAIXE EXATO DE COLUNAS
# ==============================================================================
if menu == "📝 Lançar Novos EPIs":
    st.header("📝 Registro de Entrega de Equipamentos de Proteção")
    
    if df_func.empty or df_epis.empty:
        st.warning("⚠️ Carregando tabelas base do GitHub...")
    else:
        df_func_limpo = df_func.dropna(subset=[df_func.columns[0], df_func.columns[1]])
        
        mapa_re_nome = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[1]).strip() for _, row in df_func_limpo.iterrows()}
        mapa_re_cracha = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[4]).strip() if len(row) > 4 else "" for _, row in df_func_limpo.iterrows()}
        mapa_cracha_nome = {str(row.iloc[4]).strip(): str(row.iloc[1]).strip() for _, row in df_func_limpo.iterrows() if len(row) > 4 and pd.notnull(row.iloc[4])}
        
        lista_epis = sorted(df_epis.iloc[:, 0].dropna().unique().tolist())
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            re_digitado = st.text_input("Digite o número do RE:", key="re_usuario").strip()
        with col_f2:
            nome_funcionario = mapa_re_nome.get(re_digitado, "")
            if re_digitado and not nome_funcionario: 
                st.error("❌ RE não localizado.")
            elif re_digitado and nome_funcionario: 
                st.info(f"👤 Colaborador: {nome_funcionario}")
                
        st.markdown("---")
        st.markdown("#### 💳 Autenticação e Validação")
        bypass_nfc = st.checkbox("⚠️ Liberar sem a presença do trabalhador (Gerar Assinatura Pendente)")
        
        situacao_assinatura = "PENDENTE"
        
        if not bypass_nfc:
            nfc_input = st.text_input("CLIQUE AQUI e aproxime o Crachá do Leitor NFC para assinar:", type="password").strip()
            if nfc_input and re_digitado:
                cracha_esperado = mapa_re_cracha.get(re_digitado, "")
                if nfc_input == cracha_esperado:
                    situacao_assinatura = "Assinado"
                    st.success("🟢 Crachá validado com sucesso!")
                else:
                    dono_desse_cracha = mapa_cracha_nome.get(nfc_input, "Desconhecido")
                    st.error(f"❌ Este crachá pertence a '{dono_desse_cracha}'! Registro ficará PENDENTE.")
        else:
            st.info("ℹ️ Modo Bypass Ativo: A entrega será salva com status 'PENDENTE'.")
            
        st.markdown("---")
        epis_selecionados = st.multiselect("Selecione os Equipamentos de Proteção (EPIs):", options=lista_epis, key="epis_usuario")
        data_entrega_sel = st.date_input("Data da Entrega:", value=datetime.now().date(), key="data_usuario")
            
        st.markdown("<br>", unsafe_allow_html=True)
        botao_salvar = st.button("💾 Gravar Lançamentos no Sistema")
        
        if botao_salvar:
            if not re_digitado or not nome_funcionario:
                st.error("❌ Digite um RE válido antes de salvar.")
            elif not epis_selecionados:
                st.error("❌ Selecione ao menos um EPI.")
            else:
                lote_linhas = []
                for epi in epis_selecionados:
                    # Monta o registro de forma cirúrgica para encaixar nas colunas A, B, C, D, E, F do repositório
                    lote_linhas.append({
                        0: "",                                                                       # Coluna A (Vazia)
                        1: str(epi),                                                                 # Coluna B (EPI)
                        2: "",                                                                       # Coluna C (Vazia)
                        3: "",                                                                       # Coluna D (Vazia)
                        4: str(nome_funcionario),                                                    # Coluna E (Funcionário)
                        5: data_entrega_sel.strftime("%Y-%m-%d") if situacao_assinatura == "Assinado" else "PENDENTE" # Coluna F (Status/Data)
                    })
                
                with st.spinner("Salvando lote no GitHub..."):
                    if salvar_lote_no_github(lote_linhas):
                        st.success(f"🎉 Gravado com sucesso para {nome_funcionario}!")
                        st.balloons()
                    else:
                        st.error("❌ Erro ao salvar no GitHub.")

# ==============================================================================
# VISÃO 2: ELIMINAÇÃO DE PENDÊNCIAS PELO RE FILTRADO VIA SELEÇÃO MAPEADA
# ==============================================================================
elif menu == "✍️ Coletar Assinaturas Pendentes":
    st.header("✍️ Regularização de Assinaturas Pendentes")
    st.markdown("Busque o RE do colaborador, confira os itens pendentes e aproxime o crachá do próprio trabalhador.")
    
    re_busca = st.text_input("Digite o RE do funcionário para buscar pendências:").strip()
    
    if re_busca:
        if df_base_completa.empty:
            st.info("Nenhum histórico encontrado.")
        else:
            df_pendentes_func = df_base_completa[(df_base_completa['RE'] == re_busca) & (df_base_completa['Assinatura'] == "Pendente")]
            
            if df_pendentes_func.empty:
                st.success("🎉 Este colaborador não possui nenhuma assinatura pendente no sistema!")
            else:
                st.warning(f"📋 Encontradas {len(df_pendentes_func)} entregas pendentes para este RE:")
                df_exibir = df_pendentes_func[["EPI", "Qtd", "Data Entrega"]].copy()
                df_exibir["Data Entrega"] = df_exibir["Data Entrega"].dt.strftime("%d/%m/%Y")
                st.dataframe(df_exibir, use_container_width=True)
                
                st.markdown("### 💳 Validação de Baixa Segura")
                nfc_baixa = st.text_input("APROXIME O CRACHÁ DO TRABALHADOR AQUI PARA ASSINAR TUDO:", type="password").strip()
                
                if nfc_baixa:
                    df_func_limpo = df_func.dropna(subset=[df_func.columns[0]])
                    mapa_re_cracha = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[4]).strip() if len(row) > 4 else "" for _, row in df_func_limpo.iterrows()}
                    mapa_cracha_nome = {str(row.iloc[4]).strip(): str(row.iloc[1]).strip() for _, row in df_func_limpo.iterrows() if len(row) > 4 and pd.notnull(row.iloc[4])}
                    
                    cracha_correto = mapa_re_cracha.get(re_busca, "")
                    
                    if nfc_baixa != cracha_correto:
                        dono_desse_cracha = mapa_cracha_nome.get(nfc_baixa, "Desconhecido")
                        st.error(f"❌ Bloqueado: Este crachá pertence a '{dono_desse_cracha}'!")
                    else:
                        with st.spinner("Processando assinaturas legítimas..."):
                            try:
                                url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
                                headers = {"Authorization": f"token {GITHUB_TOKEN}"}
                                req_get = requests.get(url_api, headers=headers)
                                
                                if req_get.status_code == 200:
                                    conteudo_bruto = base64.b64decode(req_get.json()['content']).decode('utf-8')
                                    df_raw_csv = pd.read_csv(io.StringIO(conteudo_bruto), header=None, dtype=str)
                                    
                                    indices_para_alterar = df_pendentes_func['INDEX_ORIGINAL'].tolist()
                                    data_hoje_str = datetime.now().strftime("%Y-%m-%d")
                                    
                                    for idx_orig in indices_para_alterar:
                                        # Sobrescreve especificamente a Coluna F (Índice 5) onde estava escrito PENDENTE
                                        df_raw_csv.iloc[int(idx_orig), 5] = data_hoje_str
                                    
                                    if atualizar_csv_completo(df_raw_csv):
                                        st.success(f"🎉 Sucesso! {len(indices_para_alterar)} pendências eliminadas e assinadas!")
                                        st.balloons()
                                    else:
                                        st.error("Erro ao salvar no GitHub.")
                            except Exception as ex:
                                st.error(f"Falha técnica: {ex}")

# ==============================================================================
# VISÕES DO DASHBOARD E ALERTAS
# ==============================================================================
else:
    if df_base_completa.empty:
        st.warning("Aguardando a sincronização dos dados...")
    else:
        if menu == "📊 Dashboard de Gestão":
            st.header("📊 Painel de Indicadores Estratégicos")
            col_d1, col_d2 = st.columns(2)
            with col_d1: data_ini_dash = st.date_input("De:", datetime.now().date() - timedelta(days=90))
            with col_d2: data_fim_dash = st.date_input("Até:", datetime.now().date())
            
            df_dash = df_base_completa[(df_base_completa['Data Entrega'] >= pd.to_datetime(data_ini_dash)) & (df_base_completa['Data Entrega'] <= pd.to_datetime(data_fim_dash))]
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total de EPIs Entregues", df_dash['Qtd'].sum() if not df_dash.empty else 0)
            c2.metric("Assinaturas Pendentes", len(df_dash[df_dash['Assinatura'] == "Pendente"]) if not df_dash.empty else 0)
            c3.metric("Itens Vencidos (NR-6)", len(df_dash[df_dash['Status'] == "🔴 VENCIDO"]) if not df_dash.empty else 0)
            
            st.markdown("---")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("#### Consumo por Setor")
                if not df_dash.empty: st.bar_chart(data=df_dash.groupby('Departamento')['Qtd'].sum().reset_index(), x='Departamento', y='Qtd')
            with col_g2:
                st.markdown("#### Modelos de EPI")
                if not df_dash.empty: st.bar_chart(data=df_dash.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False), x='EPI', y='Qtd')

        elif menu == "⚠️ EPIs Vencidos/A Vencer":
            st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
            aba_val, aba_ass = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
            with aba_val:
                df_exib_val = df_base_completa.copy()
                df_exib_val["Data Entrega"] = df_exib_val["Data Entrega"].dt.strftime("%d/%m/%Y")
                df_exib_val["Data Vencimento"] = df_exib_val["Data Vencimento"].dt.strftime("%d/%m/%Y")
                st.dataframe(df_exib_val.sort_values(by="Dias Restantes"), use_container_width=True)
            with aba_ass:
                df_exib_ass = df_base_completa[df_base_completa['Assinatura'] == "Pendente"].copy()
                df_exib_ass["Data Entrega"] = df_exib_ass["Data Entrega"].dt.strftime("%d/%m/%Y")
                df_exib_ass["Data Vencimento"] = df_exib_ass["Data Vencimento"].dt.strftime("%d/%m/%Y")
                st.dataframe(df_exib_ass, use_container_width=True)
