import re
import sqlite3
from typing import Dict, Any, Optional

import textstat
import language_tool_python
from textblob import TextBlob

# ── служебные объекты ───────────────────────────────────────────────────────────
tool_ru = language_tool_python.LanguageTool("ru-RU")
tool_en = language_tool_python.LanguageTool("en-US")

TEMPLATE_PATTERNS = [
    r"(?i)as an ai language model",
    r"(?i)как (?:модель|искусственный интеллект)",
    r"(?i)я не могу (?:ответить|предоставить)",
]
REFUSAL_PATTERNS = [
    r"(?i)извините[, ]+но я не могу",
    r"(?i)i'?m sorry[, ]+but i cannot",
    r"(?i)к сожалению[, ]+я не могу",
]
REFERENCE_HINT = re.compile(r"\d{1,2}\s*[а-яa-z]{3,}")  # упоминание дат

# ── helpers ─────────────────────────────────────────────────────────────────────
def _match_any(text: str, patterns) -> bool:
    return any(re.search(p, text) for p in patterns)

def _sentiment(text: str) -> float:
    """Полярность: –1…+1 (TextBlob)."""
    try:
        return TextBlob(text).sentiment.polarity
    except Exception:
        return 0.0



# ── public API ──────────────────────────────────────────────────────────────────
UNCERTAIN = [
    "возможно", "может", "полагаю", "кажется", "вероятно",
    "maybe", "probably", "perhaps", "i think"
]

def _confidence(text: str, logprobs: Optional[list] = None) -> float:
    """
    Возвращает 0‒1:
    • если передан список чисел/кортежей/словарей — усредняем,
    • иначе эвристика по числу «неуверенных» слов в тексте.
    """
    # ── 1. пробуем использовать числовые logprobs (если пришли) ────────────
    if logprobs:
        nums = []
        for item in logprobs:
            if isinstance(item, (int, float)):                 # число
                nums.append(float(item))
            elif isinstance(item, (list, tuple)) and isinstance(item[-1], (int, float)):
                nums.append(float(item[-1]))                   # (token, prob)
            elif isinstance(item, dict) and "logprob" in item:
                nums.append(float(item["logprob"]))            # {'logprob': …}
        if nums:
            return round(sum(nums) / len(nums), 4)

    # ── 2. эвристика: чем больше «хеджей», тем ниже уверенность ────────────
    words = text.lower().split()
    total = len(words) or 1
    hedges = sum(text.lower().count(w) for w in UNCERTAIN)
    conf = max(0.0, 1 - (hedges / total) * 5)   # линейно понижает, 0–1
    return round(conf, 2)


def analyse(question: str,
            answer: str,
            gen_time: float,
            logprobs: Optional[list] = None) -> Dict[str, Any]:

    clean = answer.strip()

    return {
        "confidence"     : _confidence(clean, logprobs),             # ←
        "sentiment"      : _sentiment(clean),
        "template_flag"  : int(_match_any(clean, TEMPLATE_PATTERNS)),
        "word_count"     : len(clean.split()),
        "response_time"  : gen_time,
        "reference_flag" : int(bool(REFERENCE_HINT.search(clean))),
        "refusal_flag"   : int(_match_any(clean, REFUSAL_PATTERNS)),
        "readability"    : textstat.flesch_reading_ease(clean),
        "grammar_errors" : len(tool_ru.check(clean)) + len(tool_en.check(clean)),
        "complex_words"  : textstat.difficult_words(clean),
        "question_repeat": int(clean.lower().startswith(question.lower()[:50])),
        "user_feedback"  : None,
    }


def save(conn: sqlite3.Connection, log_id: int, m: Dict[str, Any]) -> None:
    """Вставка одной строки анализа по foreign-key log_id."""
    conn.execute("""
        INSERT OR REPLACE INTO analysis
        (log_id, confidence, sentiment, template_flag, word_count,
         response_time, reference_flag, refusal_flag, readability,
         grammar_errors, complex_words, question_repeat, user_feedback)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        log_id, m["confidence"], m["sentiment"], m["template_flag"], m["word_count"],
        m["response_time"], m["reference_flag"], m["refusal_flag"], m["readability"],
        m["grammar_errors"], m["complex_words"], m["question_repeat"], m["user_feedback"]
    ))
    conn.commit()
