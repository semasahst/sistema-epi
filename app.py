import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
import base64
import io

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
# FUNÇÃO PARA GRAVARE EDITIONS/BAIXAS DE ASSINATURA
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
# CONSTRUÇÃO DA BASE COMPLETA (HISTÓRICO AUDITÁVEL)
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
        mapa_validades = {str(row.iloc[0]).strip(): int(row.iloc[2]) if pd.notnull(row.iloc[2]) else 90 for _, row in df_epis.iterrows()}
        mapa_ca = {str(row.iloc[0]).strip(): str(row.iloc[1]).strip() for _, row in df_epis.iterrows()}
    
    for idx, row in df_hist.iterrows():
        total_cols = len(row)
        if total_cols < 2:
            continue
            
        nome_epi = str(row.iloc[0]).strip() if total_cols < 6 else str(row.iloc[1]).strip()
        nome_func = str(row.iloc[4]).strip() if total_cols >= 5 else (str(row.iloc[1]).strip() if total_cols >= 2 else "")
        raw_data_entrega = str(row.iloc[5]).strip() if total_cols >= 6 else (str(row.iloc[2]).strip() if total_cols >= 3 else "PENDENTE")
        
        if not nome_func or nome_func.lower() == 'nan' or nome_func == '':
            continue

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

# Definição Global da Base do Sistema
df_base_completa = construir_base_alertas()

# ==============================================================================
# FUNÇÃO AUXILIAR: GERADOR DE PDF DA FICHA DE EPI (NORMA NR-6)
# ==============================================================================
def gerar_pdf_ficha(re_func, nome_func, depto_func, df_itens):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    style_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], alignment=1, fontSize=16, spaceAfter=15)
    style_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=10, leading=14)
    style_termo = ParagraphStyle('Termo', parent=styles['Normal'], fontSize=8, leading=11, alignment=4)
    style_auditoria = ParagraphStyle('Auditoria', parent=styles['Normal'], alignment=1, fontSize=9, textColor=colors.HexColor('#222222'), spaceBefore=20)
    
    story.append(Paragraph("<b>SEMASA - SERVIÇO MUNICIPAL DE SANEAMENTO AMBIENTAL</b>", style_titulo))
    story.append(Paragraph("<b>FICHA DE REGISTRO DE ENTREGA DE EPIs (NR-6)</b>", style_titulo))
    story.append(Spacer(1, 10))
    
    dados_colaborador = f"""
    <b>Colaborador:</b> {nome_func} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>RE:</b> {re_func}<br/>
    <b>Departamento / Setor:</b> {depto_func} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Data de Emissão da Ficha:</b> {datetime.now().strftime('%d/%m/%Y')}
    """
    story.append(Paragraph(dados_colaborador, style_texto))
    story.append(Spacer(1, 15))
    
    termo_legal = """
Declaramos para os devidos fins legais que recebi do SEMASA os Equipamentos de Proteção Individual (EPIs)
relacionados na listagem abaixo, adequados ao risco das minhas funções operacionais. Comprometo-me ao uso
obrigatório, guarda, zelo e higienização dos mesmos. Cláusula de Validação Biométrica Corporativa: Fica
expressamente eleito e acordado entre as partes que a aposição física do crachá funcional NFC com código UID
unívoco e individualizado do trabalhador atua como assinatura eletrônica avançada, plenamente íntegra e com total
validade de prova pericial trabalhista nos termos do Artigo 158 da CLT.
    """
    story.append(Paragraph(f"<i>{termo_legal}</i>", style_termo))
    story.append(Spacer(1, 15))
    
    tabela_dados = [["EPI / Descrição", "C.A.", "Qtd", "Data Entrega", "Forma de Assinatura"]]
    for _, row in df_itens.iterrows():
        dt_str = row['Data Entrega'].strftime('%d/%m/%Y') if isinstance(row['Data Entrega'], datetime) else str(row['Data Entrega'])
        tipo_ass = "Digital (NFC)" if row['Assinatura'] == "Assinado" else "⚠️ PENDENTE (Assinar à caneta)"
        tabela_dados.append([row['EPI'], row['CA'], str(row['Qtd']), dt_str, tipo_ass])
        
    t = Table(tabela_dados, colWidths=[220, 60, 40, 80, 140])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
    ]))
    story.append(t)
    story.append(Spacer(1, 35))
    
    story.append(Paragraph("____________________________________________________", style_titulo))
    story.append(Paragraph(f"Assinatura do Colaborador: {nome_func}", ParagraphStyle('Sub', parent=styles['Normal'], alignment=1, fontSize=10)))
    
    story.append(Paragraph("<b>VALIDADO EM AUDITORIA VIA ASSINATURA ELETRÔNICA DE CRACHÁ NFC</b>", style_auditoria))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ==============================================================================
# MENU LATERAL INTERATIVO
# ==============================================================================
st.sidebar.markdown("## 🧭 Navegação Sistema")
menu = st.sidebar.selectbox(
    "Escolha a Visão:", 
    [
        "📝 Lançar Novos EPIs", 
        "✍️ Coletar Assinaturas Pendentes", 
        "📄 Gerar Ficha de EPI (Impressão)", 
        "📊 Dashboard de Gestão", 
        "⚠️ EPIs Vencidos/A Vencer"
    ]
)

# ==============================================================================
# VISÃO 1: LANÇAMENTO COM SUPORTE A MÚLTIPLOS EPIS
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
                    lote_linhas.append({
                        0: "",                                                                       
                        1: str(epi),                                                                 
                        2: "",                                                                       
                        3: "",                                                                       
                        4: str(nome_funcionario),                                                    
                        5: data_entrega_sel.strftime("%Y-%m-%d") if situacao_assinatura == "Assinado" else "PENDENTE" 
                    })
                
                with st.spinner("Salvando lote no GitHub..."):
                    if salvar_lote_no_github(lote_linhas):
                        st.success(f"🎉 Gravado com sucesso para {nome_funcionario}!")
                        st.balloons()
                    else:
                        st.error("❌ Erro ao salvar no GitHub.")

# ==============================================================================
# VISÃO 2: ELIMINAÇÃO DE PENDÊNCIAS PELO RE
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
                
                if "input_cracha_baixa" not in st.session_state:
                    st.session_state.input_cracha_baixa = ""
                
                nfc_baixa = st.text_input(
                    "APROXIME O CRACHÁ DO TRABALHADOR AQUI PARA ASSINAR TUDO:", 
                    type="password",
                    key="input_cracha_baixa"
                ).strip()
                
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
                                        df_raw_csv.iloc[int(idx_orig), 5] = data_hoje_str
                                    
                                    if atualizar_csv_completo(df_raw_csv):
                                        st.success(f"🎉 Sucesso! {len(indices_para_alterar)} pendências eliminadas e assinadas!")
                                        st.balloons()
                                        st.session_state.input_cracha_baixa = ""
                                        st.rerun()
                                    else:
                                        st.error("Erro ao salvar no GitHub.")
                                else:
                                    st.error("Não foi possível acessar o repositório.")
                            except Exception as ex:
                                st.error(f"Falha técnica: {ex}")

# ==============================================================================
# VISÃO 3: GERAR FICHA OFICIAL DE EPI PARA IMPRESSÃO/SALVAMENTO
# ==============================================================================
elif menu == "📄 Gerar Ficha de EPI (Impressão)":
    st.header("📄 Ficha de Registro de EPIs em PDF (Norma Regulamentadora NR-6)")
    st.markdown("Digite o RE para consolidar todo o histórico do trabalhador e gerar a ficha auditável em PDF.")
    
    re_exportar = st.text_input("Digite o RE do Colaborador:").strip()
    
    if re_exportar:
        if df_func.empty:
            st.error("❌ Não foi possível carregar a tabela de funcionários para validação.")
        else:
            df_func_limpo = df_func.dropna(subset=[df_func.columns[0]])
            re_busca_limpo = re_exportar.split('.')[0].strip()
            f_match = df_func_limpo[df_func_limpo.iloc[:, 0].astype(str).str.split('.').str[0].str.strip() == re_busca_limpo]
            
            if f_match.empty:
                st.error(f"❌ O RE {re_exportar} não foi localizado no cadastro de funcionários.")
            else:
                nome_oficial = str(f_match.iloc[0, 1]).strip()
                depto_oficial = str(f_match.iloc[0, 2]).strip()
                
                if df_base_completa.empty:
                    st.info("Nenhum histórico geral de EPIs encontrado no sistema.")
                else:
                    # Aqui usamos a base com o histórico completo do trabalhador
                    df_historico_func = df_base_completa[df_base_completa['Funcionário'].str.strip().str.upper() == nome_oficial.upper()]
                    
                    if df_historico_func.empty:
                        st.warning(f"📋 Funcionário localizado: **{nome_oficial}** ({depto_oficial}), mas ele ainda não possui nenhuma entrega registrada.")
                    else:
                        st.success(f"👤 **Funcionário localizado:** {nome_oficial} | **Setor:** {depto_oficial}")
                        st.markdown("### Itens que constarão no documento:")
                        
                        df_preview = df_historico_func[["EPI", "CA", "Qtd", "Data Entrega", "Assinatura"]].copy()
                        df_preview["Data Entrega"] = df_preview["Data Entrega"].dt.strftime("%d/%m/%Y")
                        st.dataframe(df_preview, use_container_width=True)
                        
                        st.markdown("---")
                        pdf_data = gerar_pdf_ficha(re_exportar, nome_oficial, depto_oficial, df_historico_func)
                        
                        st.download_button(
                            label="📥 Baixar Ficha de EPI Oficial (PDF)",
                            data=pdf_data,
                            file_name=f"Ficha_EPI_{re_exportar}_{nome_oficial.replace(' ', '_')}.pdf",
                            mime="application/pdf"
                        )

# ==============================================================================
# VISÕES DO DASHBOARD E ALERTAS (COMPLETO, COM FILTROS, GRÁFICOS E DOWNLOAD)
# ==============================================================================
else:
    if df_base_completa.empty:
        st.warning("Aguardando a sincronização dos dados...")
    else:
        # 1. Aplicação estrita da regra de negócio: Vencimento baseado apenas na última entrega ativa
        df_alertas_filtrado = df_base_completa.sort_values(by="Data Entrega", ascending=True)
        df_alertas_filtrado = df_alertas_filtrado.drop_duplicates(subset=["Funcionário", "EPI"], keep="last")

        # ==============================================================================
        # PAINEL DE FILTROS DINÂMICOS NA BARRA LATERAL
        # ==============================================================================
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🔍 Filtros do Painel")
        
        # Filtro de Departamento/Setor
        lista_deptos = sorted(df_alertas_filtrado['Departamento'].dropna().unique().tolist())
        deptos_selecionados = st.sidebar.multiselect("Filtrar por Departamento:", options=lista_deptos, default=lista_deptos)
        
        # Filtro de Status de Validade
        lista_status = sorted(df_alertas_filtrado['Status'].dropna().unique().tolist())
        status_selecionados = st.sidebar.multiselect("Filtrar por Status:", options=lista_status, default=lista_status)
        
        # Aplicando os filtros ao Dataframe do Dashboard
        df_painel_filtrado = df_alertas_filtrado[
            (df_alertas_filtrado['Departamento'].isin(deptos_selecionados)) & 
            (df_alertas_filtrado['Status'].isin(status_selecionados))
        ]

        # ==============================================================================
        # VISÃO: DASHBOARD DE GESTÃO INTERATIVO
        # ==============================================================================
        if menu == "📊 Dashboard de Gestão":
            st.header("📊 Painel de Indicadores Estratégicos")
            st.markdown("Indicadores de distribuição física e conformidade legal baseados na última entrega vigente de cada funcionário.")
            
            # Cards de Métricas Principais
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("EPIs Ativos Monitorados", len(df_painel_filtrado))
            c2.metric("🟢 Itens Regulares", len(df_painel_filtrado[df_painel_filtrado['Status'] == "🟢 Regular"]))
            c3.metric("🟡 Alertas Críticos", len(df_painel_filtrado[df_painel_filtrado['Status'].str.contains("🟡")]))
            c4.metric("🔴 Total Vencidos", len(df_painel_filtrado[df_painel_filtrado['Status'] == "🔴 VENCIDO"]))
            
            st.markdown("---")
            
            col_g1, col_g2 = st.columns([1, 2])
            
            with col_g1:
                st.markdown("#### 📈 Distribuição de Status de Validade")
                if not df_painel_filtrado.empty:
                    df_status_grafico = df_painel_filtrado.groupby('Status').size().reset_index(name='Quantidade')
                    # Gráfico nativo do Streamlit mapeando a proporção de status
                    st.bar_chart(data=df_status_grafico, x='Status', y='Quantidade', color='Status')
                else:
                    st.info("Sem dados para exibir o gráfico de status.")
                    
            with col_g2:
                st.markdown("#### 👔 Matriz: Departamentos / Setores vs EPIs Solicitados")
                if not df_painel_filtrado.empty:
                    # Agrupamento cruzado para responder quais EPIs estão em quais setores
                    df_pivot = df_painel_filtrado.groupby(['Departamento', 'EPI']).size().reset_index(name='Qtd')
                    st.bar_chart(data=df_pivot, x='Departamento', y='Qtd', color='EPI', stack=True)
                else:
                    st.info("Sem dados para exibir a matriz de setores.")
                    
            st.markdown("---")
            
            # Seção de Exportação para Apresentações e E-mails
            st.markdown("### 💾 Central de Exportação de Dados")
            st.markdown("Baixe os dados consolidados e filtrados acima para anexar em e-mails corporativos ou montar seus relatórios e apresentações de slides.")
            
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                # Preparando o arquivo CSV tratado para download rápido
                df_export_clean = df_painel_filtrado[["RE", "Funcionário", "Departamento", "EPI", "CA", "Data Entrega", "Data Vencimento", "Dias Restantes", "Status", "Assinatura"]].copy()
                df_export_clean["Data Entrega"] = df_export_clean["Data Entrega"].dt.strftime("%d/%m/%Y")
                df_export_clean["Data Vencimento"] = df_export_clean["Data Vencimento"].dt.strftime("%d/%m/%Y")
                
                csv_dados = df_export_clean.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Baixar Relatório de Indicadores (CSV)",
                    data=csv_dados,
                    file_name=f"Relatorio_Indicadores_EPI_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_exp2:
                st.info("💡 **Dica para Apresentações:** Você pode tirar um print dos gráficos acima usando o atalho `Win + Shift + S` para colar direto nos seus slides do PowerPoint ou e-mails!")

        # ==============================================================================
        # VISÃO: MONITOR DE EPIS VENCIDOS / A VENCER
        # ==============================================================================
        elif menu == "⚠️ EPIs Vencidos/A Vencer":
            st.header("⚠️ Gestão de Alertas e Pendências Logísticas")
            st.markdown("Listagem operacional detalhada para ações corretivas imediatas de troca ou coleta de assinaturas.")
            
            aba_val, aba_ass = st.tabs(["📋 Monitor de Validade (NR-6)", "✍️ Assinaturas Pendentes"])
            
            with aba_val:
                if not df_painel_filtrado.empty:
                    df_exib_val = df_painel_filtrado.copy()
                    df_exib_val["Data Entrega"] = df_exib_val["Data Entrega"].dt.strftime("%d/%m/%Y")
                    df_exib_val["Data Vencimento"] = df_exib_val["Data Vencimento"].dt.strftime("%d/%m/%Y")
                    
                    st.dataframe(df_exib_val[["RE", "Funcionário", "Departamento", "EPI", "CA", "Data Entrega", "Data Vencimento", "Dias Restantes", "Status"]].sort_values(by="Dias Restantes"), use_container_width=True)
                    
                    # Botão dedicado para baixar a lista de compras/trocas de EPIs baseado no que foi filtrado
                    csv_Valores = df_exib_val.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Exportar Lista Operacional de Prazos (CSV)",
                        data=csv_Valores,
                        file_name=f"Planilha_Prazos_EPI_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("Nenhum item pendente de validação nos filtros selecionados.")
                    
            with aba_ass:
                df_exib_ass = df_painel_filtrado[df_painel_filtrado['Assinatura'] == "Pendente"].copy()
                if not df_exib_ass.empty:
                    df_exib_ass["Data Entrega"] = df_exib_ass["Data Entrega"].dt.strftime("%d/%m/%Y")
                    df_exib_ass["Data Vencimento"] = df_exib_ass["Data Vencimento"].dt.strftime("%d/%m/%Y")
                    
                    st.dataframe(df_exib_ass[["RE", "Funcionário", "Departamento", "EPI", "Data Entrega", "Status"]], use_container_width=True)
                    
                    csv_ass = df_exib_ass.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Exportar Lista de Pendentes de Assinatura (CSV)",
                        data=csv_ass,
                        file_name=f"Funcionarios_Sem_Assinatura_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.success("🎉 Nenhuma assinatura pendente de crachá NFC encontrada para os filtros atuais!")
