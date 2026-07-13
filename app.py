import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import base64
import io
import urllib.parse

# Importações para a geração do PDF da Ficha de EPI
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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
# FUNÇÃO MASTER DE GRAVAÇÃO UNIFICADA 
# ==============================================================================
def salvar_lote_no_github(novas_linhas_lista):
    if not GITHUB_TOKEN:
        st.error("Erro: GITHUB_TOKEN não configurado nas Secrets.")
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
# CONSTRUÇÃO DA BASE COMPLETA (HISTÓRICO AUDITÁVEL) - ULTRA ROBUSTO
# ==============================================================================
def construir_base_alertas():
    try:
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
        mapa_validades = {str(row.iloc[0]).replace('?', '').strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
        mapa_ca = {str(row.iloc[0]).replace('?', '').strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    for idx, row in df_hist.iterrows():
        linha_completa_texto = " ".join([str(val).upper() for val in row.values if pd.notnull(val)])
        
        if "PENDENTE" in linha_completa_texto or "PEND" in linha_completa_texto:
            status_assinatura = "Pendente"
            raw_data_entrega_limpa = datetime.now().strftime("%d/%m/%Y")
        else:
            status_assinatura = "Assinado"
            raw_data_entrega_limpa = str(row.iloc[-1]).strip() if len(row) > 0 else datetime.now().strftime("%d/%m/%Y")
            
        total_cols = len(row)
        if total_cols >= 6:
            nome_epi = str(row.iloc[1]).replace('?', '').strip()
            nome_func = str(row.iloc[4]).replace('?', '').strip()
        elif total_cols >= 3:
            nome_epi = str(row.iloc[0]).replace('?', '').strip()
            nome_func = str(row.iloc[1]).replace('?', '').strip()
        else:
            continue

        if not nome_func or nome_func.lower() == 'nan' or nome_func == '':
            continue
            
        dt_entrega_parsed = pd.to_datetime(raw_data_entrega_limpa, errors='coerce', dayfirst=True)
        if pd.isnull(dt_entrega_parsed):
            dt_entrega_parsed = pd.to_datetime(raw_data_entrega_limpa, errors='coerce')
            if pd.isnull(dt_entrega_parsed):
                dt_entrega_parsed = hoje
            
        dt_entrega_parsed = pd.to_datetime(dt_entrega_parsed.date())
        dias_validade = mapa_validades.get(nome_epi, 90)
        dt_vencimento = dt_entrega_parsed + timedelta(days=dias_validade)
        dias_restantes = (dt_vencimento - hoje).days
        status_validade = "VENCIDO" if dias_restantes < 0 else ("CRITICO (Ate 15 dias)" if dias_restantes <= 15 else "Regular")
        
        re_vinculado = "N/A"
        departamento = "Não Informado"
        email_func = ""
        
        # Cruzamento alternativo caso o RE direto falhe
        if not df_func.empty:
            nome_func_busca = " ".join(nome_func.upper().split())
            f_match = df_func[df_func.iloc[:, 1].astype(str).str.replace('?', '', regex=False).apply(lambda x: " ".join(str(x).upper().split())) == nome_func_busca]
            
            if not f_match.empty:
                re_vinculado = str(f_match.iloc[0, 0]).split('.')[0].strip()
                departamento = str(f_match.iloc[0, 2]).replace('?', '').strip()
                # Se a planilha funcionários tiver coluna de e-mail (geralmente coluna 5 ou 6 se disponível)
                if len(f_match.columns) > 5:
                    email_func = str(f_match.iloc[0, 5]).strip()
        
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
            "Assinatura": status_assinatura,
            "Email": email_func if email_func and "@" in email_func else f"{re_vinculado}@semasa.sp.gov.br" # Fallback padrão de e-mail institucional
        })
        
    return pd.DataFrame(linhas_processadas) if linhas_processadas else pd.DataFrame()

df_base_completa = construir_base_alertas()

elif menu == "coletar_ass":
    st.header("✍️ Regularização e Cobrança de Assinaturas Pendentes")
    st.markdown("Busque por **RE** ou veja a **Lista Geral de Pendências** abaixo para cobrar os colaboradores.")
    
    # Opção de busca rápida ou visualização geral para não ficar travado
    modo_busca = st.radio("Método de Localização:", ["Ver Todas as Pendências do Semasa", "Filtrar por RE específico"])
    
    if df_base_completa.empty:
        st.info("Nenhum histórico com assinatura pendente localizado no arquivo respostas.csv.")
    else:
        df_todas_pendentes = df_base_completa[df_base_completa['Assinatura'] == "Pendente"]
        
        if modo_busca == "Filtrar por RE específico":
            re_busca = st.text_input("Digite o RE do funcionário:").strip()
            # Se a busca por RE falhar devido a digitação ou cadastro, busca também por aproximação de string
            df_pendentes_func = df_todas_pendentes[(df_todas_pendentes['RE'] == re_busca) | (df_todas_pendentes['Funcionário'].str.contains(re_busca, case=False))]
        else:
            df_pendentes_func = df_todas_pendentes

        if df_pendentes_func.empty:
            st.success("Nenhuma assinatura pendente encontrada para os critérios selecionados!")
        else:
            st.warning(f"Foram encontradas {len(df_pendentes_func)} pendências de assinatura de EPI:")
            
            # Exibição da tabela na tela
            df_exibir = df_pendentes_func[["RE", "Funcionário", "Departamento", "EPI", "Data Entrega"]].copy()
            df_exibir["Data Entrega"] = df_exibir["Data Entrega"].dt.strftime("%d/%m/%Y")
            st.dataframe(df_exibir, use_container_width=True)
            
            # ==============================================================================
            # NOVA FUNCIONALIDADE: DISPARO / COBRANÇA VIA EMAIL
            # ==============================================================================
            st.markdown("### ✉️ Cobrança Automatizada por E-mail")
            st.markdown("Clique no botão abaixo para gerar uma notificação oficial de cobrança para os funcionários selecionados.")
            
            # Agrupa as pendências por funcionário para enviar um único e-mail com todos os EPIs dele
            funcionarios_pendentes = df_pendentes_func["Funcionário"].unique()
            
            for func in funcionarios_pendentes:
                df_func_itens = df_pendentes_func[df_pendentes_func["Funcionário"] == func]
                email_destino = df_func_itens.iloc[0]["Email"]
                re_func = df_func_itens.iloc[0]["RE"]
                
                lista_itens_texto = "%0A".join([f"- {row['EPI']} (Entregue em: {row['Data Entrega'].strftime('%d/%m/%Y')})" for _, row in df_func_itens.iterrows()])
                
                assunto = urllib.parse.quote(f"CONVOCAÇÃO: Assinatura de Ficha de EPI Pendente - RE {re_func}")
                corpo_email = urllib.parse.quote(
                    f"Prezado(a) {func},%0A%0A"
                    f"Identificamos no Sistema de Gestão de Segurança do Trabalho do SEMASA que você possui "
                    f"pendências de assinatura digital referente ao recebimento dos seguintes EPIs:%0A%0A"
                    f"{lista_itens_texto}%0A%0A"
                    f"Por favor, dirija-se ao setor de Segurança do Trabalho portando seu Crachá Funcional (NFC) "
                    f"para realizar a validação biométrica e regularizar sua ficha o quanto antes.%0A%0A"
                    f"Atenciosamente,%0AEquipe de Segurança do Trabalho - SEMASA"
                )
                
                link_mailto = f"mailto:{email_destino}?subject={assunto}&body={corpo_email}"
                
                st.markdown(f"📧 **Cobrar {func} (RE: {re_func})**")
                st.markdown(f'<a href="{link_mailto}" target="_blank" style="padding:8px 14px; border-radius:5px; background-color:#1E88E5; color:white; text-decoration:none; font-weight:bold;">✉️ Disparar E-mail de Cobrança</a>', unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

            # ==============================================================================
            # SISTEMA DE BAIXA POR CRACHÁ (MANTIDO E CORRIGIDO)
            # ==============================================================================
            st.markdown("---")
            st.markdown("### 🔒 Realizar Baixa Física (Presencial com Crachá)")
            re_para_baixa = st.text_input("Confirme o RE exato do trabalhador que está na sua frente para dar baixa:").strip()
            
            if re_para_baixa:
                nfc_baixa = st.text_input("Aproxime o Crachá do Leitor NFC para validar a assinatura:", type="password").strip()
                
                if nfc_baixa:
                    df_func_limpo = df_func.dropna(subset=[df_func.columns[0]])
                    mapa_re_cracha = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[4]).strip() if len(row) > 4 else "" for _, row in df_func_limpo.iterrows()}
                    
                    cracha_correto = mapa_re_cracha.get(re_para_baixa, "")
                    
                    if nfc_baixa != cracha_correto:
                        st.error("Bloqueado: Este crachá não corresponde ao RE digitado!")
                    else:
                        with st.spinner("Processando assinaturas legítimas..."):
                            try:
                                url_api = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/respostas.csv"
                                headers = {"Authorization": f"token {GITHUB_TOKEN}"}
                                req_get = requests.get(url_api, headers=headers)
                                
                                if req_get.status_code == 200:
                                    conteudo_bruto = base64.b64decode(req_get.json()['content']).decode('utf-8')
                                    df_raw_csv = pd.read_csv(io.StringIO(conteudo_bruto), header=None, dtype=str)
                                    
                                    df_filtrado_baixa = df_todas_pendentes[df_todas_pendentes['RE'] == re_para_baixa]
                                    indices_para_alterar = df_filtrado_baixa['INDEX_ORIGINAL'].tolist()
                                    data_hoje_str = datetime.now().strftime("%Y-%m-%d")
                                    
                                    for idx_orig in indices_para_alterar:
                                        linha_idx = int(idx_orig)
                                        for col_idx in range(len(df_raw_csv.columns)):
                                            celula_val = str(df_raw_csv.iloc[linha_idx, col_idx]).upper()
                                            if "PENDENTE" in celula_val or "PEND" in celula_val:
                                                df_raw_csv.iloc[linha_idx, col_idx] = data_hoje_str
                                    
                                    if atualizar_csv_completo(df_raw_csv):
                                        st.success(f"Sucesso! Pendências eliminadas para o RE {re_para_baixa}!")
                                        st.balloons()
                                        st.rerun()
                                    else:
                                        st.error("Erro ao salvar no GitHub.")
                            except Exception as ex:
                                st.error(f"Falha técnica: {ex}")
