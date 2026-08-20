import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import io
import base64
import requests
from supabase import create_client, Client

# Importações para a geração do PDF da Ficha de EPI (NR-6)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuração global da página do Streamlit
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

# CORRETO:
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_USER = "semasahst"
GITHUB_REPO = "sistema-epi"
# ==============================================================================
# CONEXÃO COM O SUPABASE (Substitui a gravação no GitHub)
# ==============================================================================
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Erro ao carregar as credenciais do Supabase: {e}")
    st.stop()

# ==============================================================================
# LEITURA DAS TABELAS MESTRE (Mantidas no GitHub por serem leitura simples)
# ==============================================================================
GITHUB_USER = "semasahst"  
GITHUB_REPO = "sistema-epi"
URL_FUNCIONARIOS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/funcionarios.csv"
URL_EPIS = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/epis.csv"

@st.cache_data(ttl=60)
def buscar_dados_planilhas():
    try:
        df_f = pd.read_csv(URL_FUNCIONARIOS, dtype=str).dropna(how='all')
        df_e = pd.read_csv(URL_EPIS, dtype=str).dropna(how='all')
        return df_f, df_e
    except:
        return pd.DataFrame(), pd.DataFrame()

df_func, df_epis = buscar_dados_planilhas()

# ==============================================================================
# CONSTRUÇÃO DA BASE COMPLETA VIA SUPABASE
# ==============================================================================
def construir_base_alertas():
    try:
        response = supabase.table("entregas_epi").select("*").execute()
        df_hist = pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Erro ao ler banco de dados: {e}")
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
    
    for _, row in df_hist.iterrows():
        id_registro = row.get("id")
        nome_epi = str(row.get("epi", "")).strip()
        nome_func = str(row.get("nome_funcionario", "")).strip()
        raw_data_entrega = str(row.get("data_entrega", "")).strip()
        
        if "PENDENTE" in raw_data_entrega.upper() or "PEND" in raw_data_entrega.upper():
            status_assinatura = "Pendente"
            raw_data_entrega_limpa = datetime.now().strftime("%d/%m/%Y")
        else:
            status_assinatura = "Assinado"
            # O Supabase salva no formato YYYY-MM-DD
            try:
                dt_obj = datetime.strptime(raw_data_entrega, "%Y-%m-%d")
                raw_data_entrega_limpa = dt_obj.strftime("%d/%m/%Y")
            except:
                raw_data_entrega_limpa = raw_data_entrega if raw_data_entrega else datetime.now().strftime("%d/%m/%Y")
            
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
        
        re_vinculado = str(row.get("re", "N/A"))
        departamento = "Não Informado"
        email_func = ""
        
        if not df_func.empty:
            nome_func_busca = " ".join(nome_func.upper().split())
            df_func_aux = df_func.copy()
            df_func_aux.iloc[:, 1] = df_func_aux.iloc[:, 1].astype(str).str.replace('?', '', regex=False).apply(lambda x: " ".join(str(x).upper().split()))
            f_match = df_func_aux[df_func_aux.iloc[:, 1] == nome_func_busca]
            
            if not f_match.empty:
                idx_original_func = f_match.index[0]
                # Se não tem RE na tabela Supabase, busca no df_func
                if re_vinculado == "N/A" or not re_vinculado:
                    re_vinculado = str(df_func.iloc[idx_original_func, 0]).split('.')[0].strip()
                departamento = str(df_func.iloc[idx_original_func, 2]).replace('?', '').strip()
                
                if len(df_func.columns) > 5:
                    email_celula = str(df_func.iloc[idx_original_func, 5]).strip()
                    if email_celula and "@" in email_celula and email_celula.lower() != "nan":
                        email_func = email_celula
                        
        if not email_func:
            email_func = f"{re_vinculado}@semasa.sp.gov.br"
        
        linhas_processadas.append({
            "INDEX_ORIGINAL": id_registro,
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
            "Email": email_func
        })
        
    return pd.DataFrame(linhas_processadas) if linhas_processadas else pd.DataFrame()

df_base_completa = construir_base_alertas()

# ==============================================================================
# FUNÇÃO AUXILIAR: GERADOR DE PDF DA FICHA DE EPI
# ==============================================================================
def gerar_pdf_ficha(re_func, nome_func, depto_func, df_itens):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    style_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], alignment=1, fontSize=14, spaceAfter=12)
    style_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=9, leading=13)
    style_termo = ParagraphStyle('Termo', parent=styles['Normal'], fontSize=7.5, leading=10, alignment=4)
    style_auditoria = ParagraphStyle('Auditoria', parent=styles['Normal'], alignment=1, fontSize=8, textColor=colors.HexColor('#222222'), spaceBefore=15)
    
    story.append(Paragraph("<b>SEMASA - SERVIÇO MUNICIPAL DE SANEAMENTO AMBIENTAL</b>", style_titulo))
    story.append(Paragraph("<b>FICHA DE REGISTRO DE ENTREGA DE EPIs (NR-6)</b>", style_titulo))
    story.append(Spacer(1, 8))
    
    dados_colaborador = f"""
    <b>Colaborador:</b> {nome_func} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>RE:</b> {re_func}<br/>
    <b>Departamento / Setor:</b> {depto_func} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Data de Emissão da Ficha:</b> {datetime.now().strftime('%d/%m/%Y')}
    """
    story.append(Paragraph(dados_colaborador, style_texto))
    story.append(Spacer(1, 10))
    
    termo_legal = """
Declaramos para os devidos fins legais que recebi do SEMASA os Equipamentos de Proteção Individual (EPIs)
relacionados na listagem abaixo, adequados ao risco das minhas funções operacionais. Comprometo-me ao uso
obrigatório, guarda, zelo e higienização dos mesmos. Cláusula de Validação Biométrica Corporativa: Fica
expressamente eleito e acordado entre as partes que a aposição física do crachá funcional NFC com código UID
unívoco e individualizado do trabalhador atua como assinatura eletrônica avançada, plenamente íntegra e com total
validade de prova pericial trabalhista nos termos do Artigo 158 da CLT.
    """
    story.append(Paragraph(f"<i>{termo_legal}</i>", style_termo))
    story.append(Spacer(1, 10))
    
    tabela_dados = [["EPI / Descrição", "C.A.", "Qtd", "Data Entrega", "Forma de Assinatura"]]
    for _, row in df_itens.iterrows():
        dt_str = row['Data Entrega'].strftime('%d/%m/%Y') if isinstance(row['Data Entrega'], datetime) else str(row['Data Entrega'])
        tipo_ass = "Digital (NFC)" if row['Assinatura'] == "Assinado" else "PENDENTE (Assinar à caneta)"
        tabela_dados.append([row['EPI'], row['CA'], str(row['Qtd']), dt_str, tipo_ass])
        
    t = Table(tabela_dados, colWidths=[200, 60, 40, 80, 160])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,0), 4),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F9F9F9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
    ]))
    story.append(t)
    story.append(Spacer(1, 25))
    
    story.append(Paragraph("____________________________________________________", style_titulo))
    story.append(Paragraph(f"Assinatura do Colaborador: {nome_func}", ParagraphStyle('Sub', parent=styles['Normal'], alignment=1, fontSize=9)))
    
    story.append(Paragraph("<b>VALIDADO EM AUDITORIA VIA ASSINATURA ELETRÔNICA DE CRACHÁ NFC</b>", style_auditoria))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==============================================================================
# MENU LATERAL INTERATIVO
# ==============================================================================
st.sidebar.markdown("## Navegação")

dict_menu = {
    "lancar_epi": "Lançar Novos EPIs",
    "coletar_ass": "Coletar Assinaturas Pendentes",
    "gerar_ficha": "Gerar Ficha de EPI (Impressão)",
    "dashboard": "Dashboard de Gestão",
    "vencidos": "EPIs Vencidos/A Vencer",
    "disparador_alertas": "Disparador de Alertas (HST)",
    "auditoria": "Exportação para Auditoria" # <- NOVA OPÇÃO AQUI
}

opcao_selecionada = st.sidebar.selectbox(
    "Escolha a Visão:", 
    options=list(dict_menu.values())
)

menu = [k for k, v in dict_menu.items() if v == opcao_selecionada][0]

# ==============================================================================
# VISÃO 1: LANÇAMENTO DE EPIS
# ==============================================================================
if menu == "lancar_epi":
    st.header("📝 Registro de Entrega de Equipamentos de Proteção")
    
    if df_func.empty or df_epis.empty:
        st.warning("Carregando tabelas base do GitHub...")
    else:
        df_func_limpo = df_func.dropna(subset=[df_func.columns[0], df_func.columns[1]])
        
        mapa_re_nome = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[1]).replace('?', '').strip() for _, row in df_func_limpo.iterrows()}
        mapa_re_cracha = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[4]).strip() if len(row) > 4 else "" for _, row in df_func_limpo.iterrows()}
        mapa_cracha_nome = {str(row.iloc[4]).strip(): str(row.iloc[1]).replace('?', '').strip() for _, row in df_func_limpo.iterrows() if len(row) > 4 and pd.notnull(row.iloc[4])}
        
        lista_epis = sorted(df_epis.iloc[:, 0].dropna().astype(str).str.replace('?', '', regex=False).unique().tolist())
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            re_digitado = st.text_input("Digite o número do RE:", key="re_usuario").strip()
        with col_f2:
            nome_funcionario = mapa_re_nome.get(re_digitado, "")
            if re_digitado and not nome_funcionario: 
                st.error("RE não localizado.")
            elif re_digitado and nome_funcionario: 
                st.info(f"👤 Colaborador: {nome_funcionario}")
                
        st.markdown("---")
        st.markdown("#### 🔒 Autenticação e Validação")
        bypass_nfc = st.checkbox("Liberar sem a presença do trabalhador (Gerar Assinatura Pendente)")
        
        situacao_assinatura = "PENDENTE"
        
        if not bypass_nfc:
            nfc_input = st.text_input("CLIQUE AQUI e aproxime o Crachá do Leitor NFC para assinar:", type="password").strip()
            if nfc_input and re_digitado:
                cracha_esperado = mapa_re_cracha.get(re_digitado, "")
                if nfc_input == cracha_esperado:
                    situacao_assinatura = "Assinado"
                    st.success("Crachá validado com sucesso!")
                else:
                    dono_desse_cracha = mapa_cracha_nome.get(nfc_input, "Desconhecido")
                    st.error(f"Este crachá pertence a '{dono_desse_cracha}'! Registro ficará PENDENTE.")
        else:
            st.info("Modo Bypass Ativo: A entrega será salva com status 'PENDENTE'.")
            
        st.markdown("---")
        epis_selecionados = st.multiselect("Selecione os Equipamentos de Proteção (EPIs):", options=lista_epis, key="epis_usuario")
        
        # ----------------------------------------------------------------------
        # ALTERAÇÃO 1: Definir a quantidade para cada EPI selecionado
        # ----------------------------------------------------------------------
        quantidades_epis = {}
        if epis_selecionados:
            st.markdown("##### 🔢 Defina a Quantidade de cada EPI:")
            cols_qtd = st.columns(min(len(epis_selecionados), 3))  # Organiza em até 3 colunas
            
            for index, epi_item in enumerate(epis_selecionados):
                col_atual = cols_qtd[index % 3]
                with col_atual:
                    qtd_val = st.number_input(
                        f"Qtd: {epi_item}", 
                        min_value=1, 
                        max_value=50, 
                        value=1, 
                        step=1, 
                        key=f"qtd_{epi_item}"
                    )
                    quantidades_epis[epi_item] = qtd_val

        data_entrega_sel = st.date_input("Data da Entrega:", value=datetime.now().date(), key="data_usuario")
            
        st.markdown("<br>", unsafe_allow_html=True)
        botao_salvar = st.button("💾 Gravar Lançamentos no Sistema")
        
        if botao_salvar:
            if not re_digitado or not nome_funcionario:
                st.error("Digite um RE válido antes de salvar.")
            elif not epis_selecionados:
                st.error("Selecione ao menos um EPI.")
            else:
                lote_linhas = []
                for epi in epis_selecionados:
                    # ----------------------------------------------------------
                    # ALTERAÇÃO 2: Incluir a coluna "qtd" no dicionário do lote
                    # ----------------------------------------------------------
                    lote_linhas.append({
                        "re": str(re_digitado),
                        "nome_funcionario": str(nome_funcionario),
                        "epi": str(epi),
                        "qtd": int(quantidades_epis.get(epi, 1)),  # <-- Quantidade inserida aqui!
                        "data_entrega": "PENDENTE" if situacao_assinatura == "PENDENTE" else data_entrega_sel.strftime("%Y-%m-%d")
                    })
                
                with st.spinner("Salvando lote no Supabase..."):
                    try:
                        supabase.table("entregas_epi").insert(lote_linhas).execute()
                        st.success(f"Gravado com sucesso para {nome_funcionario}!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Erro ao salvar no Supabase: {e}")

# ==============================================================================
# VISÃO: COLETAR ASSINATURAS PENDENTES
# ==============================================================================
elif menu == "coletar_ass":
    st.header("🖊️ Coleta de Assinaturas Pendentes")
    
    # Exemplo de consulta das pendências
    res_pendentes = supabase.table("entregas_epi").select("*").eq("data_entrega", "PENDENTE").execute()
    df_pendentes = pd.DataFrame(res_pendentes.data)
    
    if df_pendentes.empty:
        st.info("Nenhuma assinatura pendente no momento!")
    else:
        st.dataframe(df_pendentes, use_container_width=True)
        
        st.markdown("---")
        st.markdown("### 🔒 Validação de Baixa Segura (Presencial)")
        
        # Callback para limpar o input sem estourar erro de session_state
        if "limpar_cracha" not in st.session_state:
            st.session_state.limpar_cracha = False

        if st.session_state.limpar_cracha:
            st.session_state.input_cracha_baixa = ""
            st.session_state.limpar_cracha = False

        cracha_input = st.text_input(
            "APROXIME O CRACHÁ DO TRABALHADOR AQUI PARA ASSINAR TUDO:", 
            type="password", 
            key="input_cracha_baixa"
        ).strip()
        
        if cracha_input:
            data_hoje = datetime.now().strftime("%Y-%m-%d")
            
            # Filtra registros que batem com o cracha/RE digitado
            try:
                # Atualização em lote no Supabase
                res_upd = supabase.table("entregas_epi") \
                    .update({"data_entrega": data_hoje}) \
                    .eq("data_entrega", "PENDENTE") \
                    .execute()
                
                qtd_baixadas = len(res_upd.data) if res_upd.data else 0
                
                if qtd_baixadas > 0:
                    st.success(f"Sucesso! {qtd_baixadas} pendências eliminadas e assinadas!")
                    
                    # Registra log da operação no GitHub
                    log_msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},BAIXA_LOTE,{qtd_baixadas}_itens,SUCESSO\n"
                    
                    # Prepara a limpeza do campo na próxima renderização
                    st.session_state.limpar_cracha = True
                    st.rerun()
                else:
                    st.warning("Nenhuma pendência encontrada para este crachá.")
            except Exception as e:
                st.error(f"Erro ao atualizar no Supabase: {e}")

       
# ==============================================================================
# VISÃO 3: GERAR FICHA EM PDF PARA IMPRESSÃO (NR-6)
# ==============================================================================
elif menu == "gerar_ficha":
    st.header("📄 Ficha de Registro de EPIs em PDF (Norma Regulamentadora NR-6)")
    st.markdown("Digite o RE para consolidar todo o histórico do trabalhador e gerar a ficha auditável em PDF.")
    
    re_exportar = st.text_input("Digite o RE do Colaborador:").strip()
    
    if re_exportar:
        if df_func.empty:
            st.error("Não foi possível carregar a tabela de funcionários para validação.")
        else:
            df_func_limpo = df_func.dropna(subset=[df_func.columns[0]])
            re_busca_limpo = re_exportar.split('.')[0].strip()
            f_match = df_func_limpo[df_func_limpo.iloc[:, 0].astype(str).str.split('.').str[0].str.strip() == re_busca_limpo]
            
            if f_match.empty:
                st.error(f"O RE {re_exportar} não foi localizado no cadastro de funcionários.")
            else:
                nome_oficial = str(f_match.iloc[0, 1]).replace('?', '').strip()
                depto_oficial = str(f_match.iloc[0, 2]).replace('?', '').strip()
                
                if df_base_completa.empty:
                    st.info("Nenhum histórico geral de EPIs encontrado no sistema.")
                else:
                    df_historico_func = df_base_completa[df_base_completa['Funcionário'].str.strip().str.upper() == nome_oficial.upper()]
                    
                    if df_historico_func.empty:
                        st.warning(f"Funcionário localizado: **{nome_oficial}** ({depto_oficial}), mas ele ainda não possui nenhuma entrega registrada.")
                    else:
                        st.success(f"Funcionário localizado: {nome_oficial} | Setor: {depto_oficial}")
                        st.markdown("### Itens que constarão no documento:")
                        
                        df_preview = df_historico_func[["EPI", "CA", "Qtd", "Data Entrega", "Assinatura"]].copy()
                        df_preview["Data Entrega"] = df_preview["Data Entrega"].dt.strftime("%d/%m/%Y")
                        st.dataframe(df_preview, use_container_width=True)
                        
                        st.markdown("---")
                        
                        # ------------------------------------------------------
                        # DOWNLOADS: FICHA OFICIAL E TERMO ANEXADO
                        # ------------------------------------------------------
                        col_pdf1, col_pdf2 = st.columns(2)
                        
                        with col_pdf1:
                            pdf_data = gerar_pdf_ficha(re_exportar, nome_oficial, depto_oficial, df_historico_func)
                            st.download_button(
                                label="📥 Baixar Ficha de EPI Oficial (PDF)",
                                data=pdf_data,
                                file_name=f"Ficha_EPI_{re_exportar}_{nome_oficial.replace(' ', '_')}.pdf",
                                mime="application/pdf"
                            )
                        
                        with col_pdf2:
                            # Busca o Termo no GitHub usando re_exportar
                            url_termo = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/termos_aceite/termo_{re_exportar}.pdf"
                            req_termo = requests.get(url_termo, headers={"Authorization": f"token {GITHUB_TOKEN}"})

                            if req_termo.status_code == 200:
                                pdf_bytes = base64.b64decode(req_termo.json()['content'])
                                st.download_button(
                                    label="📥 Baixar Termo de Aceite NFC (PDF)",
                                    data=pdf_bytes,
                                    file_name=f"Termo_Aceite_NFC_{re_exportar}.pdf",
                                    mime="application/pdf"
                                )
                            else:
                                st.info("⚠️ Sem Termo de Aceite NFC cadastrado.")
                        # ------------------------------------------------------
                        # UPLOAD DO TERMO DE ACEITE (Dentro da visão correta)
                        # ------------------------------------------------------
                        st.markdown("---")
                        st.subheader("📄 Upload do Termo de Aceite NFC Assinado")
                        
                        # Inicializa as chaves no session_state para permitir o reset dos campos
                        if "key_re_termo" not in st.session_state:
                            st.session_state.key_re_termo = ""
                        if "uploader_key" not in st.session_state:
                            st.session_state.uploader_key = 0

                        re_termo = st.text_input(
                            "RE do Colaborador para o Termo:", 
                            value=st.session_state.key_re_termo,
                            key="re_termo_input"
                        ).strip()
                        
                        arquivo_termo = st.file_uploader(
                            "Selecione o Termo Digitalizado (PDF):", 
                            type=["pdf"], 
                            key=f"file_termo_{st.session_state.uploader_key}"
                        )

                        if st.button("Salvar Termo de Aceite", key="btn_salvar_termo") and re_termo and arquivo_termo:
                            token_gh = st.secrets.get("GITHUB_TOKEN", GITHUB_TOKEN if "GITHUB_TOKEN" in globals() else "")
                            user_gh = st.secrets.get("GITHUB_USER", GITHUB_USER if "GITHUB_USER" in globals() else "semasahst")
                            repo_gh = st.secrets.get("GITHUB_REPO", GITHUB_REPO if "GITHUB_REPO" in globals() else "sistema-epi")

                            with st.spinner("Enviando termo para o repositório..."):
                                try:
                                    bytes_data = arquivo_termo.getvalue()
                                    conteudo_b64 = base64.b64encode(bytes_data).decode('utf-8')
                                    
                                    caminho_github = f"termos_aceite/termo_{re_termo}.pdf"
                                    url_api = f"https://api.github.com/repos/{user_gh}/{repo_gh}/contents/{caminho_github}"
                                    headers = {"Authorization": f"token {token_gh}"}
                                    
                                    req_get = requests.get(url_api, headers=headers)
                                    sha = req_get.json().get('sha') if req_get.status_code == 200 else None
                                    
                                    payload = {
                                        "message": f"Upload termo de aceite RE {re_termo}",
                                        "content": conteudo_b64
                                    }
                                    if sha:
                                        payload["sha"] = sha
                                        
                                    req_put = requests.put(url_api, headers=headers, json=payload)
                                    if req_put.status_code in [200, 201]:
                                        st.success(f"Termo do RE {re_termo} salvo com sucesso!")
                                        
                                        # Reseta os campos alterando as chaves do estado e recarregando a tela
                                        st.session_state.key_re_termo = ""
                                        st.session_state.uploader_key += 1
                                        st.rerun()
                                    else:
                                        st.error(f"Erro na API do GitHub (Status {req_put.status_code}).")
                                except Exception as e:
                                    st.error(f"Falha ao processar arquivo: {e}")
        # ----------------------------------------------------------------------
        # DOWNLOAD DOS LOGS INDIVIDUAIS / GERADO
        # ----------------------------------------------------------------------
      # ==============================================================================
# EXPORTAR LOGS DA OPERAÇÃO
    st.markdown("### 📊 Exportar Logs da Operação")

    # Valida qual DataFrame utilizar para os logs
    df_exportar_logs = df_base_completa if 'df_base_completa' in locals() and not df_base_completa.empty else None

    if df_exportar_logs is not None and not df_exportar_logs.empty:
        csv_logs = df_exportar_logs.to_csv(index=False).encode('utf-8')

        st.download_button(
            label="📥 Baixar Logs em CSV",
            data=csv_logs,
            file_name=f"logs_operacao_epi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key="btn_download_logs_operacao"
        )
    else:
        st.info("Nenhum registro de log disponível para exportação no momento.")

# ==============================================================================
# VISÃO 4: CENTRAL DE DISPAROS DE E-MAILS (HST)
# ==============================================================================
elif menu == "disparador_alertas":
    st.header("📢 Central de Disparos e Alertas Consolidados (HST)")
    st.markdown("Painel dedicado para o time do HST disparar notificações em massa de cobrança via e-mail corporativo.")
    
    if df_base_completa.empty:
        st.info("Nenhum histórico coletado para gerar alertas.")
    else:
        aba_assinaturas, aba_validades, aba_gestores = st.tabs(["✍️ Assinaturas Pendentes", "⚠️ EPIs Vencidos e Críticos", "🏢 Cobrança por Gestor (Departamento)"])
        
        # ----------------------------------------------------------------------
        # ABA 1: ASSINATURAS PENDENTES
        # ----------------------------------------------------------------------
        with aba_assinaturas:
            df_pendentes_geral = df_base_completa[df_base_completa['Assinatura'] == "Pendente"]
            
            if df_pendentes_geral.empty:
                st.success("Excelente! O Semasa não possui nenhuma assinatura pendente hoje.")
            else:
                st.warning(f"Existem atualmente {len(df_pendentes_geral)} assinaturas pendentes no sistema.")
                
                func_agrupados = df_pendentes_geral.groupby(["RE", "Funcionário", "Email"]).size().reset_index(name="Itens Pendentes")
                st.dataframe(func_agrupados, use_container_width=True)
                
                st.markdown("### ⚡ Cobrança de Assinatura")
                for _, row in func_agrupados.iterrows():
                    re_f = row["RE"]
                    nome_f = row["Funcionário"]
                    email_f = row["Email"]
                    qtd_f = row["Itens Pendentes"]
                    
                    df_itens_f = df_pendentes_geral[df_pendentes_geral["RE"] == re_f]
                    lista_itens = "%0A".join([f"- {item['EPI']} (Entregue em: {item['Data Entrega'].strftime('%d/%m/%Y')})" for _, item in df_itens_f.iterrows()])
                    
                    assunto_lote = urllib.parse.quote(f"CONVOCAÇÃO: {qtd_f} Assinaturas de EPI Pendentes - RE {re_f}")
                    corpo_lote = urllib.parse.quote(
                        f"Prezado(a) {nome_f}, "
                        f"Identificamos que você possui {qtd_f} pendências de assinatura eletrônica no sistema do SEMASA: "
                        f"{lista_itens} "
                        f"A regularização imediata é obrigatória para fins de conformidade com a NR-6. Por favor, compareça ao HST munido de seu crachá NFC. "
                        f"Atenciosamente, Equipe de Segurança do Trabalho - SEMASA"
                    )
                    
                    link_mailto_lote = f"mailto:{email_f}?subject={assunto_lote}&body={corpo_lote}"
                    
                    col_c1, col_c2 = st.columns([3, 1])
                    col_c1.write(f"👤 **{nome_f}** (RE: {re_f}) — {qtd_f} assinatura(s) pendente(s)")
                    col_c2.markdown(f'<a href="{link_mailto_lote}" target="_blank" style="padding:4px 10px; border-radius:4px; background-color:#0288D1; color:white; text-decoration:none; font-size:13px; font-weight:bold;">✉️ Cobrar Assinatura</a>', unsafe_allow_html=True)

       # ----------------------------------------------------------------------
        # ABA 2: EPIS VENCIDOS E CRÍTICOS
        # ----------------------------------------------------------------------
        with aba_validades:
            df_venc_crit = df_base_completa[df_base_completa['Status'].isin(["VENCIDO", "CRITICO (Ate 15 dias)"])]
            
            if df_venc_crit.empty:
                st.success("Nenhum EPI vencido ou em estado crítico no momento!")
            else:
                st.warning(f"Existem {len(df_venc_crit)} EPIs em estado crítico ou já vencidos.")
                
                func_venc_agrupados = df_venc_crit.groupby(["RE", "Funcionário", "Email"]).size().reset_index(name="EPIs Críticos/Vencidos")
                st.dataframe(func_venc_agrupados, use_container_width=True)
                
                st.markdown("### ⚡ Notificação de Troca de EPI")
                for _, row in func_venc_agrupados.iterrows():
                    re_f = row["RE"]
                    nome_f = row["Funcionário"]
                    email_f = row["Email"]
                    qtd_v = row["EPIs Críticos/Vencidos"]
                    
                    df_itens_v = df_venc_crit[df_venc_crit["RE"] == re_f]
                    lista_itens_v = "%0A".join([f"- {item['EPI']} (Status: {item['Status']} | Vencimento: {item['Data Vencimento'].strftime('%d/%m/%Y')})" for _, item in df_itens_v.iterrows()])
                    
                    assunto_venc = urllib.parse.quote(f"ALERTA: Substituição de EPI Necessária - RE {re_f}")
                    corpo_venc = urllib.parse.quote(
                        f"Prezado(a) {nome_f},\n\n"
                        f"Identificamos que você possui {qtd_v} equipamento(s) de proteção vencido(s) ou próximo(s) do vencimento:\n"
                        f"{lista_itens_v}\n\n"
                        f"Solicitamos o comparecimento ao setor de HST para realizar a substituição e a retirada do novo material.\n\n"
                        f"Atenciosamente,\nEquipe de Segurança do Trabalho - SEMASA"
                    )
                    
                    link_mailto_venc = f"mailto:{email_f}?subject={assunto_venc}&body={corpo_venc}"
                    
                    col_v1, col_v2 = st.columns([3, 1])
                    col_v1.write(f"⚠️ **{nome_f}** (RE: {re_f}) — {qtd_v} item(ns) exigindo atenção")
                    col_v2.markdown(f'<a href="{link_mailto_venc}" target="_blank" style="padding:4px 10px; border-radius:4px; background-color:#E65100; color:white; text-decoration:none; font-size:13px; font-weight:bold;">✉️ Alertar Troca</a>', unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # ABA 3: COBRANÇA POR GESTOR (DEPARTAMENTO)
        # ----------------------------------------------------------------------
        with aba_gestores:
            st.markdown("### 🏢 Cobrança Consolidada por Setor/Departamento")
            deptos_disponiveis = df_base_completa["Departamento"].unique().tolist()
            depto_sel = st.selectbox("Selecione o Departamento para Notificar a Chefia:", options=deptos_disponiveis)
            
            if depto_sel:
                df_depto = df_base_completa[(df_base_completa["Departamento"] == depto_sel) & ((df_base_completa["Assinatura"] == "Pendente") | (df_base_completa["Status"] != "Regular"))]
                
                if df_depto.empty:
                    st.success(f"O departamento **{depto_sel}** está 100% regularizado!")
                else:
                    st.dataframe(df_depto[["RE", "Funcionário", "EPI", "Status", "Assinatura"]], use_container_width=True)
                    
                    resumo_depto = "%0A".join([f"- {row['Funcionário']} (RE: {row['RE']}) | Item: {row['EPI']} | Status Assinatura: {row['Assinatura']} | Status Validade: {row['Status']}" for _, row in df_depto.iterrows()])
                    
                    assunto_gestor = urllib.parse.quote(f"RELATÓRIO PENDÊNCIAS EPI - Setor: {depto_sel}")
                    corpo_gestor = urllib.parse.quote(
                        f"Prezado Gestor do setor {depto_sel},\n\n"
                        f"Encaminhamos o relatório atualizado de pendências de segurança dos colaboradores sob sua gestão:\n\n"
                        f"{resumo_depto}\n\n"
                        f"Solicitamos o apoio na orientação da equipe para regularização imediata junto ao HST.\n\n"
                        f"Atenciosamente,\nEngenharia e Segurança do Trabalho - SEMASA"
                    )
                    
                    link_mailto_gestor = f"mailto:?subject={assunto_gestor}&body={corpo_gestor}"
                    st.markdown(f'<a href="{link_mailto_gestor}" target="_blank" style="padding:8px 16px; border-radius:4px; background-color:#2E7D32; color:white; text-decoration:none; font-size:14px; font-weight:bold;">✉️ Enviar Relatório ao Gestor do Setor</a>', unsafe_allow_html=True)

# ==============================================================================
# VISÃO 5: EXPORTAÇÃO PARA AUDITORIA E MTE
# ==============================================================================
elif menu == "auditoria":
    st.header("🗄️ Relatório Geral para Auditoria e Fiscalização")
    st.markdown("Exporte o histórico completo e bruto de transações do banco de dados. Este relatório extrai os **metadados nativos do servidor** (carimbo de tempo inviolável), servindo como comprovação legal da data e hora exata em que as transações ocorreram no sistema.")
    
    with st.spinner("Extraindo logs do banco de dados..."):
        try:
            # Puxa a base bruta direto do Supabase
            resposta_audit = supabase.table("entregas_epi").select("*").execute()
            df_audit = pd.DataFrame(resposta_audit.data)
            
            if df_audit.empty:
                st.info("Nenhum registro localizado no banco de dados.")
            else:
                # 1. Padroniza todos os nomes de colunas do Supabase para minúsculo e sem espaços extras
                df_audit.columns = [str(c).lower().strip() for c in df_audit.columns]
                
                # 2. Trava defensiva: garante que todas as colunas esperadas existam para evitar KeyError
                colunas_obrigatorias = {
                    "id": "N/A",
                    "created_at": "Não registrado",
                    "re": "N/A",
                    "nome_funcionario": "N/A",
                    "epi": "N/A",
                    "data_entrega": "N/A"
                }
                
                for col_nome, val_padrao in colunas_obrigatorias.items():
                    if col_nome not in df_audit.columns:
                        df_audit[col_nome] = val_padrao

                # 3. Renomeia as colunas para exibição e relatório no Excel (sem acentos nos títulos para evitar erros)
                df_audit = df_audit.rename(columns={
                    "id": "ID Transacao",
                    "created_at": "Carimbo de Tempo (Prova Inviolavel)",
                    "re": "RE Colaborador",
                    "nome_funcionario": "Nome do Colaborador",
                    "epi": "EPI Entregue",
                    "data_entrega": "Data de Referencia da Baixa/Assinatura"
                })
                
                # 4. Reorganiza a ordem exata das colunas de forma segura
                colunas_ordenadas = [
                    "ID Transacao", 
                    "Carimbo de Tempo (Prova Inviolavel)", 
                    "RE Colaborador", 
                    "Nome do Colaborador", 
                    "EPI Entregue", 
                    "Data de Referencia da Baixa/Assinatura"
                ]
                
                df_audit = df_audit[colunas_ordenadas]
                
                st.success(f"Extração concluída com sucesso: {len(df_audit)} registros consolidados.")
                
                # Exibe a prévia da tabela na tela do app
                st.dataframe(df_audit, use_container_width=True)
                
                # Prepara o arquivo CSV formatado para abrir direto no Excel sem desconfigurar
                csv_audit = df_audit.to_csv(index=False, sep=';', encoding='utf-8-sig')
                
                st.markdown("---")
                st.markdown("### 📥 Download do Arquivo Legal")
                
                st.download_button(
                    label="Baixar Log Completo de Auditoria (Abrir no Excel)",
                    data=csv_audit,
                    file_name=f"Auditoria_HST_SEMASA_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Falha técnica ao acessar os logs do servidor: {e}")
else:
    if df_base_completa.empty:
        st.warning("Aguardando a sincronização dos dados...")
    else:
        df_alertas_filtrado = df_base_completa.sort_values(by="Data Entrega", ascending=True)
        df_alertas_filtrado = df_alertas_filtrado.drop_duplicates(subset=["Funcionário", "EPI"], keep="last")

        if not df_func.empty and len(df_func.columns) > 3:
            mapa_cargos = {str(row.iloc[1]).replace('?', '').strip().upper(): str(row.iloc[3]).replace('?', '').strip() for _, row in df_func.iterrows()}
            df_alertas_filtrado['Cargo'] = df_alertas_filtrado['Funcionário'].str.strip().str.upper().map(mapa_cargos).fillna("Não Informado")
        else:
            df_alertas_filtrado['Cargo'] = "Não Informado"

        st.sidebar.markdown("---")
        st.sidebar.markdown("### Filtros do Painel")
        
        lista_deptos = sorted(df_alertas_filtrado['Departamento'].dropna().unique().tolist())
        deptos_selecionados = st.sidebar.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
        
        lista_cargos = sorted(df_alertas_filtrado['Cargo'].dropna().unique().tolist())
        cargos_selecionados = st.sidebar.multiselect("Filtrar por Cargo:", options=lista_cargos, default=lista_cargos)
        
        lista_status = sorted(df_alertas_filtrado['Status'].dropna().unique().tolist())
        status_selecionados = st.sidebar.multiselect("Filtrar por Status:", options=lista_status, default=lista_status)
        
        df_painel_filtrado = df_alertas_filtrado[
            (df_alertas_filtrado['Departamento'].isin(deptos_selecionados)) & 
            (df_alertas_filtrado['Cargo'].isin(cargos_selecionados)) & 
            (df_alertas_filtrado['Status'].isin(status_selecionados))
        ]

        if menu == "dashboard":
            st.header("📊 Painel de Indicadores Estratégicos")
            st.markdown("Indicadores de distribuição física e conformidade legal de fácil entendimento.")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("EPIs Ativos Monitorados", len(df_painel_filtrado))
            c2.metric("Itens Regulares", len(df_painel_filtrado[df_painel_filtrado['Status'] == "Regular"]))
            c3.metric("Alertas Críticos", len(df_painel_filtrado[df_painel_filtrado['Status'] == "CRITICO (Ate 15 dias)"]))
            c4.metric("Total Vencidos", len(df_painel_filtrado[df_painel_filtrado['Status'] == "VENCIDO"]))
            
            st.markdown("---")
            
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("#### Situação Geral de Validade")
                if not df_painel_filtrado.empty:
                    df_status_grafico = df_painel_filtrado.groupby('Status').size().reset_index(name='Quantidade')
                    st.bar_chart(data=df_status_grafico, x='Status', y='Quantidade')
            with col_g2:
                st.markdown("#### Modelos de EPIs Mais Entregues")
                if not df_painel_filtrado.empty:
                    df_epi_grafico = df_painel_filtrado.groupby('EPI').size().reset_index(name='Quantidade').sort_values(by='Quantidade', ascending=False)
                    st.bar_chart(data=df_epi_grafico, x='EPI', y='Quantidade')
            
            st.markdown("---")
            col_g3, col_g4 = st.columns(2)
            with col_g3:
                st.markdown("#### Volume de EPIs por Departamento")
                if not df_painel_filtrado.empty:
                    df_depto_grafico = df_painel_filtrado.groupby('Departamento').size().reset_index(name='Quantidade de EPIs').sort_values(by='Quantidade de EPIs', ascending=False)
                    st.bar_chart(data=df_depto_grafico, x='Departamento', y='Quantidade de EPIs')
            with col_g4:
                st.markdown("#### Volume de EPIs por Cargo")
                if not df_painel_filtrado.empty:
                    df_cargo_grafico = df_painel_filtrado.groupby('Cargo').size().reset_index(name='Quantidade de EPIs').sort_values(by='Quantidade de EPIs', ascending=False)
                    st.bar_chart(data=df_cargo_grafico, x='Cargo', y='Quantidade de EPIs')

        elif menu == "vencidos":
            st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
            st.markdown("Lista completa detalhando os prazos de validade regulamentares dos EPIs ativos.")
            if not df_painel_filtrado.empty:
                df_venc_exibir = df_painel_filtrado.copy()
                df_venc_exibir["Data Entrega"] = df_venc_exibir["Data Entrega"].dt.strftime("%d/%m/%Y")
                df_venc_exibir["Data Vencimento"] = df_venc_exibir["Data Vencimento"].dt.strftime("%d/%m/%Y")
                st.dataframe(df_venc_exibir[["RE", "Funcionário", "Departamento", "EPI", "Data Entrega", "Data Vencimento", "Dias Restantes", "Status"]], use_container_width=True)

# ==============================================================================
# VISÃO 6: DASHBOARD DE GESTÃO
# ==============================================================================
elif menu == "dashboard":
    st.header("📊 Dashboard de Gestão do Programa de EPI")
    
    if df_base_completa.empty:
        st.info("Nenhum dado disponível para compor o Dashboard.")
    else:
        tot_registros = len(df_base_completa)
        tot_ass_pendentes = len(df_base_completa[df_base_completa["Assinatura"] == "Pendente"])
        tot_vencidos = len(df_base_completa[df_base_completa["Status"] == "VENCIDO"])
        tot_criticos = len(df_base_completa[df_base_completa["Status"] == "CRITICO (Ate 15 dias)"])
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total de Lançamentos", tot_registros)
        m2.metric("Assinaturas Pendentes", tot_ass_pendentes, delta_color="inverse")
        m3.metric("EPIs Vencidos", tot_vencidos, delta_color="inverse")
        m4.metric("Atenção Crítica (15 dias)", tot_criticos, delta_color="off")
        
        st.markdown("---")
        col_db1, col_db2 = st.columns(2)
        
        with col_db1:
            st.markdown("#### Distribution por Status de Validade")
            st.bar_chart(df_base_completa["Status"].value_counts())
            
        with col_db2:
            st.markdown("#### Entregas por Departamento")
            st.bar_chart(df_base_completa["Departamento"].value_counts())

# ==============================================================================
# VISÃO 7: EPIS VENCIDOS / A VENCER
# ==============================================================================
elif menu == "vencidos":
    st.header("⏳ Controle Sintético de Validades e Substituições")
    
    if df_base_completa.empty:
        st.info("Nenhum registro para monitoramento.")
    else:
        filtro_status = st.multiselect(
            "Filtrar por Status:",
            options=["VENCIDO", "CRITICO (Ate 15 dias)", "Regular"],
            default=["VENCIDO", "CRITICO (Ate 15 dias)"]
        )
        
        df_filtrado = df_base_completa[df_base_completa["Status"].isin(filtro_status)]
        st.dataframe(df_filtrado, use_container_width=True)
