import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import io
import base64
from supabase import create_client, Client

# Importações para a geração do PDF da Ficha de EPI (NR-6)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuração global da página do Streamlit
st.set_page_config(page_title="Controle de EPIs - Semasa", layout="wide")

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
                    lote_linhas.append({
                        "re": str(re_digitado),
                        "nome_funcionario": str(nome_funcionario),
                        "epi": str(epi),
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
# VISÃO 2: COLETAR ASSINATURAS PENDENTES (INDIVIDUAL)
# ==============================================================================
elif menu == "coletar_ass":
    st.header("✍️ Regularização de Assinaturas Pendentes")
    st.markdown("Busque o RE do colaborador para listar os itens pendentes e realizar a baixa física com crachá ou cobrá-lo por e-mail.")
    
    re_busca = st.text_input("Digite o RE do funcionário para buscar pendências:").strip()
    
    if re_busca:
        if df_base_completa.empty:
            st.info("Nenhum histórico encontrado.")
        else:
            df_pendentes_func = df_base_completa[(df_base_completa['RE'] == re_busca) & (df_base_completa['Assinatura'] == "Pendente")]
            
            if df_pendentes_func.empty:
                st.success("Este colaborador não possui nenhuma assinatura pendente no sistema!")
            else:
                st.warning(f"Encontradas {len(df_pendentes_func)} entregas pendentes para este RE:")
                df_exibir = df_pendentes_func[["EPI", "Qtd", "Data Entrega"]].copy()
                df_exibir["Data Entrega"] = df_exibir["Data Entrega"].dt.strftime("%d/%m/%Y")
                st.dataframe(df_exibir, use_container_width=True)
                
                # Cobrança rápida por e-mail
                st.markdown("### ✉️ Notificação por E-mail")
                func_nome = df_pendentes_func.iloc[0]["Funcionário"]
                email_destino = df_pendentes_func.iloc[0]["Email"]
                
                lista_itens_texto = "%0A".join([f"- {row['EPI']} (Pendente)" for _, row in df_pendentes_func.iterrows()])
                assunto = urllib.parse.quote(f"COBRANÇA: Assinatura de Ficha de EPI Pendente - RE {re_busca}")
                corpo_email = urllib.parse.quote(
                    f"Prezado(a) Gestor(a) Consta em nosso sistema que {func_nome}, "
                    f"Possui pendências de assinatura no recebimento dos seguintes EPIs: "
                    f"{lista_itens_texto} "
                    f"Por favor, solicite que o(a) mesmo(a) compareça ao HST munido de seu crachá NFC para regularização. "
                    f"Atenciosamente, Equipe HST - Higiene e Segurança do Trabalho - SEMASA"
                )
                link_mailto = f"mailto:{email_destino}?subject={assunto}&body={corpo_email}"
                st.markdown(f'<a href="{link_mailto}" target="_blank" style="padding:10px 18px; border-radius:5px; background-color:#D32F2F; color:white; text-decoration:none; font-weight:bold;">📧 Enviar E-mail de Cobrança para {func_nome}</a>', unsafe_allow_html=True)
                
                st.markdown("---")
                st.markdown("### 🔒 Validação de Baixa Segura (Presencial)")
                
                # Input de crachá
                nfc_baixa = st.text_input("APROXIME O CRACHÁ DO TRABALHADOR AQUI PARA ASSINAR TUDO:", type="password", key="input_cracha_baixa").strip()
                
                if nfc_baixa:
                    df_func_limpo = df_func.dropna(subset=[df_func.columns[0]])
                    mapa_re_cracha = {str(row.iloc[0]).split('.')[0].strip(): str(row.iloc[4]).strip() if len(row) > 4 else "" for _, row in df_func_limpo.iterrows()}
                    mapa_cracha_nome = {str(row.iloc[4]).strip(): str(row.iloc[1]).replace('?', '').strip() for _, row in df_func_limpo.iterrows() if len(row) > 4 and pd.notnull(row.iloc[4])}
                    
                    cracha_correto = mapa_re_cracha.get(re_busca, "")
                    
                    if nfc_baixa != cracha_correto:
                        dono_desse_cracha = mapa_cracha_nome.get(nfc_baixa, "Desconhecido")
                        st.error(f"Bloqueado: Este crachá pertence a '{dono_desse_cracha}'!")
                    else:
                        with st.spinner("Processando assinaturas legítimas no Supabase..."):
                            try:
                                indices_para_alterar = df_pendentes_func['INDEX_ORIGINAL'].tolist()
                                data_hoje_str = datetime.now().strftime("%Y-%m-%d")
                                
                                for id_reg in indices_para_alterar:
                                    supabase.table("entregas_epi").update({"data_entrega": data_hoje_str}).eq("id", id_reg).execute()
                                
                                st.success(f"Sucesso! {len(indices_para_alterar)} pendências eliminadas e assinadas!")
                                st.balloons()
                                
                                st.session_state["input_cracha_baixa"] = ""
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Falha técnica ao atualizar Supabase: {ex}")

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
                        pdf_data = gerar_pdf_ficha(re_exportar, nome_oficial, depto_oficial, df_historico_func)
                        
                        st.download_button(
                            label="📥 Baixar Ficha de EPI Oficial (PDF)",
                            data=pdf_data,
                            file_name=f"Ficha_EPI_{re_exportar}_{nome_oficial.replace(' ', '_')}.pdf",
                            mime="application/pdf"
                        )

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
            df_validades_alertas = df_base_completa.sort_values(by="Data Entrega", ascending=True)
            df_validades_alertas = df_validades_alertas.drop_duplicates(subset=["Funcionário", "EPI"], keep="last")
            
            df_irregulares = df_validades_alertas[df_validades_alertas['Status'].isin(["VENCIDO", "CRITICO (Ate 15 dias)"])]
            
            if df_irregulares.empty:
                st.success("Sensacional! Todos os colaboradores estão com os prazos e trocas de EPIs em dia!")
            else:
                st.error(f"Atenção: Foram localizados {len(df_irregulares)} registros de EPIs vencidos ou com validade crítica.")
                
                func_vencidos_agrupados = df_irregulares.groupby(["RE", "Funcionário", "Email"]).size().reset_index(name="EPIs Irregulares")
                st.dataframe(df_irregulares[["RE", "Funcionário", "EPI", "Data Vencimento", "Dias Restantes", "Status"]], use_container_width=True)
                
                st.markdown("### ⚡ Notificação de Troca / Renovação Obrigatória")
                
                for _, row in func_vencidos_agrupados.iterrows():
                    re_v = row["RE"]
                    nome_v = row["Funcionário"]
                    email_v = row["Email"]
                    qtd_v = row["EPIs Irregulares"]
                    
                    df_itens_v = df_irregulares[df_irregulares["RE"] == re_v]
                    
                    lista_vencidos_texto = []
                    for _, item in df_itens_v.iterrows():
                        prazo_txt = f"VENCIDO há {abs(item['Dias Restantes'])} dias" if item['Dias Restantes'] < 0 else f"A VENCER (Restam {item['Dias Restantes']} dias)"
                        lista_vencidos_texto.append(f"- {item['EPI']} | Status: {prazo_txt} (Vencimento em: {item['Data Vencimento'].strftime('%d/%m/%Y')})")
                    
                    lista_vencidos_pronta = "%0A".join(lista_vencidos_texto)
                    
                    assunto_vencido = urllib.parse.quote(f"AVISO: Renovação e Troca de EPI Obrigatória - RE {re_v}")
                    corpo_vencido = urllib.parse.quote(
                        f"Prezado(a) {nome_v}, "
                        f"Identificamos em nosso cronograma de controle do SEMASA que seu(s) equipamento(s) "
                        f"de proteção individual listado(s) abaixo atingiu(aram) o prazo limite de validade de uso: "
                        f"{lista_vencidos_pronta} "
                        f"Para sua total proteção e em cumprimento às Normas Regulamentadoras, solicitamos que compareça "
                        f"ao setor de Segurança do Trabalho (HST) o quanto antes. "
                        f"Atenciosamente, Equipe de Segurança do Trabalho - SEMASA"
                    )
                    
                    link_mailto_vencido = f"mailto:{email_v}?subject={assunto_vencido}&body={corpo_vencido}"
                    
                    col_v1, col_v2 = st.columns([3, 1])
                    cor_status = "#D32F2F" if any(df_itens_v['Dias Restantes'] < 0) else "#EF6C00"
                    
                    col_v1.markdown(f"👤 **{nome_v}** (RE: {re_v}) — possui <span style='color:{cor_status}; font-weight:bold;'>{qtd_v} equipamento(s)</span> precisando de troca.", unsafe_allow_html=True)
                    col_v2.markdown(f'<a href="{link_mailto_vencido}" target="_blank" style="padding:4px 10px; border-radius:4px; background-color:{cor_status}; color:white; text-decoration:none; font-size:13px; font-weight:bold;">✉️ Cobrar Troca</a>', unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # ABA 3: COBRANÇA CONSOLIDADA POR GESTOR (DEPARTAMENTO)
        # ----------------------------------------------------------------------
        with aba_gestores:
            st.markdown("### 🏢 Envio de Relatório de Pendências para as Chefias")
            st.markdown("Cobre os gestores enviando uma lista unificada com todos os colaboradores do departamento que possuem pendências.")
            
            df_ass_pend = df_base_completa[df_base_completa['Assinatura'] == "Pendente"]
            df_val_ativas = df_base_completa.sort_values(by="Data Entrega", ascending=True).drop_duplicates(subset=["Funcionário", "EPI"], keep="last")
            df_epi_irreg = df_val_ativas[df_val_ativas['Status'].isin(["VENCIDO", "CRITICO (Ate 15 dias)"])]
            
            deptos_com_problema = set(df_ass_pend['Departamento'].dropna().unique()).union(set(df_epi_irreg['Departamento'].dropna().unique()))
            deptos_com_problema = sorted([d for d in deptos_com_problema if d and str(d).lower() != 'nan' and str(d).strip() != 'Não Informado'])
            
            if not deptos_com_problema:
                st.success("🎉 Excelente! Nenhum departamento possui pendências no momento.")
            else:
                st.info("Clique no departamento para expandir e gerar o e-mail para o gestor correspondente.")
                
                for depto in deptos_com_problema:
                    with st.expander(f"📁 Relatório do Departamento: {depto}"):
                        texto_email = f"Prezado(a) Gestor(a) do departamento {depto},\n\n"
                        texto_email += "Abaixo listamos as pendências de Segurança do Trabalho (HST) referentes aos colaboradores sob sua gestão. Solicitamos seu apoio na orientação para que os mesmos regularizem sua situação o mais breve possível.\n\n"
                        
                        tem_pendencia = False
                        
                        # 1. Agrupando Assinaturas do Departamento
                        df_ass_dep = df_ass_pend[df_ass_pend['Departamento'] == depto]
                        if not df_ass_dep.empty:
                            tem_pendencia = True
                            texto_email += "🔴 ASSINATURAS PENDENTES (Falta validação com Crachá):\n"
                            func_ass_grp = df_ass_dep.groupby("Funcionário")
                            for func, itens in func_ass_grp:
                                lista_epis = ", ".join(itens['EPI'].tolist())
                                texto_email += f"   - {func}: {lista_epis}\n"
                            texto_email += "\n"
                            
                        # 2. Agrupando EPIs Vencidos do Departamento
                        df_epi_dep = df_epi_irreg[df_epi_irreg['Departamento'] == depto]
                        if not df_epi_dep.empty:
                            tem_pendencia = True
                            texto_email += "🟠 EPIs VENCIDOS OU COM TROCA OBRIGATÓRIA PRÓXIMA:\n"
                            func_epi_grp = df_epi_dep.groupby("Funcionário")
                            for func, itens in func_epi_grp:
                                lista_epis_v = []
                                for _, row in itens.iterrows():
                                    status_txt = "VENCIDO" if row['Dias Restantes'] < 0 else "A VENCER"
                                    lista_epis_v.append(f"{row['EPI']} ({status_txt})")
                                texto_email += f"   - {func}: {', '.join(lista_epis_v)}\n"
                            texto_email += "\n"
                            
                        texto_email += "Por favor, oriente-os a comparecer ao HST munidos do crachá funcional.\n\nAtenciosamente,\nEquipe de Segurança do Trabalho - SEMASA"
                        
                        if tem_pendencia:
                            c_info, c_btn = st.columns([3, 1])
                            total_irreg = len(df_ass_dep) + len(df_epi_dep)
                            c_info.write(f"Há um total de **{total_irreg} irregularidades** somando todos os funcionários da(o) **{depto}**.")
                            
                            assunto_depto = urllib.parse.quote(f"Relatório de Pendências de EPIs (HST) - {depto}")
                            corpo_depto = urllib.parse.quote(texto_email)
                            link_mailto_depto = f"mailto:?subject={assunto_depto}&body={corpo_depto}"
                            
                            c_btn.markdown(f'<a href="{link_mailto_depto}" target="_blank" style="display:inline-block; padding:8px 12px; border-radius:4px; background-color:#2E7D32; color:white; text-decoration:none; font-size:13px; font-weight:bold; text-align:center;">✉️ Notificar Gestor(a)</a>', unsafe_allow_html=True)

# ==============================================================================
# VISÕES DE DASHBOARD E ALERTAS (DEMAIS TELAS)
# ==============================================================================
# ==============================================================================
# VISÃO 5: EXPORTAÇÃO PARA AUDITORIA E MTE
# ==============================================================================
elif menu == "auditoria":
    st.header("🗄️ Relatório Geral para Auditoria e Fiscalização")
    st.markdown("Exporte o histórico completo e bruto de transações do banco de dados. Este relatório extrai os **metadados nativos do servidor** (carimbo de tempo inviolável), servindo como comprovação legal da data e hora exata em que as transações ocorreram no sistema.")
    
    with st.spinner("Extraindo logs criptografados do banco de dados..."):
        try:
            # Puxa a base bruta direto do Supabase, incluindo o created_at (Prova de Ouro)
            resposta_audit = supabase.table("entregas_epi").select("*").execute()
            df_audit = pd.DataFrame(resposta_audit.data)
            
            if df_audit.empty:
                st.info("Nenhum registro localizado no banco de dados.")
            else:
                # Renomeia as colunas para o auditor entender exatamente o que é cada dado
                df_audit = df_audit.rename(columns={
                    "id": "ID Transação",
                    "created_at": "Carimbo de Tempo do Servidor (Prova Inviolável)",
                    "re": "RE Colaborador",
                    "nome_funcionario": "Nome do Colaborador",
                    "epi": "EPI Entregue",
                    "data_entrega": "Data de Referência da Baixa/Assinatura"
                })
                
                # Reorganiza a ordem das colunas para destacar o carimbo de tempo
                ordem_colunas = ["ID Transação", "Carimbo de Tempo do Servidor (Prova Inviolável)", "RE Colaborador", "Nome do Colaborador", "EPI Entregue", "Data de Referência da Baixa/Assinatura"]
                df_audit = df_audit[ordem_colunas]
                
                st.success(f"Extração concluída: {len(df_audit)} registros consolidados protegidos contra alteração.")
                
                # Mostra uma prévia na tela
                st.dataframe(df_audit, use_container_width=True)
                
                # Configura a exportação para CSV compatível nativamente com o Excel (utf-8-sig)
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
