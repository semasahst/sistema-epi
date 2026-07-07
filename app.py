import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import base64
import io  # Importação correta adicionada aqui!

# Configuração global da página do Streamlit (Deve ser a primeira instrução)
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DE ACESSO AOS ARQUIVOS REPOSITÓRIO (GITHUB)
# ==============================================================================
# Ajustado automaticamente para o seu usuário baseado nos seus prints anteriores
GITHUB_USER = "semasahst"  
GITHUB_REPO = "sistema-epi"
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")

URL_RESPOSTAS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/respostas.csv"
URL_FUNCIONARIOS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/funcionarios.csv"
URL_EPIS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/epis.csv"

# ==============================================================================
# CARREGAMENTO DOS DADOS OPERACIONAIS COM SISTEMA DE TRATAMENTO DE ERROS
# ==============================================================================
@st.cache_data(ttl=5)
def buscar_dados_planilhas():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = buscar_dados_planilhas()

# ==============================================================================
# FUNÇÃO PARA GRAVAR DADOS DIRETAMENTE NO GITHUB CSV (CORRIGIDA)
# ==============================================================================
def salvar_no_github(nova_linha_dict):
    if not GITHUB_TOKEN:
        st.error("❌ Erro de Configuração: A chave 'GITHUB_TOKEN' não foi configurada nas Secrets do Streamlit.")
        return False
        
    url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    
    # 1. Pega o arquivo atual para não apagar o histórico
    req_get = requests.get(url_api, headers=headers)
    if req_get.status_code == 200:
        dados_repo = req_get.json()
        sha_arquivo = dados_repo['sha']
        conteudo_antigo = base64.b64decode(dados_repo['content']).decode('utf-8')
        # CORREÇÃO AQUI: Usando o io.StringIO correto e moderno
        df_atual = pd.read_csv(io.StringIO(conteudo_antigo), dtype=str)
    else:
        try:
            df_atual = pd.read_csv(URL_RESPOSTAS, dtype=str)
            sha_arquivo = "" 
        except:
            st.error("Não foi possível sincronizar com o histórico do GitHub.")
            return False

    # 2. Adiciona a nova linha
    df_nova_linha = pd.DataFrame([nova_linha_dict])
    df_final = pd.concat([df_atual, df_nova_linha], ignore_index=True)
    
    # 3. Transforma em CSV string e envia de volta
    csv_string = df_final.to_csv(index=False)
    conteudo_bytes = csv_string.encode('utf-8')
    conteudo_base64 = base64.b64encode(conteudo_bytes).decode('utf-8')
    
    payload = {
        "message": f"Lançamento de EPI automático: RE {nova_linha_dict.get('RE')}",
        "content": conteudo_base64,
        "sha": sha_arquivo
    }
    
    req_put = requests.put(url_api, headers=headers, json=payload)
    if req_put.status_code in [200, 201]:
        return True
    else:
        st.error(f"Erro ao enviar dados para o GitHub: {req_put.text}")
        return False
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
        
    col_timestamp = df_hist.columns[0]
    col_re = df_hist.columns[1]
    col_func = df_hist.columns[2]
    col_epi = df_hist.columns[3]
    col_data = df_hist.columns[4]
    col_qtd = df_hist.columns[5]

    linhas_processadas = []
    hoje = pd.to_datetime(datetime.now().date())
    
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

        if "PENDENTE" in raw_data_entrega.upper() or "PENDENTE" in raw_timestamp.upper():
            status_assinatura = "Pendente"
            if len(raw_data_entrega) >= 10:
                raw_data_entrega = raw_data_entrega[:10].strip()
        else:
            status_assinatura = "Assinado"
            
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega, errors='coerce')
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_timestamp.split()[0], dayfirst=True, errors='coerce')
        
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = hoje
            
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
            
        dias_validade = mapa_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        
        status_validade = "🔴 VENCIDO" if dias_restantes < 0 else ("🟡 CRÍTICO (Até 15 days)" if dias_restantes <= 15 else "🟢 Regular")
        
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

df_base_completa = construir_base_alertas()

# ==============================================================================
# MENU LATERAL INTERATIVO
# ==============================================================================
st.sidebar.markdown("## 🧭 Navegação Sistema")
menu = st.sidebar.selectbox(
    "Escolha a Visão:", 
    ["📝 Lançar Novos EPIs", "📊 Dashboard de Gestão", "⚠️ EPIs Vencidos/A Vencer"]
)

# ==============================================================================
# VISÃO: FORMULÁRIO NATIVO AVANÇADO CORRIGIDO (NFC SEM APAGAR OS DADOS)
# ==============================================================================
if menu == "📝 Lançar Novos EPIs":
    st.header("📝 Registro de Entrega de Equipamentos de Proteção")
    st.markdown("Busque pelo RE, selecione quantos EPIs forem necessários e valide com o crachá NFC.")
    
    if df_func.empty or df_epis.empty:
        st.warning("⚠️ Aguardando carregamento das tabelas base do GitHub...")
    else:
        # Criar dicionário de RE -> Nome para busca instantânea rápida
        df_func_limpo = df_func.dropna(subset=[df_func.columns[0], df_func.columns[1]])
        mapa_re_nome = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[1]).strip() for _, row in df_func_limpo.iterrows()}
        lista_epis = sorted(df_epis.iloc[:, 0].dropna().unique().tolist())
        
        # 1. ENTRADA DO CRACHÁ NFC (Fora do form para não dar refresh e limpar os campos)
        st.markdown("#### 💳 Autenticação e Assinatura Eletrônica")
        nfc_input = st.text_input(
            "CLIQUE AQUI e aproxime o Crachá do Leitor NFC para assinar:", 
            type="password", 
            help="Mantenha o cursor piscando aqui antes de aproximar o crachá físico."
        ).strip()
        
        situacao_assinatura = "Assinado" if nfc_input else "PENDENTE"
        
        if nfc_input:
            st.success("🟢 Crachá lido com sucesso! Assinatura vinculada para este lançamento.")
        else:
            st.warning("⚠️ Nenhum crachá detectado ainda. O registro atual está como 'PENDENTE'.")
            
        st.markdown("---")
        
        # 2. FORMULÁRIO DOS DADOS DO EPI (Preserva as seleções na tela)
        with st.form("form_lancamento_avancado", clear_on_submit=False):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                re_digitado = st.text_input("Digite o número do RE:", key="input_re").strip()
            with col_f2:
                nome_funcionario = mapa_re_nome.get(re_digitado, "")
                if re_digitado and not nome_funcionario:
                    st.error("❌ RE não localizado na base de dados de funcionários.")
                elif re_digitado and nome_funcionario:
                    st.info(f"👤 Colaborador: {nome_funcionario}")
            
            # Seleção de Múltiplos EPIs
            epis_selecionados = st.multiselect(
                "Selecione os Equipamentos de Proteção (EPIs):", 
                options=lista_epis,
                help="Você pode selecionar vários itens ao mesmo tempo (Ex: Luva, Óculos e Capacete)"
            )
            
            col_f3, col_f4 = st.columns(2)
            with col_f3:
                quantidade_sel = st.number_input("Quantidade (Aplicada a cada item selecionado):", min_value=1, max_value=10, value=1)
            with col_f4:
                data_entrega_sel = st.date_input("Data da Entrega:", value=datetime.now().date())
                
            st.markdown("<br>", unsafe_allow_html=True)
            botao_salvar = st.form_submit_button("💾 Gravar Lançamentos no Sistema")
            
            if botao_salvar:
                if not re_digitado or not nome_funcionario:
                    st.error("❌ Erro: É necessário informar um RE válido antes de salvar.")
                elif not epis_selecionados:
                    st.error("❌ Erro: Selecione ao menos um EPI para realizar o lançamento.")
                else:
                    sucessos_grava = 0
                    erros_grava = 0
                    
                    with st.spinner("Registrando itens no banco de dados do GitHub..."):
                        for epi in epis_selecionados:
                            nova_linha = {
                                "Carimbo de data/hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                                "RE": str(re_digitado),
                                "Nome completo do funcionário:": str(nome_funcionario),
                                "EPI": str(epi),
                                "Data da entrega:": data_entrega_sel.strftime("%Y-%m-%d") if situacao_assinatura == "Assinado" else "PENDENTE",
                                "Quantidade:": int(quantidade_sel)
                            }
                            
                            if salvar_no_github(nova_linha):
                                sucessos_grava += 1
                            else:
                                erros_grava += 1
                    
                    if sucessos_grava == len(epis_selecionados):
                        st.success(f"🎉 Perfeito! {sucessos_grava} EPI(s) registrado(s) com sucesso para {nome_funcionario}.")
                        st.balloons()
                    elif sucessos_grava > 0:
                        st.warning(f"⚠️ Operação parcial: {sucessos_grava} itens salvos, mas {erros_grava} falharam.")
                    else:
                        st.error("❌ Erro crítico: Não foi possível gravar no GitHub. Verifique a internet ou o Token.")
# ==============================================================================
# VISÕES DO DASHBOARD (MANTIDAS EXATAMENTE IGUAIS)
# ==============================================================================
else:
    if df_base_completa.empty:
        st.warning("Aguardando a sincronização dos dados do histórico respostas.csv...")
    else:
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
                    
            with col_g2:
                st.markdown("#### Distribuição de Consumo por Modelo de EPI")
                if not df_dash.empty:
                    df_ranking = df_dash.groupby('EPI')['Qtd'].sum().reset_index().sort_values(by='Qtd', ascending=False)
                    st.bar_chart(data=df_ranking, x='EPI', y='Qtd', use_container_width=True)

        elif menu == "⚠️ EPIs Vencidos/A Vencer":
            st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
            aba_validade, aba_assinaturas = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
            
            with aba_validade:
                df_exibicao_val = df_base_completa.copy()
                df_exibicao_val['Data Entrega'] = df_exibicao_val['Data Entrega'].dt.strftime('%d/%m/%Y')
                df_exibicao_val['Data Vencimento'] = df_exibicao_val['Data Vencimento'].dt.strftime('%d/%m/%Y')
                st.dataframe(df_exibicao_val.sort_values(by="Dias Restantes"), use_container_width=True)
                
            with aba_assinaturas:
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    lista_deptos = sorted(list(df_base_completa['Departamento'].unique()))
                    depto_sel = st.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
                with col_f2:
                    data_ini_p = st.date_input("Início Período:", datetime.now().date() - timedelta(days=60), key="ini_p")
                with col_f3:
                    data_fim_p = st.date_input("Fim Período:", datetime.now().date() + timedelta(days=1), key="fim_p")
                    
                df_pendentes = df_base_completa[
                    (df_base_completa['Assinatura'] == "Pendente") & 
                    (df_base_completa['Departamento'].isin(depto_sel)) &
                    (df_base_completa['Data Entrega'] >= pd.to_datetime(data_ini_p)) & 
                    (df_base_completa['Data Entrega'] <= pd.to_datetime(data_fim_p))
                ]
                st.dataframe(df_pendentes, use_container_width=True)
