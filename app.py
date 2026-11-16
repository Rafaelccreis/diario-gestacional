import hmac
import html
import io
import os
import re
import sqlite3
import time as _time
import unicodedata
import zipfile
from contextlib import contextmanager
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

# ============================================================
# Diário Gestacional
# Compatível com o banco da versão anterior (mesmas tabelas).
# ============================================================

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(APP_DIR / "diario_gestacional.db")))
TZ = ZoneInfo("America/Sao_Paulo")

WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
WEEKDAYS_FULL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
                 "Sexta-feira", "Sábado", "Domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]
BABIES = ["Davi Lucca", "Leon", "Não identificado / geral"]
TABLES = {"glucose", "blood_pressure", "meals", "contractions", "movements",
          "symptoms", "notes", "reminders"}
DATE_COLS = {"Data e horário", "Início"}

st.set_page_config(
    page_title="Diário Gestacional",
    page_icon="♡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------
# Compatibilidade: versões novas do Streamlit trocaram
# use_container_width=True por width="stretch".
# ------------------------------------------------------------
def _st_version():
    out = []
    for part in st.__version__.split(".")[:2]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    return tuple(out)


FULL = {"width": "stretch"} if _st_version() >= (1, 50) else {"use_container_width": True}

# ------------------------------------------------------------
# Visual: azul bebê + branco sobre noite azulada
# ------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&display=swap');

:root {
  --night: #0A1220;
  --surface: #111C2F;
  --surface-2: #16253D;
  --line: rgba(156, 211, 245, .16);
  --baby: #9CD3F5;
  --baby-strong: #B9E3FA;
  --baby-soft: rgba(156, 211, 245, .10);
  --white: #F5FAFF;
  --muted: #9DB2C7;
  --display: 'Fraunces', Georgia, 'Times New Roman', serif;
  --body: 'Figtree', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

.stApp {
  background:
    radial-gradient(900px 480px at 88% -8%, rgba(156,211,245,.10), transparent 60%),
    radial-gradient(700px 420px at -10% 108%, rgba(156,211,245,.06), transparent 60%),
    var(--night);
  color: var(--white);
  font-family: var(--body);
}
button, input, textarea, select { font-family: var(--body) !important; }
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1240px; padding-top: 2rem; padding-bottom: 3rem; }

h1, h2, h3, h4 {
  font-family: var(--display) !important;
  color: var(--white) !important;
  font-weight: 500 !important;
  letter-spacing: -.01em;
}
p, label, li { color: var(--white); }
[data-testid="stCaptionContainer"], .section-note { color: var(--muted) !important; }
a { color: var(--baby) !important; }

/* ---------- Hero ---------- */
.hero {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 28px;
  padding: 34px 38px 32px;
  margin: 0 0 26px 0;
  background:
    radial-gradient(520px 260px at 96% 0%, rgba(156,211,245,.22), transparent 65%),
    linear-gradient(135deg, #15253E 0%, #0F1A2D 70%);
  box-shadow: 0 20px 50px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.04);
}
.hero-date {
  display: inline-block;
  font-size: .86rem;
  font-weight: 600;
  color: var(--baby-strong);
  background: var(--baby-soft);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 5px 14px;
  margin-bottom: 16px;
}
.hero h1 {
  margin: 0 !important;
  font-size: 2.7rem !important;
  line-height: 1.08;
  color: var(--white) !important;
}
.hero p {
  margin: 12px 0 0;
  max-width: 62ch;
  font-size: 1.04rem;
  line-height: 1.55;
  color: #C3D6E8 !important;
}
.hero-center { text-align: center; }
.hero-center p { margin-left: auto; margin-right: auto; }

/* ---------- Seções ---------- */
h3 { font-size: 1.45rem !important; margin-top: .4rem !important; }
.section-note { font-size: .95rem; margin: -6px 0 14px; }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
  background: #0D1727;
  border-right: 1px solid var(--line);
}
.brand { font-family: var(--display); font-size: 1.45rem; color: var(--white); line-height: 1.15; }
.brand small { display: block; margin-top: 4px; font-family: var(--body); font-size: .85rem; color: var(--muted); }
.brand .heart { color: var(--baby); }

[data-testid="stSidebar"] [data-testid="stRadio"] > div[role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid transparent;
  transition: background .15s ease, border-color .15s ease;
  cursor: pointer;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child { display: none; }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover { background: var(--baby-soft); }
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
  background: var(--baby-soft);
  border-color: var(--line);
  box-shadow: inset 3px 0 0 var(--baby);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-weight: 500; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p { color: var(--baby-strong); font-weight: 650; }

/* ---------- Métricas ---------- */
div[data-testid="stMetric"] {
  background: linear-gradient(180deg, var(--surface-2), var(--surface));
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 18px 20px;
}
div[data-testid="stMetricLabel"] p { color: var(--muted) !important; font-weight: 500; }
div[data-testid="stMetricValue"] {
  font-family: var(--display);
  color: var(--baby-strong) !important;
  font-weight: 500;
}

/* ---------- Formulários e campos ---------- */
[data-testid="stForm"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 24px 24px 18px;
}
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
  background: #0C1627 !important;
  border-color: var(--line) !important;
  border-radius: 12px !important;
}
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea { color: var(--white) !important; }
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"] > div:focus-within {
  border-color: var(--baby) !important;
  box-shadow: 0 0 0 3px rgba(156,211,245,.20) !important;
}
label[data-testid="stWidgetLabel"] p { color: #D5E4F2 !important; font-weight: 500; }

/* ---------- Botões ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 12px;
  font-weight: 650;
  min-height: 2.8rem;
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--white);
  transition: transform .12s ease, background .15s ease, border-color .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
  border-color: var(--baby);
  color: var(--baby-strong);
}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {
  outline: 3px solid rgba(156,211,245,.45);
  outline-offset: 2px;
}
button[kind="primary"], button[kind="primaryFormSubmit"],
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--baby) !important;
  border-color: var(--baby) !important;
  color: #0A1830 !important;
}
button[kind="primary"] p, button[kind="primaryFormSubmit"] p,
button[data-testid="stBaseButton-primary"] p, button[data-testid="stBaseButton-primaryFormSubmit"] p {
  color: #0A1830 !important;
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover,
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background: var(--baby-strong) !important;
  border-color: var(--baby-strong) !important;
  transform: translateY(-1px);
}

/* ---------- Tabelas, expanders, alertas ---------- */
[data-testid="stDataFrame"] {
  border: 1px solid var(--line);
  border-radius: 16px;
  overflow: hidden;
}
div[data-testid="stExpander"] {
  background: var(--surface);
  border: 1px solid var(--line) !important;
  border-radius: 16px;
}
div[data-testid="stAlert"] { border-radius: 14px; }
hr { border-color: var(--line) !important; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--line) !important; border-radius: 18px !important; }

/* ---------- Componentes próprios ---------- */
.callout {
  margin: 18px 0 6px;
  padding: 15px 18px;
  border-radius: 16px;
  background: var(--baby-soft);
  border: 1px solid var(--line);
  border-left: 4px solid var(--baby);
  color: #D9E8F5;
  font-size: .95rem;
  line-height: 1.55;
}
.callout b { color: var(--white); }

.timer {
  text-align: center;
  padding: 30px 18px 26px;
  margin-bottom: 16px;
  border-radius: 24px;
  border: 1px solid var(--line);
  background:
    radial-gradient(340px 180px at 50% 0%, rgba(156,211,245,.20), transparent 70%),
    var(--surface);
}
.timer-num {
  display: block;
  font-family: var(--display);
  font-size: 4.2rem;
  line-height: 1;
  color: var(--baby-strong);
  font-variant-numeric: tabular-nums;
}
.timer-lbl { display: block; margin-top: 10px; color: var(--muted); font-size: .95rem; }

.rem {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 16px; margin-bottom: 8px;
  border-radius: 14px;
  background: var(--surface);
  border: 1px solid var(--line);
}
.rem-time { font-family: var(--display); font-size: 1.2rem; color: var(--baby-strong); min-width: 3.6rem; }
.rem-title { flex: 1; color: var(--white); }
.pill {
  font-size: .78rem; font-weight: 600;
  padding: 3px 11px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted);
}
.pill.now { background: var(--baby); color: #0A1830; border-color: var(--baby); }
.pill.soon { color: var(--baby-strong); background: var(--baby-soft); }

.note-meta { color: var(--muted); font-size: .85rem; margin-bottom: 6px; }
.note-title { font-family: var(--display); font-size: 1.2rem; color: var(--white); margin: 0 0 4px; }
.note-body { color: #D5E4F2; white-space: pre-wrap; line-height: 1.6; }

.small-footer { color: var(--muted) !important; font-size: .8rem; line-height: 1.5; }

@media (max-width: 700px) {
  .block-container { padding: 1rem .8rem 2.5rem; }
  .hero { padding: 24px 22px; border-radius: 22px; }
  .hero h1 { font-size: 2rem !important; }
  .timer-num { font-size: 3.2rem; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------
def now_local():
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def now_time():
    return now_local().time().replace(second=0)


def esc(value):
    return html.escape(str(value), quote=True)


def slug(text):
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", norm.lower()).strip("_")


def long_date(d):
    return f"{WEEKDAYS_FULL[d.weekday()]}, {d.day} de {MONTHS[d.month - 1]}"


def fmt_dt(value):
    try:
        return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(value)


def flash(message):
    st.session_state["_flash"] = message


def saved(message):
    flash(message)
    st.rerun()


# ------------------------------------------------------------
# Banco de dados
# ------------------------------------------------------------
@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with db() as con:
        con.execute("PRAGMA journal_mode=WAL")
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


def query_df(sql, params=()):
    with db() as con:
        return pd.read_sql_query(sql, con, params=params)


def execute(sql, params=()):
    with db() as con:
        return con.execute(sql, params).lastrowid


def get_state(key):
    with db() as con:
        row = con.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
    return None if row is None else row["value"]


def set_state(key, value):
    execute(
        "INSERT INTO app_state(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def count_today(table, column, today_s):
    assert table in TABLES
    df = query_df(f"SELECT COUNT(*) AS n FROM {table} WHERE substr({column},1,10)=?", (today_s,))
    return int(df.iloc[0]["n"])


# ------------------------------------------------------------
# Componentes de interface
# ------------------------------------------------------------
def hero(title, subtitle, date_chip=True, center=False):
    chip = f'<div class="hero-date">{esc(long_date(now_local().date()))}</div>' if date_chip else ""
    cls = "hero hero-center" if center else "hero"
    st.markdown(
        f'<div class="{cls}">{chip}<h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>',
        unsafe_allow_html=True,
    )


def section(title, subtitle=None):
    st.subheader(title)
    if subtitle:
        st.markdown(f'<p class="section-note">{esc(subtitle)}</p>', unsafe_allow_html=True)


def callout(text, title=None):
    head = f"<b>{esc(title)}</b> " if title else ""
    st.markdown(f'<div class="callout">{head}{esc(text)}</div>', unsafe_allow_html=True)


def _row_label(row, cols, id_col):
    bits = []
    for c in cols[:2]:
        value = fmt_dt(row[c]) if c in DATE_COLS else str(row[c])
        bits.append(value if len(value) <= 40 else value[:37] + "…")
    return f"#{int(row[id_col])} · " + " · ".join(bits)


def _do_delete(table, select_key, confirm_key):
    if table in TABLES and select_key in st.session_state:
        execute(f"DELETE FROM {table} WHERE id=?", (int(st.session_state[select_key]),))
        flash("Registro excluído.")
    st.session_state[confirm_key] = False


def delete_box(df, table, label, id_col="id"):
    cols = [c for c in df.columns if c != id_col]
    labels = {int(r[id_col]): _row_label(r, cols, id_col) for _, r in df.iterrows()}
    select_key, confirm_key = f"delete_{table}", f"confirm_{table}"
    with st.expander(f"Excluir {label}"):
        st.selectbox("Registro", list(labels), format_func=labels.get, key=select_key)
        st.checkbox("Confirmo que quero excluir este registro", key=confirm_key)
        st.button(
            "Excluir registro",
            key=f"delete_btn_{table}",
            disabled=not st.session_state.get(confirm_key, False),
            on_click=_do_delete,
            args=(table, select_key, confirm_key),
        )


def show_history(df, table, label="registro", id_col="id"):
    if df.empty:
        st.caption(f"Nenhum {label} cadastrado ainda. Use o formulário acima para criar o primeiro.")
        return
    display = df.drop(columns=[id_col], errors="ignore").copy()
    for col in display.columns:
        if col in DATE_COLS:
            display[col] = display[col].map(fmt_dt)
    st.dataframe(display, hide_index=True, **FULL)
    delete_box(df, table, label, id_col)


def trend_chart(df, x, series, y_title, height=280):
    long = df.melt(id_vars=[x], value_vars=series, var_name="Medida", value_name="Valor").dropna()
    palette = ["#9CD3F5", "#F5FAFF"]
    legend = alt.Legend(orient="top", title=None, labelColor="#D5E4F2") if len(series) > 1 else None
    chart = (
        alt.Chart(long)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=70), strokeWidth=2.5, interpolate="monotone")
        .encode(
            x=alt.X(f"{x}:T", title=None),
            y=alt.Y("Valor:Q", title=y_title, scale=alt.Scale(zero=False)),
            color=alt.Color("Medida:N", scale=alt.Scale(domain=series, range=palette[:len(series)]), legend=legend),
            tooltip=[
                alt.Tooltip(f"{x}:T", title="Data", format="%d/%m/%Y %H:%M"),
                alt.Tooltip("Medida:N", title="Medida"),
                alt.Tooltip("Valor:Q", title="Valor"),
            ],
        )
        .properties(height=height)
        .configure(background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor="#9DB2C7", titleColor="#9DB2C7",
            gridColor="rgba(156,211,245,0.10)", domainColor="rgba(156,211,245,0.25)",
            tickColor="rgba(156,211,245,0.25)",
        )
    )
    st.altair_chart(chart, theme=None, **FULL)


def todays_reminders():
    now = now_local()
    day = WEEKDAYS[now.weekday()]
    df = query_df("SELECT title, reminder_time, days FROM reminders WHERE active=1 ORDER BY reminder_time")
    rows = [r for _, r in df.iterrows() if day in str(r["days"]).split(",")]
    return rows, now.strftime("%H:%M")


def render_reminders(rows, now_hm):
    for r in rows:
        t = str(r["reminder_time"])
        if t == now_hm:
            pill = '<span class="pill now">Agora</span>'
        elif t > now_hm:
            pill = '<span class="pill soon">Mais tarde</span>'
        else:
            pill = '<span class="pill">Já passou</span>'
        st.markdown(
            f'<div class="rem"><span class="rem-time">{esc(t)}</span>'
            f'<span class="rem-title">{esc(r["title"])}</span>{pill}</div>',
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------
# Acesso
# ------------------------------------------------------------
def login_gate():
    configured = None
    try:
        configured = st.secrets.get("app_password") or st.secrets.get("APP_PASSWORD")
    except Exception:
        pass
    configured = configured or os.getenv("APP_PASSWORD")

    if not configured:
        hero("Diário Gestacional", "Seu espaço de registros e acompanhamento.", date_chip=False)
        st.error("Defina uma senha antes de usar o diário.")
        st.code('app_password = "sua-senha-forte"', language="toml")
        st.caption("No Streamlit Cloud: Manage app → Settings → Secrets. Não publique a senha no código.")
        st.stop()

    if not st.session_state.get("authenticated", False):
        _, mid, _ = st.columns([1, 2.2, 1])
        with mid:
            hero("Diário Gestacional",
                 "Um espaço calmo para guardar os registros da gestação.",
                 date_chip=False, center=True)
            with st.form("login_form"):
                pwd = st.text_input("Senha de acesso", type="password")
                submit = st.form_submit_button("Entrar", type="primary", **FULL)
            if submit:
                if hmac.compare_digest(pwd.encode(), str(configured).encode()):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    _time.sleep(1)
                    st.error("Senha incorreta. Confira e tente de novo.")
        st.stop()


init_db()
login_gate()

today = now_local().date()
today_s = today.isoformat()

# ------------------------------------------------------------
# Menu lateral
# ------------------------------------------------------------
PAGES = [
    "Visão geral", "Glicemia", "Pressão arterial", "Refeições",
    "Contrações", "Movimentos dos bebês", "Sintomas", "Anotações",
    "Lembretes", "Relatórios",
]
with st.sidebar:
    st.markdown(
        '<div class="brand"><span class="heart">♡</span> Diário Gestacional'
        '<small>Acompanhamento pessoal</small></div>',
        unsafe_allow_html=True,
    )
    st.divider()
    page = st.radio("Menu", PAGES, label_visibility="collapsed")
    st.divider()
    if st.button("Sair da conta", **FULL):
        st.session_state.authenticated = False
        st.rerun()
    st.markdown(
        '<p class="small-footer">Este diário organiza informações para consulta. '
        'Não substitui a avaliação ou a orientação da equipe obstétrica.</p>',
        unsafe_allow_html=True,
    )

_msg = st.session_state.pop("_flash", None)
if _msg:
    st.toast(_msg)

# ------------------------------------------------------------
# VISÃO GERAL
# ------------------------------------------------------------
if page == "Visão geral":
    hero("Bem-vinda de volta", "Veja o que foi registrado hoje e acompanhe as últimas medições.")

    g = query_df(
        "SELECT value FROM glucose WHERE substr(measured_at,1,10)=? ORDER BY measured_at DESC LIMIT 1",
        (today_s,),
    )
    bp = query_df(
        "SELECT systolic, diastolic FROM blood_pressure WHERE substr(measured_at,1,10)=? "
        "ORDER BY measured_at DESC LIMIT 1",
        (today_s,),
    )
    a, b, c, d, e = st.columns(5)
    a.metric("Última glicemia", f'{g.iloc[0]["value"]:g} mg/dL' if not g.empty else "—")
    b.metric("Última pressão", f'{int(bp.iloc[0]["systolic"])}/{int(bp.iloc[0]["diastolic"])}' if not bp.empty else "—")
    c.metric("Refeições", count_today("meals", "eaten_at", today_s))
    d.metric("Contrações", count_today("contractions", "started_at", today_s))
    e.metric("Movimentos", count_today("movements", "recorded_at", today_s))
    callout("Os números aparecem exatamente como foram registrados. O aplicativo não interpreta exames nem recomenda condutas.")

    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        section("Últimas glicemias")
        hist = query_df("SELECT measured_at AS 'Data e horário', value AS 'mg/dL', context AS 'Contexto' "
                        "FROM glucose ORDER BY measured_at DESC LIMIT 5")
        if hist.empty:
            st.caption("As medições aparecerão aqui depois de cadastradas.")
        else:
            hist["Data e horário"] = hist["Data e horário"].map(fmt_dt)
            st.dataframe(hist, hide_index=True, **FULL)
    with right:
        section("Últimas pressões")
        hist = query_df("SELECT measured_at AS 'Data e horário', systolic AS 'Sistólica', "
                        "diastolic AS 'Diastólica', pulse AS 'Pulso' FROM blood_pressure "
                        "ORDER BY measured_at DESC LIMIT 5")
        if hist.empty:
            st.caption("As medições aparecerão aqui depois de cadastradas.")
        else:
            hist["Data e horário"] = hist["Data e horário"].map(fmt_dt)
            st.dataframe(hist, hide_index=True, **FULL)

    rows, now_hm = todays_reminders()
    if rows:
        st.write("")
        section("Lembretes de hoje")
        render_reminders(rows, now_hm)

# ------------------------------------------------------------
# GLICEMIA
# ------------------------------------------------------------
elif page == "Glicemia":
    hero("Glicemia", "Registre a medição, o contexto e observações para consultar depois.")
    with st.form("glucose_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        dt = c1.date_input("Data", value=today, format="DD/MM/YYYY", key="glu_date")
        tm = c2.time_input("Horário", value=now_time(), step=60, key="glu_time")
        c1, c2 = st.columns(2)
        value = c1.number_input("Resultado (mg/dL)", min_value=1.0, max_value=1000.0,
                                value=None, step=1.0, placeholder="Digite o valor medido", key="glu_val")
        context = c2.selectbox("Contexto da medição",
                               ["Jejum", "Antes da refeição", "1 hora após refeição",
                                "2 horas após refeição", "Outro"], key="glu_ctx")
        mins = st.number_input("Minutos após a refeição (se aplicável)", min_value=0, max_value=1440,
                               value=0, step=5, key="glu_min")
        notes = st.text_area("Observações", placeholder="Ex.: como estava se sentindo, orientação recebida...",
                             key="glu_notes")
        if st.form_submit_button("Salvar medição", type="primary", **FULL):
            if value is None:
                st.error("Informe o resultado da medição.")
            else:
                execute(
                    "INSERT INTO glucose(measured_at,value,context,minutes_after_meal,notes) VALUES(?,?,?,?,?)",
                    (datetime.combine(dt, tm).isoformat(sep=" "), float(value), context,
                     int(mins) or None, notes.strip()),
                )
                saved("Medição de glicemia salva.")

    section("Histórico de medições")
    df = query_df("SELECT id, measured_at AS 'Data e horário', value AS 'mg/dL', context AS 'Contexto', "
                  "minutes_after_meal AS 'Minutos após refeição', notes AS 'Observações' "
                  "FROM glucose ORDER BY measured_at DESC")
    show_history(df, "glucose", label="medição de glicemia")
    if not df.empty:
        st.write("")
        section("Evolução")
        chart = query_df("SELECT measured_at, value FROM glucose ORDER BY measured_at")
        chart["Data"] = pd.to_datetime(chart["measured_at"])
        chart = chart.rename(columns={"value": "Glicemia"})
        trend_chart(chart, "Data", ["Glicemia"], "mg/dL")

# ------------------------------------------------------------
# PRESSÃO ARTERIAL
# ------------------------------------------------------------
elif page == "Pressão arterial":
    hero("Pressão arterial", "Guarde as medições e as observações informadas pela equipe de saúde.")
    with st.form("bp_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        dt = c1.date_input("Data", value=today, format="DD/MM/YYYY", key="bp_date")
        tm = c2.time_input("Horário", value=now_time(), step=60, key="bp_time")
        a, b, c = st.columns(3)
        systolic = a.number_input("Sistólica (mmHg)", min_value=1, max_value=300, value=None,
                                  placeholder="Ex.: 120", key="bp_sys")
        diastolic = b.number_input("Diastólica (mmHg)", min_value=1, max_value=200, value=None,
                                   placeholder="Ex.: 80", key="bp_dia")
        pulse = c.number_input("Pulso (bpm, opcional)", min_value=0, max_value=250, value=None,
                               placeholder="Ex.: 78", key="bp_pulse")
        notes = st.text_area("Observações", key="bp_notes")
        if st.form_submit_button("Salvar pressão", type="primary", **FULL):
            if systolic is None or diastolic is None:
                st.error("Informe a sistólica e a diastólica.")
            else:
                execute(
                    "INSERT INTO blood_pressure(measured_at,systolic,diastolic,pulse,notes) VALUES(?,?,?,?,?)",
                    (datetime.combine(dt, tm).isoformat(sep=" "), int(systolic), int(diastolic),
                     int(pulse) if pulse else None, notes.strip()),
                )
                saved("Medição de pressão salva.")

    section("Histórico")
    df = query_df("SELECT id, measured_at AS 'Data e horário', systolic AS 'Sistólica', "
                  "diastolic AS 'Diastólica', pulse AS 'Pulso', notes AS 'Observações' "
                  "FROM blood_pressure ORDER BY measured_at DESC")
    show_history(df, "blood_pressure", label="medição de pressão")
    if not df.empty:
        st.write("")
        section("Evolução")
        chart = query_df("SELECT measured_at, systolic AS 'Sistólica', diastolic AS 'Diastólica' "
                         "FROM blood_pressure ORDER BY measured_at")
        chart["Data"] = pd.to_datetime(chart["measured_at"])
        trend_chart(chart, "Data", ["Sistólica", "Diastólica"], "mmHg")

# ------------------------------------------------------------
# REFEIÇÕES
# ------------------------------------------------------------
elif page == "Refeições":
    hero("Refeições", "Registre alimentos e bebidas para manter um histórico organizado.")
    with st.form("meal_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        dt = c1.date_input("Data", value=today, format="DD/MM/YYYY", key="meal_date")
        tm = c2.time_input("Horário", value=now_time(), step=60, key="meal_time")
        kind = st.selectbox("Tipo de refeição",
                            ["Café da manhã", "Lanche da manhã", "Almoço", "Lanche da tarde",
                             "Jantar", "Ceia", "Outro"], key="meal_kind")
        desc = st.text_area("O que comeu ou bebeu?", placeholder="Descreva os alimentos e bebidas...",
                            key="meal_desc")
        notes = st.text_input("Observações (opcional)", key="meal_notes")
        if st.form_submit_button("Salvar refeição", type="primary", **FULL):
            if not desc.strip():
                st.error("Descreva a refeição antes de salvar.")
            else:
                execute("INSERT INTO meals(eaten_at,meal_type,description,notes) VALUES(?,?,?,?)",
                        (datetime.combine(dt, tm).isoformat(sep=" "), kind, desc.strip(), notes.strip()))
                saved("Refeição salva.")

    section("Histórico de refeições")
    df = query_df("SELECT id, eaten_at AS 'Data e horário', meal_type AS 'Tipo', "
                  "description AS 'Descrição', notes AS 'Observações' FROM meals ORDER BY eaten_at DESC")
    show_history(df, "meals", label="refeição")

# ------------------------------------------------------------
# CONTRAÇÕES
# ------------------------------------------------------------
elif page == "Contrações":
    hero("Contrações", "Use o cronômetro para registrar o início e o fim de cada episódio.")

    @st.fragment(run_every=1)
    def live_timer(start_iso):
        start = datetime.fromisoformat(start_iso)
        elapsed = max(0, int((now_local() - start).total_seconds()))
        st.markdown(
            f'<div class="timer"><span class="timer-num">{elapsed // 60:02d}:{elapsed % 60:02d}</span>'
            f'<span class="timer-lbl">Contração em andamento, iniciada às {start.strftime("%H:%M:%S")}</span></div>',
            unsafe_allow_html=True,
        )

    running = get_state("contraction_started_at")
    start_dt = None
    if running:
        try:
            start_dt = datetime.fromisoformat(running)
        except ValueError:
            set_state("contraction_started_at", "")

    if start_dt:
        live_timer(start_dt.isoformat(sep=" "))
        b1, b2 = st.columns([3, 1])
        if b1.button("Finalizar e salvar contração", type="primary", **FULL):
            end_dt = now_local()
            previous = query_df("SELECT started_at FROM contractions ORDER BY started_at DESC LIMIT 1")
            interval = None
            if not previous.empty:
                interval = int((start_dt - datetime.fromisoformat(previous.iloc[0]["started_at"])).total_seconds())
            duration = max(0, int((end_dt - start_dt).total_seconds()))
            execute("INSERT INTO contractions(started_at,ended_at,duration_seconds,interval_seconds) VALUES(?,?,?,?)",
                    (start_dt.isoformat(sep=" "), end_dt.isoformat(sep=" "), duration, interval))
            set_state("contraction_started_at", "")
            saved("Contração registrada.")
        if b2.button("Descartar", **FULL):
            set_state("contraction_started_at", "")
            saved("Contração descartada.")
    else:
        st.markdown(
            '<div class="timer"><span class="timer-num">00:00</span>'
            '<span class="timer-lbl">Toque em iniciar no começo da contração e finalize quando ela terminar.</span></div>',
            unsafe_allow_html=True,
        )
        if st.button("Iniciar contração", type="primary", **FULL):
            set_state("contraction_started_at", now_local().isoformat(sep=" "))
            st.rerun()

    st.write("")
    section("Histórico recente")
    df = query_df("SELECT id, started_at, ended_at, duration_seconds, interval_seconds "
                  "FROM contractions ORDER BY started_at DESC LIMIT 100")
    if df.empty:
        st.caption("Nenhuma contração registrada ainda.")
    else:
        view = pd.DataFrame({
            "id": df["id"],
            "Início": df["started_at"],
            "Duração": df["duration_seconds"].apply(lambda x: f"{int(x) // 60:02d}:{int(x) % 60:02d}"),
            "Intervalo entre inícios (min)": (df["interval_seconds"] / 60).round(1),
        })
        show_history(view, "contractions", label="contração")
    callout("Este cronômetro serve apenas para registrar horários. Não use os intervalos para decidir quando "
            "procurar atendimento. Siga as orientações da maternidade ou da equipe obstétrica.", title="Importante.")

# ------------------------------------------------------------
# MOVIMENTOS
# ------------------------------------------------------------
elif page == "Movimentos dos bebês":
    hero("Movimentos dos bebês", "Anote o que percebeu e a qual bebê o registro se refere.")
    with st.form("movement_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        dt = c1.date_input("Data", value=today, format="DD/MM/YYYY", key="mov_date")
        tm = c2.time_input("Horário", value=now_time(), step=60, key="mov_time")
        baby = st.selectbox("Bebê", BABIES, key="mov_baby")
        typ = st.selectbox("Tipo de registro",
                           ["Movimento percebido", "Sequência de movimentos", "Mudança percebida", "Outro"],
                           key="mov_type")
        notes = st.text_area("Observações", placeholder="Descreva o que percebeu...", key="mov_notes")
        if st.form_submit_button("Salvar registro", type="primary", **FULL):
            execute("INSERT INTO movements(recorded_at,baby,movement_type,notes) VALUES(?,?,?,?)",
                    (datetime.combine(dt, tm).isoformat(sep=" "), baby, typ, notes.strip()))
            saved("Registro de movimento salvo.")

    section("Histórico")
    df = query_df("SELECT id, recorded_at AS 'Data e horário', baby AS 'Bebê', movement_type AS 'Registro', "
                  "notes AS 'Observações' FROM movements ORDER BY recorded_at DESC")
    show_history(df, "movements", label="registro de movimento")
    callout("Se perceber redução, ausência ou mudança preocupante nos movimentos habituais, entre em contato "
            "imediatamente com a maternidade ou a equipe obstétrica. Não espere completar uma contagem no aplicativo.",
            title="Importante.")

# ------------------------------------------------------------
# SINTOMAS
# ------------------------------------------------------------
elif page == "Sintomas":
    hero("Sintomas", "Registre o que sentiu, a intensidade percebida e os detalhes relevantes.")
    with st.form("symptom_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        dt = c1.date_input("Data", value=today, format="DD/MM/YYYY", key="sym_date")
        tm = c2.time_input("Horário", value=now_time(), step=60, key="sym_time")
        symptom = st.text_input("Sintoma", placeholder="Ex.: dor de cabeça, náusea, inchaço...", key="sym_name")
        intensity = st.selectbox("Intensidade percebida",
                                 ["Leve", "Moderado", "Intenso", "Não sei avaliar"], key="sym_int")
        notes = st.text_area("Detalhes, duração e contexto", key="sym_notes")
        if st.form_submit_button("Salvar sintoma", type="primary", **FULL):
            if not symptom.strip():
                st.error("Informe o sintoma.")
            else:
                execute("INSERT INTO symptoms(recorded_at,symptom,intensity,notes) VALUES(?,?,?,?)",
                        (datetime.combine(dt, tm).isoformat(sep=" "), symptom.strip(), intensity, notes.strip()))
                saved("Sintoma salvo.")

    section("Histórico")
    df = query_df("SELECT id, recorded_at AS 'Data e horário', symptom AS 'Sintoma', intensity AS 'Intensidade', "
                  "notes AS 'Detalhes' FROM symptoms ORDER BY recorded_at DESC")
    show_history(df, "symptoms", label="sintoma")
    callout("Sangramento, perda de líquido, falta de ar, dor forte ou outros sinais de alerta exigem contato "
            "imediato com a equipe obstétrica ou com um serviço de urgência.", title="Importante.")

# ------------------------------------------------------------
# ANOTAÇÕES
# ------------------------------------------------------------
elif page == "Anotações":
    hero("Anotações", "Guarde dúvidas, orientações recebidas e informações para a próxima consulta.")
    with st.form("note_form", clear_on_submit=True):
        subject = st.text_input("Assunto", placeholder="Ex.: Dúvidas para a próxima consulta", key="note_subject")
        content = st.text_area("Anotação", height=150, key="note_content")
        if st.form_submit_button("Salvar anotação", type="primary", **FULL):
            if not subject.strip() or not content.strip():
                st.error("Preencha o assunto e a anotação.")
            else:
                execute("INSERT INTO notes(created_at,subject,content) VALUES(?,?,?)",
                        (now_local().isoformat(sep=" "), subject.strip(), content.strip()))
                saved("Anotação salva.")

    section("Anotações salvas")
    df = query_df("SELECT id, created_at AS 'Data e horário', subject AS 'Assunto', content AS 'Anotação' "
                  "FROM notes ORDER BY created_at DESC")
    if df.empty:
        st.caption("Nenhuma anotação salva ainda. Use o formulário acima para criar a primeira.")
    else:
        for _, row in df.iterrows():
            with st.container(border=True):
                st.markdown(
                    f'<div class="note-meta">{esc(fmt_dt(row["Data e horário"]))}</div>'
                    f'<div class="note-title">{esc(row["Assunto"])}</div>'
                    f'<div class="note-body">{esc(row["Anotação"])}</div>',
                    unsafe_allow_html=True,
                )
        delete_box(df, "notes", "anotação")

# ------------------------------------------------------------
# LEMBRETES
# ------------------------------------------------------------
elif page == "Lembretes":
    hero("Lembretes", "Organize lembretes que ficam visíveis dentro do aplicativo.")
    callout("Os lembretes aparecem quando você abre o aplicativo. Esta versão não envia notificações "
            "com o navegador fechado.")
    st.write("")
    with st.form("reminder_form", clear_on_submit=True):
        title = st.text_input("O que deseja lembrar?", placeholder="Ex.: Separar exames para a consulta",
                              key="rem_title")
        c1, c2 = st.columns(2)
        rtime = c1.time_input("Horário", value=time(8, 0), step=60, key="rem_time")
        days = c2.multiselect("Repetir nos dias", WEEKDAYS, default=WEEKDAYS, key="rem_days")
        if st.form_submit_button("Criar lembrete", type="primary", **FULL):
            if not title.strip() or not days:
                st.error("Informe o lembrete e selecione ao menos um dia.")
            else:
                ordered = [d for d in WEEKDAYS if d in days]
                execute("INSERT INTO reminders(title,reminder_time,days,active) VALUES(?,?,?,1)",
                        (title.strip(), rtime.strftime("%H:%M"), ",".join(ordered)))
                saved("Lembrete criado.")

    rows, now_hm = todays_reminders()
    if rows:
        section("Para hoje")
        render_reminders(rows, now_hm)
        st.write("")

    section("Todos os lembretes")
    df = query_df("SELECT id, title AS 'Lembrete', reminder_time AS 'Horário', days AS 'Dias', active "
                  "FROM reminders ORDER BY reminder_time")
    if df.empty:
        st.caption("Você ainda não criou lembretes.")
    else:
        view = df.copy()
        view["Status"] = view["active"].map({1: "Ativo", 0: "Pausado"})
        show_history(view[["id", "Lembrete", "Horário", "Dias", "Status"]], "reminders", label="lembrete")
        labels = {int(r["id"]): f'#{int(r["id"])} · {r["Lembrete"]} ({r["Horário"]})' for _, r in df.iterrows()}
        st.write("")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        chosen = c1.selectbox("Lembrete para ativar ou pausar", list(labels),
                              format_func=labels.get, key="rem_toggle_sel")
        if c2.button("Ativar / pausar", **FULL):
            execute("UPDATE reminders SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (int(chosen),))
            saved("Status do lembrete atualizado.")

# ------------------------------------------------------------
# RELATÓRIOS
# ------------------------------------------------------------
elif page == "Relatórios":
    hero("Relatórios", "Consulte e baixe os registros para compartilhar com a equipe de saúde.")
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
    all_data = {label: query_df(sql) for label, sql in tables.items()}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for label, df in all_data.items():
            archive.writestr(f"{slug(label)}.csv", df.to_csv(index=False).encode("utf-8-sig"))
    st.download_button(
        "Baixar backup completo (ZIP)",
        data=buffer.getvalue(),
        file_name=f"backup_diario_gestacional_{today_s}.zip",
        mime="application/zip",
        type="primary",
        **FULL,
    )
    st.caption("O backup reúne todos os registros em arquivos CSV. Guarde-o em um local seguro.")
    st.write("")

    for label, df in all_data.items():
        with st.expander(f"{label} · {len(df)} registro(s)"):
            if df.empty:
                st.caption("Sem registros.")
            else:
                st.dataframe(df, hide_index=True, **FULL)
                st.download_button(
                    f"Baixar {label} em CSV",
                    df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"{slug(label)}.csv",
                    mime="text/csv",
                    key=f"csv_{slug(label)}",
                )

st.divider()
st.markdown(
    '<p class="small-footer">Diário Gestacional · Ferramenta de organização pessoal. Os registros não '
    'constituem diagnóstico, triagem ou orientação médica. Em caso de dúvida ou sinal de alerta, '
    'contate a equipe obstétrica.</p>',
    unsafe_allow_html=True,
)
