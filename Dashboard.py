# ── импорт и конфигурация — без изменений ─────────────────────────────—
import streamlit as st, pandas as pd, sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt, matplotlib.dates as mdates
import plotly.express as px, altair as alt
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timedelta


st.set_page_config(page_title="Bot Dashboard", layout="wide")
st.title("📊 Дашборд чат-бота")
# st_autorefresh(interval=10000, key="auto_refresh")

# —— кнопка обновления ——————————————————————————————
if st.button("🔄 Обновить"):
    st.rerun()
# ── загрузка данных ───────────────────────────────────────────────────—
conn = sqlite3.connect("bot_logs.db", check_same_thread=False)

@st.cache_data(ttl=5)
def load():
    return pd.read_sql("""
         SELECT logs.id, logs.timestamp, logs.user_id, logs.question, logs.answer,
                analysis.*, campus, education_level, education_type
         FROM logs
         JOIN analysis      ON logs.id   = analysis.log_id
         LEFT JOIN user_profiles ON logs.user_id = user_profiles.user_id
         ORDER BY logs.timestamp DESC
    """, conn, parse_dates=["timestamp"])

df_base = load()
if df_base.empty:
    st.info("Пока нет данных.")
    st.stop()

# --- подсчёты для лейблов фильтров (на весь период) -----------------
campus_counts   = df_base['campus'].value_counts().to_dict()
level_counts    = df_base['education_level'].value_counts().to_dict()
type_counts     = df_base['education_type'].value_counts().to_dict()
cat_counts      = df_base['category'].value_counts().to_dict()

# Приведение числовых колонок
for col in ["response_time","confidence","readability",
            "grammar_errors","complex_words","sentiment"]:
    df_base[col] = pd.to_numeric(df_base[col], errors="coerce")

# ── период (общий, т.к. к времени вопросы одинаковы) ─────────────────—
sd, ed = st.date_input(
    "Период", [datetime.utcnow()-timedelta(days=7), datetime.utcnow()]
)
if isinstance(sd, datetime): sd = sd.date()
if isinstance(ed, datetime): ed = ed.date()
df_base = df_base[(df_base.timestamp.dt.date >= sd) & (df_base.timestamp.dt.date <= ed)]

# ── универсальная функция фильтрации ──────────────────────────────────—
def apply_filters(df: pd.DataFrame, prefix: str, *,
                  with_category: bool = False, disabled: bool = False):
    """Рисует селекторы и фильтрует df.
       Если disabled=True → просто возвращает df (селекторы не показываются)."""
    if disabled:
        return df

    cols = st.columns(4 if with_category else 3)
    campus = cols[0].multiselect(
        "Кампус", ["Пермь", "Нижний Новгород", "Москва", "Санкт-Петербург"],
        key=f"{prefix}_campus")
    level = cols[1].multiselect(
        "Уровень", ["Бакалавр", "Специалитет", "Магистр", "Аспирант"],
        key=f"{prefix}_level")
    ed_type = cols[2].multiselect(
        "Тип", ["Очный", "Заочный"],
        key=f"{prefix}_type")
    category = []
    if with_category:
        category = cols[3].multiselect(
            "Категория", ["Финансовые вопросы", "Учеба",
                          "Цифровые сервисы и техподдержка", "Обратная связь",
                          "Соц вопросы", "Наука", "Военка",
                          "Внеучебка", "Практика", "Другое"],
            key=f"{prefix}_cat")

    if campus:
        df = df[df.campus.isin(campus)]
    if level:
        df = df[df.education_level.isin(level)]
    if ed_type:
        df = df[df.education_type.isin(ed_type)]
    if category:
        df = df[df.category.isin(category)]
    return df

# ── Статус работы бота (по heartbeat) ─────────────────────────────────
try:
    hb_row = conn.execute(
        "SELECT ts FROM heartbeat WHERE id = 1"
    ).fetchone()
    if hb_row:
        last_hb = pd.to_datetime(hb_row[0])
        is_alive = (datetime.utcnow() - last_hb) < timedelta(minutes=0.1)
    else:
        is_alive = False
except Exception:
    is_alive = False

status_html = (
    "<span style='color:limegreen; font-weight:bold; font-size:18px'>🟢 Бот работает</span>"
    if is_alive else
    "<span style='color:#d63333; font-weight:bold; font-size:18px'>🔴 Бот не работает</span>"
)
st.sidebar.markdown(status_html, unsafe_allow_html=True)
st.sidebar.markdown("---")



with st.sidebar.expander("🎛️ Глобальные фильтры", expanded=False):

    g_campus = st.multiselect(
        "Кампус",
        ["Пермь", "Нижний Новгород", "Москва", "Санкт-Петербург"],
        key="g_campus",
        format_func=lambda x: f"{x} ({campus_counts.get(x,0)})"
    )

    g_level = st.multiselect(
        "Уровень образования",
        ["Бакалавр", "Специалитет", "Магистр", "Аспирант"],
        key="g_level",
        format_func=lambda x: f"{x} ({level_counts.get(x,0)})"
    )

    g_type = st.multiselect(
        "Тип обучения",
        ["Очный", "Заочный"],
        key="g_type",
        format_func=lambda x: f"{x} ({type_counts.get(x,0)})"
    )

    g_category = st.multiselect(
        "Категория вопроса",
        ["Финансовые вопросы", "Учеба",
         "Цифровые сервисы и техподдержка", "Обратная связь",
         "Соц вопросы", "Наука", "Военка",
         "Внеучебка", "Практика", "Другое"],
        key="g_category",
        format_func=lambda x: f"{x} ({cat_counts.get(x,0)})"
    )
st.sidebar.markdown("---")
# ── Системные метрики бота ────────────────────────────────────────────
# 1) выборка последних 100 запросов
last_100 = df_base.head(100)                # df_base уже отфильтрован по датам

# 2) расчёты
avg_rt  = last_100.response_time.mean()
p95_rt  = last_100.response_time.quantile(0.95)
unique_24h = df_base[
    df_base.timestamp >= datetime.utcnow() - timedelta(hours=24)
]["user_id"].nunique()

# 3) вывод в сайдбаре
st.sidebar.subheader("⚙️ Системные метрики")
st.sidebar.metric(
    "⏱ Среднее время ответа (посл. 100)",
    f"{avg_rt:.2f} сек" if not pd.isna(avg_rt) else "—"
)
st.sidebar.metric(
    "🚀 P95 времени ответа",
    f"{p95_rt:.2f} сек" if not pd.isna(p95_rt) else "—"
)
st.sidebar.metric(
    "👥 Уникальных пользователей (24 ч)",
    unique_24h
)
st.sidebar.markdown("---")


# применяем глобальные фильтры
df_master = df_base.copy()
if g_campus:
    df_master = df_master[df_master.campus.isin(g_campus)]
if g_level:
    df_master = df_master[df_master.education_level.isin(g_level)]
if g_type:
    df_master = df_master[df_master.education_type.isin(g_type)]
if g_category:
    df_master = df_master[df_master.category.isin(g_category)]

# True → локальные фильтры отключаем
master_active = any([g_campus, g_level, g_type, g_category])
# ──────────────────────────────────────────────────────────────

# ── сводные индикаторы (отдельные фильтры) ─────────────────────────────
st.subheader("Сводные показатели")

# базовый датасет уже прошёл через ГЛОБАЛЬНЫЕ фильтры → df_master
# если глобальные фильтры активны → локальные селекторы скрыты
summary_df = apply_filters(
    df_master.copy(),
    "summary",
    disabled=master_active   # True → просто вернёт df_master без UI
)

# ——— 4 индикатора ——————————————————————————————————————————
m1, m2, m3, m4 = st.columns(4)
m1.metric("Запросов", len(summary_df))

if summary_df.empty:
    m2.metric("Средняя длина (слов)", "—")
    m3.metric("Средний confidence",  "—")
    m4.metric("Отказов %",           "—")
else:
    m2.metric("Средняя длина (слов)", f"{summary_df.word_count.mean():.0f}")
    m3.metric(
        "Средний confidence",
        f"{summary_df.confidence.mean():.2f}"
        if summary_df.confidence.notna().any() else "—"
    )
    m4.metric(
        "Отказов %",
        f"{summary_df.refusal_flag.mean() * 100:.1f}%"
        if summary_df.refusal_flag.notna().any() else "—"
    )

st.markdown("---")

# ── 1. Динамика запросов / время генерации ───────────────────────────—
st.subheader("Динамика запросов / время генерации")
dyn_df = apply_filters(df_master.copy(), "dyn", disabled=master_active)
left, right = st.columns(2)
with left:
    series = dyn_df.set_index("timestamp").resample("1T").count()["id"]
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(series.index, series.values, marker="o")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate(rotation=45, ha="right"); ax.set_ylabel("шт")
    st.pyplot(fig)
with right:
    rt = dyn_df.set_index("timestamp")["response_time"].resample("1T").mean().dropna()
    fig, ax = plt.subplots(figsize=(6,3))
    ax.plot(rt.index, rt.values)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate(rotation=45, ha="right"); ax.set_ylabel("сек")
    st.pyplot(fig)

# ── 2. Pie-метрики (тон, отказы, шаблонность) ─────────────────────────—
st.subheader("Категориальные метрики")
pie_df = apply_filters(df_master.copy(), "pie", disabled=master_active)
p1,p2,p3 = st.columns(3)
with p1:
    st.plotly_chart(px.pie(
        names=["Позитив","Нейтрал","Негатив"],
        values=[(pie_df.sentiment>0).sum(), (pie_df.sentiment==0).sum(), (pie_df.sentiment<0).sum()],
        title="Тональность"), use_container_width=True)
with p2:
    st.plotly_chart(px.pie(
        names=["Отказы","Обычные"],
        values=[pie_df.refusal_flag.sum(), len(pie_df)-pie_df.refusal_flag.sum()],
        title="Отказы"), use_container_width=True)
with p3:
    st.plotly_chart(px.pie(
        names=["Шаблон","Нет шаблона"],
        values=[pie_df.template_flag.sum(), len(pie_df)-pie_df.template_flag.sum()],
        title="Шаблонность"), use_container_width=True)

# ── 3. Bar-plot оценок пользователей ─────────────────────────────────—
st.subheader("Распределение оценок пользователей")
fb_df = apply_filters(df_master.copy(), "fb", disabled=master_active)
fb_counts = {"Положительные": int((fb_df.user_feedback==1).sum()),
             "Негативные":   int((fb_df.user_feedback==-1).sum()),
             "Без оценки":   int(fb_df.user_feedback.isna().sum())}
bar_df = pd.DataFrame({"Оценка": fb_counts.keys(), "Количество": fb_counts.values()})
fig = px.bar(bar_df, x="Оценка", y="Количество", color="Оценка", text="Количество",
             title="Оценки ответов бота")
fig.update_traces(textposition="outside")
fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Количество")
st.plotly_chart(fig, use_container_width=True)

# ── 4. Распределение вопросов по категориям ───────────────────────────—
st.subheader("Распределение вопросов по категориям")
cat_df = apply_filters(df_master.copy(), "cats", disabled=master_active)
cat_counts = cat_df['category'].value_counts().reset_index()
cat_counts.columns = ["Категория","Количество"]
if not cat_counts.empty:
    st.plotly_chart(px.bar(cat_counts, x="Количество", y="Категория",
                           orientation="h"), use_container_width=True)
else:
    st.info("Нет данных для выбранных фильтров.")

# ── 5. Гистограммы длины и ошибок ─────────────────────────────────────—
st.subheader("Распределения")
h_df = apply_filters(df_master.copy(), "hist", disabled=master_active)
col_a, col_b = st.columns(2)
with col_a:
    st.plotly_chart(px.histogram(h_df, x="word_count", nbins=20,
                    title="Длина ответов (слов)"), use_container_width=True)
with col_b:
    st.plotly_chart(px.histogram(h_df, x="grammar_errors", nbins=10,
                    title="Грамматические ошибки"), use_container_width=True)

# ── 6. Scatter confidence vs sentiment ───────────────────────────────—
st.subheader("Уверенность vs Тональность")
sc_df = apply_filters(df_master.copy(), "scatter", disabled=master_active)
sc = alt.Chart(sc_df).mark_circle(size=60).encode(
    x='confidence', y='sentiment',
    color=alt.condition(alt.datum.refusal_flag==1,
                        alt.value('red'), alt.value('steelblue')),
    tooltip=['timestamp','question','answer']
).interactive()
st.altair_chart(sc, use_container_width=True)

# ── последние 5 диалогов (без локальных фильтров) ─────────────────────
st.markdown("---")
st.subheader("Последние 5 диалогов")
for _, row in df_base.head(5).iterrows():          # df_base — только фильтр по датам
    campus = row.campus if pd.notna(row.campus) else "—"
    level  = row.education_level if pd.notna(row.education_level) else "—"
    edu_t  = row.education_type if pd.notna(row.education_type) else "—"
    st.write(f"**{row.timestamp}** | User `{row.user_id}` | {campus}, {level}, {edu_t}")
    st.write(f"Q: {row.question}")
    st.write(f"A: {row.answer}")
    tags = []
    if row.refusal_flag:  tags.append("🚫 Отказ")
    if row.template_flag: tags.append("📋 Шаблон")
    if row.sentiment>0:   tags.append("🙂 Позитив")
    elif row.sentiment<0: tags.append("🙁 Негатив")
    if tags: st.write("Метки: " + " · ".join(tags))
    st.markdown("---")

# ── диалоги с негативной оценкой (с локальными фильтрами) ──────────────
st.subheader("Диалоги с негативной оценкой")
neg_base = apply_filters(df_master.copy(), "neg",
                         with_category=True,
                         disabled=master_active)
neg_df = neg_base[neg_base.user_feedback < 0]

# метрика «Негатив / все» для текущих фильтров
ratio = 0 if len(neg_base) == 0 else len(neg_df) / len(neg_base)
st.metric("Негатив / все", f"{ratio:.1%}")

# вывод самих диалогов
if neg_df.empty:
    st.info("Нет диалогов с негативной оценкой для выбранных фильтров.")
else:
    for _, row in neg_df.iterrows():
        campus = row.campus if pd.notna(row.campus) else "—"
        level  = row.education_level if pd.notna(row.education_level) else "—"
        edu_t  = row.education_type if pd.notna(row.education_type) else "—"
        st.write(f"**{row.timestamp}** | User `{row.user_id}` | {campus}, {level}, {edu_t}")
        st.write(f"Q: {row.question}")
        st.write(f"A: {row.answer}")
        st.markdown("---")