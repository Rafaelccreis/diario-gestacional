import os
import sqlite3
from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).parent
DB_PATH = Path(os.getenv("DB_PATH", APP_DIR / "diario_gestacional.db"))
TZ = ZoneInfo("America/Sao_Paulo")

st.set_page_config(
    page_title="Diário Gestacional",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp { background: #f5f8fc; }
    [data-testid="stSidebar"] { background: #edf3f8; }
    .block-container { padding-top: 1.5rem; max-width: 1200px; }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e4ebf2;
        padding: 14px; border-radius: 14px;
    }
    .hero {
        background: linear-gradient(120deg,#ffffff,#eaf3f7);
        border: 1px solid #e2ebf2; border-radius: 18px;
        padding: 22px; margin-bottom: 16px;
    }
    .muted { color: #64748b; }
</style>
""", unsafe_allow_html=True)

def now_local():
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)

def connect():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS glucose (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measured_at TEXT NOT NULL,
            value REAL NOT NULL,
            context TEXT NOT NULL,
            minutes_after_meal INTEGER,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS blood_pressure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measured_at TEXT NOT NULL,
            systolic INTEGER NOT NULL,
            diastolic INTEGER NOT NULL,
            pulse INTEGER,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            eaten_at TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            description TEXT NOT NULL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS contractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            interval_seconds INTEGER
        );
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            baby TEXT NOT NULL,
            movement_type TEXT NOT NULL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS symptoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            symptom TEXT NOT NULL,
            intensity TEXT NOT NULL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            subject TEXT NOT NULL,
            content TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            reminder_time TEXT NOT NULL,
            days TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
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
    df = query_df("SELECT value FROM app_state WHERE key=?", (key,))
    return None if df.empty else df.iloc[0]["value"]

def set_state(key, value):
    execute("INSERT INTO app_state(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def fmt_dt(value):
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value

def login_gate():
    configured = None
    try:
        configured = st.secrets.get("app_password")
    except Exception:
        configured = None
    configured = configured or os.getenv("APP_PASSWORD")
    if not configured:
        st.error("A senha ainda não foi configurada. Configure APP_PASSWORD ou .streamlit/secrets.toml antes de usar.")
        st.code('app_password = "crie-uma-senha-forte-aqui"', language="toml")
        st.stop()
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.markdown('<div class="hero"><h1>♡ Diário Gestacional</h1><p class="muted">Acompanhamento pessoal e privado</p></div>', unsafe_allow_html=True)
        pwd = st.text_input("Senha de acesso", type="password")
        if st.button("Entrar", type="primary", use_container_width=True):
            if pwd == configured:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Senha incorreta.")
        st.stop()

init_db()
login_gate()

st.sidebar.title("♡ Diário Gestacional")
st.sidebar.caption("Acompanhamento pessoal")
page = st.sidebar.radio("Navegação", [
    "Visão geral", "Glicemia", "Pressão arterial", "Refeições",
    "Contrações", "Movimentos dos bebês", "Sintomas", "Anotações",
    "Lembretes", "Relatórios"
])
st.sidebar.divider()
if st.sidebar.button("Sair", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()
st.sidebar.caption("Este diário organiza registros; não substitui orientação ou avaliação obstétrica.")

st.markdown('<div class="hero"><h1 style="margin:0;color:#203b59">Diário Gestacional</h1><p class="muted" style="margin:6px 0 0">Registre, acompanhe e compartilhe informações com a equipe de saúde.</p></div>', unsafe_allow_html=True)

today = date.today().isoformat()

if page == "Visão geral":
    st.subheader("Resumo de hoje")
    g = query_df("SELECT * FROM glucose WHERE substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1", (today,))
    bp = query_df("SELECT * FROM blood_pressure WHERE substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1", (today,))
    meals_today = query_df("SELECT COUNT(*) n FROM meals WHERE substr(eaten_at,1,10)=?", (today,)).iloc[0]["n"]
    c_today = query_df("SELECT COUNT(*) n FROM contractions WHERE substr(started_at,1,10)=?", (today,)).iloc[0]["n"]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Última glicemia", f'{g.iloc[0]["value"]:g} mg/dL' if not g.empty else "—")
    c2.metric("Última pressão", f'{bp.iloc[0]["systolic"]}/{bp.iloc[0]["diastolic"]}' if not bp.empty else "—")
    c3.metric("Refeições registradas", int(meals_today))
    c4.metric("Contrações registradas", int(c_today))
    st.info("Os valores são exibidos como foram registrados. O aplicativo não classifica resultados nem recomenda condutas.")
    st.subheader("Últimos registros")
    for title, sql, col in [
        ("Glicemia", "SELECT measured_at AS Data, value AS 'mg/dL', context AS Contexto FROM glucose ORDER BY measured_at DESC LIMIT 5", None),
        ("Pressão arterial", "SELECT measured_at AS Data, systolic AS Sistólica, diastolic AS Diastólica, pulse AS Pulso FROM blood_pressure ORDER BY measured_at DESC LIMIT 5", None),
        ("Refeições", "SELECT eaten_at AS Data, meal_type AS Refeição, description AS Descrição FROM meals ORDER BY eaten_at DESC LIMIT 5", None),
    ]:
        st.markdown(f"**{title}**")
        df = query_df(sql)
        if df.empty: st.caption("Nenhum registro ainda.")
        else: st.dataframe(df, use_container_width=True, hide_index=True)

elif page == "Glicemia":
    st.subheader("Registrar glicemia")
    with st.form("glucose_form", clear_on_submit=True):
        d = st.date_input("Data", value=date.today())
        t = st.time_input("Horário", value=now_local().time())
        value = st.number_input("Glicemia (mg/dL)", min_value=1.0, max_value=1000.0, step=1.0)
        context = st.selectbox("Quando foi medida?", ["Jejum", "Antes da refeição", "1 hora após refeição", "2 horas após refeição", "Outro"])
        mins = st.number_input("Minutos após refeição (se aplicável)", min_value=0, max_value=1440, value=0)
        notes = st.text_input("Observações")
        ok = st.form_submit_button("Salvar glicemia", type="primary")
        if ok:
            execute("INSERT INTO glucose(measured_at,value,context,minutes_after_meal,notes) VALUES(?,?,?,?,?)",
                    (datetime.combine(d,t).isoformat(sep=" "), value, context, int(mins) if mins else None, notes))
            st.success("Glicemia registrada.")
    df = query_df("SELECT measured_at AS Data, value AS 'mg/dL', context AS Contexto, minutes_after_meal AS 'Minutos após refeição', notes AS Observações FROM glucose ORDER BY measured_at DESC")
    st.subheader("Histórico")
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        chart = query_df("SELECT measured_at, value FROM glucose ORDER BY measured_at")
        chart["medição"] = pd.to_datetime(chart["measured_at"])
        st.line_chart(chart.set_index("medição")["value"])
    else: st.caption("Ainda não há medições.")

elif page == "Pressão arterial":
    st.subheader("Registrar pressão arterial")
    with st.form("bp_form", clear_on_submit=True):
        d = st.date_input("Data", value=date.today(), key="bp_date")
        t = st.time_input("Horário", value=now_local().time(), key="bp_time")
        a,b,c = st.columns(3)
        systolic = a.number_input("Sistólica (mmHg)", min_value=1, max_value=300, value=120)
        diastolic = b.number_input("Diastólica (mmHg)", min_value=1, max_value=200, value=80)
        pulse = c.number_input("Pulso (bpm)", min_value=0, max_value=250, value=0)
        notes = st.text_input("Observações", key="bp_notes")
        if st.form_submit_button("Salvar pressão", type="primary"):
            execute("INSERT INTO blood_pressure(measured_at,systolic,diastolic,pulse,notes) VALUES(?,?,?,?,?)",
                    (datetime.combine(d,t).isoformat(sep=" "), int(systolic), int(diastolic), int(pulse) or None, notes))
            st.success("Pressão registrada.")
    df = query_df("SELECT measured_at AS Data, systolic AS Sistólica, diastolic AS Diastólica, pulse AS Pulso, notes AS Observações FROM blood_pressure ORDER BY measured_at DESC")
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.caption("Ainda não há medições.")

elif page == "Refeições":
    st.subheader("Registrar refeição")
    with st.form("meal_form", clear_on_submit=True):
        d = st.date_input("Data", value=date.today(), key="meal_date")
        t = st.time_input("Horário", value=now_local().time(), key="meal_time")
        kind = st.selectbox("Tipo", ["Café da manhã", "Lanche da manhã", "Almoço", "Lanche da tarde", "Jantar", "Ceia", "Outro"])
        desc = st.text_area("O que comeu ou bebeu?")
        notes = st.text_input("Observações")
        if st.form_submit_button("Salvar refeição", type="primary"):
            if not desc.strip(): st.error("Descreva a refeição.")
            else:
                execute("INSERT INTO meals(eaten_at,meal_type,description,notes) VALUES(?,?,?,?)",
                        (datetime.combine(d,t).isoformat(sep=" "), kind, desc.strip(), notes))
                st.success("Refeição registrada.")
    df = query_df("SELECT eaten_at AS Data, meal_type AS Tipo, description AS Descrição, notes AS Observações FROM meals ORDER BY eaten_at DESC")
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.caption("Ainda não há refeições registradas.")

elif page == "Contrações":
    st.subheader("Cronômetro de contrações")
    running = get_state("contraction_started_at")
    if running:
        start_dt = datetime.fromisoformat(running)
        elapsed = max(0, int((now_local() - start_dt).total_seconds()))
        st.warning(f"Contração em andamento — início {start_dt.strftime('%H:%M:%S')} · duração atual {elapsed // 60:02d}:{elapsed % 60:02d}")
        if st.button("Finalizar contração", type="primary", use_container_width=True):
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
        st.caption("Toque em iniciar no começo da contração e finalize quando ela terminar.")
        if st.button("Iniciar contração", type="primary", use_container_width=True):
            set_state("contraction_started_at", now_local().isoformat(sep=" "))
            st.rerun()
    df = query_df("SELECT * FROM contractions ORDER BY started_at DESC LIMIT 30")
    if not df.empty:
        df["Início"] = pd.to_datetime(df["started_at"]).dt.strftime("%d/%m %H:%M:%S")
        df["Duração (seg)"] = df["duration_seconds"]
        df["Intervalo entre inícios (min)"] = (df["interval_seconds"] / 60).round(1)
        st.subheader("Histórico recente")
        st.dataframe(df[["Início","Duração (seg)","Intervalo entre inícios (min)"]], use_container_width=True, hide_index=True)
        intervals = df["interval_seconds"].dropna()
        if not intervals.empty:
            st.metric("Média dos intervalos registrados", f"{intervals.mean()/60:.1f} minutos")
    else: st.caption("Nenhuma contração registrada.")
    st.info("O cronômetro é apenas um registro. Não use médias ou intervalos do aplicativo para decidir quando procurar atendimento. Siga as orientações da maternidade/equipe obstétrica.")

elif page == "Movimentos dos bebês":
    st.subheader("Registrar movimentos")
    with st.form("movement_form", clear_on_submit=True):
        d = st.date_input("Data", value=date.today(), key="mov_date")
        t = st.time_input("Horário", value=now_local().time(), key="mov_time")
        baby = st.selectbox("Bebê", ["Bebê 1", "Bebê 2", "Não identificado / geral"])
        typ = st.selectbox("Registro", ["Movimento percebido", "Sequência de movimentos", "Mudança percebida", "Outro"])
        notes = st.text_input("Observações")
        if st.form_submit_button("Salvar movimento", type="primary"):
            execute("INSERT INTO movements(recorded_at,baby,movement_type,notes) VALUES(?,?,?,?)",
                    (datetime.combine(d,t).isoformat(sep=" "), baby, typ, notes))
            st.success("Registro salvo.")
    df = query_df("SELECT recorded_at AS Data, baby AS Bebê, movement_type AS Registro, notes AS Observações FROM movements ORDER BY recorded_at DESC")
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.caption("Ainda não há registros.")
    st.warning("Se perceber redução, ausência ou mudança preocupante nos movimentos habituais, entre em contato imediatamente com a maternidade/equipe obstétrica. Não espere completar uma contagem no aplicativo.")

elif page == "Sintomas":
    st.subheader("Registrar sintomas")
    with st.form("symptom_form", clear_on_submit=True):
        d = st.date_input("Data", value=date.today(), key="sym_date")
        t = st.time_input("Horário", value=now_local().time(), key="sym_time")
        symptom = st.text_input("Sintoma (ex.: dor de cabeça, inchaço, náusea)")
        intensity = st.selectbox("Como foi?", ["Leve", "Moderado", "Intenso", "Não sei avaliar"])
        notes = st.text_area("Detalhes / duração / contexto")
        if st.form_submit_button("Salvar sintoma", type="primary"):
            if not symptom.strip(): st.error("Informe o sintoma.")
            else:
                execute("INSERT INTO symptoms(recorded_at,symptom,intensity,notes) VALUES(?,?,?,?)",
                        (datetime.combine(d,t).isoformat(sep=" "), symptom.strip(), intensity, notes))
                st.success("Sintoma registrado.")
    df = query_df("SELECT recorded_at AS Data, symptom AS Sintoma, intensity AS Intensidade, notes AS Detalhes FROM symptoms ORDER BY recorded_at DESC")
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.caption("Ainda não há sintomas registrados.")
    st.info("Sintomas intensos, sangramento, perda de líquido, falta de ar, dor forte ou outros sinais de alerta exigem contato imediato com a equipe obstétrica ou serviço de urgência.")

elif page == "Anotações":
    st.subheader("Anotações para o obstetra")
    with st.form("note_form", clear_on_submit=True):
        subject = st.text_input("Assunto")
        content = st.text_area("Anotação", height=150)
        if st.form_submit_button("Salvar anotação", type="primary"):
            if not subject.strip() or not content.strip(): st.error("Preencha o assunto e a anotação.")
            else:
                execute("INSERT INTO notes(created_at,subject,content) VALUES(?,?,?)",
                        (now_local().isoformat(sep=" "), subject.strip(), content.strip()))
                st.success("Anotação salva.")
    df = query_df("SELECT created_at AS Data, subject AS Assunto, content AS Anotação FROM notes ORDER BY created_at DESC")
    if not df.empty: st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.caption("Ainda não há anotações.")

elif page == "Lembretes":
    st.subheader("Lembretes")
    st.caption("Os lembretes aparecem dentro do aplicativo quando ele é aberto. Esta primeira versão não envia notificações se o navegador estiver fechado.")
    with st.form("reminder_form", clear_on_submit=True):
        title = st.text_input("O que lembrar? (ex.: medir glicemia)")
        rtime = st.time_input("Horário", value=time(8,0))
        days = st.multiselect("Dias", ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"], default=["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"])
        if st.form_submit_button("Criar lembrete", type="primary"):
            if not title.strip() or not days: st.error("Informe o lembrete e selecione ao menos um dia.")
            else:
                execute("INSERT INTO reminders(title,reminder_time,days,active) VALUES(?,?,?,1)",
                        (title.strip(), rtime.strftime("%H:%M"), ",".join(days)))
                st.success("Lembrete criado.")
    df = query_df("SELECT id, title AS Lembrete, reminder_time AS Horário, days AS Dias, active FROM reminders ORDER BY reminder_time")
    if not df.empty:
        st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)
        options = {f'{r["title"]} — {r["reminder_time"]}': int(r["id"]) for _,r in df.iterrows()}
        selected = st.selectbox("Selecionar lembrete para ativar/desativar", list(options))
        if st.button("Alternar ativo/inativo"):
            rid = options[selected]
            execute("UPDATE reminders SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (rid,))
            st.rerun()
    else: st.caption("Nenhum lembrete cadastrado.")
    weekdays = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
    now = now_local()
    day = weekdays[now.weekday()]
    due = query_df("SELECT title, reminder_time FROM reminders WHERE active=1")
    due_now = []
    for _, r in due.iterrows():
        if day in r["days"] and r["reminder_time"] == now.strftime("%H:%M"):
            due_now.append(r["title"])
    if due_now:
        for item in due_now: st.warning(f"Lembrete ({now.strftime('%H:%M')}): {item}")

elif page == "Relatórios":
    st.subheader("Exportar histórico")
    tables = {
        "Glicemia": ("glucose", "SELECT measured_at AS data_hora, value AS glicemia_mg_dl, context AS contexto, minutes_after_meal AS minutos_apos_refeicao, notes AS observacoes FROM glucose ORDER BY measured_at"),
        "Pressão arterial": ("blood_pressure", "SELECT measured_at AS data_hora, systolic AS sistolica, diastolic AS diastolica, pulse AS pulso, notes AS observacoes FROM blood_pressure ORDER BY measured_at"),
        "Refeições": ("meals", "SELECT eaten_at AS data_hora, meal_type AS tipo, description AS descricao, notes AS observacoes FROM meals ORDER BY eaten_at"),
        "Contrações": ("contractions", "SELECT started_at AS inicio, ended_at AS fim, duration_seconds AS duracao_segundos, interval_seconds AS intervalo_segundos FROM contractions ORDER BY started_at"),
        "Movimentos": ("movements", "SELECT recorded_at AS data_hora, baby AS bebe, movement_type AS registro, notes AS observacoes FROM movements ORDER BY recorded_at"),
        "Sintomas": ("symptoms", "SELECT recorded_at AS data_hora, symptom AS sintoma, intensity AS intensidade, notes AS detalhes FROM symptoms ORDER BY recorded_at"),
        "Anotações": ("notes", "SELECT created_at AS data_hora, subject AS assunto, content AS anotacao FROM notes ORDER BY created_at"),
    }
    for label, (_, sql) in tables.items():
        df = query_df(sql)
        with st.expander(label):
            if df.empty: st.caption("Sem registros.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(f"Baixar {label} em CSV", df.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"{label.lower().replace(' ','_')}.csv", mime="text/csv")
    st.caption("Os relatórios são registros informativos para compartilhar com o profissional de saúde.")

st.divider()
st.caption("Diário Gestacional • Os registros não são diagnóstico, triagem ou orientação médica. Em caso de dúvida ou sinal de alerta, contate a equipe obstétrica.")
