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

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_USER = "semasahst"
GITHUB_REPO = "sistema-epi"

# ==============================================================================
# CONEXÃO COM O SUPABASE
# ==============================================================================
try:
    url: str = st.secrets["SUPABASE_URL"]
    key: str = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"Erro ao carregar as credenciais do Supabase: {e}")
    st.stop()

# ==============================================================================
# LEITURA DAS TABELAS MESTRE (GitHub)
# ==============================================================================
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
        carimbo_inviolavel = row.get("created_at", "Não registrado")
        
        nome_epi = str(row.get("epi", "")).strip()
        nome_func = str(row.get("nome_funcionario", "")).strip()
        raw_data_entrega = str(row.get("data_entrega", "")).strip()
        
        if "PENDENTE" in raw_data_entrega.upper() or "PEND" in raw_data_entrega.upper():
            status_assinatura = "Pendente"
            raw_data_entrega_limpa = datetime.now().strftime("%d/%m/%Y")
        else:
            status_assinatura = "Assinado"
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
        cargo = "Não Informado"
        email_func = ""
        
        if not df_func.empty:
            nome_func_busca = " ".join(nome_func.upper().split())
            df_func_aux = df_func.copy()
            df_func_aux.iloc[:, 1] = df_func_aux.iloc[:, 1].astype(str).str.replace('?', '', regex=False).apply(lambda x: " ".join(str(x).upper().split()))
            f_match = df_func_aux[df_func_aux.iloc[:, 1] == nome_func_busca]
            
            if not f_match.empty:
                idx_original_func = f_match.index[0]
                if re_vinculado == "N/A" or not re_vinculado:
                    re_vinculado = str(df_func.iloc[idx_original_func, 0]).split('.')[0].strip()
                departamento = str(df_func.iloc[idx_original_func, 2]).replace('?', '').strip()
                
                if len(df_func.columns) > 3:
                    cargo_celula = str(df_func.iloc[idx_original_func, 3]).replace('?', '').strip()
                    if cargo_celula and cargo_celula.lower() != "nan":
                        cargo = cargo_celula
                
                if len(df_func.columns) > 5:
                    email_celula = str(df_func.iloc[idx_original_func, 5]).strip()
                    if email_celula and "@" in email_celula and email_celula.lower() != "nan":
                        email_func = email_celula
                        
        if not email_func:
            email_func = f"{re_vinculado}@semasa.sp.gov.br"
        
        linhas_processadas.append({
            "Data e Hora da Transacao (Inviolavel)": carimbo_inviolavel,
            "INDEX_ORIGINAL": id_registro,
            "RE": re_vinculado,
            "Funcionário": nome_func, 
            "Departamento": departamento,
            "Cargo": cargo,
            "EPI": nome_epi, 
            "CA": mapa_ca.get(nome_epi, "N/A"), 
            "Qtd": row.get("qtd", 1),
            "Data Entrega Declarada": dt_entrega_parsed, 
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
        dt_str = row['Data Entrega Declarada'].strftime('%d/%m/%Y') if isinstance(row['Data Entrega Declarada'], datetime) else str(row['Data Entrega Declarada'])
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
    "auditoria": "Exportação para Auditoria"
}

opcao_selecionada = st.sidebar.selectbox(
    "Escolha a Visão:", 
    options=list(dict_menu.values())
)

menu = [k for k, v in dict_menu.items() if v == opcao_selecionada][0]

# ==============================================================================
# VISÃO 1: LANÇAMENTO DE EPIS (Com suporte a Empréstimo RE 0000)
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
            if re_digitado == "0000":
                nome_funcionario = "Empréstimo (Outras Unidades)"
                st.info(f"🏢 Destino: {nome_funcionario}")
            else:
                nome_funcionario = mapa_re_nome.get(re_digitado, "")
                if re_digitado and not nome_funcionario: 
                    st.error("RE não localizado.")
                elif re_digitado and nome_funcionario: 
                    st.info(f"👤 Colaborador: {nome_funcionario}")
                
        st.markdown("---")
        st.markdown("#### 🔒 Autenticação e Validação")
        
        situacao_assinatura = "PENDENTE"
        justificativa_emprestimo = ""
        
        if re_digitado == "0000":
            st.warning("⚠️ MODO DE EMPRÉSTIMO ATIVADO")
            justificativa_emprestimo = st.text_input("Justificativa e Autorização do Empréstimo (Ex: Autorizado por Diretor João):").strip()
            
            if justificativa_emprestimo:
                situacao_assinatura = "Assinado"
                st.success("Empréstimo autorizado e justificado!")
            else:
                st.error("Preencha quem autorizou o empréstimo para liberar a entrega.")
        else:
            bypass_nfc = st.checkbox("Liberar sem a presença do trabalhador (Gerar Assinatura Pendente)")
            
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
        
        quantidades_epis = {}
        justificativas_epis = {}
        bloquear_salvamento = False 
        
        if epis_selecionados:
            st.markdown("##### 🔢 Análise de Validade, Quantidade e Justificativas:")
            
            df_hist_re = pd.DataFrame()
            if re_digitado and not df_base_completa.empty:
                df_hist_re = df_base_completa[df_base_completa["RE"] == str(re_digitado)]
                if not df_hist_re.empty:
                    df_hist_re = df_hist_re.sort_values(by="Data Entrega Declarada", ascending=False)
            
            for epi_item in epis_selecionados:
                st.markdown("<hr style='margin: 10px 0; border-color: #555;'>", unsafe_allow_html=True)
                
                status_atual = "NUNCA ENTREGUE"
                if not df_hist_re.empty:
                    df_epi = df_hist_re[df_hist_re["EPI"] == epi_item]
                    if not df_epi.empty:
                        status_atual = df_epi.iloc[0]["Status"]
                
                if re_digitado == "0000":
                    st.markdown(f"**EPI:** <span style='color:#4CAF50; font-size:18px; font-weight:bold;'>{epi_item}</span> — Status: **EMPRÉSTIMO** ✅", unsafe_allow_html=True)
                    qtd_val = st.number_input(f"Quantidade ({epi_item}):", min_value=1, max_value=50, value=1, step=1, key=f"qtd_{epi_item}")
                    quantidades_epis[epi_item] = qtd_val
                    justificativas_epis[epi_item] = justificativa_emprestimo
                else:
                    if status_atual in ["VENCIDO", "CRITICO (Ate 15 dias)", "NUNCA ENTREGUE"]:
                        st.markdown(f"**EPI:** <span style='color:#4CAF50; font-size:18px; font-weight:bold;'>{epi_item}</span> — Status Histórico: **{status_atual}** ✅ *(Substituição Liberada)*", unsafe_allow_html=True)
                        qtd_val = st.number_input(f"Quantidade ({epi_item}):", min_value=1, max_value=50, value=1, step=1, key=f"qtd_{epi_item}")
                        quantidades_epis[epi_item] = qtd_val
                        justificativas_epis[epi_item] = "" 
                    else:
                        st.markdown(f"**EPI:** <span style='color:#F44336; font-size:18px; font-weight:bold;'>{epi_item}</span> — Status Histórico: **{status_atual}** ❌ *(Ainda no prazo de validade)*", unsafe_allow_html=True)
                        
                        col_q, col_j = st.columns([1, 2])
                        with col_q:
                            qtd_val = st.number_input(f"Quantidade ({epi_item}):", min_value=1, max_value=50, value=1, step=1, key=f"qtd_{epi_item}")
                            quantidades_epis[epi_item] = qtd_val
                        with col_j:
                            tem_justificativa = st.checkbox(f"Solicitar troca antecipada?", key=f"check_{epi_item}")
                            if tem_justificativa:
                                just = st.text_input("Qual o motivo da troca?", key=f"just_{epi_item}").strip()
                                if just == "":
                                    st.error("⚠️ Digite a justificativa.")
                                    bloquear_salvamento = True
                                else:
                                    justificativas_epis[epi_item] = just
                            else:
                                st.warning("⚠️ Justifique a troca antecipada.")
                                bloquear_salvamento = True

        data_entrega_sel = st.date_input("Data da Entrega:", value=datetime.now().date(), key="data_usuario")
            
        st.markdown("<br>", unsafe_allow_html=True)
        botao_salvar = st.button("💾 Gravar Lançamentos no Sistema")
        
        if botao_salvar:
            if re_digitado == "0000" and not justificativa_emprestimo:
                st.error("🛑 Preencha o campo de 'Justificativa e Autorização' do empréstimo.")
            elif bloquear_salvamento:
                st.error("🛑 Existem itens no prazo de validade sem justificativa de troca antecipada.")
            elif not re_digitado or not nome_funcionario:
                st.error("Digite um RE válido antes de salvar.")
            elif not epis_selecionados:
                st.error("Selecione ao menos um EPI.")
            else:
                lote_linhas = []
                for epi in epis_selecionados:
                    texto_justificativa = justificativas_epis.get(epi, "")
                    if re_digitado == "0000":
                        texto_justificativa = f"EMPRÉSTIMO AUTORIZADO: {justificativa_emprestimo}"

                    lote_linhas.append({
                        "re": str(re_digitado),
                        "nome_funcionario": str(nome_funcionario),
                        "epi": str(epi),
                        "qtd": int(quantidades_epis.get(epi, 1)), 
                        "data_entrega": "PENDENTE" if situacao_assinatura == "PENDENTE" else data_entrega_sel.strftime("%Y-%m-%d"),
                        "justificativa": texto_justificativa 
                    })
                
                with st.spinner("Salvando lote no Supabase..."):
                    try:
                        supabase.table("entregas_epi").insert(lote_linhas).execute()
                        st.success(f"Gravado com sucesso para {nome_funcionario}!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Erro ao salvar no Supabase. Detalhes: {e}")

# ==============================================================================
# VISÃO 2: COLETAR ASSINATURAS PENDENTES
# ==============================================================================
elif menu == "coletar_ass":
    st.header("🖊️ Coleta de Assinaturas Pendentes")
    
    res_pendentes = supabase.table("entregas_epi").select("*").eq("data_entrega", "PENDENTE").execute()
    df_pendentes = pd.DataFrame(res_pendentes.data)
    
    if df_pendentes.empty:
        st.info("Nenhuma assinatura pendente no momento!")
    else:
        st.dataframe(df_pendentes, use_container_width=True)
        st.markdown("---")
        st.markdown("### 🔒 Validação de Baixa Segura (Presencial)")
        
        if "limpar_cracha" not in st.session_state:
            st.session_state.limpar_cracha = False

        if st.session_state.limpar_cracha:
            st.session_state.input_cracha_baixa = ""
            st.session_state.limpar_cracha = False

        cracha_input = st.text_input("APROXIME O CRACHÁ AQUI PARA ASSINAR TUDO:", type="password", key="input_cracha_baixa").strip()
        
        if cracha_input:
            data_hoje = datetime.now().strftime("%Y-%m-%d")
            try:
                res_upd = supabase.table("entregas_epi").update({"data_entrega": data_hoje}).eq("data_entrega", "PENDENTE").execute()
                qtd_baixadas = len(res_upd.data) if res_upd.data else 0
                if qtd_baixadas > 0:
                    st.success(f"Sucesso! {qtd_baixadas} pendências eliminadas!")
                    st.session_state.limpar_cracha = True
                    st.rerun()
                else:
                    st.warning("Nenhuma pendência encontrada.")
            except Exception as e:
                st.error(f"Erro ao atualizar: {e}")

# ==============================================================================
# VISÃO 3: GERAR FICHA EM PDF E EXPORTAR LOGS DO COLABORADOR
# ==============================================================================
elif menu == "gerar_ficha":
    st.header("📄 Ficha de Registro de EPIs em PDF (NR-6)")
    re_exportar = st.text_input("Digite o RE do Colaborador:").strip()
    
    if re_exportar:
        if df_func.empty:
            st.error("Não foi possível carregar a tabela de funcionários.")
        else:
            df_func_limpo = df_func.dropna(subset=[df_func.columns[0]])
            re_busca_limpo = re_exportar.split('.')[0].strip()
            f_match = df_func_limpo[df_func_limpo.iloc[:, 0].astype(str).str.split('.').str[0].str.strip() == re_busca_limpo]
            
            if f_match.empty:
                st.error(f"O RE {re_exportar} não foi localizado.")
            else:
                nome_oficial = str(f_match.iloc[0, 1]).replace('?', '').strip()
                depto_oficial = str(f_match.iloc[0, 2]).replace('?', '').strip()
                
                if df_base_completa.empty:
                    st.info("Nenhum histórico geral de EPIs encontrado.")
                else:
                    df_historico_func = df_base_completa[df_base_completa['Funcionário'].str.strip().str.upper() == nome_oficial.upper()]
                    
                    if df_historico_func.empty:
                        st.warning(f"Funcionário **{nome_oficial}** sem entregas registradas.")
                    else:
                        st.success(f"Funcionário localizado: {nome_oficial} | Setor: {depto_oficial}")
                        
                        col_pdf1, col_pdf2 = st.columns(2)
                        with col_pdf1:
                            pdf_data = gerar_pdf_ficha(re_exportar, nome_oficial, depto_oficial, df_historico_func)
                            st.download_button(
                                label="📥 Baixar Ficha de EPI Oficial (PDF)",
                                data=pdf_data,
                                file_name=f"Ficha_EPI_{re_exportar}.pdf",
                                mime="application/pdf"
                            )
                        with col_pdf2:
                            url_termo = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/termos_aceite/termo_{re_exportar}.pdf"
                            req_termo = requests.get(url_termo, headers={"Authorization": f"token {GITHUB_TOKEN}"})
                            if req_termo.status_code == 200:
                                pdf_bytes = base64.b64decode(req_termo.json()['content'])
                                st.download_button(
                                    label="📥 Baixar Termo de Aceite NFC (PDF)",
                                    data=pdf_bytes,
                                    file_name=f"Termo_Aceite_{re_exportar}.pdf",
                                    mime="application/pdf"
                                )
                            else:
                                st.info("⚠️ Sem Termo de Aceite NFC cadastrado.")

                        st.markdown("---")
                        st.markdown("### 📊 Exportar Logs do Colaborador (Com Carimbo Inviolável)")
                        colunas_ordenadas = ["Data e Hora da Transacao (Inviolavel)", "RE", "Funcionário", "Departamento", "Cargo", "EPI", "CA", "Qtd", "Data Entrega Declarada", "Data Vencimento", "Status", "Assinatura"]
                        df_para_exportar = df_historico_func[colunas_ordenadas]
                        
                        csv_logs_func = df_para_exportar.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            label=f"📥 Baixar Logs em CSV (RE {re_exportar})",
                            data=csv_logs_func,
                            file_name=f"logs_epi_RE_{re_exportar}.csv",
                            mime="text/csv"
                        )

# ==============================================================================
# VISÃO 4: DASHBOARD DE GESTÃO
# ==============================================================================
elif menu == "dashboard":
    st.header("📊 Dashboard de Gestão Estratégica")
    if df_base_completa.empty:
        st.info("Nenhum dado disponível para o Dashboard.")
    else:
        tot_registros = len(df_base_completa)
        tot_ass_pendentes = len(df_base_completa[df_base_completa["Assinatura"] == "Pendente"])
        tot_vencidos = len(df_base_completa[df_base_completa["Status"] == "VENCIDO"])
        tot_criticos = len(df_base_completa[df_base_completa["Status"] == "CRITICO (Ate 15 dias)"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total de Lançamentos", tot_registros)
        m2.metric("Assinaturas Pendentes", tot_ass_pendentes)
        m3.metric("EPIs Vencidos", tot_vencidos)
        m4.metric("Atenção Crítica", tot_criticos)
        
        st.markdown("---")
        col_db1, col_db2 = st.columns(2)
        with col_db1:
            st.markdown("#### Status de Validade")
            st.bar_chart(df_base_completa["Status"].value_counts())
        with col_db2:
            st.markdown("#### Entregas por Departamento")
            st.bar_chart(df_base_completa["Departamento"].value_counts())

# ==============================================================================
# VISÃO 5: EPIS VENCIDOS / A VENCER
# ==============================================================================
elif menu == "vencidos":
    st.header("⏳ Controle Sintético de Validades")
    if not df_base_completa.empty:
        df_venc = df_base_completa[df_base_completa["Status"].isin(["VENCIDO", "CRITICO (Ate 15 dias)"])]
        st.dataframe(df_venc[["RE", "Funcionário", "Departamento", "EPI", "Status"]], use_container_width=True)

# ==============================================================================
# VISÃO 6: CENTRAL DE DISPAROS DE E-MAILS (HST)
# ==============================================================================
elif menu == "disparador_alertas":
    st.header("📢 Central de Disparos e Alertas (HST)")
    if not df_base_completa.empty:
        df_pendentes_geral = df_base_completa[df_base_completa['Assinatura'] == "Pendente"]
        st.write(f"Total de pendências gerais: {len(df_pendentes_geral)}")

# ==============================================================================
# VISÃO 7: EXPORTAÇÃO PARA AUDITORIA E MTE
# ==============================================================================
elif menu == "auditoria":
    st.header("🗄️ Relatório Geral para Auditoria e Fiscalização")
    st.markdown("Extração bruta contendo os metadados nativos do servidor (carimbo de tempo inviolável).")
    try:
        resposta_audit = supabase.table("entregas_epi").select("*").execute()
        df_audit = pd.DataFrame(resposta_audit.data)
        if not df_audit.empty:
            if "created_at" in df_audit.columns:
                df_audit = df_audit.rename(columns={"created_at": "Data e Hora da Transacao (Inviolavel)"})
            st.dataframe(df_audit, use_container_width=True)
            csv_audit = df_audit.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Base Bruta para Auditoria (CSV)", data=csv_audit, file_name="auditoria_bruta_epis.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Erro ao extrair logs: {e}")
