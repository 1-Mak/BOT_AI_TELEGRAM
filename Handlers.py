import os, time, textwrap, logging, sqlite3, asyncio, random, json, httpx
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from openai import AsyncOpenAI
from pathlib import Path
from Keyboards import main_kb, confirm_kb, campus_kb, level_kb, type_kb
import Analysis

load_dotenv()
router = Router()
logger = logging.getLogger(__name__)

# Временное хранение данных пользователя при опросе
user_data_temp = {}

oai = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ── базы данных ─────────────────────────────────────────────────
conn = sqlite3.connect("bot_logs.db", check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, user_id INTEGER, username TEXT,
    question TEXT, answer TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INTEGER PRIMARY KEY,
    campus TEXT, education_level TEXT, education_type TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS analysis (
    log_id INTEGER PRIMARY KEY,
    confidence REAL, sentiment REAL, template_flag INTEGER, word_count INTEGER,
    response_time REAL, reference_flag INTEGER, refusal_flag INTEGER,
    readability REAL, grammar_errors INTEGER, complex_words INTEGER,
    question_repeat INTEGER, user_feedback INTEGER, category TEXT
)""")
conn.commit()

# ── системный промпт — пропущен ради краткости ─────────────────
PROMPT_PATH = Path(__file__).with_name("SYSTEM_PROMPT.txt")
with open(PROMPT_PATH, encoding="utf-8") as f:
    PROMPT_SYSTEM = f.read()

# ── команды и диалог ───────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(msg: Message):
    user_id = msg.from_user.id
    # Очистка возможных старых данных профиля и проверка существования профиля
    user_data_temp.pop(user_id, None)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_profiles WHERE user_id=?", (user_id,))
    if cur.fetchone():
        # Профиль уже сохранён – приветствуем и показываем меню
        await msg.answer(
            "Здравствуйте! Я — виртуальный ассистент учебного офиса.\n"
            "Напишите вопрос или нажмите кнопку ниже ↓",
            reply_markup=main_kb
        )
    else:
        # Профиль не задан – начинаем опрос
        await msg.answer(
            "Здравствуйте! Я — виртуальный ассистент учебного офиса.\n"
            "Для начала работы, пожалуйста, ответьте на несколько вопросов.\n\n"
            "Из какого вы кампуса?",
            reply_markup=campus_kb
        )

@router.callback_query(F.data.startswith("campus_"))
async def on_choose_campus(cb: CallbackQuery):
    # Сохранение выбранного кампуса и переход к вопросу об уровне образования
    _, campus_raw = cb.data.split("_", 1)
    campus = campus_raw.replace("_", " ")
    user_data_temp[cb.from_user.id] = {"campus": campus}
    await cb.message.edit_reply_markup()  # убираем кнопки кампуса
    await cb.message.answer("Какой уровень образования у вас?", reply_markup=level_kb)
    await cb.answer()

@router.callback_query(F.data.startswith("level_"))
async def on_choose_level(cb: CallbackQuery):
    # Сохранение уровня образования и переход к вопросу о типе обучения
    _, level_raw = cb.data.split("_", 1)
    education_level = level_raw.replace("_", " ")
    user_data_temp[cb.from_user.id]["education_level"] = education_level
    await cb.message.edit_reply_markup()
    await cb.message.answer("Тип обучения?", reply_markup=type_kb)
    await cb.answer()

@router.callback_query(F.data.startswith("type_"))
async def on_choose_type(cb: CallbackQuery):
    # Сохранение типа обучения и завершение опроса профиля
    _, type_raw = cb.data.split("_", 1)
    education_type = type_raw.replace("_", " ")
    user_id = cb.from_user.id
    # Дописываем тип обучения к временным данным
    if user_id in user_data_temp:
        user_data_temp[user_id]["education_type"] = education_type
    else:
        user_data_temp[user_id] = {"education_type": education_type}
    # Сохраняем профиль пользователя в БД
    conn.execute(
        "INSERT OR REPLACE INTO user_profiles (user_id, campus, education_level, education_type) VALUES (?,?,?,?)",
        (user_id, user_data_temp[user_id].get("campus"), user_data_temp[user_id].get("education_level"), user_data_temp[user_id].get("education_type"))
    )
    conn.commit()
    user_data_temp.pop(user_id, None)  # очистка временных данных
    await cb.message.edit_reply_markup()  # убираем кнопки типа обучения
    await cb.message.answer("✅ Данные сохранены. Теперь вы можете задать свой вопрос.", reply_markup=main_kb)
    await cb.answer()

@router.message(F.text & ~F.via_bot)
async def ask_gpt(msg: Message):
    question = msg.text
    start_t = time.monotonic()

    response = await oai.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user",   "content": question}
        ],
        max_tokens=1024,
        temperature=0.5
    )
    gen_time = time.monotonic() - start_t
    answer = response.choices[0].message.content.replace("**", "").strip()

    # 1) логируем вопрос/ответ
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO logs (timestamp, user_id, username, question, answer) 
                   VALUES (?,?,?,?,?)""",
        (datetime.utcnow().isoformat(),
         msg.from_user.id,
         msg.from_user.username or "",
         question, answer)
    )
    conn.commit()
    log_id = cur.lastrowid

    # 2) анализируем ответ и определяем категорию вопроса
    metrics = Analysis.analyse(question, answer, gen_time)
    # Классификация вопроса по категориям через API DeepSeek
    category_resp = await oai.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": (
                "Ты классификатор студенческих вопросов по категориям. "
                "Доступные категории: Финансовые вопросы, Учеба, Цифровые сервисы и техподдержка, "
                "Обратная связь, Соц вопросы, Наука, Военка, Внеучебка, Практика, Другое. "
                "Определи наиболее подходящую категорию для вопроса пользователя. "
                "Ответь только названием категории."
            )},
            {"role": "user", "content": question}
        ],
        max_tokens=10,
        temperature=0
    )
    category = category_resp.choices[0].message.content.strip()
    metrics["category"] = category

    Analysis.save(conn, log_id, metrics)

    # 3) отправляем ответ пользователю
    for chunk in textwrap.wrap(answer, 4096, replace_whitespace=False):
        await msg.answer(chunk, reply_markup=confirm_kb(log_id))

@router.callback_query(F.data.startswith("confirm_"))
async def on_confirm(cb: CallbackQuery):
    # формат данных: confirm_yes_123  |  confirm_no_123
    _, vote, log_id = cb.data.split("_")
    fb = 1 if vote == "yes" else -1

    conn.execute("UPDATE analysis SET user_feedback=? WHERE log_id=?", (fb, log_id))
    conn.commit()

    await cb.message.edit_reply_markup()
    await cb.answer("Спасибо!" if fb == 1 else "Понял, попробуем иначе.")