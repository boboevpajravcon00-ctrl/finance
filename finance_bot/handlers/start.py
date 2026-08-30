from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()

def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="💳 Мои деньги"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📋 История"), KeyboardButton(text="👥 Долги")],
        [KeyboardButton(text="➕ Добавить счет"), KeyboardButton(text="🤝 Добавить долг")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    welcome_text = (
        "👋 **Добро пожаловать в Payravjon Finance!**\n\n"
        "💡 **Как записать расход:**\n"
        "Просто отправьте сумму (например: `20` или `50 обед`), и бот предложит выбрать категорию и счет по кнопкам.\n\n"
        "Используйте меню внизу для управления."
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")