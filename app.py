import os
import sqlite3
import io
import zipfile
from datetime import datetime, date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# ============================================================
# Diário Gestacional — versão revisada
# Mantém compatibilidade com as tabelas da versão anterior.
# ============================================================

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(APP_DIR / "diario_gestacional.db")))
TZ = ZoneInfo("America/Sao_Paulo")
WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

st.set_page_config(
    page_title="Diário Gestacional",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paleta com contraste explícito para evitar textos brancos/invisíveis
st.markdown("""
<style>
:root {
  --navy: #18324b;
  --blue: #315d7d;
  --teal: #5b9b91;
  --pink: #d98e9b;
  --ink: #243447;
  --muted: #64748b;
  --line: #e3eaf0;
  --paper: #ffffff;
  --canvas: #f4f7fa;
}
html, body, [class*="css"], .stApp {
  color: var(--ink) !important;
}
.stApp { background: var(--canvas); }
[data-testid="stHeader"] { background: rgba(244,247,250,.92); }
[data-testid="stSidebar"] {
  background: #edf3f7;
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] * { color: #29445b !important; }
.block-container {
  max-width: 1320px;
  padding-top: 1.6rem;
  padding-bottom: 2.5rem;
}
h1, h2, h3, h4, p, label, span, div {
  text-rendering: optimizeLegibility;
}
h1, h2, h3 { color: var(--navy) !important; }
p, label, .stMarkdown, .stCaption, [data-testid="stMetricLabel"] {
  color: var(--ink);
}
.hero {
  background: linear-gradient(120deg, #ffffff 0%, #e8f1f5 100%);
  border: 1px solid #dce7ee;
  border-radius: 22px;
  padding: 25px 28px;
  margin: 4px 0 22px 0;
  box-shadow: 0 8px 24px rgba(24,50,75,.045);
}
.hero h1 { margin: 0; color: #18324b !important; font-size: 2rem; }
.hero p { margin: 7px 0 0; color: #587084 !important; }
.eyebrow {
  color: #56847e !important;
  font-size: .78rem;
  font-weight: 700;
  letter-spacing: .09em;
  text-transform: uppercase;
  margin-bottom: 5px;
}
.section-note { color: #64748b !important; font-size: .92rem; }
div[data-testid="stMetric"] {
  background: white;
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 16px 18px;
  box-shadow: 0 5px 18px rgba(24,50,75,.035);
}
div[data-testid="stMetricLabel"] { color: #617487 !important; }
div[data-testid="stMetricValue"] { color: var(--navy) !important; }
.stButton > button, .stDownloadButton > button {
  border-radius: 11px;
  font-weight: 650;
  min-height: 2.65rem;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button {
  background: var(--navy);
  border-color: var(--navy);
  color: white !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button:hover {
  background: #284d69;
  border-color: #284d69;
}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stNumberInput"] input,
div[data-testid="stDateInput"] input,
div[data-testid="stTimeInput"] input {
  color: #243447 !important;
  background: white !important;
}
div[data-baseweb="select"] > div {
  background: white !important;
  color: #243447 !important;
}
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
}
div[data-testid="stExpander"] {
  background: white;
  border: 1px solid var(--line);
  border-radius: 13px;
}
hr { border-color: var(--line); }
.small-footer { color: #718096 !important; font-size: .78rem; }
@media (max-width: 700px) {
  .block-container { padding: 1rem .8rem 2rem; }
  .hero { padding: 19px; }
  .hero h1 { font-size: 1.55rem; }
}
</style>
""", unsafe_allow_html=True)


def now_local():
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS glucose (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measured_at TEXT NOT NULL, value REAL NOT NULL, context TEXT NOT NULL,
            minutes_after_meal INTEGER, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS blood_pressure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measured_at TEXT NOT NULL, systolic INTEGER NOT NULL,
            diastolic INTEGER NOT NULL, pulse INTEGER, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eaten_at TEXT NOT NULL, meal_type TEXT NOT NULL,
            description TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS contractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL, ended_at TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL, interval_seconds INTEGER
        );
        CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL, baby TEXT NOT NULL,
            movement_type TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS symptoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL, symptom TEXT NOT NULL,
            intensity TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL, subject TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, reminder_time TEXT NOT NULL,
            days TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
        );
        """)
        con.commit()


def query_df(sql, params=()):
    with connect() as con:
        return pd.read_sql_query(sql, con, params=params)


def execute(sql, params=()):
    with connect() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid


def get_state(key):
    with connect() as con:
        row = con.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def set_state(key, value):
    execute(
        "INSERT INTO app_state(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def fmt_dt(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(value)


def section(title, subtitle=None):
    st.subheader(title)
    if subtitle:
        st.markdown(f'<p class="section-note">{subtitle}</p>', unsafe_allow_html=True)


def show_history(df, table, id_col="id", label="registro"):
    if df.empty:
        st.info(f"Nenhum {label} cadastrado ainda.")
        return
    display = df.drop(columns=[id_col], errors="ignore").copy()
    st.dataframe(display, use_container_width=True, hide_index=True)
    ids = df[id_col].astype(int).tolist()
    with st.expander(f"Excluir {label}"):
        chosen = st.selectbox(
            "Selecione pelo número do registro",
            ids,
            format_func=lambda x: f"Registro #{x}",
            key=f"delete_{table}",
        )
        if st.button("Excluir registro selecionado", key=f"delete_btn_{table}"):
            execute(f"DELETE FROM {table} WHERE id=?", (int(chosen),))
            st.success("Registro excluído.")
            st.rerun()


def login_gate():
    configured = None
    try:
        configured = st.secrets.get("app_password") or st.secrets.get("APP_PASSWORD")
    except Exception:
        pass
    configured = configured or os.getenv("APP_PASSWORD")
    if not configured:
        st.markdown('<div class="hero"><div class="eyebrow">Acesso privado</div><h1>♡ Diário Gestacional</h1><p>Seu espaço de registros e acompanhamento.</p></div>', unsafe_allow_html=True)
        st.error("Configure uma senha antes de usar o diário.")
        st.code('app_password = "sua-senha-forte"', language="toml")
        st.caption("No Streamlit Cloud: Manage app → Settings → Secrets. Não publique a senha no código.")
        st.stop()

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.markdown('<div class="hero"><div class="eyebrow">Bem-vinda</div><h1>♡ Diário Gestacional</h1><p>Um espaço organizado para acompanhar os registros da gestação.</p></div>', unsafe_allow_html=True)
        with st.form("login_form"):
            pwd = st.text_input("Senha de acesso", type="password")
            submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if submit:
            if pwd == configured:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")
        st.stop()


init_db()
login_gate()

with st.sidebar:
    st.markdown("## ♡ Diário Gestacional")
    st.caption("Acompanhamento pessoal")
    st.divider()
    page = st.radio(
        "MENU PRINCIPAL",
        [
            "Visão geral", "Glicemia", "Pressão arterial", "Refeições",
            "Contrações", "Movimentos dos bebês", "Sintomas", "Anotações",
            "Lembretes", "Relatórios",
        ],
        label_visibility="visible",
    )
    st.divider()
    if st.button("Sair da conta", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()
    st.markdown(
        '<p class="small-footer">Este diário organiza informações para consulta. Não substitui avaliação ou orientação da equipe obstétrica.</p>',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="hero"><div class="eyebrow">Cuidado, memória e acompanhamento</div>'
    '<h1>Diário Gestacional</h1>'
    '<p>Registre informações importantes e consulte seu histórico em um só lugar.</p></div>',
    unsafe_allow_html=True,
)

today = now_local().date()
today_s = today.isoformat()

# --------------------------- VISÃO GERAL ---------------------------
if page == "Visão geral":
    section("Resumo do dia", today.strftime("%A, %d/%m/%Y"))
    g = query_df(
        "SELECT value, measured_at FROM glucose WHERE substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1",
        (today_s,),
    )
    bp = query_df(
        "SELECT systolic,diastolic,measured_at FROM blood_pressure WHERE substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1",
        (today_s,),
    )
    meals_n = int(query_df("SELECT COUNT(*) n FROM meals WHERE substr(eaten_at,1,10)=?", (today_s,)).iloc[0]["n"])
    contractions_n = int(query_df("SELECT COUNT(*) n FROM contractions WHERE substr(started_at,1,10)=?", (today_s,)).iloc[0]["n"])
    movements_n = int(query_df("SELECT COUNT(*) n FROM movements WHERE substr(recorded_at,1,10)=?", (today_s,)).iloc[0]["n"])

    a, b, c, d, e = st.columns(5)
    a.metric("Última glicemia", f'{g.iloc[0]["value"]:g} mg/dL' if not g.empty else "—")
    b.metric("Última pressão", f'{int(bp.iloc[0]["systolic"])}/{int(bp.iloc[0]["diastolic"])}' if not bp.empty else "—")
    c.metric("Refeições", meals_n)
    d.metric("Contrações", contractions_n)
    e.metric("Movimentos", movements_n)
    st.info("Os números são apresentados como foram registrados. O aplicativo não interpreta exames nem recomenda condutas.")
    st.divider()
    left, right = st.columns(2)
    with left:
        section("Últimas medições de glicemia")
        hist = query_df("SELECT measured_at AS 'Data e horário', value AS 'mg/dL', context AS 'Contexto' FROM glucose ORDER BY measured_at DESC LIMIT 5")
        if hist.empty:
            st.caption("As medições aparecerão aqui depois de cadastradas.")
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
    with right:
        section("Últimas medições de pressão")
        hist = query_df("SELECT measured_at AS 'Data e horário', systolic AS 'Sistólica', diastolic AS 'Diastólica', pulse AS 'Pulso' FROM blood_pressure ORDER BY measured_at DESC LIMIT 5")
        if hist.empty:
            st.caption("As medições aparecerão aqui depois de cadastradas.")
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
# --------------------------- GLICEMIA ---------------------------
elif page == "Glicemia":
    section("Glicemia", "Registre a medição, o contexto e observações para consultar depois.")
    with st.form("glucose_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Data", value=today)
        t = c2.time_input("Horário", value=now_local().time())
        c1, c2 = st.columns(2)
        value = c1.number_input("Resultado (mg/dL)", min_value=1.0, max_value=1000.0, value=90.0, step=1.0)
        context = c2.selectbox("Contexto da medição", ["Jejum", "Antes da refeição", "1 hora após refeição", "2 horas após refeição", "Outro"])
        mins = st.number_input("Minutos após refeição (se aplicável)", min_value=0, max_value=1440, value=0, step=5)
        notes = st.text_area("Observações", placeholder="Ex.: como estava se sentindo, orientação recebida...")
        if st.form_submit_button("Salvar medição", type="primary", use_container_width=True):
            execute(
                "INSERT INTO glucose(measured_at,value,context,minutes_after_meal,notes) VALUES(?,?,?,?,?)",
                (datetime.combine(d, t).isoformat(sep=" "), value, context, int(mins) or None, notes.strip()),
            )
            st.success("Medição salva.")
            st.rerun()
    section("Histórico de medições")
    df = query_df("SELECT id, measured_at AS 'Data e horário', value AS 'mg/dL', context AS 'Contexto', minutes_after_meal AS 'Minutos após refeição', notes AS 'Observações' FROM glucose ORDER BY measured_at DESC")
    show_history(df, "glucose", label="medição de glicemia")
    if not df.empty:
        chart = query_df("SELECT measured_at, value FROM glucose ORDER BY measured_at")
        chart["Data"] = pd.to_datetime(chart["measured_at"])
        st.line_chart(chart.set_index("Data")["value"], y_label="mg/dL")

# --------------------------- PRESSÃO ---------------------------
elif page == "Pressão arterial":
    section("Pressão arterial", "Guarde as medições e observações informadas pela equipe de saúde.")
    with st.form("bp_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Data", value=today, key="bp_date")
        t = c2.time_input("Horário", value=now_local().time(), key="bp_time")
        a, b, c = st.columns(3)
        systolic = a.number_input("Sistólica (mmHg)", min_value=1, max_value=300, value=120)
        diastolic = b.number_input("Diastólica (mmHg)", min_value=1, max_value=200, value=80)
        pulse = c.number_input("Pulso (bpm)", min_value=0, max_value=250, value=0)
        notes = st.text_area("Observações", key="bp_notes")
        if st.form_submit_button("Salvar pressão", type="primary", use_container_width=True):
            execute(
                "INSERT INTO blood_pressure(measured_at,systolic,diastolic,pulse,notes) VALUES(?,?,?,?,?)",
                (datetime.combine(d, t).isoformat(sep=" "), int(systolic), int(diastolic), int(pulse) or None, notes.strip()),
            )
            st.success("Medição salva.")
            st.rerun()
    section("Histórico")
    df = query_df("SELECT id, measured_at AS 'Data e horário', systolic AS 'Sistólica', diastolic AS 'Diastólica', pulse AS 'Pulso', notes AS 'Observações' FROM blood_pressure ORDER BY measured_at DESC")
    show_history(df, "blood_pressure", label="medição de pressão")

# --------------------------- REFEIÇÕES ---------------------------
elif page == "Refeições":
    section("Refeições", "Registre alimentos e bebidas para manter um histórico organizado.")
    with st.form("meal_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Data", value=today, key="meal_date")
        t = c2.time_input("Horário", value=now_local().time(), key="meal_time")
        kind = st.selectbox("Tipo de refeição", ["Café da manhã", "Lanche da manhã", "Almoço", "Lanche da tarde", "Jantar", "Ceia", "Outro"])
        desc = st.text_area("O que comeu ou bebeu?", placeholder="Descreva os alimentos e bebidas...")
        notes = st.text_input("Observações (opcional)")
        if st.form_submit_button("Salvar refeição", type="primary", use_container_width=True):
            if not desc.strip():
                st.error("Descreva a refeição antes de salvar.")
            else:
                execute("INSERT INTO meals(eaten_at,meal_type,description,notes) VALUES(?,?,?,?)",
                        (datetime.combine(d, t).isoformat(sep=" "), kind, desc.strip(), notes.strip()))
                st.success("Refeição salva.")
                st.rerun()
    section("Histórico de refeições")
    df = query_df("SELECT id, eaten_at AS 'Data e horário', meal_type AS 'Tipo', description AS 'Descrição', notes AS 'Observações' FROM meals ORDER BY eaten_at DESC")
    show_history(df, "meals", label="refeição")

# --------------------------- CONTRAÇÕES ---------------------------
elif page == "Contrações":
    section("Cronômetro de contrações", "Use o cronômetro para registrar início e término de cada episódio.")
    running = get_state("contraction_started_at")
    if running:
        start_dt = datetime.fromisoformat(running)
        elapsed = max(0, int((now_local() - start_dt).total_seconds()))
        st.warning(f"Contração em andamento · Início {start_dt.strftime('%H:%M:%S')} · Duração {elapsed // 60:02d}:{elapsed % 60:02d}")
        if st.button("Finalizar e salvar contração", type="primary", use_container_width=True):
            end_dt = now_local()
            previous = query_df("SELECT started_at FROM contractions ORDER BY started_at DESC LIMIT 1")
            interval = None
            if not previous.empty:
                interval = int((start_dt - datetime.fromisoformat(previous.iloc[0]["started_at"])).total_seconds())
            duration = max(0, int((end_dt - start_dt).total_seconds()))
            execute("INSERT INTO contractions(started_at,ended_at,duration_seconds,interval_seconds) VALUES(?,?,?,?)",
                    (start_dt.isoformat(sep=" "), end_dt.isoformat(sep=" "), duration, interval))
            set_state("contraction_started_at", "")
            st.success("Contração registrada.")
            st.rerun()
    else:
        st.caption("Toque em iniciar no começo e finalize quando terminar.")
        if st.button("Iniciar contração", type="primary", use_container_width=True):
            set_state("contraction_started_at", now_local().isoformat(sep=" "))
            st.rerun()
    df = query_df("SELECT id, started_at, ended_at, duration_seconds, interval_seconds FROM contractions ORDER BY started_at DESC LIMIT 100")
    if not df.empty:
        view = df.copy()
        view["Início"] = pd.to_datetime(view["started_at"]).dt.strftime("%d/%m/%Y %H:%M:%S")
        view["Duração"] = view["duration_seconds"].apply(lambda x: f"{int(x)//60:02d}:{int(x)%60:02d}")
        view["Intervalo entre inícios (min)"] = (view["interval_seconds"] / 60).round(1)
        section("Histórico recente")
        show_history(view[["id", "Início", "Duração", "Intervalo entre inícios (min)"]], "contractions", label="contração")
    else:
        st.info("Nenhuma contração registrada.")
    st.warning("Este cronômetro serve somente para registrar horários. Não use os intervalos para decidir quando procurar atendimento. Siga as orientações da maternidade/equipe obstétrica.")

# --------------------------- MOVIMENTOS ---------------------------
elif page == "Movimentos dos bebês":
    section("Movimentos dos bebês", "Anote percepções e a qual bebê o registro se refere.")
    with st.form("movement_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Data", value=today, key="mov_date")
        t = c2.time_input("Horário", value=now_local().time(), key="mov_time")
        baby = st.selectbox("Bebê", ["Davi Lucca", "Leon", "Não identificado / geral"])
        typ = st.selectbox("Tipo de registro", ["Movimento percebido", "Sequência de movimentos", "Mudança percebida", "Outro"])
        notes = st.text_area("Observações", placeholder="Descreva o que percebeu...")
        if st.form_submit_button("Salvar registro", type="primary", use_container_width=True):
            execute("INSERT INTO movements(recorded_at,baby,movement_type,notes) VALUES(?,?,?,?)",
                    (datetime.combine(d, t).isoformat(sep=" "), baby, typ, notes.strip()))
            st.success("Registro salvo.")
            st.rerun()
    section("Histórico")
    df = query_df("SELECT id, recorded_at AS 'Data e horário', baby AS 'Bebê', movement_type AS 'Registro', notes AS 'Observações' FROM movements ORDER BY recorded_at DESC")
    show_history(df, "movements", label="registro de movimento")
    st.warning("Se perceber redução, ausência ou mudança preocupante nos movimentos habituais, entre em contato imediatamente com a maternidade/equipe obstétrica. Não espere completar uma contagem no aplicativo.")

# --------------------------- SINTOMAS ---------------------------
elif page == "Sintomas":
    section("Sintomas", "Registre o que sentiu, a intensidade percebida e detalhes relevantes.")
    with st.form("symptom_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Data", value=today, key="sym_date")
        t = c2.time_input("Horário", value=now_local().time(), key="sym_time")
        symptom = st.text_input("Sintoma", placeholder="Ex.: dor de cabeça, náusea, inchaço...")
        intensity = st.selectbox("Intensidade percebida", ["Leve", "Moderado", "Intenso", "Não sei avaliar"])
        notes = st.text_area("Detalhes, duração e contexto")
        if st.form_submit_button("Salvar sintoma", type="primary", use_container_width=True):
            if not symptom.strip():
                st.error("Informe o sintoma.")
            else:
                execute("INSERT INTO symptoms(recorded_at,symptom,intensity,notes) VALUES(?,?,?,?)",
                        (datetime.combine(d, t).isoformat(sep=" "), symptom.strip(), intensity, notes.strip()))
                st.success("Sintoma salvo.")
                st.rerun()
    section("Histórico")
    df = query_df("SELECT id, recorded_at AS 'Data e horário', symptom AS 'Sintoma', intensity AS 'Intensidade', notes AS 'Detalhes' FROM symptoms ORDER BY recorded_at DESC")
    show_history(df, "symptoms", label="sintoma")
    st.info("Sangramento, perda de líquido, falta de ar, dor forte, sintomas intensos ou outros sinais de alerta exigem contato imediato com a equipe obstétrica ou serviço de urgência.")

# --------------------------- ANOTAÇÕES ---------------------------
elif page == "Anotações":
    section("Anotações para a equipe de saúde", "Guarde dúvidas, orientações recebidas e informações para a próxima consulta.")
    with st.form("note_form", clear_on_submit=True):
        subject = st.text_input("Assunto", placeholder="Ex.: Dúvidas para a próxima consulta")
        content = st.text_area("Anotação", height=150)
        if st.form_submit_button("Salvar anotação", type="primary", use_container_width=True):
            if not subject.strip() or not content.strip():
                st.error("Preencha o assunto e a anotação.")
            else:
                execute("INSERT INTO notes(created_at,subject,content) VALUES(?,?,?)",
                        (now_local().isoformat(sep=" "), subject.strip(), content.strip()))
                st.success("Anotação salva.")
                st.rerun()
    section("Anotações salvas")
    df = query_df("SELECT id, created_at AS 'Data e horário', subject AS 'Assunto', content AS 'Anotação' FROM notes ORDER BY created_at DESC")
    show_history(df, "notes", label="anotação")

# --------------------------- LEMBRETES ---------------------------
elif page == "Lembretes":
    section("Lembretes", "Organize lembretes que ficam visíveis dentro do aplicativo.")
    st.info("Os lembretes são exibidos quando você abre o aplicativo. Esta versão não envia notificações com o navegador fechado.")
    with st.form("reminder_form", clear_on_submit=True):
        title = st.text_input("O que deseja lembrar?", placeholder="Ex.: Separar exames para a consulta")
        c1, c2 = st.columns(2)
        rtime = c1.time_input("Horário", value=time(8, 0))
        days = c2.multiselect("Repetir nos dias", WEEKDAYS, default=WEEKDAYS)
        if st.form_submit_button("Criar lembrete", type="primary", use_container_width=True):
            if not title.strip() or not days:
                st.error("Informe o lembrete e selecione ao menos um dia.")
            else:
                execute("INSERT INTO reminders(title,reminder_time,days,active) VALUES(?,?,?,1)",
                        (title.strip(), rtime.strftime("%H:%M"), ",".join(days)))
                st.success("Lembrete criado.")
                st.rerun()
    df = query_df("SELECT id, title AS 'Lembrete', reminder_time AS 'Horário', days AS 'Dias', active FROM reminders ORDER BY reminder_time")
    if not df.empty:
        view = df.copy()
        view["Status"] = view["active"].map({1: "Ativo", 0: "Pausado"})
        show_history(view[["id", "Lembrete", "Horário", "Dias", "Status"]], "reminders", label="lembrete")
        ids = {f'#{int(r["id"])} · {r["Lembrete"]} ({r["Horário"]})': int(r["id"]) for _, r in df.iterrows()}
        selected = st.selectbox("Lembrete para ativar/pausar", list(ids))
        if st.button("Ativar / pausar lembrete"):
            execute("UPDATE reminders SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (ids[selected],))
            st.rerun()
    else:
        st.caption("Você ainda não criou lembretes.")
    now = now_local()
    day = WEEKDAYS[now.weekday()]
    due = query_df("SELECT title, reminder_time FROM reminders WHERE active=1")
    # Consulta simples, mantendo os dias como foram cadastrados.
    due = query_df("SELECT title, reminder_time, days FROM reminders WHERE active=1")
    due_now = [r["title"] for _, r in due.iterrows()
               if day in str(r["days"]).split(",") and r["reminder_time"] == now.strftime("%H:%M")]
    if due_now:
        for item in due_now:
            st.success(f"Lembrete de agora ({now.strftime('%H:%M')}): {item}")

# --------------------------- RELATÓRIOS ---------------------------
elif page == "Relatórios":
    section("Relatórios e exportação", "Consulte e baixe os registros para compartilhar com a equipe de saúde.")
    tables = {
        "Glicemia": "SELECT measured_at AS data_hora, value AS glicemia_mg_dl, context AS contexto, minutes_after_meal AS minutos_apos_refeicao, notes AS observacoes FROM glucose ORDER BY measured_at",
        "Pressão arterial": "SELECT measured_at AS data_hora, systolic AS sistolica, diastolic AS diastolica, pulse AS pulso, notes AS observacoes FROM blood_pressure ORDER BY measured_at",
        "Refeições": "SELECT eaten_at AS data_hora, meal_type AS tipo, description AS descricao, notes AS observacoes FROM meals ORDER BY eaten_at",
        "Contrações": "SELECT started_at AS inicio, ended_at AS fim, duration_seconds AS duracao_segundos, interval_seconds AS intervalo_segundos FROM contractions ORDER BY started_at",
        "Movimentos": "SELECT recorded_at AS data_hora, baby AS bebe, movement_type AS registro, notes AS observacoes FROM movements ORDER BY recorded_at",
        "Sintomas": "SELECT recorded_at AS data_hora, symptom AS sintoma, intensity AS intensidade, notes AS detalhes FROM symptoms ORDER BY recorded_at",
        "Anotações": "SELECT created_at AS data_hora, subject AS assunto, content AS anotacao FROM notes ORDER BY created_at",
        "Lembretes": "SELECT title AS lembrete, reminder_time AS horario, days AS dias, active AS ativo FROM reminders ORDER BY reminder_time",
    }
    all_data = {}
    for label, sql in tables.items():
        df = query_df(sql)
        all_data[label] = df
        with st.expander(f"{label} · {len(df)} registro(s)"):
            if df.empty:
                st.caption("Sem registros.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    f"Baixar {label} em CSV",
                    df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{label.lower().replace(' ', '_')}.csv",
                    mime="text/csv",
                    key=f"csv_{label}",
                )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for label, df in all_data.items():
            archive.writestr(f"{label.lower().replace(' ', '_')}.csv", df.to_csv(index=False).encode("utf-8-sig"))
    st.download_button(
        "Baixar backup completo (ZIP)",
        data=buffer.getvalue(),
        file_name=f"backup_diario_gestacional_{today_s}.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )
    st.caption("O backup reúne os dados cadastrados em arquivos CSV. Guarde-o em local seguro.")

st.divider()
st.markdown(
    '<p class="small-footer">Diário Gestacional · Ferramenta de organização pessoal. Os registros não constituem diagnóstico, triagem ou orientação médica. Em caso de dúvida ou sinal de alerta, contate a equipe obstétrica.</p>',
    unsafe_allow_html=True,
)
