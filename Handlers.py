import os, time, textwrap, logging, sqlite3, asyncio, random, json, httpx
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from openai import AsyncOpenAI
from pathlib import Path
from Keyboards import main_kb, confirm_kb
import Analysis                                   # ← новый модуль

load_dotenv()
router = Router()
logger = logging.getLogger(__name__)

oai = AsyncOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# ── базы данных ────────────────────────────────────────────────────────────────
conn = sqlite3.connect("bot_logs.db", check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, user_id INTEGER, username TEXT,
    question TEXT, answer TEXT
)""")
conn.execute("""CREATE TABLE IF NOT EXISTS analysis (
    log_id INTEGER PRIMARY KEY,
    confidence REAL, sentiment REAL, template_flag INTEGER, word_count INTEGER,
    response_time REAL, reference_flag INTEGER, refusal_flag INTEGER,
    readability REAL, grammar_errors INTEGER, complex_words INTEGER,
    question_repeat INTEGER, user_feedback INTEGER
)""")
conn.commit()

# ── системный промпт — пропущен ради краткости ────────────────────────────────
PROMPT_PATH = Path(__file__).with_name("SYSTEM_PROMPT.txt")
with open(PROMPT_PATH, encoding="utf-8") as f:
    PROMPT_SYSTEM = f.read()

# ── команды и диалог ───────────────────────────────────────────────────────────
@router.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer(
        "Здравствуйте! Я — виртуальный ассистент учебного офиса.\n"
        "Напишите вопрос или нажмите кнопку ниже ↓",
        reply_markup=main_kb
    )

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
    cur.execute("""INSERT INTO logs (timestamp,user_id,username,question,answer)
                   VALUES (?,?,?,?,?)""",
                (datetime.utcnow().isoformat(),
                 msg.from_user.id,
                 msg.from_user.username or "",
                 question, answer))
    conn.commit()
    log_id = cur.lastrowid



    metrics = Analysis.analyse(question, answer, gen_time)
    Analysis.save(conn, log_id, metrics)

    # 3) отправляем пользователю
    for chunk in textwrap.wrap(answer, 4096, replace_whitespace=False):
        await msg.answer(chunk, reply_markup=confirm_kb(log_id))

@router.callback_query(F.data.startswith("confirm_"))
async def on_confirm(cb: CallbackQuery):
    # формат: confirm_yes_123  |  confirm_no_123
    _, vote, log_id = cb.data.split("_")
    fb = 1 if vote == "yes" else -1

    conn.execute("UPDATE analysis SET user_feedback=? WHERE log_id=?", (fb, log_id))
    conn.commit()

    await cb.message.edit_reply_markup()
    await cb.answer("Спасибо!" if fb == 1 else "Понял, попробуем иначе.")
