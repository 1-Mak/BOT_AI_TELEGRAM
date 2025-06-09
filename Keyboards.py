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
        InlineKeyboardButton(text="👍 Да", callback_data=f"confirm_yes_{log_id}"),
        InlineKeyboardButton(text="👎 Нет", callback_data=f"confirm_no_{log_id}")
    ]])

# ——— Клавиатура выбора кампуса ———————————————————————
campus_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Пермь", callback_data="campus_Пермь"),
        InlineKeyboardButton(text="Нижний Новгород", callback_data="campus_Нижний_Новгород")
    ],
    [
        InlineKeyboardButton(text="Москва", callback_data="campus_Москва"),
        InlineKeyboardButton(text="Санкт-Петербург", callback_data="campus_Санкт-Петербург")
    ]
])

# ——— Клавиатура выбора уровня образования —————————————
level_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Бакалавр", callback_data="level_Бакалавр"),
        InlineKeyboardButton(text="Специалитет", callback_data="level_Специалитет")
    ],
    [
        InlineKeyboardButton(text="Магистр", callback_data="level_Магистр"),
        InlineKeyboardButton(text="Аспирант", callback_data="level_Аспирант")
    ]
])

# ——— Клавиатура выбора типа обучения ——————————————————
type_kb = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Очный", callback_data="type_Очный"),
        InlineKeyboardButton(text="Заочный", callback_data="type_Заочный")
    ]
])