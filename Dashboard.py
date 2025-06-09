import streamlit as st, pandas as pd, sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt, matplotlib.dates as mdates
import plotly.express as px, altair as alt
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Bot Dashboard", layout="wide")
st.title("📊 Дашборд чат-бота")
st_autorefresh(interval=10000, key="auto_refresh")

# ── загрузка данных ────────────────────────────────────────────────────────────
conn = sqlite3.connect("bot_logs.db", check_same_thread=False)

@st.cache_data(ttl=5)
def load():
    return pd.read_sql("""
        SELECT logs.id, logs.timestamp, logs.user_id, logs.question, logs.answer,
               analysis.*
        FROM logs JOIN analysis ON logs.id = analysis.log_id
        ORDER BY logs.timestamp DESC
    """, conn, parse_dates=["timestamp"])

if st.button("🔄 Обновить"): st.rerun()
df = load()
if df.empty:
    st.info("Пока нет данных.")
    st.stop()

num_cols = ["response_time", "confidence", "readability",
            "grammar_errors", "complex_words", "sentiment"]
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

# ── фильтр периода ─────────────────────────────────────────────────────────────
sd, ed = st.date_input("Период",
        [datetime.utcnow() - timedelta(days=7), datetime.utcnow()])
if isinstance(sd, datetime): sd = sd.date()
if isinstance(ed, datetime): ed = ed.date()
df = df[(df.timestamp.dt.date >= sd) & (df.timestamp.dt.date <= ed)]

# ── ключевые индикаторы ────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Запросов", len(df))
c2.metric("Средняя длина (слов)", f"{df.word_count.mean():.0f}")
c3.metric("Средний confidence", f"{df.confidence.mean():.2f}" if df.confidence.notna().any() else "—")
c4.metric("Отказов %", f"{df.refusal_flag.mean()*100:.1f}%")

st.markdown("---")  # разделитель

# ── динамика запросов ──────────────────────────────────────────────────────────
st.subheader("Динамика запросов / время генерации")
left, right = st.columns(2)

with left:
    by_min = df.set_index("timestamp").resample("1T").count()["id"]
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(by_min.index, by_min.values, marker="o")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate(rotation=45, ha="right"); ax.set_ylabel("шт"); ax.set_xlabel("UTC")
    st.pyplot(fig)

with right:
    rt = (df.set_index("timestamp")["response_time"]
            .resample("1T")
            .mean()
            .dropna())                                 # ← только числовые
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(rt.index, rt.values)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate(rotation=45, ha="right")
    ax.set_ylabel("сек"); ax.set_xlabel("UTC")
    st.pyplot(fig)

# ── круговые диаграммы ─────────────────────────────────────────────────────────
st.subheader("Категориальные метрики")
p1, p2, p3 = st.columns(3)
with p1:
    st.plotly_chart(px.pie(
        names=["Позитив","Нейтрал","Негатив"],
        values=[(df.sentiment>0).sum(), (df.sentiment==0).sum(), (df.sentiment<0).sum()],
        title="Тональность"), use_container_width=True)
with p2:
    st.plotly_chart(px.pie(
        names=["Отказы","Обычные"],
        values=[df.refusal_flag.sum(), len(df)-df.refusal_flag.sum()],
        title="Отказы"), use_container_width=True)
with p3:
    st.plotly_chart(px.pie(
        names=["Шаблон","Нет шаблона"],
        values=[df.template_flag.sum(), len(df)-df.template_flag.sum()],
        title="Шаблонность"), use_container_width=True)

# ── распределения ──────────────────────────────────────────────────────────────
st.subheader("Распределения")
h1, h2 = st.columns(2)
with h1:
    st.plotly_chart(px.histogram(df, x="word_count", nbins=20,
                    title="Длина ответов (слов)"), use_container_width=True)
with h2:
    st.plotly_chart(px.histogram(df, x="grammar_errors", nbins=10,
                    title="Грамматические ошибки"), use_container_width=True)

# ── scatter: уверенность vs тональность ────────────────────────────────────────
st.subheader("Уверенность vs Тональность")
sc = alt.Chart(df).mark_circle(size=60).encode(
    x='confidence', y='sentiment',
    color=alt.condition(alt.datum.refusal_flag==1,
                        alt.value('red'), alt.value('steelblue')),
    tooltip=['timestamp', 'question', 'answer']
).interactive()
st.altair_chart(sc, use_container_width=True)

# ── последние диалоги ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Последние 5 диалогов")
for _, row in df.head(5).iterrows():
    st.write(f"**{row.timestamp}** | User `{row.user_id}`")
    st.write(f"Q: {row.question}")
    st.write(f"A: {row.answer}")
    tags = []
    if row.refusal_flag:  tags.append("🚫 Отказ")
    if row.template_flag: tags.append("📋 Шаблон")
    if row.sentiment>0:   tags.append("🙂 Позитив")
    elif row.sentiment<0: tags.append("🙁 Негатив")
    if tags: st.write("Метки: " + " · ".join(tags))
    st.markdown("---")
