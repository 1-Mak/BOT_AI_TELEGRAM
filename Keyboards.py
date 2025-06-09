from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ——— Главное меню ——————————————————————————————————————————
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="💬 Спросить ChatGPT")]],
    resize_keyboard=True,
    input_field_placeholder="Напишите сообщение или нажмите кнопку…"
)

# ——— Клавиатура подтверждения (нужен log_id) ——————————————
def confirm_kb(log_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👍 Да",  callback_data=f"confirm_yes_{log_id}"),
        InlineKeyboardButton(text="👎 Нет", callback_data=f"confirm_no_{log_id}")
    ]])
