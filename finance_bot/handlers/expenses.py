import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database import (
    get_user_accounts,
    update_account_balance,
    add_transaction,
    delete_transaction,
    get_transaction_by_id,
    add_debt
)

router = Router()

CATEGORIES = [
    ("🍔 Еда", "Еда"),
    ("🚖 Транспорт", "Транспорт"),
    ("🛒 Покупки", "Покупки"),
    ("💊 Здоровье", "Здоровье"),
    ("📱 Связь", "Связь"),
    ("👔 Одежда", "Одежда"),
    ("⚽ Спорт", "Спорт"),
    ("🍿 Досуг", "Развлечения"),
    ("🤝 Долг", "Долг"),
    ("📦 Разное", "Разное")
]

class DebtState(StatesGroup):
    waiting_for_person = State()
    waiting_for_amount = State()

def get_categories_keyboard(amount: float, comment: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for icon_name, cat in CATEGORIES:
        row.append(InlineKeyboardButton(text=icon_name, callback_data=f"cat_{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_entry")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_accounts_keyboard(accounts: list) -> InlineKeyboardMarkup:
    buttons = []
    for acc in accounts:
        buttons.append([InlineKeyboardButton(
            text=f"💳 {acc['name']} ({acc['balance']:,.2f} {settings.CURRENCY_SYMBOL})",
            callback_data=f"acc_{acc['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_entry")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "cancel_entry")
async def cancel_entry_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ввод отменен.")
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_tx_"))
async def cancel_tx_callback(callback: CallbackQuery):
    tx_id = int(callback.data.split("_")[2])
    tx = await get_transaction_by_id(tx_id)
    if not tx:
        await callback.answer("Операция уже отменена.", show_alert=True)
        return
    if tx["account_id"]:
        await update_account_balance(tx["account_id"], tx["amount"])
    await delete_transaction(tx_id)
    await callback.message.edit_text(f"↩️ Расход на сумму `{tx['amount']:,.2f} {settings.CURRENCY_SYMBOL}` отменен!", parse_mode="Markdown")
    await callback.answer()

@router.message(F.text.in_(["🤝 Добавить долг", "➕ Долг"]))
async def add_debt_prompt(message: Message, state: FSMContext):
    await message.answer("👤 Введите **имя человека** и кому должны (например: `Али дал` или `Вали взял`):", parse_mode="Markdown")
    await state.set_state(DebtState.waiting_for_person)

@router.message(DebtState.waiting_for_person)
async def process_debt_person(message: Message, state: FSMContext):
    text = message.text.strip()
    debt_type = "debt_received" if "взял" in text.lower() else "debt_given"
    clean_name = text.replace("дал", "").replace("взял", "").replace("в долг", "").strip()
    await state.update_data(person_name=clean_name, debt_type=debt_type)
    await message.answer(f"💰 Введите сумму долга для **{clean_name}**:", parse_mode="Markdown")
    await state.set_state(DebtState.waiting_for_amount)

@router.message(DebtState.waiting_for_amount)
async def process_debt_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.').strip())
    except ValueError:
        await message.answer("⚠️ Введите корректную сумму числом.")
        return
    data = await state.get_data()
    await add_debt(
        user_id=message.from_user.id,
        person_name=data["person_name"],
        amount=amount,
        debt_type=data["debt_type"],
        comment=""
    )
    await state.clear()
    label = "Вам должны" if data["debt_type"] == "debt_given" else "Вы должны"
    await message.answer(f"✅ Записано: **{label}** `{amount:,.2f} {settings.CURRENCY_SYMBOL}` — **{data['person_name']}**", parse_mode="Markdown")

# Хендлер произвольного текста (ввод суммы расхода)
@router.message(F.text)
async def process_amount_input(message: Message, state: FSMContext):
    # Игнорируем кнопки меню
    if message.text in ["💳 Мои деньги", "📊 Статистика", "📋 История", "👥 Долги", "🤝 Долги", "➕ Добавить счет"]:
        return

    # Извлекаем сумму из сообщения
    match = re.search(r'\b\d+(?:[.,]\d+)?\b', message.text)
    if not match:
        await message.answer("💡 Чтобы записать расход, отправьте сумму (например: `20` или `20 кофе`).")
        return

    amount = float(match.group().replace(',', '.'))
    # Комментарий (все слова кроме цифры)
    comment = re.sub(r'\b\d+(?:[.,]\d+)?\b', '', message.text).strip() or "Расход"

    await state.update_data(amount=amount, comment=comment)
    await message.answer(
        f"💸 Сумма: `{amount:,.2f} {settings.CURRENCY_SYMBOL}` ({comment})\n\n📂 **Выберите категорию:**",
        reply_markup=get_categories_keyboard(amount, comment),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("cat_"))
async def category_selected(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split("_")[1]
    await state.update_data(category=category)
    
    accounts = await get_user_accounts(callback.from_user.id)
    if not accounts:
        data = await state.get_data()
        tx_id = await add_transaction(callback.from_user.id, None, "expense", data["amount"], category, data["comment"])
        await state.clear()
        await callback.message.edit_text(
            f"💸 Расход: `{data['amount']:,.2f} {settings.CURRENCY_SYMBOL}` | **{category}**\n⚠️ _Счета не добавлены._",
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    data = await state.get_data()
    await callback.message.edit_text(
        f"💸 `{data['amount']:,.2f} {settings.CURRENCY_SYMBOL}` | **{category}**\n\n💳 **С какого счета списать?**",
        reply_markup=get_accounts_keyboard(accounts),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("acc_"))
async def account_selected(callback: CallbackQuery, state: FSMContext):
    acc_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    amount = data.get("amount", 0.0)
    category = data.get("category", "Разное")
    comment = data.get("comment", "")

    accounts = await get_user_accounts(callback.from_user.id)
    acc = next((a for a in accounts if a["id"] == acc_id), None)
    acc_name = acc["name"] if acc else "Счет"

    await update_account_balance(acc_id, -amount)
    tx_id = await add_transaction(callback.from_user.id, acc_id, "expense", amount, category, comment)
    await state.clear()

    currency = settings.CURRENCY_SYMBOL
    comm_str = f" — _{comment}_" if comment and comment != "Расход" else ""
    text = (
        f"✅ **Расход успешно записан!**\n"
        f"💸 `{amount:,.2f} {currency}` | **{category}**{comm_str}\n"
        f"💳 Списано с: **{acc_name}**"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить операцию", callback_data=f"cancel_tx_{tx_id}")]
    ])
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    await callback.answer()